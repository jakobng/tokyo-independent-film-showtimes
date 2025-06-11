"""
bunkamura_module.py — Selenium‑powered scraper for Bunkamura Le Cinéma (渋谷宮下)
Updated: 2025‑06‑11 – switched from plain requests to headless‑Chrome because most
of the schedule markup is injected client‑side via JavaScript (‘func‑lineupSet.js’).

Returned list of dict rows matches the rest of the bot:
    cinema, date_text (YYYY‑MM‑DD), screen, title, showtime

Works on local Windows + ChromeDriver or GitHub Actions.
"""
from __future__ import annotations

import re
import sys
import os
import time
from datetime import datetime, timedelta, date
from typing import Dict, List

from bs4 import BeautifulSoup

# Selenium imports -----------------------------------------------------------
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CINEMA_NAME = "Bunkamuraル・シネマ 渋谷宮下"
URL = "https://www.bunkamura.co.jp/pickup/movie.html"

INITIAL_LOAD_TIMEOUT = 30   # seconds – wait for first article to appear
MAX_DAYS_AHEAD      = 10    # keep parity with other cinema modules

__all__ = ["scrape_bunkamura"]

# ---------------------------------------------------------------------------
# WebDriver helper
# ---------------------------------------------------------------------------

def _init_driver() -> webdriver.Chrome:
    """Return a ready‑to‑use headless Chrome/Brave driver (JST timezone)."""
    opts = ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable‑gpu")
    opts.add_argument("--no‑sandbox")
    opts.add_argument("--disable‑dev‑shm‑usage")
    opts.add_argument("--window‑size=1920,1080")
    opts.add_experimental_option('excludeSwitches', ['enable-logging'])

    # Prefer Brave on Windows if available so user’s main Chrome profile keeps clean
    brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    if os.name == "nt" and os.path.exists(brave_path):
        opts.binary_location = brave_path

    # Decide ChromeDriver location – CI uses PATH, local dev expects ./chromedriver.exe
    chromedriver_local = "./chromedriver.exe"
    if os.name == "nt" and os.path.exists(chromedriver_local):
        service = ChromeService(executable_path=chromedriver_local)
    else:
        service = ChromeService()  # PATH / GitHub Actions

    driver = webdriver.Chrome(service=service, options=opts)

    # Force Asia/Tokyo so any JavaScript date math lines up with scraper expectations
    try:
        driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {'timezoneId': 'Asia/Tokyo'})
    except Exception:
        pass
    return driver

# ---------------------------------------------------------------------------
# Parsing helpers (mostly unchanged from v1) --------------------------------
# ---------------------------------------------------------------------------

def _parse_mmdd(token: str, year_hint: int) -> date:
    m, d = map(int, token.split("/"))
    y = year_hint
    if m == 1 and datetime.today().month == 12:
        y += 1
    return date(y, m, d)


def _date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _clean_time(raw: str) -> str | None:
    m = re.search(r"(\d{1,2}):(\d{2})", raw)
    if not m:
        return None
    hh, mm = m.groups()
    return f"{int(hh):02d}:{mm}"

# ---------------------------------------------------------------------------
# Core extraction ------------------------------------------------------------
# ---------------------------------------------------------------------------

def _extract_from_soup(soup: BeautifulSoup) -> List[Dict[str, str]]:
    year = datetime.today().year
    rows: List[Dict[str, str]] = []

    now_showing = soup.find("section", id="todays")
    if not now_showing:
        return rows

    for art in now_showing.select("div.eventLineUp article.cinema"):
        default_title = art.select_one("h3.title-article span.ttl")
        default_title = default_title.get_text(" ", strip=True) if default_title else "Unknown Title"

        time_block = art.select_one("div.timetable_todays p.timetable_todays_caption")
        if not time_block:
            continue

        lines = [ln.strip().replace("　", " ") for ln in time_block.get_text("\n", strip=True).split("\n") if ln.strip()]

        active_range: tuple[date, date] | None = None
        active_title = default_title

        for ln in lines:
            if ln.startswith("◆"):
                continue  # header like “◆6/19(木)までの上映◆”

            m_range = re.match(r"\[(\d{1,2}/\d{1,2})[^～]+～(\d{1,2}/\d{1,2})", ln)
            if m_range:
                start_s, end_s = m_range.groups()
                active_range = (_parse_mmdd(start_s, year), _parse_mmdd(end_s, year))
                continue

            m_title = re.match(r"『([^']+?)』", ln)
            if m_title:
                active_title = m_title.group(1).strip()
                continue

            if active_range:
                for raw in re.split(r"/|、", ln):
                    t = _clean_time(raw)
                    if not t:
                        continue
                    for d in _date_range(*active_range):
                        rows.append({
                            "cinema": CINEMA_NAME,
                            "date_text": d.isoformat(),
                            "screen": "",
                            "title": active_title,
                            "showtime": t,
                        })
    # Dedup & horizon filter
    seen = set()
    today = datetime.today().date()
    cutoff = today + timedelta(days=MAX_DAYS_AHEAD - 1)
    unique = []
    for r in rows:
        key = (r["date_text"], r["title"], r["showtime"])
        dt_obj = datetime.fromisoformat(r["date_text"]).date()
        if key in seen or not (today <= dt_obj <= cutoff):
            continue
        unique.append(r)
        seen.add(key)
    return unique

# ---------------------------------------------------------------------------
# Public API ----------------------------------------------------------------
# ---------------------------------------------------------------------------

def scrape_bunkamura() -> List[Dict[str, str]]:
    driver: webdriver.Chrome | None = None
    try:
        driver = _init_driver()
        driver.get(URL)
        WebDriverWait(driver, INITIAL_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section#todays div.eventLineUp article.cinema"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
        return _extract_from_soup(soup)
    except TimeoutException:
        print(f"Error ({CINEMA_NAME}): page did not render showtimes within {INITIAL_LOAD_TIMEOUT}s", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error ({CINEMA_NAME}): unexpected failure: {e}", file=sys.stderr)
        return []
    finally:
        if driver:
            driver.quit()

# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if sys.platform == "win32":
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    print(f"Testing {CINEMA_NAME} scraper (Selenium)…")
    shows = scrape_bunkamura()
    print(f"Found {len(shows)} showings.")
    for s in sorted(shows, key=lambda r: (r['date_text'], r['showtime'], r['title']))[:10]:
        print(f"  {s['date_text']} {s['showtime']} {s['title']}")
