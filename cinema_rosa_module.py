"""
cinema_rosa_module.py - Scraper for Ikebukuro Cinema Rosa (Eigaland platform)
USING SELENIUM - Corrected title selector.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import time
import traceback
from typing import Dict, List, Optional, Set

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Constants ---
BASE_URL = "https://schedule.eigaland.com/schedule?webKey={web_key}"
CINEMA_NAME_FALLBACK = "池袋シネマ・ロサ"

DATE_CALENDAR_AREA_SELECTOR_CSS = "div.calendar-head.component"
DATE_ITEM_SELECTOR_CSS = "div.calendar-head.component .calender-head-item"
DATE_VALUE_IN_ITEM_SELECTOR_CSS = "p.date"

MOVIE_ITEM_BLOCK_SELECTOR_CSS = "div.movie-schedule-body > div.movie-schedule-item"

# REVISED MOVIE TITLE SELECTOR (relative to MOVIE_ITEM_BLOCK_SELECTOR_CSS)
MOVIE_TITLE_IN_ITEM_BLOCK_SELECTOR_CSS = "span[style*='font-weight: 700']" 
# This targets the span with bold font weight, which is likely the title from the debug HTML.

SHOWTIME_TABLE_ROWS_SELECTOR_CSS = "table.schedule-table tbody tr"
SCREEN_IN_TABLE_ROW_SELECTOR_CSS = "td.place span.name"
SLOT_CELL_SELECTOR_CSS = "td.slot"
START_TIME_IN_SLOT_SELECTOR_CSS = "h2"

DEFAULT_SELENIUM_TIMEOUT = 20
DAYS_TO_SCRAPE = 7
__all__ = ["scrape_cinema_rosa_schedule"]

def _get_current_year() -> int:
    return dt.date.today().year

def _parse_date_from_eigaland(date_str: str, current_year_for_schedule: int) -> Optional[dt.date]:
    match = re.match(r"(\d{1,2})/(\d{1,2})", date_str)
    if match:
        month, day = map(int, match.groups())
        try:
            parsed_dt_obj = dt.date(current_year_for_schedule, month, day)
            today = dt.date.today()
            if parsed_dt_obj.month < today.month and (today.month - parsed_dt_obj.month) > 6:
                 if current_year_for_schedule == today.year:
                    parsed_dt_obj = dt.date(current_year_for_schedule + 1, month, day)
            return parsed_dt_obj
        except ValueError: return None
    return None

def _init_selenium_driver() -> webdriver.Chrome:
    chrome_options = ChromeOptions()
    RUN_HEADLESS_SELENIUM = True 
    if RUN_HEADLESS_SELENIUM:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1366,800")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument('--lang=ja-JP')
    chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'ja,en-US,en'})
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Error initializing WebDriver with webdriver-manager: {e}", file=sys.stderr)
        raise
    driver.set_page_load_timeout(DEFAULT_SELENIUM_TIMEOUT * 2)
    return driver

def scrape_cinema_rosa_schedule(web_key: str, cinema_name_override: Optional[str] = None) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    url = BASE_URL.format(web_key=web_key)
    driver: Optional[webdriver.Chrome] = None
    actual_cinema_name = cinema_name_override or CINEMA_NAME_FALLBACK

    try:
        driver = _init_selenium_driver()
        print(f"Navigating to {url} with Selenium", file=sys.stderr)
        driver.get(url)
        
        WebDriverWait(driver, DEFAULT_SELENIUM_TIMEOUT).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, DATE_CALENDAR_AREA_SELECTOR_CSS))
        )
        print("Main date calendar area loaded and visible.", file=sys.stderr)
        time.sleep(3) 

        try:
            h1_element = driver.find_element(By.CSS_SELECTOR, "h1.title.movie-title")
            scraped_name = h1_element.text.strip()
            if scraped_name: actual_cinema_name = scraped_name
        except Exception: pass
        print(f"Using cinema name: {actual_cinema_name}", file=sys.stderr)

        date_item_elements = driver.find_elements(By.CSS_SELECTOR, DATE_ITEM_SELECTOR_CSS)
        if not date_item_elements:
            print(f"CRITICAL: No date items found using Selenium selector '{DATE_ITEM_SELECTOR_CSS}'.", file=sys.stderr)
            driver.save_screenshot("debug_selenium_no_date_items.png")
            return []

        print(f"Found {len(date_item_elements)} clickable date items. Processing up to {DAYS_TO_SCRAPE} days.", file=sys.stderr)
        year_for_schedule = _get_current_year()

        for date_idx in range(min(len(date_item_elements), DAYS_TO_SCRAPE)):
            current_page_date_items = driver.find_elements(By.CSS_SELECTOR, DATE_ITEM_SELECTOR_CSS)
            if date_idx >= len(current_page_date_items):
                print(f"  Warning: Date index {date_idx} out of bounds. Stopping.", file=sys.stderr)
                break
            
            date_element_to_click = current_page_date_items[date_idx]
            date_str_mm_dd = "N/A"
            try:
                date_value_tag = date_element_to_click.find_element(By.CSS_SELECTOR, DATE_VALUE_IN_ITEM_SELECTOR_CSS)
                date_str_mm_dd = date_value_tag.text.strip()
                print(f"\nProcessing Date {date_idx + 1}: {date_str_mm_dd}", file=sys.stderr)

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_element_to_click)
                time.sleep(0.5)
                WebDriverWait(driver, DEFAULT_SELENIUM_TIMEOUT).until(EC.element_to_be_clickable(date_element_to_click))
                date_element_to_click.click()
                print(f"  Clicked date: {date_str_mm_dd}", file=sys.stderr)
                time.sleep(4) 

                parsed_date_obj = _parse_date_from_eigaland(date_str_mm_dd, year_for_schedule)
                if not parsed_date_obj: 
                    print(f"  Skipping date {date_str_mm_dd} due to parsing error.", file=sys.stderr)
                    continue
                current_date_iso = parsed_date_obj.isoformat()

                movie_item_blocks = driver.find_elements(By.CSS_SELECTOR, MOVIE_ITEM_BLOCK_SELECTOR_CSS)
                print(f"  Found {len(movie_item_blocks)} movie item blocks for {current_date_iso} using '{MOVIE_ITEM_BLOCK_SELECTOR_CSS}'.", file=sys.stderr)
                if not movie_item_blocks and date_idx == 0:
                    driver.save_screenshot(f"debug_selenium_no_movie_items_{date_str_mm_dd.replace('/', '-')}.png")

                for item_block_idx, movie_item_element in enumerate(movie_item_blocks):
                    movie_title = "Unknown Title"
                    print(f"    Processing Movie Item Block #{item_block_idx + 1} on {current_date_iso}", file=sys.stderr)
                    try:
                        title_tag = movie_item_element.find_element(By.CSS_SELECTOR, MOVIE_TITLE_IN_ITEM_BLOCK_SELECTOR_CSS)
                        movie_title = title_tag.text.strip()
                        print(f"      Movie Title: '{movie_title}'", file=sys.stderr)
                    except NoSuchElementException:
                        print(f"      Warning: Title not found in movie item block {item_block_idx + 1} using '{MOVIE_TITLE_IN_ITEM_BLOCK_SELECTOR_CSS}'.", file=sys.stderr)
                        # print(f"      HTML of movie_item_element: {movie_item_element.get_attribute('outerHTML')[:600]}", file=sys.stderr)


                    try:
                        table_rows = movie_item_element.find_elements(By.CSS_SELECTOR, SHOWTIME_TABLE_ROWS_SELECTOR_CSS)
                        print(f"      Found {len(table_rows)} table rows for '{movie_title}'.", file=sys.stderr)

                        if not table_rows and movie_title != "Unknown Title": # Only print debug HTML if title was found but no rows
                             print(f"      DEBUG: HTML of movie_item_element for '{movie_title}' (if no table rows found):\n{movie_item_element.get_attribute('outerHTML')[:1000]}", file=sys.stderr)

                        for row_idx, tr_element in enumerate(table_rows):
                            screen_name = "N/A"
                            try:
                                screen_tag = tr_element.find_element(By.CSS_SELECTOR, SCREEN_IN_TABLE_ROW_SELECTOR_CSS)
                                screen_name = screen_tag.text.strip()
                            except NoSuchElementException:
                                pass 

                            slot_cells = tr_element.find_elements(By.CSS_SELECTOR, SLOT_CELL_SELECTOR_CSS)
                            for slot_cell in slot_cells:
                                showtime_tags = slot_cell.find_elements(By.CSS_SELECTOR, START_TIME_IN_SLOT_SELECTOR_CSS)
                                for st_tag in showtime_tags:
                                    try:
                                        showtime_text = st_tag.text.strip()
                                        if not re.match(r"^\d{1,2}:\d{2}$", showtime_text):
                                            continue
                                        
                                        print(f"          SUCCESS: Adding show: '{movie_title}' at {showtime_text} on {screen_name}", file=sys.stderr)
                                        results.append({
                                            "cinema": actual_cinema_name, "date_text": current_date_iso,
                                            "screen": screen_name, "title": movie_title, "showtime": showtime_text,
                                        })
                                    except Exception as e_st_inner:
                                        print(f"              Error processing an h2 tag in slot: {e_st_inner}", file=sys.stderr)
                    except NoSuchElementException:
                         print(f"      No showtime table/rows found for '{movie_title}'.", file=sys.stderr)

            except TimeoutException:
                print(f"  Timeout clicking or processing date item {date_idx} ('{date_str_mm_dd}')", file=sys.stderr)
            except Exception as e_date: # Catching the InvalidSelectorException here
                print(f"  Error processing date item {date_idx} ('{date_str_mm_dd}'): {type(e_date).__name__} - {e_date}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr, limit=1) # Limit traceback to avoid spam for repeated errors
                # If it's an invalid selector, it will likely repeat for all dates, so break
                if "invalid selector" in str(e_date).lower():
                    print("  Due to invalid selector, stopping further date processing.", file=sys.stderr)
                    break


    except TimeoutException as te:
        print(f"Selenium Timeout during page setup for {CINEMA_NAME_FALLBACK}: {te}", file=sys.stderr)
        if driver: driver.save_screenshot("debug_selenium_main_timeout.png")
        traceback.print_exc(file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred with Selenium for {CINEMA_NAME_FALLBACK}: {e}", file=sys.stderr)
        if driver: driver.save_screenshot("debug_selenium_unexpected_error.png")
        traceback.print_exc(file=sys.stderr)
    finally:
        if driver:
            print("Quitting Selenium WebDriver.", file=sys.stderr)
            driver.quit()

    unique_results_list: List[Dict[str, str]] = []
    seen_keys: Set[tuple] = set()
    for item in results:
        key = (item["cinema"], item["date_text"], item["title"], item["screen"], item["showtime"])
        if key not in seen_keys:
            unique_results_list.append(item)
            seen_keys.add(key)
    
    print(f"Scraping (Selenium) for {actual_cinema_name} (webKey: {web_key}) complete. Found {len(unique_results_list)} unique showings.", file=sys.stderr)
    return unique_results_list

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception: pass

    TARGET_WEB_KEY = "c34cee0e-5a5e-4b99-8978-f04879a82299"
    TARGET_CINEMA_NAME = "池袋シネマ・ロサ"

    print(f"Attempting to scrape (Selenium): {TARGET_CINEMA_NAME} (webKey: {TARGET_WEB_KEY})")
    
    showings = scrape_cinema_rosa_schedule(web_key=TARGET_WEB_KEY, cinema_name_override=TARGET_CINEMA_NAME)

    if showings:
        print(f"\n--- Showings for {TARGET_CINEMA_NAME} ({len(showings)} found) ---")
        showings.sort(key=lambda x: (x["date_text"], x["title"], x["showtime"]))
        for i, show in enumerate(showings):
            print(f"{i+1}. {show['date_text']} - {show['title']} - {show['showtime']} ({show['screen']})")
    else:
        print(f"No showings found for {TARGET_CINEMA_NAME}. Check logs and any debug_*.png screenshots.")