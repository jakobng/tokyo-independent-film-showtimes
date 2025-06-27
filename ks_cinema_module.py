from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Constants ---
CINEMA_NAME_KC = "K's Cinema (ケイズシネマ)"
BASE_URL = "https://www.ks-cinema.com/"
IFRAME_SRC_URL_KC = urljoin(BASE_URL, "/calendar/index.html")

# --- Helper Functions ---

def _clean_text(element_or_string) -> str:
    """A helper to normalize whitespace."""
    if element_or_string is None:
        return ""
    if hasattr(element_or_string, 'get_text'):
        raw_text = element_or_string.get_text(separator=' ', strip=True)
    else:
        raw_text = str(element_or_string)
    return ' '.join(raw_text.strip().split())


def _fetch_soup(url: str) -> Optional[BeautifulSoup]:
    """Fetches a URL and returns a BeautifulSoup object."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser', from_encoding='shift_jis')
    except requests.RequestException as e:
        print(f"ERROR: [{CINEMA_NAME_KC}] Could not fetch {url}: {e}", file=sys.stderr)
        return None


# --- Detail Page Parsing ---

def _parse_detail_page(soup: BeautifulSoup) -> Dict[str, str]:
    """Parses a movie detail page for rich information."""
    details = {"director": "", "year": "", "runtime_min": "", "country": "", "synopsis": ""}
    
    # Details Table Parsing
    for table in soup.select("#txt-area table"):
        table_text = table.get_text()
        if '監督' in table_text or '作品データ' in table_text:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) != 2:
                    continue
                key, value = _clean_text(cells[0]), _clean_text(cells[1])

                if "監督" in key:
                    details["director"] = value
                elif "作品データ" in key:
                    year_match = re.search(r"(\d{4})年", value)
                    runtime_match = re.search(r"(\d+)分", value)
                    country_match = re.search(r"／\s*([^／]+?)\s*／", value)
                    if year_match:
                        details["year"] = year_match.group(1)
                    if runtime_match:
                        details["runtime_min"] = runtime_match.group(1)
                    if country_match:
                        details["country"] = country_match.group(1).strip()
            break

    # Synopsis Parsing
    synopsis_div = soup.select_one("div.wixui-rich-text")
    if synopsis_div:
        details["synopsis"] = _clean_text(synopsis_div)
    else:
        txt_area_div = soup.select_one("#txt-area")
        if txt_area_div:
            synopsis_parts = []
            start_node = txt_area_div.select_one("table.alignright") or txt_area_div.select_one("p > img")
            if start_node:
                for element in start_node.find_next_siblings():
                    if element.name == 'table' and ('監督' in element.get_text() or '作品データ' in element.get_text()):
                        break
                    if element.name == 'p':
                        p_text = _clean_text(element)
                        if p_text:
                            synopsis_parts.append(p_text)
                if synopsis_parts:
                    details["synopsis"] = " ".join(synopsis_parts)
    return details


# --- Main Scraping Logic ---
def scrape_ks_cinema(max_days: int = 7) -> List[Dict]:
    print(f"INFO: [{CINEMA_NAME_KC}] Fetching calendar iframe: {IFRAME_SRC_URL_KC}")
    iframe_soup = _fetch_soup(IFRAME_SRC_URL_KC)
    if not iframe_soup:
        return []

    details_cache: Dict[str, Dict[str, str]] = {}
    unique_detail_urls = {urljoin(BASE_URL, a['href']) for a in iframe_soup.select("td a[href*='/movie/']")}
    
    print(f"INFO: [{CINEMA_NAME_KC}] Found {len(unique_detail_urls)} unique detail pages to scrape.")
    for url in unique_detail_urls:
        print(f"INFO: [{CINEMA_NAME_KC}] Scraping detail page: {url}")
        detail_soup = _fetch_soup(url)
        if detail_soup:
            details_cache[url] = _parse_detail_page(detail_soup)
    print(f"INFO: [{CINEMA_NAME_KC}] Finished scraping details. Parsing schedule...")

    all_showings: List[Dict] = []
    today = date.today()
    end_date = today + timedelta(days=max_days - 1)
    
    for table in iframe_soup.select("div.slide > table"):
        month_row = table.find('tr', class_='month')
        day_header_row = table.find('tr', class_='day')
        if not month_row or not day_header_row:
            continue

        column_dates: Dict[int, date] = {}
        day_ths = day_header_row.find_all('th', scope='col')
        current_col_index = 0
        last_month = 0
        current_year = today.year
        for month_th in month_row.find_all('th'):
            month_match = re.search(r'(\d{1,2})月', _clean_text(month_th))
            if not month_match:
                continue
            
            month = int(month_match.group(1))
            if last_month > 0 and month < last_month:
                current_year += 1
            last_month = month
            
            colspan = int(month_th.get('colspan', 1))
            for i in range(colspan):
                day_index = current_col_index + i
                if day_index < len(day_ths):
                    try:
                        day = int(_clean_text(day_ths[day_index]))
                        column_dates[day_index] = date(current_year, month, day)
                    except ValueError:
                        pass
            current_col_index += colspan
        
        for row in table.select('tr.movie'):
            current_cell_idx = 0
            for cell in row.find_all('td'):
                colspan = int(cell.get('colspan', 1))
                title_span = cell.select_one('span.title_s')
                if not title_span:
                    current_cell_idx += colspan
                    continue

                title = _clean_text(title_span)
                link = cell.select_one("a[href*='/movie/']")
                detail_url = urljoin(BASE_URL, link['href']) if link else ""
                details = details_cache.get(detail_url, {})
                showtimes = re.findall(r"\d{1,2}:\d{2}", cell.get_text())

                for day_offset in range(colspan):
                    col_idx = current_cell_idx + day_offset
                    if col_idx in column_dates:
                        show_date = column_dates[col_idx]
                        if today <= show_date <= end_date:
                            for st in showtimes:
                                all_showings.append({
                                    "cinema_name": CINEMA_NAME_KC,
                                    "movie_title": title,
                                    "movie_title_en": "",
                                    "date_text": show_date.isoformat(),
                                    "showtime": st,
                                    "director": details.get("director", ""),
                                    "year": details.get("year", ""),
                                    "country": details.get("country", ""),
                                    "runtime_min": details.get("runtime_min", ""),
                                    "synopsis": details.get("synopsis", ""),
                                    "detail_page_url": detail_url,
                                })
                current_cell_idx += colspan

    unique_showings = list({(s["date_text"], s["movie_title"], s["showtime"]): s for s in all_showings}.values())
    print(f"INFO: [{CINEMA_NAME_KC}] Collected {len(unique_showings)} unique showings.")
    return unique_showings


if __name__ == '__main__':
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
            
    print(f"Testing {CINEMA_NAME_KC} scraper module...")
    showings = scrape_ks_cinema(max_days=7)
    
    if showings:
        showings.sort(key=lambda x: (x.get('date_text', ''), x.get('showtime', '')))
        
        output_filename = "ks_cinema_showtimes.json"
        print(f"\nINFO: Writing {len(showings)} records to {output_filename}...")
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(showings, f, ensure_ascii=False, indent=2)
        print(f"INFO: Successfully created {output_filename}.")

        print("\n--- Sample of First Showing ---")
        from pprint import pprint
        pprint(showings[0])
    else:
        print(f"\nNo showings found by {CINEMA_NAME_KC} scraper.")
