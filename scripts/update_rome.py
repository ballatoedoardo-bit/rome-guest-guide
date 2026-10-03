"""Fetch dated event listings from Rome's official tourism office. Fail closed."""
import concurrent.futures as cf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
import json, re, pathlib, time
from bs4 import BeautifulSoup
ROOT = pathlib.Path(__file__).resolve().parents[1]
NOW = datetime.now(ZoneInfo('Europe/Rome'))
TODAY = NOW.date()
BASE = 'https://www.turismoroma.it'

def fetch(url):
    if urlparse(url).hostname != 'www.turismoroma.it':
        raise ValueError('Unexpected source host')
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'RomeGuestGuide/1.0 (official-source reader)'}), timeout=18) as r:
                if urlparse(r.url).hostname != 'www.turismoroma.it':
                    raise ValueError('Unexpected redirect')
                return BeautifulSoup(r.read(3_000_000), 'html.parser')
        except Exception:
            if attempt: raise
            time.sleep(1)

def date(text):
    m = re.search(r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b', text)
    return datetime.strptime(m.group(0), '%d %B %Y').date() if m else None

def event(url):
    try:
        soup = fetch(url)
        # Only the event's dedicated date field, never dates in body copy or related events.
        period = soup.select_one('#informazioni .field-name-field-periodo-08')
        if not period: return None
        start = period.select_one('.date-display-start')
        end = period.select_one('.date-display-end')
        single = period.select_one('.date-display-single')
        first = date((start or single).get_text(' ', strip=True)) if (start or single) else None
        last = date(end.get_text(' ', strip=True)) if end else first
        title = soup.select_one('h1')
        if not first or not last or last < first or not title: return None
        if first > TODAY + timedelta(days=1) or last < TODAY: return None
        return {'title': title.get_text(' ', strip=True)[:140], 'url': url,
                'start': first.isoformat(), 'end': last.isoformat(), 'source': 'Turismo Roma'}
    except Exception as exc:
        print(f'Skipped event: {url}: {type(exc).__name__}')
        return None

def main():
    urls = []
    successes = 0
    for listing in [BASE + '/en', BASE + '/en/events']:
        try:
            soup = fetch(listing)
            successes += 1
            for a in soup.select('a[href]'):
                u = urljoin(BASE, a['href']).split('#')[0].split('?')[0]
                if urlparse(u).hostname == 'www.turismoroma.it' and '/en/events/' in u and u not in urls:
                    urls.append(u)
        except Exception as exc:
            print(f'Listing unavailable: {type(exc).__name__}')
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        items = [e for e in pool.map(event, urls[:40]) if e]
    items.sort(key=lambda e: (e['start'] > TODAY.isoformat(), (datetime.fromisoformat(e['end']) - datetime.fromisoformat(e['start'])).days, e['end'], e['title']))
    # A recent successful listing check is separate from an empty dated-event selection.
    result = {'checkedAt': datetime.now(ZoneInfo('Europe/Rome')).isoformat(), 'sourceAvailable': bool(successes and urls), 'events': items[:8]}
    (ROOT / 'data').mkdir(exist_ok=True)
    output = ROOT / 'data/rome-today.json'
    temp = output.with_suffix('.tmp')
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    temp.replace(output)
    print(f'Official listings checked: {successes}; candidates: {len(urls)}; dated current events: {len(items)}')
    if not successes or not urls: raise SystemExit('Official source unavailable; fallback links will be displayed')

if __name__ == '__main__': main()
