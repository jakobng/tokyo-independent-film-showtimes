"""
nfaj_calendar_module.py — scraper for NFAJ Calendar (国立映画アーカイブ)
Last updated: 2025-05-28

Returns a list of dicts with keys:
    cinema, date_text (YYYY-MM-DD), screen, title, showtime

Designed to mirror the structure used by the other cinema modules so it can be
plugged straight into `main_scraper3.py`.
"""

from __future__ import annotations

import sys
import re
from datetime import date, datetime, timedelta
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config / constants
# ---------------------------------------------------------------------------

CINEMA_NAME = "国立映画アーカイブ"
URL = "https://www.nfaj.go.jp/calendar/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT = 20  # seconds for requests.get

__all__ = ["scrape_nfaj_calendar"]

# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def scrape_nfaj_calendar() -> List[Dict[str, str]]:
    """
    Scrape the monthly calendar for NFAJ.

    Returns:
        List of dict rows with keys: cinema, date_text (ISO YYYY-MM-DD), screen,
        title, showtime (HH:MM). Only includes events within the next 10 days.
    """
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Error ({CINEMA_NAME}): failed to fetch calendar page: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.content, "html.parser")
    calendar = soup.find("div", id="calendar_sp")
    if not calendar:
        print(f"Error ({CINEMA_NAME}): calendar container not found", file=sys.stderr)
        return []

    # Determine year/month from header
    year = datetime.today().year
    month = datetime.today().month
    header_h2 = calendar.find("h2")
    if header_h2:
        m = re.search(r"(\d{4})年\s*(\d{1,2})月", header_h2.get_text())
        if m:
            year = int(m.group(1))
            month = int(m.group(2))

    results: List[Dict[str, str]] = []
    # Each <details> groups several days
    for detail in calendar.find_all("details"):
        # For each direct child <div> (day block)
        for block in detail.find_all("div", recursive=False):
            day_div = block.find("div", class_="day")
            if not day_div:
                continue
            # Parse day number
            day_em = day_div.find("em")
            if not day_em:
                continue
            try:
                day_num = int(day_em.get_text())
                current = date(year, month, day_num)
            except ValueError:
                continue
            # Find each screening time in this block
            for time_tag in block.find_all("time"):  # <time datetime="HH:MM">HH:MM</time>
                showtime = time_tag.get_text(strip=True)
                # Program link follows time
                prog_anchor = time_tag.find_next_sibling("a")
                if not prog_anchor:
                    continue
                title = prog_anchor.get_text(strip=True)
                if not title or title == "/":
                    continue
                results.append({
                    "cinema": CINEMA_NAME,
                    "date_text": current.isoformat(),
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

    # Filter to next 10 days (including today)
    today = datetime.today().date()
    cutoff = today + timedelta(days=9)
    filtered = [
        row for row in unique
        if today <= datetime.fromisoformat(row["date_text"]).date() <= cutoff
    ]

    return filtered

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
    print(f"Testing {CINEMA_NAME} calendar scraper…")
    shows = scrape_nfaj_calendar()
    if not shows:
        print("No events found — check warnings above.")
        sys.exit(0)
    shows.sort(key=lambda x: (x["date_text"], x["showtime"], x["title"]))
    print(f"Found {len(shows)} events. First 10:\n")
    for ev in shows[:10]:
        print(f"  {ev['date_text']}  {ev['showtime']}  {ev['title']}")
