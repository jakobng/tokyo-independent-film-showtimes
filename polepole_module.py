"""polepole_module.py — scraper for ポレポレ東中野 (Pole‑Pole Higashi‑Nakano)

Scrapes the Jorudan schedule page and associated detail pages to produce
a standardized data output.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

# --- Constants ---
CINEMA_NAME = "ポレポレ東中野"
SCHEDULE_URL = "https://movie.jorudan.co.jp/theater/1000506/schedule/"
BASE_URL = "https://movie.jorudan.co.jp"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}
TIMEOUT = 15

# --- Helper Functions ---

def _fetch_soup(url: str) -> Optional[BeautifulSoup]:
    """Fetches a URL and returns a BeautifulSoup object."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.content, "html.parser")
    except requests.RequestException as e:
        print(f"ERROR [{CINEMA_NAME}]: Could not fetch {url}. Reason: {e}", file=sys.stderr)
        return None

def _clean_text(element: Optional[Tag]) -> str:
    """Extracts and normalizes whitespace from a BeautifulSoup Tag."""
    if not element:
        return ""
    return " ".join(element.get_text(strip=True).split())

# --- Detail Page Parsing ---

def _parse_detail_page(soup: BeautifulSoup) -> Dict:
    """Parses a film's detail page on Jorudan for rich information."""
    details = {
        "director": None, "year": None, "runtime_min": None,
        "country": None, "synopsis": None
    }
    
    commentary = soup.select_one("section#commentary p.text")
    if commentary:
        details["synopsis"] = _clean_text(commentary)

    info_table = soup.select_one("section#information table")
    if info_table:
        for row in info_table.find_all("tr"):
            th = _clean_text(row.find("th"))
            td = _clean_text(row.find("td"))
            
            if "監督" in th or ("キャスト" in th and "監督" in td):
                director_text = re.sub(r".*監督：", "", td).strip()
                details["director"] = director_text.split(" ")[0]
            
            elif "制作国" in th:
                details["country"] = td.split('（')[0]
                year_match = re.search(r"（(\d{4})）", td)
                if year_match:
                    details["year"] = year_match.group(1)
            
            elif "上映時間" in th:
                runtime_match = re.search(r"(\d+)分", td)
                if runtime_match:
                    details["runtime_min"] = runtime_match.group(1)
    
    return details

# --- Main Scraper ---

def scrape_polepole(max_days: int = 7) -> List[Dict]:
    """
    Scrapes the Jorudan schedule page, follows links to detail pages,
    and returns combined, standardized information.
    """
    print(f"INFO [{CINEMA_NAME}]: Fetching schedule page: {SCHEDULE_URL}")
    main_soup = _fetch_soup(SCHEDULE_URL)
    if not main_soup:
        return []

    details_cache = {}
    film_sections = main_soup.select("main > section[id^='cnm']")
    
    print(f"INFO [{CINEMA_NAME}]: Found {len(film_sections)} films on schedule page.")
    for section in film_sections:
        link_tag = section.select_one(".btn a[href*='/film/']")
        if not link_tag:
            continue
            
        detail_url = urljoin(BASE_URL, link_tag['href'])
        if detail_url not in details_cache:
            print(f"INFO [{CINEMA_NAME}]: Scraping detail page: {detail_url}")
            detail_soup = _fetch_soup(detail_url)
            if detail_soup:
                details_cache[detail_url] = _parse_detail_page(detail_soup)

    all_showings = []
    today = dt.date.today()
    end_date = today + dt.timedelta(days=max_days - 1)  # FIXED: Added 'dt.' prefix
    
    for section in film_sections:
        title = _clean_text(section.find("h2"))
        if not title: continue

        link_tag = section.select_one(".btn a[href*='/film/']")
        detail_url = urljoin(BASE_URL, link_tag['href']) if link_tag else None
        details = details_cache.get(detail_url, {})

        table = section.find("table")
        if not table: continue
            
        headers = [th.get_text(strip=True) for th in table.select("tr:first-of-type th")]
        date_map = {}
        for i, header_text in enumerate(headers):
            match = re.search(r"(\d{1,2})/(\d{1,2})", header_text)
            if match:
                month, day = map(int, match.groups())
                year = today.year if month >= today.month else today.year + 1
                try:
                    show_date = dt.date(year, month, day)
                    if today <= show_date <= end_date:
                        date_map[i] = show_date.isoformat()
                except ValueError:
                    continue
        
        time_row = table.select("tr:nth-of-type(2)")
        if not time_row: continue

        for i, cell in enumerate(time_row[0].find_all("td")):
            if i in date_map:
                date_text = date_map[i]
                showtimes = re.findall(r"\d{1,2}:\d{2}", cell.get_text())
                for st in showtimes:
                    all_showings.append({
    "cinema_name": CINEMA_NAME,
    "movie_title":       title,
    "movie_title_en":    "",
    "date_text":         date_text,
    "showtime":          st,
    "director":          details.get("director", ""),
    "year":              details.get("year", ""),
    "country":           details.get("country", ""),
    "runtime_min":       details.get("runtime_min", ""),
    "synopsis":          details.get("synopsis", ""),
    "detail_page_url":   detail_url,
                    })

    unique_showings = list({(s["date_text"], s["movie_title"], s["showtime"]): s for s in all_showings}.values())
    unique_showings.sort(key=lambda r: (r["date_text"], r["showtime"]))
    print(f"INFO [{CINEMA_NAME}]: Collected {len(unique_showings)} showings within the {max_days}-day window.")
    return unique_showings


# --- CLI test harness ---
if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception: pass

    print(f"Testing {CINEMA_NAME} scraper...")
    data = scrape_polepole(max_days=7)
    
    if data:
        output_filename = "polepole_showtimes.json"
        print(f"\nINFO: Writing {len(data)} records to {output_filename}...")
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"INFO: Successfully created {output_filename}.")
        
        print("\n--- Sample of First Showing ---")
        from pprint import pprint
        pprint(data[0])
    else:
        print("\nNo showings found.")