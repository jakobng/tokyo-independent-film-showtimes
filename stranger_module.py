import requests
from bs4 import BeautifulSoup, NavigableString
import re
import sys
from datetime import datetime, date, timedelta
import os
import time

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException, ElementClickInterceptedException

# NO webdriver-manager import needed if not using it

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
# After clicking a date tab, how long to explicitly wait for AJAX content to render.
# This is important if WebDriver's waits return too early.
POST_CLICK_RENDER_PAUSE = 1.5 # You can experiment with this value (e.g., 1.0, 2.0)

def _init_driver_stranger(): # Renamed to avoid global namespace issues if other modules define it
    print(f"Debug ({CINEMA_NAME_ST}): Initializing WebDriver for Stranger.", file=sys.stderr)
    options = ChromeOptions()
    options.add_argument("--headless=new") # Use modern headless
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1920,1080")
    # Log preferences to suppress DevTools messages if they are noisy
    options.add_experimental_option('excludeSwitches', ['enable-logging'])


    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
    driver = None

    if is_github_actions:
        print(f"Debug ({CINEMA_NAME_ST}): Running in GitHub Actions. Expecting ChromeDriver in PATH.", file=sys.stderr)
        try:
            # In GitHub Actions, your YAML installs chromedriver to /usr/local/bin/chromedriver,
            # which should be in PATH. Selenium's Service() without args should find it.
            # Also, Chrome itself should be found automatically from where apt installed it.
            service = ChromeService() # Assumes chromedriver is in PATH
            driver = webdriver.Chrome(service=service, options=options)
            print(f"Debug ({CINEMA_NAME_ST}): WebDriver initialized for GitHub Actions.", file=sys.stderr)
        except Exception as e:
            print(f"Error ({CINEMA_NAME_ST}): Failed to init WebDriver in GitHub Actions: {e}", file=sys.stderr)
            print(f"  Ensure ChromeDriver is in PATH and Google Chrome is installed.", file=sys.stderr)
            raise
    else: # Local execution logic
        webdriver_path_local = './chromedriver.exe' # Assuming it's in the same directory as your script
        
        # Attempt to find Brave browser in standard locations
        brave_exe_path_local = r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe'
        if not os.path.exists(brave_exe_path_local):
            user_profile = os.getenv('USERPROFILE', '')
            brave_exe_path_local_user = fr'{user_profile}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe'
            if os.path.exists(brave_exe_path_local_user):
                brave_exe_path_local = brave_exe_path_local_user
            else: # Fallback: try to find Chrome if Brave not found
                print(f"Debug ({CINEMA_NAME_ST}): Brave browser not found in typical locations. Will try default Chrome.", file=sys.stderr)
                brave_exe_path_local = None # Unset to use default Chrome

        if brave_exe_path_local and os.path.exists(brave_exe_path_local):
            options.binary_location = brave_exe_path_local
            print(f"Debug ({CINEMA_NAME_ST}): Using Brave browser from: {brave_exe_path_local}", file=sys.stderr)
        else:
            print(f"Debug ({CINEMA_NAME_ST}): Using default system Chrome/Chromium for local run.", file=sys.stderr)
            # No options.binary_location needed if default Chrome is in PATH

        if not os.path.exists(webdriver_path_local):
            print(f"Error ({CINEMA_NAME_ST}): ChromeDriver not found at '{webdriver_path_local}' for local run.", file=sys.stderr)
            print(f"  Please ensure '{webdriver_path_local}' exists or update the path.", file=sys.stderr)
            raise FileNotFoundError(f"ChromeDriver not found at {webdriver_path_local}")

        try:
            service = ChromeService(executable_path=webdriver_path_local)
            driver = webdriver.Chrome(service=service, options=options)
            print(f"Debug ({CINEMA_NAME_ST}): WebDriver initialized locally (ChromeDriver: '{webdriver_path_local}').", file=sys.stderr)
        except Exception as e:
            print(f"Error ({CINEMA_NAME_ST}): Failed to init WebDriver locally: {e}", file=sys.stderr)
            print(f"  Using ChromeDriver: '{webdriver_path_local}', Browser Binary: '{options.binary_location if options.binary_location else 'Default system Chrome'}'", file=sys.stderr)
            raise
            
    return driver

def clean_text_st(element_or_string):
    if hasattr(element_or_string, 'get_text'):
        # Consolidate multiple spaces into one, then strip leading/trailing
        text = ' '.join(element_or_string.get_text(strip=True).split())
    elif isinstance(element_or_string, str):
        text = ' '.join(element_or_string.strip().split())
    else:
        return ""
    return text.strip() # Final strip for safety

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
    except ValueError:
        return processed_date_str
    except Exception: # Catch any other error during parsing
        return processed_date_str # Fallback

def extract_showings_from_soup(soup, date_for_showings, year_for_parsing):
    daily_showings = []
    schedule_section_root = soup.find('div', id='block--screen', class_='p-top__screen')
    if not schedule_section_root:
        print(f"Debug ({CINEMA_NAME_ST}): Root schedule section 'div#block--screen' not found for date {date_for_showings}.", file=sys.stderr)
        return daily_showings
    
    showings_list_container = schedule_section_root.find('div', class_='c-screen__list')
    if not showings_list_container:
        print(f"Debug ({CINEMA_NAME_ST}): Showings list container 'div.c-screen__list' not found for date {date_for_showings}.", file=sys.stderr)
        return daily_showings
    
    showings_ul = showings_list_container.find('ul')
    if not showings_ul:
        print(f"Debug ({CINEMA_NAME_ST}): Showings 'ul' not found for date {date_for_showings}.", file=sys.stderr)
        return daily_showings
    
    movie_items_li = showings_ul.find_all('li', recursive=False)
    if not movie_items_li:
        print(f"Debug ({CINEMA_NAME_ST}): No 'li' movie items found for date {date_for_showings}.", file=sys.stderr)

    for item_li_idx, item_li in enumerate(movie_items_li):
        screen_box_div = item_li.find('div', class_='c-screenBox') 
        if not screen_box_div: continue

        info_div = screen_box_div.find('div', class_='c-screenBox__info')
        if not info_div: continue

        time_tag = info_div.find('time')
        title_h2 = info_div.find('h2')

        showtime = "N/A"
        if time_tag:
            # --- CRITICAL CHANGE FOR TIME PARSING ---
            # Get all text nodes within the <time> tag directly.
            # This avoids issues with <br> or other nested tags if the first text node is the time.
            raw_time_text = ""
            for content in time_tag.contents:
                if isinstance(content, NavigableString):
                    raw_time_text = content.strip()
                    if re.match(r'\d{1,2}:\d{2}', raw_time_text): # Found a time-like string
                        break # Take the first one
            
            showtime_str_cleaned = clean_text_st(raw_time_text) # Clean this specific text
            print(f"Debug ({CINEMA_NAME_ST}): Raw time text found: '{raw_time_text}', Cleaned: '{showtime_str_cleaned}'", file=sys.stderr)
            
            showtime_match = re.search(r'(\d{1,2}:\d{2})', showtime_str_cleaned) # HH:MM
            if showtime_match:
                showtime = showtime_match.group(1)
                print(f"Debug ({CINEMA_NAME_ST}): Parsed showtime: '{showtime}'", file=sys.stderr)
            else:
                print(f"Debug ({CINEMA_NAME_ST}): No HH:MM match in cleaned time string: '{showtime_str_cleaned}'", file=sys.stderr)
        
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
    print(f"Debug ({CINEMA_NAME_ST}): Assuming year for dates as {assumed_year}.", file=sys.stderr)
    
    driver = None
    try:
        driver = _init_driver_stranger()
        print(f"Debug ({CINEMA_NAME_ST}): WebDriver initialized. Navigating to {URL_ST}.", file=sys.stderr)
        driver.get(URL_ST)

        print(f"Debug ({CINEMA_NAME_ST}): Waiting up to {INITIAL_LOAD_TIMEOUT}s for date scroller.", file=sys.stderr)
        date_scroller_container_selector = "div#block--screen div.c-screen__date ul"
        WebDriverWait(driver, INITIAL_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, date_scroller_container_selector))
        )
        
        date_tabs_li_elements_locator = (By.CSS_SELECTOR, f"{date_scroller_container_selector} > li")
        WebDriverWait(driver, INITIAL_LOAD_TIMEOUT).until(
            EC.presence_of_all_elements_located(date_tabs_li_elements_locator)
        )
        
        initial_date_tabs = driver.find_elements(*date_tabs_li_elements_locator)
        num_total_date_tabs = len(initial_date_tabs)
        num_tabs_to_process = min(num_total_date_tabs, 7) 
        print(f"Debug ({CINEMA_NAME_ST}): Found {num_total_date_tabs} date tabs. Will process up to {num_tabs_to_process}.", file=sys.stderr)

        if num_tabs_to_process == 0:
            print(f"Error ({CINEMA_NAME_ST}): No date tabs found.", file=sys.stderr)
            return []
        
        for i in range(num_tabs_to_process):
            print(f"\nDebug ({CINEMA_NAME_ST}): Processing date tab index {i} (1-based: {i+1}/{num_tabs_to_process}).", file=sys.stderr)
            
            current_date_tabs = WebDriverWait(driver, CLICK_WAIT_TIMEOUT).until(
                EC.presence_of_all_elements_located(date_tabs_li_elements_locator)
            )
            if i >= len(current_date_tabs): 
                print(f"Error ({CINEMA_NAME_ST}): Date tab index {i} out of bounds. Breaking.", file=sys.stderr)
                break
            
            date_tab_to_click_selenium_element = current_date_tabs[i]
            
            date_span_in_tab = WebDriverWait(date_tab_to_click_selenium_element, CLICK_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span"))
            )
            raw_date_text_current_tab = clean_text_st(date_span_in_tab.get_attribute("innerHTML"))
            parsed_date_current_tab = parse_date_st(raw_date_text_current_tab, assumed_year)
            print(f"Debug ({CINEMA_NAME_ST}): Tab {i+1} - Raw Date: '{raw_date_text_current_tab}', Parsed Date: '{parsed_date_current_tab}'", file=sys.stderr)

            if i == 0: 
                print(f"Debug ({CINEMA_NAME_ST}): First tab (index 0), content for '{parsed_date_current_tab}'.", file=sys.stderr)
                WebDriverWait(driver, INITIAL_LOAD_TIMEOUT).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "div#block--screen div.c-screen__list ul li div.c-screenBox"))
                ) # Wait for visibility of a box
                time.sleep(POST_CLICK_RENDER_PAUSE / 2) 
            else: 
                print(f"Debug ({CINEMA_NAME_ST}): Attempting to click tab {i+1} for '{parsed_date_current_tab}'.", file=sys.stderr)
                try:
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center', inline: 'center'});", date_tab_to_click_selenium_element)
                    time.sleep(0.3) 
                    driver.execute_script("arguments[0].click();", date_tab_to_click_selenium_element)
                    print(f"Debug ({CINEMA_NAME_ST}): JS click for tab {i+1}. Pausing {POST_CLICK_RENDER_PAUSE}s for content update.", file=sys.stderr)
                    time.sleep(POST_CLICK_RENDER_PAUSE) # Explicit pause after click
                except Exception as e_click: # Catch more general exceptions during click
                    print(f"Error ({CINEMA_NAME_ST}): Error clicking tab {i+1} ('{parsed_date_current_tab}'): {e_click}", file=sys.stderr)
                    continue 
            
            current_html_content = driver.page_source
            current_soup = BeautifulSoup(current_html_content, 'html.parser')
            
            daily_showings = extract_showings_from_soup(current_soup, parsed_date_current_tab, assumed_year)
            if daily_showings:
                print(f"Debug ({CINEMA_NAME_ST}): Extracted {len(daily_showings)} showings for '{parsed_date_current_tab}'.", file=sys.stderr)
                all_showings_collected.extend(daily_showings)
            else:
                print(f"Debug ({CINEMA_NAME_ST}): No showings extracted for '{parsed_date_current_tab}'.", file=sys.stderr)
        
        unique_showings = [dict(t) for t in {tuple(d.items()) for d in all_showings_collected}]
        print(f"Debug ({CINEMA_NAME_ST}): Total unique showings collected: {len(unique_showings)}", file=sys.stderr)
        
        return unique_showings

    except TimeoutException as e_initial:
        print(f"Error ({CINEMA_NAME_ST}): Selenium timed out on initial page actions: {e_initial}", file=sys.stderr)
        if driver: 
            try:
                html_on_timeout = driver.page_source
                debug_filename = f"stranger_timeout_debug_{datetime.now():%Y%m%d%H%M%S}.html"
                with open(debug_filename, "w", encoding="utf-8") as f_timeout:
                    f_timeout.write(BeautifulSoup(html_on_timeout, 'html.parser').prettify())
                print(f"Debug ({CINEMA_NAME_ST}): Saved page source to {debug_filename}.", file=sys.stderr)
            except: pass
        return []
    except WebDriverException as e_wd:
        print(f"Error ({CINEMA_NAME_ST}): WebDriverException: {e_wd}", file=sys.stderr)
        return []
    except Exception as e_main:
        print(f"An unexpected error in scrape_stranger: {e_main}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return []
    finally:
        if driver:
            print(f"Debug ({CINEMA_NAME_ST}): Quitting WebDriver for {CINEMA_NAME_ST}.", file=sys.stderr)
            driver.quit()

if __name__ == '__main__':
    print(f"Testing {CINEMA_NAME_ST} scraper module (Selenium, headless)...")
    showings_data = scrape_stranger()
    if showings_data:
        print(f"\nFound {len(showings_data)} unique showings for {CINEMA_NAME_ST}:")
        showings_data.sort(key=lambda x: (x.get('date_text', ''), x.get('title', ''), x.get('showtime', '')))
        for i, showing_item in enumerate(showings_data):
            print(f"  {showing_item.get('cinema', 'N/A')} | {showing_item.get('date_text', 'N/A')} | Title: '{showing_item.get('title', 'N/A')}' | Showtime: '{showing_item.get('showtime', 'N/A')}'")
    else:
        print(f"\nNo showings found by {CINEMA_NAME_ST} scraper.")
        print("  Check debug messages above and any 'stranger_*_debug.html' files if created.")