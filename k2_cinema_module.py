"""
k2_cinema_module.py — scraper for K2 Cinema (K2 シネマ)
Last updated: 2025-05-28

Returns a list of dicts with keys:
    cinema, date_text (YYYY-MM-DD), screen, title, showtime

Designed to mirror the structure used by the other cinema modules so it can be
plugged straight into `main_scraper3.py`.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List

from bs4 import BeautifulSoup
# Use Playwright for JS rendering
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

# ---------------------------------------------------------------------------
# Config / constants
# ---------------------------------------------------------------------------

CINEMA_NAME = "K2 Cinema"
URL = "https://k2-cinema.com/"
TIMEOUT = 20  # seconds

__all__ = ["scrape_k2_cinema"]

# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def scrape_k2_cinema() -> List[Dict[str, str]]:
    """
    Scrape the daily schedule for K2 Cinema.

    Returns:
        List of dicts: cinema, date_text (ISO YYYY-MM-DD), screen, title, showtime.
        Only includes showings within the next 10 days.
    """
    if sync_playwright is None:
        print(
            f"Error ({CINEMA_NAME}): Playwright not installed - run 'pip install playwright' and 'playwright install chromium'",
            file=sys.stderr,
        )
        return []

    today = datetime.today().date()
    cutoff = today + timedelta(days=9)
    results: List[Dict[str, str]] = []

    # Launch browser and render page
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(URL, timeout=TIMEOUT*1000)
            page.wait_for_selector('section.homeScheduleContainer', timeout=TIMEOUT*1000)
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"Error ({CINEMA_NAME}): failed to render page: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "html.parser")
    section = soup.find("section", class_="homeScheduleContainer")
    if not section:
        print(f"Error ({CINEMA_NAME}): schedule section not found after render", file=sys.stderr)
        return []

    # Iterate each date block
    for cont in section.find_all("div", class_="dateContainer"):
        date_div = cont.find("div", class_="date")
        if not date_div:
            continue
        txt = date_div.get_text(" ", strip=True)
        m = re.search(r"(\d{2})\.(\d{2})", txt)
        if not m:
            continue
        mm, dd = m.groups()
        year = today.year
        # year rollover
        if int(mm) < today.month - 6:
            year += 1
        try:
            show_date = date(year, int(mm), int(dd))
        except ValueError:
            continue
        if not (today <= show_date <= cutoff):
            continue

        for card in cont.find_all("div", class_="scheduleCard"):
            h3 = card.find("h3", class_="scheduleCardHeading")
            if not h3:
                continue
            title = h3.get_text(strip=True)
            start_span = card.find("span", class_="startTime")
            if not start_span:
                continue
            showtime = start_span.get_text(strip=True)
            results.append({
                "cinema": CINEMA_NAME,
                "date_text": show_date.isoformat(),
                "screen": "",
                "title": title,
                "showtime": showtime,
            })

    # Deduplicate
    unique: List[Dict[str, str]] = []
    seen: set[tuple] = set()
    for row in results:
        key = (row["date_text"], row["title"], row["showtime"])
        if key not in seen:
            unique.append(row)
            seen.add(key)

    return unique

# ---------------------------------------------------------------------------
# CLI test harness
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print(f"Testing {CINEMA_NAME} scraper…")
    shows = scrape_k2_cinema()
    if not shows:
        print("No showings found — check warnings above.")
        sys.exit(0)
    shows.sort(key=lambda x: (x["date_text"], x["showtime"], x["title"]))
    print(f"Found {len(shows)} showings. First 10:\n")
    for s in shows[:10]:
        print(f"  {s['date_text']}  {s['showtime']}  {s['title']} | {s['screen']}")
