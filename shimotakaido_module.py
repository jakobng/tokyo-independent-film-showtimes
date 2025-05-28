"""
shimotakaido_module.py — scraper for Shimotakaido Cinema (下高井戸シネマ)
Last updated: 2025-05-28

Returns a list of dicts with keys:
    cinema, date_text (YYYY-MM-DD), screen, title, showtime

Designed to mirror the structure used by the other cinema modules so it can be
plugged straight into `main_scraper3.py`.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config / constants
# ---------------------------------------------------------------------------

CINEMA_NAME = "下高井戸シネマ"
URL = "http://shimotakaidocinema.com/schedule/schedule.html"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT = 20  # seconds for requests.get

__all__ = ["scrape_shimotakaido"]

# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def scrape_shimotakaido() -> List[Dict[str, str]]:
    """
    Scrape the weekly schedule for Shimotakaido Cinema.

    Returns:
        List of dict rows with keys: cinema, date_text (ISO YYYY-MM-DD), screen,
        title, showtime (HH:MM). Only includes showings within the next 10 days.
    """
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Error ({CINEMA_NAME}): failed to fetch schedule page: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.content, "html.parser")
    table = soup.find("table", class_="sche-table")
    if not table:
        print(f"Error ({CINEMA_NAME}): schedule table not found", file=sys.stderr)
        return []

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    if not rows or len(rows) < 2:
        print(f"Error ({CINEMA_NAME}): unexpected table structure", file=sys.stderr)
        return []

    # Determine year from page title
    year = None
    title_span = soup.find("span", class_="sche-title")
    if title_span:
        m_year = re.search(r"(\d{4})年", title_span.get_text())
        if m_year:
            year = int(m_year.group(1))
    if year is None:
        year = datetime.today().year

    # Parse header row for date ranges
    header_cells = rows[0].find_all("td", class_="sche-td-2")
    date_ranges: List[tuple[datetime.date, datetime.date]] = []
    for cell in header_cells:
        text = cell.get_text(strip=True)
        m = re.search(r"(\d{1,2})/(\d{1,2})[（(].*?[-–]\s*(\d{1,2})/(\d{1,2})", text)
        if not m:
            continue
        m1, d1, m2, d2 = m.groups()
        start = datetime(year, int(m1), int(d1)).date()
        end_year = year if int(m2) >= int(m1) else year + 1
        end = datetime(end_year, int(m2), int(d2)).date()
        date_ranges.append((start, end))

    results: List[Dict[str, str]] = []
    # Iterate each showtime row
    for tr in rows[1:]:
        cells = tr.find_all("td", class_="sche-td")
        if not cells:
            continue
        # For each date-range, cell pair
        for (start, end), cell in zip(date_ranges, cells):
            a = cell.find("a")
            if not a:
                continue
            text = a.get_text(separator=" ", strip=True)
            tm = re.search(r"(\d{1,2}:\d{2})", text)
            if not tm:
                continue
            showtime = tm.group(1)
            title = text[:tm.start()].strip()
            if not title or title == "/":
                continue
            # Expand over each date in range
            current = start
            while current <= end:
                results.append({
                    "cinema": CINEMA_NAME,
                    "date_text": current.isoformat(),
                    "screen": "",
                    "title": title,
                    "showtime": showtime,
                })
                current += timedelta(days=1)

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
    filtered: List[Dict[str, str]] = [
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
    print(f"Testing {CINEMA_NAME} scraper…")
    shows = scrape_shimotakaido()
    if not shows:
        print("No showings found — check warnings above.")
        sys.exit(0)
    shows.sort(key=lambda x: (x["date_text"], x["showtime"], x["title"]))
    print(f"Found {len(shows)} showings. First 10:\n")
    for s in shows[:10]:
        print(f"  {s['date_text']}  {s['showtime']}  {s['title']} | {s['screen']}")
