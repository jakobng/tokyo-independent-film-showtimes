import requests
from bs4 import BeautifulSoup
import re
import sys

CINEMA_NAME = "ユーロスペース"
URL = "http://www.eurospace.co.jp/schedule/"


def clean_text(element_or_string):
    """
    Normalize whitespace and strip HTML font tags from a BeautifulSoup element or string.
    """
    if not element_or_string:
        return ""
    if hasattr(element_or_string, 'get_text'):
        text = ' '.join(element_or_string.get_text(strip=True).split())
    else:
        text = ' '.join(str(element_or_string).strip().split())
    # Remove any leftover <font> tags
    text = re.sub(r'<font[^>]*>', '', text)
    text = text.replace('</font>', '')
    return text.strip()


def extract_specific_title(text):
    """
    If text contains Japanese quotes 『』, extract the inner content.
    """
    if not text:
        return None
    match = re.search(r'『([^』]+)』', text)
    return match.group(1).strip() if match else None


def scrape_eurospace():
    """
    Scrape the 7-day schedule from ユーロスペース and return a list of showings.

    Each showing is a dict with keys:
      - cinema
      - date_text
      - screen
      - title
      - showtime
    """
    showings = []
    try:
        resp = requests.get(URL, headers={ 'User-Agent': 'Mozilla/5.0' }, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')

        schedule_sec = soup.find('section', id='schedule')
        if not schedule_sec:
            print(f"Error ({CINEMA_NAME}): schedule section not found.", file=sys.stderr)
            return showings

        articles = schedule_sec.find_all('article', recursive=False)
        for article in articles:
            # date header
            hdr = article.find('h3')
            date_text = clean_text(hdr)
            if not re.search(r'\d{4}年\d{1,2}月\d{1,2}日', date_text):
                continue

            screen = None
            # iterate children to locate screen labels and tables
            for child in article.children:
                if isinstance(child, str):
                    t = clean_text(child)
                    if 'スクリーン1' in t:
                        screen = 'スクリーン1 (Screen 1)'
                    elif 'スクリーン2' in t:
                        screen = 'スクリーン2 (Screen 2)'
                elif getattr(child, 'name', None) == 'div' and 'scrolltable' in child.get('class', []):
                    tbl = child.find('table')
                    if not tbl or not screen:
                        continue
                    # first row: times, second row: films
                    rows = tbl.find_all('tr', recursive=False)
                    if len(rows) < 2:
                        continue
                    times = rows[0].find_all('td')
                    films = rows[1].find_all('td')
                    for td_time, td_film in zip(times, films):
                        time_txt = clean_text(td_time)
                        if not time_txt:
                            continue
                        # extract title
                        a = td_film.find('a')
                        primary = clean_text(a) if a else ''
                        # handle specific subtitles
                        for br in td_film.find_all('br'):
                            br.replace_with(' [BR] ')
                        parts = clean_text(td_film).split(' [BR] ')
                        specific = next((extract_specific_title(p) for p in parts if extract_specific_title(p)), None)
                        title = specific or primary
                        showings.append({
                            'cinema': CINEMA_NAME,
                            'date_text': date_text,
                            'screen': screen,
                            'title': title,
                            'showtime': time_txt
                        })
        return showings

    except requests.RequestException as e:
        print(f"Error fetching {URL} for {CINEMA_NAME}: {e}", file=sys.stderr)
        return showings
    except Exception as e:
        print(f"Unexpected error in {CINEMA_NAME} scraper: {e}", file=sys.stderr)
        return showings


if __name__ == '__main__':
    # Ensure UTF-8 on Windows console
    if sys.platform.startswith('win'):
        try:
            if sys.stdout.encoding.lower() != 'utf-8': sys.stdout.reconfigure(encoding='utf-8')
            if sys.stderr.encoding.lower() != 'utf-8': sys.stderr.reconfigure(encoding='utf-8')
        except:
            pass
    print(f"Testing {CINEMA_NAME} scraper...")
    data = scrape_eurospace()
    if data:
        print(f"Found {len(data)} showings:")
        for s in data[:10]:
            print(f"  {s['date_text']} {s['screen']} {s['title']} @ {s['showtime']}")
        if len(data) > 10:
            print(f"... and {len(data) - 10} more.")
    else:
        print("No showings found.")
