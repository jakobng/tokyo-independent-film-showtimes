"""
theatre_shinjuku_module.py — scraper for テアトル新宿 (Theatre Shinjuku)
- Revision 5 (Corrected Final): Implements the correct copyright regex, finalizing all improvements.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Constants ---
CINEMA_NAME = "テアトル新宿"
BASE_URL = "https://ttcg.jp"
SCHEDULE_DATA_URL = f"{BASE_URL}/data/theatre_shinjuku.js"

# --- Helper Functions ---

def _fetch_content(url: str, is_json: bool) -> Optional[str]:
    """Fetches raw content from a URL, handling specific encodings."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        request_url = f"{url}?t={datetime.now().timestamp()}"
        print(f"INFO: Fetching {'JSON' if is_json else 'HTML'} from {request_url}")
        
        response = requests.get(request_url, timeout=20, headers=headers)
        response.raise_for_status()

        if is_json:
            return response.content.decode('cp932', errors='replace')
        else:
            response.encoding = 'utf-8'
            return response.text
    except requests.RequestException as e:
        print(f"ERROR: Could not fetch {url}: {e}", file=sys.stderr)
        return None

def _parse_js_variable(js_content: str) -> Optional[Any]:
    """Extracts a JSON object from a JavaScript variable assignment."""
    if not js_content: return None
    try:
        match = re.search(r'=\s*(\{.*\}|\[.*\]);?', js_content, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        if js_content.strip().startswith(('{', '[')):
             return json.loads(js_content.strip())
        return None
    except (json.JSONDecodeError, IndexError) as e:
        print(f"ERROR: Could not parse JSON from JS content: {e}", file=sys.stderr)
        return None

def _parse_detail_page(detail_url: str, detail_cache: Dict) -> Dict:
    """
    Scrapes a movie detail page for rich information.
    - Revision 5: Implements the correct copyright regex, finalizing all logic.
    """
    if detail_url in detail_cache:
        return detail_cache[detail_url]
    
    print(f"INFO: Scraping new detail page: {detail_url}")
    html_content = _fetch_content(detail_url, is_json=False)
    if not html_content:
        detail_cache[detail_url] = {}
        return {}
        
    soup = BeautifulSoup(html_content, 'html.parser')
    details = {
        "movie_title": None, "director": None, "year": None, 
        "country": None, "synopsis": None
    }
    
    title_tag = soup.select_one('h2.movie-title')
    if title_tag:
        if title_tag.find('span'):
            title_tag.find('span').decompose()
        
        title_text = title_tag.get_text(strip=True)
        details['movie_title'] = re.sub(r'[【\[(].*?[)\]】]', '', title_text).strip()

    staff_dl = soup.find('dl', class_='movie-staff')
    if staff_dl:
        for dt in staff_dl.find_all('dt'):
            if '監督' in dt.get_text():
                dd = dt.find_next_sibling('dd')
                if dd:
                    director_text = dd.get_text(strip=True).lstrip('：').strip()
                    director_text = re.sub(r'[（(].*?[)）]', '', director_text).strip()
                    details['director'] = director_text.split('/')[0].strip()
                    break
                    
    synopsis_tag = soup.select_one('.mod-imageText-a-text p')
    if synopsis_tag:
        details['synopsis'] = synopsis_tag.get_text(strip=True)
    
    overview_div = soup.select_one('.movie-overview')
    if overview_div:
        overview_text = unicodedata.normalize('NFKC', overview_div.get_text())

        # Priority 1: Check for the structured 'movie-data' paragraph.
        meta_tag = overview_div.select_one('p.movie-data')
        if meta_tag:
            meta_text = unicodedata.normalize('NFKC', meta_tag.get_text(strip=True))
            year_match = re.search(r'\(?(\d{4})[年/]', meta_text)
            if year_match:
                details['year'] = year_match.group(1)
            
            parts = re.split(r'[／/]', meta_text)
            if len(parts) > 1 and details['year']:
                country_candidate = parts[1].strip()
                if '分' not in country_candidate and not country_candidate.isdigit():
                     details['country'] = country_candidate

        # Priority 2: If no year yet, check the copyright notice.
        if not details['year']:
            copyright_tag = overview_div.find('p', class_='title-copyright')
            if copyright_tag:
                copyright_text = unicodedata.normalize('NFKC', copyright_tag.get_text())
                # CORRECTED a more robust regex to handle copyright symbol variations.
                year_match = re.search(r'[©Ⓒ]\s*(\d{4})', copyright_text)
                if year_match:
                    details['year'] = year_match.group(1)

        # Priority 3: If no year yet, look for a release year pattern in the overview text.
        if not details['year']:
             year_match = re.search(r'(\d{4})年.*?公開', overview_text)
             if year_match:
                 details['year'] = year_match.group(1)
        
        # Priority 4: If no year yet, check for a year in the movie-award section.
        if not details['year']:
            award_div = overview_div.select_one('.movie-award')
            if award_div:
                award_text = unicodedata.normalize('NFKC', award_div.get_text())
                year_match = re.search(r'(\d{4})年', award_text)
                if year_match:
                    details['year'] = year_match.group(1)

    if not details['country']:
        country_label = soup.select_one('.schedule-nowShowing-label .label-type-b')
        if country_label:
            country_text = country_label.get_text(strip=True)
            if '不可' not in country_text:
                details['country'] = country_text
            
    detail_cache[detail_url] = details
    return details

def scrape_theatre_shinjuku(max_days: int = 7) -> List[Dict]:
    js_content = _fetch_content(SCHEDULE_DATA_URL, is_json=True)
    schedule_data = _parse_js_variable(js_content)
    
    if not schedule_data:
        print("ERROR: Failed to fetch or parse schedule data. Aborting.")
        return []

    detail_cache = {}
    all_showings = []

    dates_to_process = schedule_data.get('dates', [])[:max_days]
    movies_map = schedule_data.get('movies', {})
    screens_map = schedule_data.get('screens', {})

    for date_info in dates_to_process:
        date_str = f"{date_info['date_year']}-{str(date_info['date_month']).zfill(2)}-{str(date_info['date_day']).zfill(2)}"
        
        for movie_id in date_info.get('movie', []):
            movie_id_str = str(movie_id)
            
            if movie_id_str not in movies_map or not movies_map[movie_id_str]:
                continue
            movie_details_json = movies_map[movie_id_str][0]

            json_title = movie_details_json.get('name', '').strip()
            runtime_min = movie_details_json.get('running_time')
            
            if not json_title or (runtime_min is not None and int(runtime_min) < 30):
                continue
            if re.search(r'トーク|舞台挨拶|予告編', json_title):
                print(f"INFO: Skipping likely event based on title: '{json_title}'")
                continue

            detail_page_url = urljoin(BASE_URL, f"theatre_shinjuku/movie/{movie_id_str}.html")
            details = _parse_detail_page(detail_page_url, detail_cache)
            
            clean_title = details.get('movie_title')
            if not clean_title:
                clean_title = re.sub(r'[【\[(].*?[)\]】]', '', json_title).strip()
            
            screen_key = f"{movie_id_str}-{date_info['date_year']}-{str(date_info['date_month']).zfill(2)}-{str(date_info['date_day']).zfill(2)}"
            screen_schedules = screens_map.get(screen_key, [])
            
            for screen in screen_schedules:
                for time_info in screen.get('time', []):
                    showtime = f"{str(time_info['start_time_hour']).zfill(2)}:{str(time_info['start_time_minute']).zfill(2)}"
                    
                    all_showings.append({
                        "cinema_name": CINEMA_NAME,
                        "movie_title": clean_title,
                        "date_text": date_str,
                        "showtime": showtime,
                        "director": details.get("director"),
                        "year": details.get("year"),
                        "country": details.get("country"),
                        "runtime_min": str(runtime_min) if runtime_min else None,
                        "synopsis": details.get("synopsis"),
                        "detail_page_url": detail_page_url,
                    })

    unique_showings = list({(s["date_text"], s["movie_title"], s["showtime"]): s for s in all_showings}.values())
    unique_showings.sort(key=lambda x: (x.get('date_text', ''), x.get('showtime', '')))

    print(f"INFO: Collected {len(unique_showings)} unique showings for {CINEMA_NAME}.")
    return unique_showings


if __name__ == '__main__':
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
            
    showings = scrape_theatre_shinjuku(max_days=7)
    
    if showings:
        output_filename = "theatre_shinjuku_showtimes_final.json"
        print(f"\nINFO: Writing {len(showings)} records to {output_filename}...")
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(showings, f, ensure_ascii=False, indent=2)
        print(f"INFO: Successfully created {output_filename}.")

        print("\n--- Sample of First Showing ---")
        from pprint import pprint
        pprint(showings[0])
    else:
        print(f"\nNo showings found for {CINEMA_NAME}.")