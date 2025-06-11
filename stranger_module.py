import requests
from bs4 import BeautifulSoup, NavigableString
import re
import sys
from datetime import datetime, date, timedelta
import os
import time
import traceback # <-- FIX: Added missing import

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException, ElementClickInterceptedException

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
POST_CLICK_RENDER_PAUSE = 1.5

def _init_driver_stranger():
    print(f"Debug ({CINEMA_NAME_ST}): Initializing WebDriver for Stranger.", file=sys.stderr)
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
    driver = None

    if is_github_actions:
        print(f"Debug ({CINEMA_NAME_ST}): Running in GitHub Actions. Expecting ChromeDriver in PATH.", file=sys.stderr)
        try:
            service = ChromeService()
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"Error ({CINEMA_NAME_ST}): Failed to init WebDriver in GitHub Actions: {e}", file=sys.stderr)
            raise
    else: # Local execution logic
        webdriver_path_local = './chromedriver.exe'
        brave_exe_path_local = r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe'
        if not os.path.exists(brave_exe_path_local):
            user_profile = os.getenv('USERPROFILE', '')
            brave_exe_path_local_user = fr'{user_profile}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe'
            if os.path.exists(brave_exe_path_local_user):
                brave_exe_path_local = brave_exe_path_local_user
            else:
                print(f"Debug ({CINEMA_NAME_ST}): Brave browser not found. Using default Chrome.", file=sys.stderr)
                brave_exe_path_local = None

        if brave_exe_path_local and os.path.exists(brave_exe_path_local):
            options.binary_location = brave_exe_path_local
            print(f"Debug ({CINEMA_NAME_ST}): Using Brave browser from: {brave_exe_path_local}", file=sys.stderr)
        else:
            print(f"Debug ({CINEMA_NAME_ST}): Using default system Chrome/Chromium for local run.", file=sys.stderr)

        if not os.path.exists(webdriver_path_local):
            print(f"Error ({CINEMA_NAME_ST}): ChromeDriver not found at '{webdriver_path_local}'.", file=sys.stderr)
            raise FileNotFoundError(f"ChromeDriver not found at {webdriver_path_local}")

        try:
            service = ChromeService(executable_path=webdriver_path_local)
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"Error ({CINEMA_NAME_ST}): Failed to init WebDriver locally: {e}", file=sys.stderr)
            raise
    
    # --- FIX: Set the browser's timezone to Japan Standard Time ---
    try:
        print(f"Debug ({CINEMA_NAME_ST}): Overriding browser timezone to Asia/Tokyo.", file=sys.stderr)
        driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {'timezoneId': 'Asia/Tokyo'})
    except Exception as e_tz:
        print(f"Warning ({CINEMA_NAME_ST}): Could not set timezone override. Scraped times may be in UTC. Error: {e_tz}", file=sys.stderr)
    # --- End Fix ---
            
    print(f"Debug ({CINEMA_NAME_ST}): WebDriver initialized.", file=sys.stderr)
    return driver

def clean_text_st(element_or_string):
    if hasattr(element_or_string, 'get_text'):
        text = ' '.join(element_or_string.get_text(strip=True).split())
    elif isinstance(element_or_string, str):
        text = ' '.join(element_or_string.strip().split())
    else:
        return ""
    return text.strip()

def parse_date_st(date_str_raw, year):
    if not date_str_raw or date_str_raw == "Unknown Date":
        return date_str_raw
    
    processed_date_str = re.sub(r'^[一-龠々]+曜?\s*(<br\s*/?>)?\s*|\s*\(?[月火水木金土日]\)?\s*(<br\s*/?>)?\s*', '', date_str_raw.strip(), flags=re.IGNORECASE)
    processed_date_str = processed_date_str.replace('<br>', ' ').replace('<br/>', ' ').strip()
    processed_date_str = ' '.join(processed_date_str.split())

    if not processed_date_str:
        return date_str_raw 

    try:
        month_day_match = re.match(r'(\d{1,2})/(\d{1,2})', processed_date_str)
        if month_day_match:
            month = int(month_day_match.group(1))
            day = int(month_day_match.group(2))
            if not (1 <= month <= 12 and 1 <= day <= 31):
                return processed_date_str 
            return f"{year}-{month:02d}-{day:02d}"
        else:
            return processed_date_str 
    except (ValueError, Exception):
        return processed_date_str

def extract_showings_from_soup(soup, date_for_showings, year_for_parsing):
    daily_showings = []
    schedule_section_root = soup.find('div', id='block--screen', class_='p-top__screen')
    if not schedule_section_root: return daily_showings
    
    showings_list_container = schedule_section_root.find('div', class_='c-screen__list')
    if not showings_list_container: return daily_showings
    
    showings_ul = showings_list_container.find('ul')
    if not showings_ul: return daily_showings
    
    movie_items_li = showings_ul.find_all('li', recursive=False)

    for item_li in movie_items_li:
        screen_box_div = item_li.find('div', class_='c-screenBox') 
        if not screen_box_div: continue

        info_div = screen_box_div.find('div', class_='c-screenBox__info')
        if not info_div: continue

        time_tag = info_div.find('time')
        title_h2 = info_div.find('h2')

        showtime = "N/A"
        if time_tag:
            raw_time_text = ""
            for content in time_tag.contents:
                if isinstance(content, NavigableString):
                    raw_time_text = content.strip()
                    if re.match(r'\d{1,2}:\d{2}', raw_time_text):
                        break
            
            showtime_str_cleaned = clean_text_st(raw_time_text)
            showtime_match = re.search(r'(\d{1,2}:\d{2})', showtime_str_cleaned)
            if showtime_match:
                showtime = showtime_match.group(1)
        
        film_title = "Unknown Film"
        if title_h2:
            film_title = clean_text_st(title_h2)
            if not film_title: film_title = "Unknown Film (empty H2)"
        
        if showtime == "N/A" and film_title.startswith("Unknown Film"): continue
        
        daily_showings.append({
            "cinema": CINEMA_NAME_ST,
            "date_text": date_for_showings,
            "title": film_title,
            "showtime": showtime
        })
    return daily_showings

def scrape_stranger():
    all_showings_collected = []
    print(f"Debug ({CINEMA_NAME_ST}): Starting scrape_stranger.", file=sys.stderr)
    assumed_year = date.today().year
    
    driver = None
    try:
        driver = _init_driver_stranger()
        driver.get(URL_ST)

        date_scroller_container_selector = "div#block--screen div.c-screen__date ul"
        WebDriverWait(driver, INITIAL_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, date_scroller_container_selector))
        )
        
        date_tabs_li_elements_locator = (By.CSS_SELECTOR, f"{date_scroller_container_selector} > li")
        initial_date_tabs = WebDriverWait(driver, INITIAL_LOAD_TIMEOUT).until(
            EC.presence_of_all_elements_located(date_tabs_li_elements_locator)
        )
        
        num_tabs_to_process = min(len(initial_date_tabs), 7) 
        print(f"Debug ({CINEMA_NAME_ST}): Found {len(initial_date_tabs)} date tabs. Will process up to {num_tabs_to_process}.", file=sys.stderr)

        if num_tabs_to_process == 0:
            print(f"Error ({CINEMA_NAME_ST}): No date tabs found.", file=sys.stderr)
            return []
        
        for i in range(num_tabs_to_process):
            print(f"\nDebug ({CINEMA_NAME_ST}): Processing date tab index {i+1}/{num_tabs_to_process}.", file=sys.stderr)
            
            current_date_tabs = WebDriverWait(driver, CLICK_WAIT_TIMEOUT).until(
                EC.presence_of_all_elements_located(date_tabs_li_elements_locator)
            )
            if i >= len(current_date_tabs): 
                print(f"Error ({CINEMA_NAME_ST}): Date tab index {i} out of bounds.", file=sys.stderr)
                break
            
            date_tab_to_click_selenium_element = current_date_tabs[i]
            date_span_in_tab = date_tab_to_click_selenium_element.find_element(By.CSS_SELECTOR, "span")
            raw_date_text_current_tab = clean_text_st(date_span_in_tab.get_attribute("innerHTML"))
            parsed_date_current_tab = parse_date_st(raw_date_text_current_tab, assumed_year)

            if i > 0:
                print(f"Debug ({CINEMA_NAME_ST}): Attempting to click tab {i+1} for '{parsed_date_current_tab}'.", file=sys.stderr)
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", date_tab_to_click_selenium_element)
                    time.sleep(0.3) 
                    driver.execute_script("arguments[0].click();", date_tab_to_click_selenium_element)
                    time.sleep(POST_CLICK_RENDER_PAUSE)
                except Exception as e_click:
                    print(f"Error ({CINEMA_NAME_ST}): Could not click tab {i+1} ('{parsed_date_current_tab}'): {e_click}", file=sys.stderr)
                    continue 
            
            current_soup = BeautifulSoup(driver.page_source, 'html.parser')
            daily_showings = extract_showings_from_soup(current_soup, parsed_date_current_tab, assumed_year)
            
            if daily_showings:
                print(f"Debug ({CINEMA_NAME_ST}): Extracted {len(daily_showings)} showings for '{parsed_date_current_tab}'.", file=sys.stderr)
                all_showings_collected.extend(daily_showings)
        
        return [dict(t) for t in {tuple(d.items()) for d in all_showings_collected}]

    except Exception as e_main:
        print(f"An unexpected error in scrape_stranger: {e_main}", file=sys.stderr)
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
        for showing_item in showings_data:
            print(f"  {showing_item.get('cinema')} | {showing_item.get('date_text')} | Title: '{showing_item.get('title')}' | Showtime: '{showing_item.get('showtime')}'")
    else:
        print(f"\nNo showings found by {CINEMA_NAME_ST} scraper.")