from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
import unicodedata
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
# REMOVED: No longer using ChromeService or webdriver-manager
# from selenium.webdriver.chrome.service import Service as ChromeService
# from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

# --- Constants ---
CINEMA_NAME = "池袋シネマ・ロサ"
DEFAULT_SELENIUM_TIMEOUT = 25
EIGALAND_URL = "https://schedule.eigaland.com/schedule?webKey=c34cee0e-5a5e-4b99-8978-f04879a82299"
DATE_ITEM_SELECTOR_CSS = "div.calender-head-item"
MOVIE_SCHEDULE_SELECTOR_CSS = "div.movie-schedule"
MOVIE_TITLE_EIGALAND_CSS = "h2.text-center"
SHOWTIME_BLOCK_CSS = ".movie-schedule-info.flex-row"
SHOWTIME_TIME_CSS = ".time h2"
SHOWTIME_SCREEN_CSS = ".room .name"
ROSA_BASE_URL = "https://www.cinemarosa.net/"
ROSA_NOWSHOWING_URL = urljoin(ROSA_BASE_URL, "/nowshowing/")
ROSA_INDIES_URL = urljoin(ROSA_BASE_URL, "/indies/")


def _clean_title_for_matching(text: Optional[str]) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('映画 ', '').replace(' ', '')
    text = re.sub(r'[【『「《\(（].*?[】』」》\)）]', '', text)
    text = re.sub(r'[<【『「]', '', text)
    return text.strip()

def _clean_text(text: Optional[str]) -> str:
    if not text: return ""
    return ' '.join(text.strip().split())

def _init_selenium_driver() -> webdriver.Chrome:
    """Initializes a headless Chrome WebDriver, relying on chromedriver being in the PATH."""
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    # MODIFIED: Removed webdriver-manager. Selenium 4 automatically finds the driver
    # in the system PATH, which is where the GitHub Action places it.
    driver = webdriver.Chrome(options=chrome_options)
    
    driver.set_page_load_timeout(DEFAULT_SELENIUM_TIMEOUT * 2)
    return driver

def _fetch_soup(url: str) -> Optional[BeautifulSoup]:
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except requests.RequestException as e:
        print(f"ERROR: [{CINEMA_NAME}] Could not fetch static page {url}: {e}", file=sys.stderr)
        return None

def _parse_date_from_eigaland(date_str: str, current_year: int) -> Optional[dt.date]:
    if match := re.match(r"(\d{1,2})/(\d{1,2})", date_str):
        month, day = map(int, match.groups())
        try:
            year = current_year + 1 if month < dt.date.today().month else current_year
            return dt.date(year, month, day)
        except ValueError: return None
    return None

def _parse_rosa_detail_page(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    details = {"director": None, "year": None, "runtime_min": None, "country": None, "synopsis": None}
    if info_p := soup.select_one("p.film_info"):
        film_info_text = ' '.join(info_p.get_text(separator=' ').split())
        if match := re.search(r"(\d{4})\s*/", film_info_text): details["year"] = match.group(1)
        if match := re.search(r"(\d+時間)?\s*(\d+)分", film_info_text):
            h = int(re.sub(r'\D', '', match.group(1))) if match.group(1) else 0
            m = int(match.group(2))
            details["runtime_min"] = str(h * 60 + m)
        if parts := [p.strip() for p in film_info_text.split('/') if p]:
            if len(parts) > 1 and details["year"]: details["country"] = parts[1].strip()
    if film_txt_div := soup.select_one("div.film_txt"):
        for p_tag in film_txt_div.find_all('p'):
            if "監督" in p_tag.text:
                details["director"] = _clean_text(p_tag.text).replace("監督", "").lstrip(":： ").split(' ')[0]
                break
    if synopsis_div := soup.select_one("div.free_area"): details["synopsis"] = _clean_text(synopsis_div.text)
    return details


def scrape_cinema_rosa() -> List[Dict[str, str]]:
    details_cache = {}
    for start_url in [ROSA_NOWSHOWING_URL, ROSA_INDIES_URL]:
        print(f"INFO: [{CINEMA_NAME}] Fetching movie list from {start_url}", file=sys.stderr)
        soup = _fetch_soup(start_url)
        if not soup: continue
        for link in soup.select(".show_box a"):
            raw_title = _clean_text(link.select_one(".show_title").text)
            title_key = _clean_title_for_matching(raw_title)
            if title_key in details_cache: continue
            detail_url = urljoin(ROSA_BASE_URL, link['href'])
            detail_soup = _fetch_soup(detail_url)
            if detail_soup:
                print(f"  Scraping details for '{raw_title}'...", file=sys.stderr)
                details = _parse_rosa_detail_page(detail_soup)
                details["detail_page_url"] = detail_url
                details_cache[title_key] = details
    print(f"INFO: [{CINEMA_NAME}] Built cache for {len(details_cache)} movies.", file=sys.stderr)

    showings = []
    driver = _init_selenium_driver()
    try:
        print(f"INFO: [{CINEMA_NAME}] Navigating to Eigaland schedule...", file=sys.stderr)
        driver.get(EIGALAND_URL)
        WebDriverWait(driver, DEFAULT_SELENIUM_TIMEOUT).until(EC.visibility_of_element_located((By.CSS_SELECTOR, DATE_ITEM_SELECTOR_CSS)))
        time.sleep(2)
        
        date_elements = driver.find_elements(By.CSS_SELECTOR, DATE_ITEM_SELECTOR_CSS)
        for i in range(len(date_elements)):
            try:
                date_element = driver.find_elements(By.CSS_SELECTOR, DATE_ITEM_SELECTOR_CSS)[i]
                date_str = _clean_text(date_element.find_element(By.CSS_SELECTOR, "p.date").text)
                parsed_date = _parse_date_from_eigaland(date_str, dt.date.today().year)
                if not parsed_date: continue
                
                print(f"INFO: [{CINEMA_NAME}] Clicking date {parsed_date.isoformat()}", file=sys.stderr)
                date_element.click()
                time.sleep(2)

                for item_block in driver.find_elements(By.CSS_SELECTOR, MOVIE_SCHEDULE_SELECTOR_CSS):
                    raw_title = _clean_text(item_block.find_element(By.CSS_SELECTOR, MOVIE_TITLE_EIGALAND_CSS).text)
                    title_key = _clean_title_for_matching(raw_title)
                    details = details_cache.get(title_key, {})
                    for schedule_info in item_block.find_elements(By.CSS_SELECTOR, SHOWTIME_BLOCK_CSS):
                        showtime = _clean_text(schedule_info.find_element(By.CSS_SELECTOR, SHOWTIME_TIME_CSS).text)
                        screen = _clean_text(schedule_info.find_element(By.CSS_SELECTOR, SHOWTIME_SCREEN_CSS).text)
                        purchase_url_tag = schedule_info.find_elements(By.CSS_SELECTOR, 'a[href*="app.eigaland.com"]')
                        showings.append({
                            "cinema_name": CINEMA_NAME, "movie_title": raw_title,
                            "date_text": parsed_date.isoformat(), "showtime": showtime,
                            "screen_name": screen, **details,
                            "purchase_url": purchase_url_tag[0].get_attribute('href') if purchase_url_tag else None
                        })
            except (TimeoutException, StaleElementReferenceException) as e:
                print(f"WARN: [{CINEMA_NAME}] Problem processing date index {i}. Reason: {e}", file=sys.stderr)
    finally:
        if driver: driver.quit()

    unique = { (s["date_text"], s["movie_title"], s["showtime"]): s for s in showings }
    final_list = sorted(list(unique.values()), key=lambda r: (r.get("date_text", ""), r.get("showtime", "")))
    print(f"INFO: [{CINEMA_NAME}] Collected {len(final_list)} unique showings.")
    return final_list

if __name__ == '__main__':
    if sys.platform == "win32": sys.stdout.reconfigure(encoding='utf-8')
    showings = scrape_cinema_rosa()
    if showings:
        output_filename = "cinema_rosa_showtimes.json"
        print(f"\nINFO: Writing {len(showings)} records to {output_filename}...")
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(showings, f, ensure_ascii=False, indent=2)
        print(f"INFO: Successfully created {output_filename}.")
    else:
        print(f"\nNo showings found for {CINEMA_NAME}.")
