"""nfaj_calendar_module.py — scraper for 国立映画アーカイブ mini‑calendar (ホーム)
Updated 2025‑05‑31 — film screenings only; exposes scrape_nfaj_calendar() for the master scraper.

This module scrapes the five‑day mini‑calendar that appears on the NFAJ home
page (https://www.nfaj.go.jp/).  Only film screenings are extracted; exhibition
rooms, library hours, and gallery talks are ignored.

Return format (list[dict])::
    {
        "cinema_name": "国立映画アーカイブ",
        "screen": "長瀬記念ホール OZU",
        "title": "懷古二十五年 草に祈る 他",
        "date_text": "2025-05-31",
        "showtime": "14:00",
        "url": "https://www.nfaj.go.jp/program/…"
    }

Public API
----------
* scrape_nfaj_calendar(days_ahead: int = 7, use_selenium: str = "auto") – main entry
* get_events(...) – helper used by the CLI smoke‑test

CLI::
    $ python nfaj_calendar_module.py 5
    2025‑05‑31 14:00  懷古二十五年 草に祈る 他
    …
"""

from __future__ import annotations

import contextlib
import re
import sys
from datetime import datetime, timedelta
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

# Optional selenium imports (only loaded if needed)
with contextlib.suppress(ImportError):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options


CINEMA_NAME = "国立映画アーカイブ"
HOMEPAGE_URL = "https://www.nfaj.go.jp/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/124.0.0.0 Safari/537.36"
    )
}


def _fetch_homepage_html(use_selenium: str = "auto") -> str:
    """Return raw HTML of the homepage, optionally via Selenium.

    If *use_selenium* is "auto" we first try requests; if the resulting markup
    only contains **one** tab panel we retry with Selenium.
    """
    if use_selenium == "never":
        return requests.get(HOMEPAGE_URL, headers=HEADERS, timeout=10).text

    if use_selenium == "always":
        return _selenium_get_html()

    # auto mode – try requests first
    html = requests.get(HOMEPAGE_URL, headers=HEADERS, timeout=10).text
    if html.count("class=\"tabpanel") > 1:
        return html
    # Fallback
    return _selenium_get_html()


def _selenium_get_html() -> str:
    """Retrieve page via headless Chrome and return the full DOM after clicking tabs."""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=opts)

    try:
        driver.get(HOMEPAGE_URL)
        driver.implicitly_wait(3)

        buttons = driver.find_elements("css selector", "#calendar .tab_list button")
        for btn in buttons:
            btn.click()
            driver.implicitly_wait(1)  # wait a moment for panel swap

        html = driver.page_source
    finally:
        driver.quit()

    return html


def _parse_events(html: str, days_ahead: int = 7) -> List[Dict]:
    """Extract film screenings from the combined HTML."""
    soup = BeautifulSoup(html, "html.parser")
    today = datetime.now().date()

    events: List[Dict] = []
    # Match each button to its tabpanel by ID
    for btn in soup.select("#calendar .tab_list button")[: days_ahead]:
        date_str = btn.get_text(strip=True).split("(")[0]  # e.g. "5/31"
        month, day = map(int, date_str.split("/"))

        year = today.year
        if month < today.month - 6:  # Handle year rollover in Dec/Jan
            year += 1
        full_date = datetime(year, month, day).date()

        panel_id = btn["aria-controls"]
        panel = soup.select_one(f"#{panel_id}")

        if not panel or panel.find(class_="close_day"):
            continue  # Skip closure days

        for film_div in panel.select("div.film"):
            screen = film_div.find("h2").get_text(strip=True)
            if film_div.find(text=re.compile("休映")):
                continue

            for li in film_div.select("ul > li"):
                # Skip talks/Q&A
                title_link = li.find("a")
                if not title_link:
                    continue
                title_text = title_link.get_text(strip=True)
                if re.search(r"トーク|talk", title_text, re.I):
                    continue

                time_tag = li.find("time")
                showtime = time_tag["datetime"] if time_tag else ""

                events.append(
                    {
                        "cinema_name": CINEMA_NAME,
                        "screen": screen,
                        "title": title_text,
                        "date_text": full_date.isoformat(),
                        "showtime": showtime,
                        "url": title_link["href"],
                    }
                )
    return events


def get_events(days_ahead: int = 7, use_selenium: str = "auto") -> List[Dict]:
    """Return list of film screenings up to *days_ahead* days ahead."""
    html = _fetch_homepage_html(use_selenium=use_selenium)
    return _parse_events(html, days_ahead=days_ahead)


# ---------------------------------------------------------------------------
# Public entry point expected by main_scraperX.py
# ---------------------------------------------------------------------------

def scrape_nfaj_calendar() -> List[Dict]:  # Name expected by main_scraper2.py
    """Wrapper with default horizon of 5 days for compatibility."""
    return get_events(days_ahead=5, use_selenium="auto")


# ---------------------------------------------------------------------------
# CLI helper (for quick testing)
# ---------------------------------------------------------------------------

def main(argv=None):
    argv = argv or sys.argv[1:]
    days = int(argv[0]) if argv else 5
    rows = get_events(days_ahead=days, use_selenium="auto")
    print(f"Found {len(rows)} film screenings. First 20:\n")
    for row in rows[:20]:
        print(f"{row['date_text']} {row['showtime']:>5}  {row['title']}")


if __name__ == "__main__":
    main()
