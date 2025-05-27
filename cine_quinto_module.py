"""
cine_quinto_module.py
~~~~~~~~~~~~~~~~~~~~~
Scraper for Shibuya Cine Quinto (シネクイント渋谷).

The cinema’s e-ticketing site is a Cineticket installation identical in
structure to Cinemart Shinjuku, so we reuse the same approach:

• open the schedule page with Selenium (head-less Brave/Chrome)
• step through the first 7 “date tabs”
• for each day, parse the hidden/visible <div id="dateJoueiYYYYMMDD"> block
  with BeautifulSoup and extract every <div class="movie-schedule"> item.

Returned rows → list[dict] with keys:
    cinema, date_text (yyyy-mm-dd), screen, title, showtime (HH:MM)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# --------------------------------------------------------------------------- #
# Configuration – adjust to your local environment if needed
# --------------------------------------------------------------------------- #
BASE_URL: str = (
    "https://www.cinequinto-ticket.jp/theater/shibuya/schedule"
)  # ← no hash – we’ll add it per date

CHROME_BINARY: str | None = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
CHROMEDRIVER: str | None = "./chromedriver.exe"  # same folder as this script

MAX_DAYS: int = 7  # scrape today + next 6 days
PAGE_LOAD_TIMEOUT = 25
TAB_SWITCH_TIMEOUT = 7
HEADLESS = True

CINEMA_NAME_JP = "シネクイント渋谷"

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s: %(message)s",
)
log = logging.getLogger("cinequinto")


# --------------------------------------------------------------------------- #
# Selenium helpers
# --------------------------------------------------------------------------- #
def _init_driver() -> webdriver.Chrome:
    """Return a headless Chrome/Brave driver."""
    opts = Options()
    if HEADLESS:
        # new headless mode (chromium 109+)
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1024")
    if CHROME_BINARY:
        opts.binary_location = CHROME_BINARY

    service = Service(CHROMEDRIVER) if CHROMEDRIVER else Service()
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
    """
    Parse the <div id="dateJoueiYYYYMMDD"> block for one day and return rows.

    Each <div class="movie-schedule"> carries:
        • data-screen="10" | "20" ...
        • span.movie-schedule-begin  → '09:45'
    The title lives in the parent .movie-panel heading (div.title-jp).
    """
    rows: List[Dict] = []

    container = soup.find("div", id=f"dateJouei{ymd}")
    if not container:
        return rows

    for panel in container.select("div.movie-panel"):
        title_tag = panel.select_one("div.title-jp")
        if title_tag is None:
            continue
        title = title_tag.get_text(strip=True)

        # For each start time of this film
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
    """Run the full 7-day scrape and return collected showings."""
    log.info("Running Cinequinto Shibuya scraper …")
    driver = _init_driver()
    collected: List[Dict] = []

    try:
        driver.get(BASE_URL)
        wait = WebDriverWait(driver, PAGE_LOAD_TIMEOUT)
        wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.date-box"))
        )

        date_tabs = driver.find_elements(By.CSS_SELECTOR, "div.date-box")
        if not date_tabs:
            raise RuntimeError("No date tabs found – page layout changed?")

        # Loop over the first MAX_DAYS tabs
        for idx, tab in enumerate(date_tabs[:MAX_DAYS]):
            # Each tab has data-jouei="YYYYMMDD"
            ymd = tab.get_attribute("data-jouei")
            if not ymd:
                continue

            # Click (skip click for first tab – already selected)
            if idx != 0:
                driver.execute_script("arguments[0].click();", tab)
                # Wait for the corresponding dateJouei div to become visible
                try:
                    WebDriverWait(driver, TAB_SWITCH_TIMEOUT).until(
                        EC.visibility_of_element_located((By.ID, f"dateJouei{ymd}"))
                    )
                except TimeoutException:
                    log.warning(
                        "Timeout waiting for schedule block of %s – skipping", ymd
                    )
                    continue

            # Use driver.page_source (after click)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            day_rows = _extract_showings_for_date(soup, ymd)
            collected.extend(day_rows)

    finally:
        driver.quit()

    # Deduplicate rows (title + date + time) just in case
    dedup = {
        (r["cinema"], r["date_text"], r["screen"], r["title"], r["showtime"]): r
        for r in collected
    }
    final_rows = list(dedup.values())
    log.info("Collected %d showings from %s.", len(final_rows), CINEMA_NAME_JP)
    return final_rows


# --------------------------------------------------------------------------- #
# Stand-alone execution
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    rows = scrape_cinequinto_shibuya()
    if rows:
        # Pretty-print the first few for manual inspection
        from pprint import pprint

        pprint(rows[:10])
    else:
        log.error("No rows collected.")
