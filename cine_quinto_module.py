"""
cine_quinto_module.py
~~~~~~~~~~~~~~~~~~~~~
Scraper for Shibuya Cine Quinto (シネクイント渋谷).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService # Renamed
from webdriver_manager.chrome import ChromeDriverManager # Added
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_URL: str = (
    "https://www.cinequinto-ticket.jp/theater/shibuya/schedule"
)

# CHROME_BINARY: str | None = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" # REMOVED
# CHROMEDRIVER: str | None = "./chromedriver.exe" # REMOVED

MAX_DAYS: int = 7
PAGE_LOAD_TIMEOUT = 25
TAB_SWITCH_TIMEOUT = 7
HEADLESS = True # Keep True for GitHub Actions

CINEMA_NAME_JP = "シネクイント渋谷"

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s: %(module)-20s: %(message)s", # Added module name
)
log = logging.getLogger(__name__) # Use __name__ for logger


# --------------------------------------------------------------------------- #
# Selenium helpers
# --------------------------------------------------------------------------- #
def _init_driver() -> webdriver.Chrome:
    """Return a headless Chrome driver, using webdriver-manager."""
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1024")
    opts.add_argument("--disable-dev-shm-usage") # Often recommended for CI environments
    # if CHROME_BINARY: # REMOVED
    #     opts.binary_location = CHROME_BINARY # REMOVED

    # webdriver-manager will download and manage the correct ChromeDriver
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _yyyymmdd_to_iso(date_str: str) -> str:
    """Convert '20250527' → '2025-05-27' as str."""
    return datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")


def _extract_showings_for_date(soup: BeautifulSoup, ymd: str) -> List[Dict]:
    rows: List[Dict] = []
    container = soup.find("div", id=f"dateJouei{ymd}")
    if not container:
        return rows

    for panel in container.select("div.movie-panel"):
        title_tag = panel.select_one("div.title-jp")
        if title_tag is None:
            continue
        title = title_tag.get_text(strip=True)

        for ms in panel.select("div.movie-schedule"):
            begin_span = ms.select_one("span.movie-schedule-begin")
            if not begin_span:
                continue

            start_time = begin_span.get_text(strip=True)
            screen_raw = ms.get("data-screen", "").strip()
            screen = f"スクリーン{1 if screen_raw == '10' else 2}" if screen_raw else ""

            rows.append(
                {
                    "cinema": CINEMA_NAME_JP,
                    "date_text": _yyyymmdd_to_iso(ymd),
                    "screen": screen,
                    "title": title,
                    "showtime": start_time,
                }
            )
    return rows


# --------------------------------------------------------------------------- #
# Main scraping routine
# --------------------------------------------------------------------------- #
def scrape_cinequinto_shibuya() -> List[Dict]:
    log.info(f"Running scraper for {CINEMA_NAME_JP} …")
    driver = None # Initialize for finally block
    collected: List[Dict] = []

    try:
        driver = _init_driver() # Initialize driver here
        driver.get(BASE_URL)
        wait = WebDriverWait(driver, PAGE_LOAD_TIMEOUT)
        wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.date-box"))
        )

        date_tabs = driver.find_elements(By.CSS_SELECTOR, "div.date-box")
        if not date_tabs:
            log.error("No date tabs found – page layout may have changed.")
            return [] # Return empty if no tabs

        for idx, tab in enumerate(date_tabs[:MAX_DAYS]):
            ymd = tab.get_attribute("data-jouei")
            if not ymd:
                log.warning("Date tab found without 'data-jouei' attribute.")
                continue

            log.info(f"Processing date: {ymd}")
            if idx != 0:
                try:
                    driver.execute_script("arguments[0].click();", tab)
                    WebDriverWait(driver, TAB_SWITCH_TIMEOUT).until(
                        EC.visibility_of_element_located((By.ID, f"dateJouei{ymd}"))
                    )
                except TimeoutException:
                    log.warning(
                        f"Timeout waiting for schedule block of {ymd} – skipping"
                    )
                    continue
                except Exception as e:
                    log.error(f"Error clicking tab or waiting for content for {ymd}: {e}")
                    continue


            soup = BeautifulSoup(driver.page_source, "html.parser")
            day_rows = _extract_showings_for_date(soup, ymd)
            collected.extend(day_rows)
            time.sleep(0.5) # Polite pause

    except Exception as e:
        log.error(f"An error occurred during scraping {CINEMA_NAME_JP}: {e}")
        # Optionally re-raise or handle more specifically
    finally:
        if driver: # Check if driver was initialized
            driver.quit()

    # Deduplicate, though less likely with this structure if parsing is correct
    # dedup = {
    #     (r["cinema"], r["date_text"], r["screen"], r["title"], r["showtime"]): r
    #     for r in collected
    # }
    # final_rows = list(dedup.values())
    final_rows = collected # Using collected directly if duplicates are not expected.
    log.info(f"Collected {len(final_rows)} showings from {CINEMA_NAME_JP}.")
    return final_rows


# --------------------------------------------------------------------------- #
# Stand-alone execution
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    rows = scrape_cinequinto_shibuya()
    if rows:
        from pprint import pprint
        pprint(rows[:10])
    else:
        log.error(f"No rows collected for {CINEMA_NAME_JP}.")