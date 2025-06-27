import requests
from bs4 import BeautifulSoup, NavigableString
import re
import sys
from datetime import datetime, date, timedelta
import os
import time
import traceback
from urllib.parse import urljoin

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- Start: Configure stdout and stderr for UTF-8 on Windows (for direct script prints) ---
if __name__ == "__main__" and sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
# --- End: Configure stdout and stderr ---

CINEMA_NAME_ST = "Stranger (ストレンジャー)"
URL_ST = "https://stranger.jp/"

# Define timeouts
INITIAL_LOAD_TIMEOUT = 30
CLICK_WAIT_TIMEOUT = 10
POST_CLICK_RENDER_PAUSE = 1.0 # Can be slightly shorter now with explicit waits
SCHEDULE_RENDER_TIMEOUT = 5 # Timeout for waiting for schedule items to appear

def _init_driver_stranger():
    print(f"Debug ({CINEMA_NAME_ST}): Initializing WebDriver.", file=sys.stderr)
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
    if not is_github_actions and sys.platform == "win32":
        brave_exe_path_local = r'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe'
        if os.path.exists(brave_exe_path_local):
            options.binary_location = brave_exe_path_local
            print(f"Debug ({CINEMA_NAME_ST}): Using Brave browser.", file=sys.stderr)
        else:
            print(f"Debug ({CINEMA_NAME_ST}): Brave not found. Using default Chrome.", file=sys.stderr)

    try:
        service = ChromeService()
        driver = webdriver.Chrome(service=service, options=options)
        print(f"Debug ({CINEMA_NAME_ST}): WebDriver initialized successfully.", file=sys.stderr)
        driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {'timezoneId': 'Asia/Tokyo'})
    except Exception as e:
        print(f"Error ({CINEMA_NAME_ST}): Failed to initialize WebDriver: {e}", file=sys.stderr)
        raise
    return driver

def clean_text_st(element_or_string):
    if hasattr(element_or_string, 'get_text'):
        text = ' '.join(element_or_string.get_text(strip=True).split())
    elif isinstance(element_or_string, str):
        text = ' '.join(element_or_string.strip().split())
    else:
        return ""
    return text
    
def normalize_title(title):
    if not title: return ""
    return title.replace(" ", "").replace("　", "")

def parse_date_st(date_str_raw, year):
    processed_date_str = re.sub(r'^[一-龠々]+曜?\s*<br/?>?\s*|\s*\(?[月火水木金土日]\)?\s*<br/?>?\s*', '', date_str_raw.strip(), flags=re.IGNORECASE)
    processed_date_str = ' '.join(processed_date_str.replace('<br>', ' ').split())
    try:
        month_day_match = re.match(r'(\d{1,2})/(\d{1,2})', processed_date_str)
        if month_day_match:
            month, day = map(int, month_day_match.groups())
            return f"{year}-{month:02d}-{day:02d}"
    except (ValueError, Exception):
        pass
    return processed_date_str or date_str_raw

def _create_movie_cache(soup):
    cache = {}
    print(f"Debug ({CINEMA_NAME_ST}): Building movie metadata cache...", file=sys.stderr)
    
    featured_movies = soup.select('.p-top__movie .c-movie__list li')
    for movie_item in featured_movies:
        link_tag = movie_item.find('a', class_='c-contentBox', href=True)
        if not link_tag: continue
            
        info_div = link_tag.find('div', class_='c-contentBox__info')
        if not info_div: continue
            
        title = clean_text_st(info_div.find('h2'))
        normalized_key = normalize_title(title)
        if not normalized_key or normalized_key in cache: continue

        detail_url = urljoin(URL_ST, link_tag['href'])
        
        year = "N/A"
        meta_p = info_div.find('p')
        if meta_p:
            meta_text = meta_p.get_text(separator=" ")
            # FIX: Make regex flexible to find year followed by '年' OR '／'
            year_match = re.search(r'(\d{4})[年／]', clean_text_st(meta_text))
            if year_match:
                year = year_match.group(1)

        cache[normalized_key] = {'year': year, 'detail_url': detail_url, 'original_title': title}
        
    print(f"Debug ({CINEMA_NAME_ST}): Cache built with {len(cache)} unique movies.", file=sys.stderr)
    return cache

def extract_showings_from_schedule(soup, date_for_showings):
    showings = []
    schedule_section = soup.find('div', id='block--screen')
    if not schedule_section: return []
    
    movie_items = schedule_section.select('.c-screen__list ul li')

    for item in movie_items:
        title = clean_text_st(item.select_one('h2'))
        if not title: continue

        showtime = "N/A"
        time_tag = item.select_one('time')
        if time_tag:
            time_match = re.search(r'(\d{1,2}:\d{2})', time_tag.get_text())
            if time_match: showtime = time_match.group(1)
        
        showings.append({
            "date_text": date_for_showings,
            "title_from_schedule": title,
            "showtime": showtime
        })
    print(f"Debug ({CINEMA_NAME_ST}): Scraped {len(showings)} showings from schedule for '{date_for_showings}'.", file=sys.stderr)
    return showings

def scrape_stranger():
    final_showings = []
    driver = None
    
    try:
        driver = _init_driver_stranger()
        
        print(f"\n--- Phase 1: Building Metadata Cache ---", file=sys.stderr)
        driver.get(URL_ST)
        WebDriverWait(driver, INITIAL_LOAD_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".p-top__movie")))
        initial_soup = BeautifulSoup(driver.page_source, 'html.parser')
        movie_cache = _create_movie_cache(initial_soup)
        
        print(f"\n--- Phase 2: Scraping Schedule ---", file=sys.stderr)
        all_schedule_showings = []
        date_tabs_locator = (By.CSS_SELECTOR, "div#block--screen div.c-screen__date ul > li")
        schedule_item_locator = (By.CSS_SELECTOR, ".c-screen__list ul li")
        num_tabs = min(len(driver.find_elements(*date_tabs_locator)), 7)
        
        for i in range(num_tabs):
            date_tabs = WebDriverWait(driver, CLICK_WAIT_TIMEOUT).until(EC.presence_of_all_elements_located(date_tabs_locator))
            if i >= len(date_tabs): break
            
            date_tab = date_tabs[i]
            date_text = parse_date_st(clean_text_st(date_tab.find_element(By.CSS_SELECTOR, "span").get_attribute("innerHTML")), date.today().year)
            
            if i > 0:
                driver.execute_script("arguments[0].click();", date_tab)
                time.sleep(POST_CLICK_RENDER_PAUSE)
            
            # FIX: Add a wait to ensure the schedule items for the clicked day have loaded
            try:
                WebDriverWait(driver, SCHEDULE_RENDER_TIMEOUT).until(
                    EC.presence_of_element_located(schedule_item_locator)
                )
            except TimeoutException:
                print(f"Warning ({CINEMA_NAME_ST}): No schedule items found for {date_text} after waiting.", file=sys.stderr)
                continue # Skip to the next day

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            all_schedule_showings.extend(extract_showings_from_schedule(soup, date_text))
        
        print(f"\n--- Phase 3: Combining all data ---", file=sys.stderr)
        for showing in all_schedule_showings:
            normalized_title = normalize_title(showing['title_from_schedule'])
            matched_data = None
            for key, data in movie_cache.items():
                if normalized_title in key:
                    matched_data = data
                    break
            
            year = matched_data['year'] if matched_data else "N/A"
            detail_url = matched_data['detail_url'] if matched_data else "N/A"
            final_title = matched_data['original_title'] if matched_data else showing['title_from_schedule']
            
            final_showings.append({
                "cinema_name": CINEMA_NAME_ST,
                "date_text": showing['date_text'],
                "movie_title": final_title,
                "showtime": showing['showtime'],
                "year": year,
                "detail_page_url": detail_url
            })

        return [dict(t) for t in {tuple(d.items()) for d in final_showings}]

    except Exception as e:
        print(f"An unexpected error in scrape_stranger: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return []
    finally:
        if driver:
            print(f"Debug ({CINEMA_NAME_ST}): Quitting WebDriver.", file=sys.stderr)
            driver.quit()

if __name__ == '__main__':
    print(f"Testing {CINEMA_NAME_ST} scraper module (Selenium, headless)...")
    showings_data = scrape_stranger()
    if showings_data:
        print(f"\nFound {len(showings_data)} unique showings for {CINEMA_NAME_ST}:")
        showings_data.sort(key=lambda x: (x.get('date_text', ''), x.get('title', ''), x.get('showtime', '')))
        for showing in showings_data:
            print(f"  {showing.get('date_text')} | {showing.get('showtime')} | Title: '{showing.get('title')}' ({showing.get('year')}) | URL: {showing.get('detail_url')}")
    else:
        print(f"\nNo showings found by {CINEMA_NAME_ST} scraper.")