import datetime as _dt
import re
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup, Tag

# --- Constants ---
BASE_URL = "http://www.okura-movie.co.jp/meguro_cinema/"
SCHEDULE_PAGE_URL = f"{BASE_URL}now_showing.html"
CINEMA_NAME = "目黒シネマ"
DEFAULT_SCREEN_NAME = "Screen 1"  # Meguro Cinema appears to be a single screen venue

__all__ = ["scrape_meguro_cinema"]

# --- Helper Functions ---

def _fetch_html(url: str) -> Optional[BeautifulSoup]:
    """Fetches HTML content and returns a BeautifulSoup object."""
    try:
        headers = {
            'User-Agent': 
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/91.0.4472.124 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')
        return soup if soup.body else None
    except requests.RequestException as e:
        print(f"Error fetching {url} for {CINEMA_NAME}: {e}")
        return None


def _parse_date_japanese(date_str: str, year: int) -> Optional[_dt.date]:
    """Parses Japanese date like '5月29日' or '5/29' into a date."""
    m = re.search(r"(\d{1,2})[月/](\d{1,2})日?", date_str)
    if not m:
        return None
    month, day = map(int, m.groups())
    try:
        return _dt.date(year, month, day)
    except ValueError:
        return None


def _generate_dates_from_header(p_tag: Tag, current_year: int) -> List[_dt.date]:
    """Extracts one or multiple dates from the header <p> tag."""
    text = p_tag.get_text(strip=True)
    # Replace various dashes with a common separator
    text = re.sub(r'[〜〜−–]', '~', text)

    # Range: '5月27日〜5月29日'
    range_match = re.search(r"(\d{1,2}[月/]\d{1,2}日?)\s*~\s*(\d{1,2}[月/]\d{1,2}日?)", text)
    dates: List[_dt.date] = []
    if range_match:
        start_str, end_str = range_match.groups()
        start = _parse_date_japanese(start_str, current_year)
        end = _parse_date_japanese(end_str, current_year)
        if start and end:
            if end < start:
                end = _dt.date(current_year + 1, end.month, end.day)
            d = start
            while d <= end:
                dates.append(d)
                d += _dt.timedelta(days=1)
            return dates

    # Individual dates split by '・' or '、'
    parts = re.split(r'[・、]', text)
    for part in parts:
        dt = _parse_date_japanese(part.strip(), current_year)
        if dt:
            dates.append(dt)
    if dates:
        return dates

    # Single date fallback
    single = _parse_date_japanese(text, current_year)
    return [single] if single else []


def _parse_showtimes(row: Tag) -> List[str]:
    """Extracts showtimes (HH:MM) from a table row."""
    times: List[str] = []
    for cell in row.select("td.time_type2"):
        text = ''.join(
            part for part in cell.stripped_strings
            if re.match(r"\d{1,2}:\d{2}", part)
        )
        found = re.findall(r"(\d{1,2}:\d{2})", text)
        for t in found:
            if t not in times:
                times.append(t)
    return times


def scrape_meguro_cinema(max_days: Optional[int] = None) -> List[Dict]:
    """Scrapes the Meguro Cinema schedule and returns standardized showings."""
    soup = _fetch_html(SCHEDULE_PAGE_URL)
    if not soup:
        return []

    current_year = _dt.date.today().year
    today = _dt.date.today()
    showings = []

    blocks = soup.select("div#timetable_detail")
    for block in blocks:
        # Header <p> before schedule table
        header = block.select_one("div#timetable > p:first-of-type")
        if not header:
            header = block.find('p', recursive=False)
        if not header:
            continue

        dates = _generate_dates_from_header(header, current_year)
        if not dates:
            continue

        table = block.select_one("table.time_box")
        if not table:
            continue

        for row in table.find_all('tr'):
            title_cell = row.select_one('td.time_title')
            if not title_cell:
                continue
            title = ' '.join(
                part.strip().replace('『', '').replace('』', '')
                for part in title_cell.stripped_strings
            ) or 'タイトル不明'

            times = _parse_showtimes(row)
            if not times:
                continue

            for d in dates:
                if max_days is not None:
                    delta = (d - today).days
                    if delta < 0 or delta >= max_days:
                        continue
                date_text = d.isoformat()
                for t in times:
                    showings.append({
                        "cinema": CINEMA_NAME,
                        "date_text": date_text,
                        "screen": DEFAULT_SCREEN_NAME,
                        "title": title,
                        "showtime": t
                    })

    # Deduplicate
    unique = {}
    for s in showings:
        key = (s['cinema'], s['date_text'], s['screen'], s['title'], s['showtime'])
        unique[key] = s
    return list(unique.values())

# --- Direct execution for testing ---
if __name__ == '__main__':
    shows = scrape_meguro_cinema()
    print(f"Collected {len(shows)} showings for {CINEMA_NAME}.")
    for s in sorted(shows, key=lambda x: (x['date_text'], x['showtime']))[:10]:
        print(s)
