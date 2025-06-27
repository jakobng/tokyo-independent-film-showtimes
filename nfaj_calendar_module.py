"""
nfaj_calendar_module.py — scraper for 国立映画アーカイブ (National Film Archive of Japan)
- Final, polished version with improved data extraction accuracy.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Constants ---
CINEMA_NAME = "国立映画アーカイブ"
BASE_URL = "https://www.nfaj.go.jp/"

# --- Helper Functions ---

def _fetch_soup(url: str) -> Optional[BeautifulSoup]:
    """Fetches a URL and returns a BeautifulSoup object."""
    try:
        # print(f"INFO: Fetching HTML from {url}") # Optional: uncomment for verbose logging
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        response.encoding = 'utf-8'
        return BeautifulSoup(response.text, 'html.parser')
    except requests.RequestException as e:
        print(f"ERROR: [{CINEMA_NAME}] Could not fetch {url}: {e}", file=sys.stderr)
        return None

def _clean_text(element) -> str:
    """Extracts and normalizes whitespace from a BeautifulSoup Tag."""
    if not element: return ""
    return " ".join(element.get_text(strip=True).split())

def _parse_detail_page(detail_url: str, detail_cache: dict) -> dict:
    """Scrapes a movie detail page for rich information."""
    if detail_url in detail_cache:
        return detail_cache[detail_url]

    print(f"INFO: Scraping new detail page: {detail_url}")
    soup = _fetch_soup(detail_url)
    if not soup:
        detail_cache[detail_url] = {}
        return {}

    details = {
        "movie_title": None, "director": None, "year": None, 
        "country": "日本", "synopsis": None, "runtime_min": None
    }
    
    if title_h1 := soup.select_one('main#film-program_title h1'):
        details['movie_title'] = _clean_text(title_h1)

    if main_content := soup.select_one('main#film-program_title .grid'):
        # Use a more specific selector for the synopsis to avoid grabbing other paragraphs
        if synopsis_p := main_content.select_one('div:first-of-type > p:not([class])'):
            details['synopsis'] = _clean_text(synopsis_p)
        
        if info_list := main_content.find('ul', class_='info'):
            for li in info_list.find_all('li'):
                if '分' in li.get_text():
                    if runtime_match := re.search(r'(\d+)', li.get_text()):
                        details['runtime_min'] = runtime_match.group(1)

        production_p_list = main_content.select('div:first-of-type > p')
        if len(production_p_list) > 1:
            production_p = production_p_list[-1]
            text = _clean_text(production_p)
            # Stricter regex to only capture single 4-digit years, ignoring ranges
            if year_match := re.search(r'^(\d{4})\b', text):
                details['year'] = year_match.group(1)
            if director_match := re.search(r'（監）([\w\s]+)', text):
                details['director'] = director_match.group(1).strip()
    
    detail_cache[detail_url] = details
    return details

# --- Main Scraping Logic ---

def scrape_nfaj_calendar() -> List[Dict]:
    """
    Scrapes the NFAJ homepage calendar for all film screenings.
    """
    print(f"INFO: [{CINEMA_NAME}] Fetching homepage: {BASE_URL}")
    soup = _fetch_soup(BASE_URL)
    if not soup: return []

    all_showings = []
    detail_cache = {}
    today = datetime.now().date()

    for btn in soup.select("#calendar .tab_list button"):
        date_str_match = re.search(r'(\d{1,2}/\d{1,2})', _clean_text(btn))
        if not date_str_match: continue
        
        month, day = map(int, date_str_match.group(1).split('/'))
        year = today.year + 1 if month < today.month else today.year
        
        try:
            date_obj = datetime(year, month, day).date()
        except ValueError:
            continue

        panel_id = btn.get("aria-controls")
        panel = soup.select_one(f"div#{panel_id}")
        if not panel: continue

        for film_div in panel.select("div.film"):
            screen = _clean_text(film_div.find("h2"))
            if not screen or "長瀬記念ホール" not in screen: continue

            for li in film_div.select("ul > li"):
                if not (title_link := li.find("a")): continue
                
                if re.search(r"トーク|talk|講演|ギャラリー", _clean_text(title_link), re.I):
                    continue
                
                detail_page_url = urljoin(BASE_URL, title_link['href'])
                details = _parse_detail_page(detail_page_url, detail_cache)

                if not (showtime_tag := li.find("time")): continue
                showtime = showtime_tag.get('datetime', '')

                # Only add showing if we successfully scraped a title from the detail page
                if details.get("movie_title"):
                    all_showings.append({
                        "cinema_name": CINEMA_NAME,
                        "movie_title": details.get("movie_title"),
                        "date_text": date_obj.isoformat(),
                        "showtime": showtime,
                        "director": details.get("director"),
                        "year": details.get("year"),
                        "country": details.get("country"),
                        "runtime_min": details.get("runtime_min"),
                        "synopsis": details.get("synopsis"),
                        "detail_page_url": detail_page_url,
                        "screen_name": screen
                    })

    unique_showings = list({(s["date_text"], s["movie_title"], s["showtime"]): s for s in all_showings}.values())
    unique_showings.sort(key=lambda x: (x.get('date_text', ''), x.get('showtime', '')))

    print(f"INFO: [{CINEMA_NAME}] Collected {len(unique_showings)} unique showings.")
    return unique_showings

if __name__ == '__main__':
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
            
    showings = scrape_nfaj_calendar()
    
    if showings:
        output_filename = "nfaj_showtimes.json"
        print(f"\nINFO: Writing {len(showings)} records to {output_filename}...")
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(showings, f, ensure_ascii=False, indent=2)
        print(f"INFO: Successfully created {output_filename}.")

        print("\n--- Sample of First Showing ---")
        from pprint import pprint
        pprint(showings[0])
    else:
        print(f"\nNo showings found by {CINEMA_NAME} scraper.")