from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Constants ---
CINEMA_NAME_SB = "新文芸坐"
SCHEDULE_PAGE_URL = "https://www.shin-bungeiza.com/schedule"

# --- Regex for parsing details from the <small> tag ---
DETAILS_RE = re.compile(
    r"（(?P<year>\d{4})・(?P<country>[^/]+?)/"
    r"(?P<runtime>\d+)分.*?）"
    r"(?:監督：(?P<director>[^　\s]+))?"
)


def _clean_text(text: str) -> str:
    """Normalize whitespace."""
    return " ".join(text.strip().split())


def _parse_film_details_from_program(content_div: BeautifulSoup) -> Dict[str, Dict]:
    details_cache: Dict[str, Dict] = {}
    details_p = content_div.select_one("p.nihon-date")
    if not details_p:
        return details_cache

    for segment in details_p.decode_contents().split('<br>'):
        if not segment.strip():
            continue
        segment_soup = BeautifulSoup(segment, 'html.parser')
        title = _clean_text(segment_soup.get_text(strip=True).split('（')[0])
        small = segment_soup.find('small')
        if not small:
            continue
        match = DETAILS_RE.search(small.get_text())
        if not match:
            continue
        info = match.groupdict()
        details_cache[title] = {
            "director": info.get("director", ""),
            "year": info.get("year", ""),
            "country": info.get("country", ""),
            "runtime_min": info.get("runtime", ""),
        }
    return details_cache


def scrape_shin_bungeiza() -> List[Dict]:
    print(f"INFO: [{CINEMA_NAME_SB}] Fetching schedule page: {SCHEDULE_PAGE_URL}")
    try:
        response = requests.get(SCHEDULE_PAGE_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except requests.RequestException as e:
        print(f"ERROR: [{CINEMA_NAME_SB}] Could not fetch page: {e}", file=sys.stderr)
        return []

    program_blocks = soup.select("div.schedule-box")
    print(f"INFO: [{CINEMA_NAME_SB}] Found {len(program_blocks)} film programs on the page.")

    all_showings: List[Dict] = []
    for box in program_blocks:
        program_id = box.get('id', '')
        detail_url = f"{SCHEDULE_PAGE_URL}#{program_id}" if program_id else SCHEDULE_PAGE_URL
        content_div = box.find_next_sibling('div', class_='schedule-content')
        if not content_div:
            continue
        details = _parse_film_details_from_program(content_div)
        for date_header in content_div.select('h2'):
            date_raw = date_header.get_text(strip=True)
            m = re.search(r"(\d{1,2})/(\d{1,2})", date_raw)
            if not m:
                continue
            month, day = map(int, m.groups())
            today = _dt.date.today()
            year = today.year if month >= today.month else today.year + 1
            date_text = f"{year}-{month:02d}-{day:02d}"
            # iterate siblings until next date header
            for sib in date_header.find_next_siblings():
                if sib.name == 'h2':
                    break
                if sib.name == 'div' and 'schedule-program' in sib.get('class', []):
                    title_p = sib.find('p')
                    if not title_p:
                        continue
                    title = _clean_text(title_p.get_text(strip=True))
                    info = details.get(title, {})
                    for time_a in sib.select('ul li a'):
                        showtime = _clean_text(time_a.get_text())
                        if not re.match(r"^\d{1,2}:\d{2}$", showtime):
                            continue
                        all_showings.append({
                            "cinema_name": CINEMA_NAME_SB,
                            "movie_title": title,
                            "movie_title_en": "",
                            "date_text": date_text,
                            "showtime": showtime,
                            "director": info.get("director", ""),
                            "year": info.get("year", ""),
                            "country": info.get("country", ""),
                            "runtime_min": info.get("runtime_min", ""),
                            "synopsis": "",
                            "detail_page_url": detail_url
                        })
    print(f"INFO: [{CINEMA_NAME_SB}] Collected {len(all_showings)} total showings.")
    return all_showings


if __name__ == '__main__':
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    print(f"Testing {CINEMA_NAME_SB} scraper module...")
    showings = scrape_shin_bungeiza()
    if showings:
        showings.sort(key=lambda x: (x['date_text'], x['showtime']))
        fname = 'shin_bungeiza_showtimes.json'
        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(showings, f, ensure_ascii=False, indent=2)
        print(f"INFO: Successfully wrote {len(showings)} records to {fname}.")
        from pprint import pprint
        pprint(showings[0])
    else:
        print("No showings found by Shin-Bungeiza scraper.")
