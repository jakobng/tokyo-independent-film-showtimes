"""
yebisu_garden_module.py  –  scraper for YEBISU GARDEN CINEMA
https://www.unitedcinemas.jp/ygc/
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
import time
from typing import Dict, List

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService # Renamed to avoid conflict
from webdriver_manager.chrome import ChromeDriverManager # Added
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ──────────────────────────────────────────────────────────────
CINEMA_NAME = "YEBISU GARDEN CINEMA"
BASE_URL = "https://www.unitedcinemas.jp/ygc"
DAILY_URL = BASE_URL + "/daily.php?date={}"        # date → YYYY-MM-DD
DAYS_AHEAD = 7                                     # default window

# -- local paths (NO LONGER USED FOR DRIVER/BROWSER PATH in CI) ---
# BRAVE_BIN    = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
# CHROMEDRIVER = r"./chromedriver.exe"
# --------------------------------------------------------------


# ───── Selenium helpers ───────────────────────────────────────
def _init_driver() -> webdriver.Chrome:
    """Return a headless Chrome driver, using webdriver-manager."""
    opts = Options()
    # opts.binary_location = BRAVE_BIN # REMOVED - Let Selenium find system Chrome or use ChromeDriverManager's browser
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--disable-dev-shm-usage") # Often recommended for CI environments
    opts.add_argument("--disable-webgl")

    # webdriver-manager will download and manage the correct ChromeDriver
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def _wait_for_schedule(drv: webdriver.Chrome, timeout: int = 15) -> None:
    """Wait until Ajax has rendered <ul id="dailyList"> with showtimes."""
    sel = "ul#dailyList li.clearfix"
    WebDriverWait(drv, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
    )


# ───── HTML parsing ───────────────────────────────────────────
_SCREEN_RE = re.compile(r"(\d)screen")


def _parse_daily(html: str, date_obj: _dt.date) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[Dict] = []

    for film_li in soup.select("ul#dailyList li.clearfix"):
        title_tag = film_li.select_one("h3 span.movieTitle")
        if not title_tag:
            continue
        title = title_tag.get_text(" ", strip=True)

        screen_alt = (
            film_li.select_one("p.screenNumber img[alt*='screen']") or {}
        ).get("alt", "")
        m = _SCREEN_RE.search(screen_alt)
        screen = f"スクリーン{m.group(1)}" if m else "スクリーン"

        for st in film_li.select("li.startTime"):
            showtime = st.get_text(strip=True)
            if not showtime:
                continue
            rows.append(
                dict(
                    cinema=CINEMA_NAME,
                    date_text=str(date_obj),
                    screen=screen,
                    title=title,
                    showtime=showtime,
                )
            )
    return rows


# ───── public API ─────────────────────────────────────────────
def scrape_ygc(days_ahead: int = DAYS_AHEAD) -> List[Dict]:
    """Scrape today + *days_ahead*-1 and return list of showtime dicts."""
    rows: List[Dict] = []
    today = _dt.date.today()
    driver = None  # Initialize driver to None for finally block

    try:
        driver = _init_driver() # Initialize driver here
        for offset in range(days_ahead):
            date_obj = today + _dt.timedelta(days=offset)
            url = DAILY_URL.format(date_obj.isoformat())
            print(f"INFO   : GET {url} for {CINEMA_NAME}")

            driver.get(url)
            try:
                _wait_for_schedule(driver)
            except TimeoutException:
                print(f"WARNING: Schedule not found for {date_obj} at {CINEMA_NAME} – skipping day")
                continue

            rows.extend(_parse_daily(driver.page_source, date_obj))
            time.sleep(0.7)             # polite pause
    finally:
        if driver: # Check if driver was initialized
            driver.quit()

    print(f"INFO   : Collected {len(rows)} showings total from {CINEMA_NAME}.")
    return rows


# ───── quick-test entry point ─────────────────────────────────
if __name__ == "__main__":
    data = scrape_ygc()
    if not data:
        print(f"No data collected for {CINEMA_NAME}.")
        sys.exit(1)
    from pprint import pprint
    pprint(data[:10])