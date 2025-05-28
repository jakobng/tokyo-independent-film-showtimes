"""
cine_switch_ginza_module.py - Scraper for Cine Switch Ginza (Eigaland platform)
Adapted from cinema_rosa_module.py, assuming the same site structure.
USING SELENIUM.
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
from webdriver_manager.chrome import ChromeDriverManager # Ensure this is installed: pip install webdriver-manager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Constants ---
BASE_URL = "https://schedule.eigaland.com/schedule?webKey={web_key}"
# Updated for Cine Switch Ginza
CINEMA_NAME_FALLBACK = "シネスイッチ銀座"

# Selectors (assuming they are identical to Cinema Rosa based on user input)
DATE_CALENDAR_AREA_SELECTOR_CSS = "div.calendar-head.component"
DATE_ITEM_SELECTOR_CSS = "div.calendar-head.component .calender-head-item" # Note: "calender" might be a typo in original site
DATE_VALUE_IN_ITEM_SELECTOR_CSS = "p.date"

MOVIE_ITEM_BLOCK_SELECTOR_CSS = "div.movie-schedule-body > div.movie-schedule-item"
MOVIE_TITLE_IN_ITEM_BLOCK_SELECTOR_CSS = "span[style*='font-weight: 700']"

SHOWTIME_TABLE_ROWS_SELECTOR_CSS = "table.schedule-table tbody tr"
SCREEN_IN_TABLE_ROW_SELECTOR_CSS = "td.place span.name"
SLOT_CELL_SELECTOR_CSS = "td.slot"
START_TIME_IN_SLOT_SELECTOR_CSS = "h2" # This targets the <h2> tag containing the start time

DEFAULT_SELENIUM_TIMEOUT = 20  # seconds
DAYS_TO_SCRAPE = 7 # Number of days forward to scrape from the current date available on site

# Update __all__ if the function name changes significantly or if there are multiple public functions
__all__ = ["scrape_eigaland_schedule"]

def _get_current_year() -> int:
    """Gets the current year."""
    return dt.date.today().year

def _parse_date_from_eigaland(date_str: str, current_year_for_schedule: int) -> Optional[dt.date]:
    """
    Parses a date string like "MM/DD" from Eigaland into a datetime.date object.
    Handles year rollovers if the month appears to be in the past relative to today.
    """
    match = re.match(r"(\d{1,2})/(\d{1,2})", date_str)
    if match:
        month, day = map(int, match.groups())
        try:
            parsed_dt_obj = dt.date(current_year_for_schedule, month, day)
            today = dt.date.today()
            # Heuristic for year rollover: if the parsed month is much earlier than today's month
            # (e.g., scraping in Jan for a Dec date), assume it's next year.
            if parsed_dt_obj.month < today.month and (today.month - parsed_dt_obj.month) > 6: # More than 6 months apart
                 if current_year_for_schedule == today.year: # Only increment if current year is this year
                    # This could happen if scraping at the very end of Dec for early Jan of next year,
                    # or if scraping in early Jan for late Dec of previous year (less likely with this logic)
                    # A more robust solution might involve checking the day of the week if available.
                    parsed_dt_obj = dt.date(current_year_for_schedule + 1, month, day)
            return parsed_dt_obj
        except ValueError:
            # Invalid date (e.g., Feb 30)
            return None
    return None

def _init_selenium_driver() -> webdriver.Chrome:
    """Initializes and returns a Selenium Chrome WebDriver instance."""
    chrome_options = ChromeOptions()
    RUN_HEADLESS_SELENIUM = True # Set to False for debugging to see the browser
    if RUN_HEADLESS_SELENIUM:
        chrome_options.add_argument("--headless=new") # Recommended headless mode
    chrome_options.add_argument("--no-sandbox") # Common for server environments
    chrome_options.add_argument("--disable-dev-shm-usage") # Overcomes limited resource problems
    chrome_options.add_argument("--window-size=1366,800") # Standard window size
    # Set user agent to mimic a real browser
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument('--lang=ja-JP') # Set language to Japanese
    chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'ja,en-US,en'})

    try:
        # Use webdriver-manager to automatically handle ChromeDriver
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Error initializing WebDriver with webdriver-manager: {e}", file=sys.stderr)
        print("Please ensure Chrome is installed and webdriver-manager can download the driver.", file=sys.stderr)
        raise
    
    driver.set_page_load_timeout(DEFAULT_SELENIUM_TIMEOUT * 2) # Generous page load timeout
    return driver

def scrape_eigaland_schedule(web_key: str, cinema_name_override: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Scrapes movie schedule information from an Eigaland platform cinema page.

    Args:
        web_key: The specific web key for the cinema on Eigaland.
        cinema_name_override: Optional. If provided, this name will be used for the cinema.
                              Otherwise, it tries to scrape it or uses CINEMA_NAME_FALLBACK.

    Returns:
        A list of dictionaries, where each dictionary represents a single showtime
        with keys: "cinema", "date_text", "screen", "title", "showtime".
    """
    results: List[Dict[str, str]] = []
    url = BASE_URL.format(web_key=web_key)
    driver: Optional[webdriver.Chrome] = None
    # Use override or fallback. Will try to scrape actual name later.
    actual_cinema_name = cinema_name_override or CINEMA_NAME_FALLBACK

    try:
        driver = _init_selenium_driver()
        print(f"Navigating to {url} with Selenium for {actual_cinema_name}", file=sys.stderr)
        driver.get(url)
        
        # Wait for the main date calendar area to be visible
        WebDriverWait(driver, DEFAULT_SELENIUM_TIMEOUT).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, DATE_CALENDAR_AREA_SELECTOR_CSS))
        )
        print("Main date calendar area loaded and visible.", file=sys.stderr)
        time.sleep(3) # Allow dynamic content to settle after initial load

        # Try to scrape the cinema name from the H1 tag
        try:
            # This selector might need adjustment if the H1 structure differs
            h1_element = driver.find_element(By.CSS_SELECTOR, "h1.title.movie-title") 
            scraped_name = h1_element.text.strip()
            if scraped_name:
                actual_cinema_name = scraped_name
        except Exception:
            print(f"Could not scrape cinema name from H1. Using: {actual_cinema_name}", file=sys.stderr)
        print(f"Using cinema name: {actual_cinema_name}", file=sys.stderr)


        date_item_elements = driver.find_elements(By.CSS_SELECTOR, DATE_ITEM_SELECTOR_CSS)
        if not date_item_elements:
            print(f"CRITICAL: No date items found using Selenium selector '{DATE_ITEM_SELECTOR_CSS}'.", file=sys.stderr)
            # driver.save_screenshot(f"debug_selenium_no_date_items_{web_key}.png") # For debugging
            return []

        print(f"Found {len(date_item_elements)} clickable date items. Processing up to {DAYS_TO_SCRAPE} days.", file=sys.stderr)
        year_for_schedule = _get_current_year()

        for date_idx in range(min(len(date_item_elements), DAYS_TO_SCRAPE)):
            # Re-fetch date elements in each iteration as the page might reload/change
            current_page_date_items = driver.find_elements(By.CSS_SELECTOR, DATE_ITEM_SELECTOR_CSS)
            if date_idx >= len(current_page_date_items):
                print(f"  Warning: Date index {date_idx} out of bounds after page update. Stopping date iteration.", file=sys.stderr)
                break
            
            date_element_to_click = current_page_date_items[date_idx]
            date_str_mm_dd = "N/A" # Default in case of error
            try:
                date_value_tag = date_element_to_click.find_element(By.CSS_SELECTOR, DATE_VALUE_IN_ITEM_SELECTOR_CSS)
                date_str_mm_dd = date_value_tag.text.strip()
                print(f"\nProcessing Date {date_idx + 1}: {date_str_mm_dd}", file=sys.stderr)

                # Scroll to the element and click
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_element_to_click)
                time.sleep(0.5) # Brief pause after scroll
                WebDriverWait(driver, DEFAULT_SELENIUM_TIMEOUT).until(EC.element_to_be_clickable(date_element_to_click))
                date_element_to_click.click()
                print(f"  Clicked date: {date_str_mm_dd}", file=sys.stderr)
                # Wait for content to load after click. This might need adjustment.
                time.sleep(4) # Increased wait time for AJAX content to load

                parsed_date_obj = _parse_date_from_eigaland(date_str_mm_dd, year_for_schedule)
                if not parsed_date_obj: 
                    print(f"  Skipping date {date_str_mm_dd} due to parsing error.", file=sys.stderr)
                    continue
                current_date_iso = parsed_date_obj.isoformat()

                # After clicking a date, find all movie items for that date
                movie_item_blocks = driver.find_elements(By.CSS_SELECTOR, MOVIE_ITEM_BLOCK_SELECTOR_CSS)
                print(f"  Found {len(movie_item_blocks)} movie item blocks for {current_date_iso} using '{MOVIE_ITEM_BLOCK_SELECTOR_CSS}'.", file=sys.stderr)
                if not movie_item_blocks and date_idx == 0: # Save screenshot if no movies on first selected date
                     pass # driver.save_screenshot(f"debug_selenium_no_movie_items_{web_key}_{date_str_mm_dd.replace('/', '-')}.png")


                for item_block_idx, movie_item_element in enumerate(movie_item_blocks):
                    movie_title = "Unknown Title"
                    print(f"    Processing Movie Item Block #{item_block_idx + 1} on {current_date_iso}", file=sys.stderr)
                    try:
                        # Title is within the movie item block
                        title_tag = movie_item_element.find_element(By.CSS_SELECTOR, MOVIE_TITLE_IN_ITEM_BLOCK_SELECTOR_CSS)
                        movie_title = title_tag.text.strip()
                        print(f"      Movie Title: '{movie_title}'", file=sys.stderr)
                    except NoSuchElementException:
                        print(f"      Warning: Title not found in movie item block {item_block_idx + 1} using '{MOVIE_TITLE_IN_ITEM_BLOCK_SELECTOR_CSS}'.", file=sys.stderr)
                        # For debugging, print HTML of the block:
                        # print(f"      HTML of movie_item_element: {movie_item_element.get_attribute('outerHTML')[:600]}", file=sys.stderr)


                    # Showtimes are in a table within the movie item block
                    try:
                        table_rows = movie_item_element.find_elements(By.CSS_SELECTOR, SHOWTIME_TABLE_ROWS_SELECTOR_CSS)
                        print(f"      Found {len(table_rows)} table rows for '{movie_title}'.", file=sys.stderr)

                        if not table_rows and movie_title != "Unknown Title": 
                             # print(f"      DEBUG: HTML of movie_item_element for '{movie_title}' (if no table rows found):\n{movie_item_element.get_attribute('outerHTML')[:1000]}", file=sys.stderr)
                             pass


                        for row_idx, tr_element in enumerate(table_rows):
                            screen_name = "N/A" # Default screen name
                            try:
                                screen_tag = tr_element.find_element(By.CSS_SELECTOR, SCREEN_IN_TABLE_ROW_SELECTOR_CSS)
                                screen_name = screen_tag.text.strip()
                            except NoSuchElementException:
                                # Screen name might not always be present or selector might fail
                                pass 

                            slot_cells = tr_element.find_elements(By.CSS_SELECTOR, SLOT_CELL_SELECTOR_CSS)
                            for slot_cell in slot_cells:
                                showtime_tags = slot_cell.find_elements(By.CSS_SELECTOR, START_TIME_IN_SLOT_SELECTOR_CSS)
                                for st_tag in showtime_tags:
                                    try:
                                        showtime_text = st_tag.text.strip()
                                        # Basic validation for HH:MM format
                                        if not re.match(r"^\d{1,2}:\d{2}$", showtime_text):
                                            # print(f"            Skipping invalid showtime format: '{showtime_text}'", file=sys.stderr)
                                            continue # Skip if not in HH:MM format
                                        
                                        print(f"          SUCCESS: Adding show: '{movie_title}' at {showtime_text} on {screen_name} for date {current_date_iso}", file=sys.stderr)
                                        results.append({
                                            "cinema": actual_cinema_name,
                                            "date_text": current_date_iso,
                                            "screen": screen_name,
                                            "title": movie_title,
                                            "showtime": showtime_text,
                                        })
                                    except Exception as e_st_inner:
                                        print(f"              Error processing an h2 tag (showtime) in slot: {e_st_inner}", file=sys.stderr)
                    except NoSuchElementException:
                         print(f"      No showtime table/rows found for '{movie_title}' using '{SHOWTIME_TABLE_ROWS_SELECTOR_CSS}'.", file=sys.stderr)

            except TimeoutException:
                print(f"  Timeout clicking or processing date item {date_idx} ('{date_str_mm_dd}')", file=sys.stderr)
            except Exception as e_date: 
                print(f"  Error processing date item {date_idx} ('{date_str_mm_dd}'): {type(e_date).__name__} - {e_date}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr, limit=1) 
                if "invalid selector" in str(e_date).lower(): # If selector is bad, likely to fail for all
                    print("  Due to invalid selector, stopping further date processing.", file=sys.stderr)
                    break


    except TimeoutException as te:
        print(f"Selenium Timeout during page setup for {actual_cinema_name} (webKey: {web_key}): {te}", file=sys.stderr)
        # if driver: driver.save_screenshot(f"debug_selenium_main_timeout_{web_key}.png")
        traceback.print_exc(file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred with Selenium for {actual_cinema_name} (webKey: {web_key}): {e}", file=sys.stderr)
        # if driver: driver.save_screenshot(f"debug_selenium_unexpected_error_{web_key}.png")
        traceback.print_exc(file=sys.stderr)
    finally:
        if driver:
            print("Quitting Selenium WebDriver.", file=sys.stderr)
            driver.quit()

    # Deduplicate results (in case of any unintentional double additions)
    unique_results_list: List[Dict[str, str]] = []
    seen_keys: Set[tuple] = set()
    for item in results:
        # Create a unique key for each showtime entry
        key = (item["cinema"], item["date_text"], item["title"], item["screen"], item["showtime"])
        if key not in seen_keys:
            unique_results_list.append(item)
            seen_keys.add(key)
    
    print(f"Scraping (Selenium) for {actual_cinema_name} (webKey: {web_key}) complete. Found {len(unique_results_list)} unique showings.", file=sys.stderr)
    return unique_results_list

if __name__ == "__main__":
    # Ensure UTF-8 output for Windows console if needed
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace') # type: ignore
            sys.stderr.reconfigure(encoding='utf-8', errors='replace') # type: ignore
        except Exception:
            # Silently ignore if reconfigure fails (e.g., not in a real console)
            pass

    # --- Configuration for Cine Switch Ginza ---
    TARGET_WEB_KEY = "5c896e66-aaf7-4003-b4ff-1d8c9bf9c0fc" # Provided by user
    TARGET_CINEMA_NAME = "シネスイッチ銀座" # Cine Switch Ginza

    print(f"Attempting to scrape (Selenium): {TARGET_CINEMA_NAME} (webKey: {TARGET_WEB_KEY})")
    
    # Call the renamed generic scraping function
    showings = scrape_eigaland_schedule(web_key=TARGET_WEB_KEY, cinema_name_override=TARGET_CINEMA_NAME)

    if showings:
        print(f"\n--- Showings for {TARGET_CINEMA_NAME} ({len(showings)} found) ---")
        # Sort for consistent output, e.g., by date, then title, then showtime
        showings.sort(key=lambda x: (x["date_text"], x["title"], x["showtime"]))
        for i, show in enumerate(showings):
            print(f"{i+1}. Date: {show['date_text']}, Movie: \"{show['title']}\", Time: {show['showtime']}, Screen: {show['screen']}")
    else:
        print(f"No showings found for {TARGET_CINEMA_NAME}. Check logs and any debug_*.png screenshots if enabled.")

