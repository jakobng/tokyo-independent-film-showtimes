"""
musashino_kan_module.py — scraper for Shinjuku Musashino‑kan

Revision #6 (Final)
───────────────────────────────────────────────────────────
* Correctly scrapes details for all movies listed on the schedule page.
* Finds and parses the director, year, country, and runtime from <dl> tags.
* Extracts a clean synopsis, removing extra text like ticket prices.
* Normalises movie titles to remove prefixes/suffixes in the final output.
* Formats showtimes to include only the start time.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

# --- Constants ---
CINEMA_NAME = "新宿武蔵野館"
MAIN_SITE_URL = "https://shinjuku.musashino-k.jp/"
SCHEDULE_PAGE_URL = "https://musashino.cineticket.jp/mk/theater/shinjuku/schedule"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# --- Helper Functions ---

def _fetch_soup(url: str) -> Optional[BeautifulSoup]:
    """Fetches a URL and returns a BeautifulSoup object."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.content, "html.parser")
    except requests.RequestException as e:
        print(f"WARN: [{CINEMA_NAME}] Could not fetch {url}: {e}", file=sys.stderr)
        return None

def _clean(element: Optional[Tag | str]) -> str:
    """Extracts and normalizes whitespace from a BeautifulSoup element or string."""
    if element is None: return ""
    text = element.get_text(separator=' ', strip=True) if hasattr(element, 'get_text') else str(element)
    return ' '.join(unicodedata.normalize("NFKC", text).strip().split())

def _normalise_title(text: str) -> str:
    """Cleans movie titles by removing common prefixes and suffixes."""
    text = re.sub(r"^(?:【[^】]+】)+", "", text)
    text = re.sub(r"★.*$", "", text)
    return text.strip()

def _parse_detail_page(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    """Parses the movie detail page for metadata."""
    details = {"director": None, "year": None, "country": None, "runtime_min": None, "synopsis": None}

    text_container = soup.select_one(".module.module-text > .wrapper > .text")
    if not text_container:
        return details

    for dl in text_container.find_all("dl", recursive=False):
        dt_text = _clean(dl.find("dt"))
        dd_text = _clean(dl.find("dd"))
        
        if "監督" in dt_text:
            details["director"] = dd_text
        elif "製作年／製作国" in dt_text:
            parts = dd_text.split('／')
            if len(parts) > 0: details["year"] = re.sub(r'\D', '', parts[0])
            if len(parts) > 1: details["country"] = parts[1].strip()
        elif "上映時間" in dt_text:
            if match := re.search(r'(\d+)時間(\d+)分', dd_text):
                h, m = map(int, match.groups())
                details["runtime_min"] = str(h * 60 + m)
            elif match := re.search(r'(\d+)分', dd_text):
                details["runtime_min"] = match.group(1)

    synopsis_parts = []
    if synopsis_container := soup.select_one("div.module-text > .wrapper > .text-container > .text"):
        for element in synopsis_container.find_all(recursive=False):
            if element.name == 'dl':
                break
            if element.name == 'p':
                synopsis_parts.append(_clean(element))
    
    if synopsis_parts:
        details["synopsis"] = "\n".join(synopsis_parts)
        
    return details

# --- Main Scraping Logic ---

def scrape_musashino_kan() -> List[Dict]:
    """Scrapes movie showtimes and details from the Musashino-kan website."""
    schedule_soup = _fetch_soup(SCHEDULE_PAGE_URL)
    if not schedule_soup:
        return []

    print(f"INFO: [{CINEMA_NAME}] Fetched schedule page: {SCHEDULE_PAGE_URL}")
    all_showings = []
    
    date_blocks = schedule_soup.find_all("div", id=re.compile(r"^dateJouei(\d{8})$"))
    print(f"INFO: [{CINEMA_NAME}] Found {len(date_blocks)} date blocks to process.")
    
    processed_urls = {}

    for block in date_blocks:
        date_iso = datetime.strptime(block["id"][-8:], "%Y%m%d").date().isoformat()
        
        for panel in block.select("div.movie-panel"):
            title_tag = panel.select_one(".title-jp")
            if not title_tag: continue
            
            raw_title = _clean(title_tag)
            clean_title = _normalise_title(raw_title)
            
            metadata = {"movie_title_en": None}
            detail_url = None

            if detail_link_tag := title_tag.find('a', href=True):
                detail_url = urljoin(MAIN_SITE_URL, detail_link_tag['href'])
                
                if detail_url not in processed_urls:
                    print(f"INFO: [{CINEMA_NAME}] Scraping details for '{clean_title}' from {detail_url}")
                    detail_soup = _fetch_soup(detail_url)
                    if detail_soup:
                        processed_urls[detail_url] = _parse_detail_page(detail_soup)
                
                if detail_url in processed_urls:
                    metadata.update(processed_urls[detail_url])
            
            metadata['detail_page_url'] = detail_url

            for schedule_div in panel.select("div.movie-schedule"):
                showtime = _clean(schedule_div.select_one(".movie-schedule-begin"))
                if not showtime: continue

                all_showings.append({
                    "cinema_name": CINEMA_NAME,
                    "movie_title": clean_title,
                    "date_text": date_iso,
                    "showtime": showtime,
                    **metadata,
                })

    unique_showings = list({(s["date_text"], s["movie_title"], s["showtime"]): s for s in all_showings}.values())
    unique_showings.sort(key=lambda x: (x.get('date_text', ''), x.get('showtime', '')))
    
    print(f"\nINFO: [{CINEMA_NAME}] Collected {len(unique_showings)} unique showings.")
    return unique_showings

# --- CLI test harness ---
if __name__ == '__main__':
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    showings = scrape_musashino_kan()
    if showings:
        output_filename = "musashino_kan_showtimes_final.json"
        print(f"\nINFO: Writing {len(showings)} records to {output_filename}...")
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(showings, f, ensure_ascii=False, indent=2)
        print(f"INFO: Successfully created {output_filename}.")

        print("\n--- Sample of a successfully parsed movie ---")
        from pprint import pprint
        # Find a movie that we expect to have metadata and print it
        for movie in showings:
            if movie.get('director'):
                pprint(movie)
                break
        else:
            print("Could not find a movie with parsed metadata in the sample.")

    else:
        print(f"\nNo showings found by {CINEMA_NAME} scraper.")