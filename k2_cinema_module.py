from __future__ import annotations

import json
import re
import sys
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright, Page, Error, Playwright, TimeoutError
except ImportError:
    sys.exit("ERROR: Playwright not installed. Please run 'pip install playwright' and 'playwright install chromium'.")

from bs4 import BeautifulSoup, Tag

# --- Constants ---
CINEMA_NAME = "K2 Cinema"
BASE_URL = "https://k2-cinema.com/"
EVENT_LIST_URL = urljoin(BASE_URL, "/event/")
MAIN_PAGE_URL = urljoin(BASE_URL, "/")
TIMEOUT = 45

# --- Helper Functions ---

def _fetch_page_content(page: Page, url: str, selector: str) -> Optional[str]:
    """Navigates to a URL, waits for a selector, and returns the page content."""
    try:
        page.goto(url, timeout=TIMEOUT * 1000, wait_until='domcontentloaded')
        page.wait_for_selector(selector, timeout=15000) # Increased timeout slightly for reliability
        return page.content()
    except Error as e:
        print(f"ERROR [{CINEMA_NAME}]: Could not process page '{url}'. Reason: {e}", file=sys.stderr)
        return None

def _clean_text(element: Optional[Tag | str]) -> str:
    """Extracts and normalizes whitespace."""
    if element is None: return ""
    text = element.get_text(separator=' ', strip=True) if hasattr(element, 'get_text') else str(element)
    return ' '.join(text.strip().split())

def _clean_title(text: str) -> str:
    """Removes common annotations from titles, like event names or talk show notices."""
    text = re.sub(r'＜[^>]+＞', '', text)
    text = re.sub(r'※.*', '', text)
    return text.strip()

def _parse_detail_page(soup: BeautifulSoup) -> Dict:
    """Parses a film's detail page for rich information. Handles missing elements gracefully."""
    details = { "director": None, "year": None, "country": None, "runtime_min": None, "synopsis": None, "movie_title_en": None }
    
    if title_tag := soup.select_one('.eventTitle'):
        raw_title = _clean_text(title_tag)
        parts = [p.strip() for p in raw_title.split('／') if p.strip()]
        if len(parts) > 1:
            details["movie_title_en"] = _clean_title(parts[1])

    if desc_div := soup.select_one('.eventDescription'):
        intro_header = desc_div.find('h2', string=re.compile("INTRODUCTION|STORY"))
        if intro_header:
            p_tags = []
            for sibling in intro_header.find_next_siblings():
                if sibling.name == 'h2': break
                if sibling.name == 'p': p_tags.append(sibling)
            details["synopsis"] = " ".join([_clean_text(p) for p in p_tags if _clean_text(p)])

    if staff_info := soup.select_one('.staffInfo'):
        info_text = _clean_text(staff_info).replace('：', ':')
        if match := re.search(r'(\d{4})年', info_text): details["year"] = match.group(1)
        if match := re.search(r'(\d+)分', info_text): details["runtime_min"] = match.group(1)
        if match := re.search(r'\d{4}年\s*／\s*([^／]+?)\s*／', info_text): details["country"] = match.group(1).strip()
        if match := re.search(r'監督(?:\s*・\s*脚本)?:?\s*(.*)', info_text): details["director"] = match.group(1).strip()
            
    return details

# --- Main Scraper ---

def scrape_k2_cinema() -> List[Dict]:
    pw_instance: Playwright = sync_playwright().start()
    browser = pw_instance.chromium.launch()
    page = browser.new_page()

    try:
        # 1. Scrape the /event/ page to build a cache of movie details
        print(f"INFO [{CINEMA_NAME}]: Fetching all movie detail links from event page...")
        _fetch_page_content(page, EVENT_LIST_URL, "section.eventList")
        
        while page.locator('button#moreButton').is_visible():
            try:
                page.locator('button#moreButton').click(timeout=5000)
                page.wait_for_timeout(1000)
            except (Error, TimeoutError):
                break
        
        event_list_html = page.content()
        event_soup = BeautifulSoup(event_list_html, 'html.parser')
        details_cache = {}
        
        event_links = event_soup.select('div.eventCard a[href*="/event/title/"]')
        print(f"INFO [{CINEMA_NAME}]: Found {len(event_links)} unique movie links.")

        for link in event_links:
            detail_url = urljoin(BASE_URL, link['href'])
            title_jp = _clean_title(_clean_text(link.find_previous('h3', class_='eventCardHeading'))).split('／')[0].strip()

            if title_jp and detail_url and title_jp not in details_cache:
                print(f"INFO [{CINEMA_NAME}]: Caching details for '{title_jp}'...")
                
                # FINAL FIX: Wait for a reliable element that is always on the page.
                # The parser will then gracefully handle missing optional elements like '.staffInfo'.
                detail_html = _fetch_page_content(page, detail_url, ".eventDetailHeader")
                
                if detail_html:
                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                    details_cache[title_jp] = _parse_detail_page(detail_soup)
                    details_cache[title_jp]['detail_page_url'] = detail_url
                else:
                    print(f"WARN [{CINEMA_NAME}]: Failed to fetch detail page for '{title_jp}'.", file=sys.stderr)
                    details_cache[title_jp] = { "detail_page_url": detail_url }

        # 2. Scrape the main page for the daily schedule
        print(f"\nINFO [{CINEMA_NAME}]: Fetching schedule from the main page...")
        _fetch_page_content(page, MAIN_PAGE_URL, "section.homeScheduleContainer")
        
        while page.locator('button#moreButton').is_visible():
            try:
                page.locator('button#moreButton').click(timeout=5000)
                page.wait_for_timeout(1000)
            except (Error, TimeoutError):
                break

        main_html = page.content()
        main_soup = BeautifulSoup(main_html, "html.parser")
        all_showings = []
        today = date.today()
        
        for date_cont in main_soup.select("div.dateContainer"):
            date_div = date_cont.select_one("div.date")
            if not (date_div and (match := re.search(r"(\d{1,2})\.(\d{1,2})", _clean_text(date_div)))):
                continue
            
            month, day = map(int, match.groups())
            year = today.year + 1 if month < today.month and month < 6 else today.year
            show_date = date(year, month, day)

            for card in date_cont.select("div.scheduleCard"):
                title_tag = card.select_one("h3.scheduleCardHeading")
                time_tag = card.select_one("span.startTime")
                if not (title_tag and time_tag): continue

                raw_title = _clean_text(title_tag)
                title_jp = _clean_title(raw_title).split('／')[0].strip()
                details = details_cache.get(title_jp, {})
                
                all_showings.append({
                    "cinema_name": CINEMA_NAME, "movie_title": title_jp,
                    "date_text": show_date.isoformat(), "showtime": _clean_text(time_tag),
                    "movie_title_en": details.get("movie_title_en"),
                    "director": details.get("director"), "year": details.get("year"),
                    "country": details.get("country"), "runtime_min": details.get("runtime_min"),
                    "synopsis": details.get("synopsis"), "detail_page_url": details.get("detail_page_url"),
                    "purchase_url": (p_tag['href'] if (p_tag := card.find("a", href=True)) else None),
                })
    finally:
        if browser.is_connected(): browser.close()
        pw_instance.stop()

    unique_showings = list({(s["date_text"], s["movie_title"], s["showtime"]): s for s in all_showings}.values())
    unique_showings.sort(key=lambda r: (r["date_text"], r["showtime"]))
    print(f"\nINFO [{CINEMA_NAME}]: Collected {len(unique_showings)} unique showings.")
    return unique_showings

# --- CLI test harness ---
if __name__ == "__main__":
    if sys.platform == "win32":
        try: sys.stdout.reconfigure(encoding="utf-8")
        except TypeError: pass

    data = scrape_k2_cinema()
    
    if data:
        output_filename = "k2_cinema_showtimes_final.json"
        print(f"\nINFO: Writing {len(data)} records to {output_filename}...")
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"INFO: Successfully created {output_filename}.")
        
        print("\n--- Sample of a successfully parsed movie ---")
        from pprint import pprint
        # Find a movie that we expect to have metadata and print it
        for movie in data:
            if movie.get('year'):
                pprint(movie)
                break
        else:
            print("Could not find a movie with parsed metadata in the sample.")

    else:
        print("\nNo showings found.")