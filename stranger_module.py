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
    
    processed_date_str = re.sub(r'^[一-龠々]+曜?\s*(<br\s*/?>)?\s*|\s*[月火水木金土日]\s*(<br\s*/?>)?\s*', '', date_str_raw.strip(), flags=re.IGNORECASE)
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
    except Exception as e:
        return processed_date_str if processed_date_str else date_str_raw

def extract_showings_from_soup(soup, date_for_showings, year_for_parsing):
    daily_showings = []
    schedule_section_root = soup.find('div', id='block--screen', class_='p-top__screen')
    if not schedule_section_root:
        # print(f"Error ({CINEMA_NAME_ST}): BS4: Could not find schedule section for date {date_for_showings}.", file=sys.stderr)
        return daily_showings
    
    showings_list_container = schedule_section_root.find('div', class_='c-screen__list')
    if not showings_list_container:
        # print(f"Error ({CINEMA_NAME_ST}): BS4: Could not find showings list container for date {date_for_showings}.", file=sys.stderr)
        return daily_showings
    
    showings_ul = showings_list_container.find('ul')
    if not showings_ul:
        # print(f"Error ({CINEMA_NAME_ST}): BS4: Could not find <ul> in showings list for date {date_for_showings}.", file=sys.stderr)
        return daily_showings
    
    movie_items_li = showings_ul.find_all('li', recursive=False)

    for item_li_idx, item_li in enumerate(movie_items_li):
        screen_box_div = item_li.find('div', class_='c-screenBox') 
        if not screen_box_div: continue
        info_div = screen_box_div.find('div', class_='c-screenBox__info')
        if not info_div: continue
        time_tag = info_div.find('time')
        title_h2 = info_div.find('h2')
        showtime = "N/A"
        if time_tag:
            time_contents = time_tag.decode_contents() 
            start_time_part = time_contents.split('<br')[0] 
            showtime_str_cleaned = clean_text_st(start_time_part)
            showtime_match = re.search(r'(\d{1,2}:\d{2})', showtime_str_cleaned)
            if showtime_match: showtime = showtime_match.group(1)
        film_title = "Unknown Film"
        if title_h2:
            film_title = clean_text_st(title_h2)
            if not film_title: film_title = "Unknown Film (empty H2)"
        
        if showtime == "N/A" and film_title.startswith("Unknown Film"): continue
        
        daily_showings.append({"cinema": CINEMA_NAME_ST, "date_text": date_for_showings, "title": film_title, "showtime": showtime})
    return daily_showings


def scrape_stranger():
    all_showings_collected = []
    print(f"Debug ({CINEMA_NAME_ST}): Starting scrape_stranger function using Selenium for multiple days.", file=sys.stderr)
    assumed_year = date.today().year # Use current year dynamically
    print(f"Debug ({CINEMA_NAME_ST}): Assuming year for dates as {assumed_year}.", file=sys.stderr)
    
    options = ChromeOptions()
    options.add_argument("--headless") 
    options.add_argument("--disable-gpu") 
    options.add_argument("--no-sandbox") 
    options.add_argument("--disable-dev-shm-usage") 
    options.add_argument("--disable-extensions") 
    # options.add_argument("--start-maximized") # Less relevant for headless
    options.add_argument("--window-size=1920,1080") # Define a viewport

    driver = None 
    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true' # GITHUB_ACTIONS is true in GitHub Actions

    try:
        if is_github_actions:
            print(f"Debug ({CINEMA_NAME_ST}): Running in GitHub Actions. ChromeDriver should be in PATH.", file=sys.stderr)
            # In GitHub Actions, Chrome (google-chrome-stable) and chromedriver are installed by the workflow.
            # Selenium should find them if they are in the PATH.
            driver = webdriver.Chrome(options=options)
        else:
            # Local setup (e.g., Windows with Brave)
            webdriver_path_local = './chromedriver.exe' 
            brave_exe_path_local = r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe'
            
            # Check if local Brave path exists, try user-specific as fallback
            if not os.path.exists(brave_exe_path_local):
                user_profile = os.getenv('USERPROFILE', '') # Get user profile path
                brave_exe_path_local_user = fr'{user_profile}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe'
                if os.path.exists(brave_exe_path_local_user):
                    brave_exe_path_local = brave_exe_path_local_user
                else:
                    print(f"Warning ({CINEMA_NAME_ST}): Brave executable not found at default paths for local run. Ensure Brave is installed or path is correct.", file=sys.stderr)
                    # Attempt to run without binary_location if Brave is default and in PATH
            
            if os.path.exists(brave_exe_path_local): # Only set if found
                 options.binary_location = brave_exe_path_local

            if not os.path.exists(webdriver_path_local):
                print(f"Error ({CINEMA_NAME_ST}): ChromeDriver not found at '{webdriver_path_local}' for local run. Please ensure it's there and accessible.", file=sys.stderr)
                return [] # Cannot proceed without chromedriver locally if not in PATH

            service = ChromeService(executable_path=webdriver_path_local)
            print(f"Debug ({CINEMA_NAME_ST}): Initializing WebDriver locally (Brave: '{options.binary_location}', ChromeDriver: '{webdriver_path_local}').", file=sys.stderr)
            driver = webdriver.Chrome(service=service, options=options)

        print(f"Debug ({CINEMA_NAME_ST}): WebDriver initialized. Navigating to {URL_ST}.", file=sys.stderr)
        driver.get(URL_ST)

        timeout = 25
        print(f"Debug ({CINEMA_NAME_ST}): Waiting up to {timeout}s for initial page elements (date scroller).", file=sys.stderr)
        
        date_scroller_container_selector = "div#block--screen div.c-screen__date ul"
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, date_scroller_container_selector))
        )
        
        date_tabs_li_elements_locator = (By.CSS_SELECTOR, f"{date_scroller_container_selector} > li")
        WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located(date_tabs_li_elements_locator)
        )
        
        initial_date_tabs = driver.find_elements(*date_tabs_li_elements_locator)
        num_total_date_tabs = len(initial_date_tabs)
        num_tabs_to_process = min(num_total_date_tabs, 7) 
        print(f"Debug ({CINEMA_NAME_ST}): Found {num_total_date_tabs} total date tabs. Will process up to {num_tabs_to_process}.", file=sys.stderr)


        if num_tabs_to_process == 0:
            print(f"Error ({CINEMA_NAME_ST}): No date tabs found or to process.", file=sys.stderr)
            return []
        
        parsed_date_initial = "NotYetScraped" 

        for i in range(num_tabs_to_process):
            print(f"\nDebug ({CINEMA_NAME_ST}): Processing date tab {i+1}/{num_tabs_to_process}.", file=sys.stderr)
            
            current_date_tabs = WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located(date_tabs_li_elements_locator)
            )
            if i >= len(current_date_tabs): 
                print(f"Error ({CINEMA_NAME_ST}): Date tab index {i} out of bounds after re-finding. Breaking.", file=sys.stderr)
                break
            
            date_tab_to_click_selenium_element = current_date_tabs[i]
            
            date_span_in_tab = WebDriverWait(date_tab_to_click_selenium_element, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span")) # Ensure span is present
            )
            raw_date_text_current_tab = clean_text_st(date_span_in_tab.get_attribute("innerHTML"))
            parsed_date_current_tab = parse_date_st(raw_date_text_current_tab, assumed_year)
            print(f"Debug ({CINEMA_NAME_ST}): Current tab date: '{parsed_date_current_tab}' (raw: '{raw_date_text_current_tab}')", file=sys.stderr)
            
            if i == 0: 
                parsed_date_initial = parsed_date_current_tab 
                print(f"Debug ({CINEMA_NAME_ST}): This is the first tab (index 0), processing its schedule.", file=sys.stderr)
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div#block--screen div.c-screen__list ul li div.c-screenBox"))
                )
                time.sleep(0.5) 
            
            if i > 0 : 
                print(f"Debug ({CINEMA_NAME_ST}): Attempting to click date tab {i+1} for date '{parsed_date_current_tab}'.", file=sys.stderr)
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", date_tab_to_click_selenium_element)
                    time.sleep(0.2) 
                    driver.execute_script("arguments[0].click();", date_tab_to_click_selenium_element)
                    print(f"Debug ({CINEMA_NAME_ST}): JavaScript click executed for tab {i+1}.", file=sys.stderr)
                    
                    movie_list_item_selector = "div#block--screen div.c-screen__list ul li div.c-screenBox"
                    WebDriverWait(driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, movie_list_item_selector))
                    )
                    time.sleep(1) 
                    print(f"Debug ({CINEMA_NAME_ST}): Movie list presumed updated for '{parsed_date_current_tab}'.", file=sys.stderr)

                except ElementClickInterceptedException:
                    print(f"Warning ({CINEMA_NAME_ST}): ElementClickInterceptedException for tab {i+1}. Skipping date.", file=sys.stderr)
                    continue
                except StaleElementReferenceException:
                    print(f"Warning ({CINEMA_NAME_ST}): StaleElementReferenceException for date tab {i+1}. Skipping.", file=sys.stderr)
                    continue 
                except TimeoutException:
                    print(f"Warning ({CINEMA_NAME_ST}): Timeout waiting for movie list update after clicking tab {i+1} ('{parsed_date_current_tab}'). Skipping.", file=sys.stderr)
                    try:
                        html_on_click_timeout = driver.page_source
                        with open(f"stranger_click_timeout_debug_date_{i+1}.html", "w", encoding="utf-8") as f_timeout:
                            f_timeout.write(BeautifulSoup(html_on_click_timeout, 'html.parser').prettify())
                        # print(f"Debug ({CINEMA_NAME_ST}): Saved HTML on click timeout to stranger_click_timeout_debug_date_{i+1}.html", file=sys.stderr)
                    except Exception: pass # Ignore save error
                    continue
            
            current_html_content = driver.page_source
            current_soup = BeautifulSoup(current_html_content, 'html.parser')
            
            # print(f"Debug ({CINEMA_NAME_ST}): Extracting showings for '{parsed_date_current_tab}'.", file=sys.stderr)
            daily_showings = extract_showings_from_soup(current_soup, parsed_date_current_tab, assumed_year)
            all_showings_collected.extend(daily_showings)
            # print(f"Debug ({CINEMA_NAME_ST}): Collected {len(daily_showings)} showings for '{parsed_date_current_tab}'. Total: {len(all_showings_collected)}", file=sys.stderr)
        
        unique_showings = []
        seen_showings = set()
        for showing in all_showings_collected:
            identifier = (showing['date_text'], showing['title'], showing['showtime'])
            if identifier not in seen_showings:
                unique_showings.append(showing)
                seen_showings.add(identifier)
        all_showings_collected = unique_showings
        print(f"Debug ({CINEMA_NAME_ST}): Total unique showings collected after processing {num_tabs_to_process} tabs: {len(all_showings_collected)}", file=sys.stderr)
        
        return all_showings_collected

    except TimeoutException:
        print(f"Error ({CINEMA_NAME_ST}): Selenium timed out waiting for initial page elements.", file=sys.stderr)
        if driver: 
            try:
                html_on_timeout = driver.page_source
                with open("stranger_initial_timeout_debug.html", "w", encoding="utf-8") as f_timeout:
                    f_timeout.write(BeautifulSoup(html_on_timeout, 'html.parser').prettify())
                # print(f"Debug ({CINEMA_NAME_ST}): Saved HTML on initial timeout to stranger_initial_timeout_debug.html", file=sys.stderr)
            except: pass
        return []
    except WebDriverException as e_wd:
        print(f"Error ({CINEMA_NAME_ST}): Selenium WebDriverException: {e_wd}", file=sys.stderr)
        browser_version_info = "N/A"
        # Check if driver was initialized and has capabilities
        if driver and hasattr(driver, 'capabilities') and driver.capabilities:
            browser_version_info = driver.capabilities.get('browserVersion', 'N/A')
        print(f"  Make sure ChromeDriver (for browser version {browser_version_info}) is compatible and accessible, and browser path (if set) is correct.", file=sys.stderr)
        return []
    except Exception as e:
        print(f"An unexpected error occurred in scrape_stranger: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []
    finally:
        if driver:
            print(f"Debug ({CINEMA_NAME_ST}): Quitting WebDriver.", file=sys.stderr)
            driver.quit()
            # print(f"Debug ({CINEMA_NAME_ST}): WebDriver quit successfully.", file=sys.stderr)

if __name__ == '__main__':
    print(f"Testing {CINEMA_NAME_ST} scraper module (with Selenium for multiple days, headless)...")
    showings = scrape_stranger()
    if showings:
        print(f"\nFound {len(showings)} showings for {CINEMA_NAME_ST}:")
        showings.sort(key=lambda x: (x.get('date_text', ''), x.get('title', ''), x.get('showtime', '')))
        for i, showing in enumerate(showings):
            print(f"  Cinema: {showing.get('cinema', 'N/A')}, Date: {showing.get('date_text', 'N/A')}, Title: {showing.get('title', 'N/A')}, Showtime: {showing.get('showtime', 'N/A')}")
    else:
        print(f"\nNo showings found by {CINEMA_NAME_ST} scraper (with Selenium).")
        print("  Check debug messages above and any 'stranger_*_debug.html' files if created.")

    print(f"\nNote ({CINEMA_NAME_ST}): This version uses Selenium to iterate through available dates on the page (up to 7 days, headless).")
