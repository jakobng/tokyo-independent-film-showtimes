# theatreguild_daikanyama_module.py
"""
Scraper – Theatre Guild Daikanyama
Site   : https://theaterguild.co/movie/space/daikanyama/
Output : list[dict] → {cinema, date_text (YYYY-MM-DD), screen, title, showtime}
"""

from __future__ import annotations

import datetime as _dt
import logging as _log
import re as _re
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #

BASE_URL = "https://theaterguild.co/movie/space/daikanyama/"
CINEMA_NAME = "シアターギルド代官山"
DAYS_AHEAD = 7                        # how many days (including today) to keep
TIMEOUT = 15                          # seconds for requests.get

_log.basicConfig(
    level=_log.INFO,
    format="%(levelname)-7s: %(message)s",
)

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _fetch_html() -> str:
    """GET the full HTML of the schedule page."""
    _log.info("GET %s", BASE_URL)
    resp = requests.get(BASE_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _parse_schedule(html: str) -> List[Dict]:
    """Extract showings from the supplied HTML."""
    soup = BeautifulSoup(html, "html.parser")

    today = _dt.date.today()
    last_day = today + _dt.timedelta(days=DAYS_AHEAD - 1)

    date_pat = _re.compile(r"tab-(\d{8})")  # e.g. tab-20250528
    rows: List[Dict] = []

    # every 'schedule-panel' contains that day's <li> screenings
    for panel in soup.find_all("div", class_="schedule-panel"):
        class_str = " ".join(panel.get("class", []))
        m = date_pat.search(class_str)
        if not m:
            continue

        date_obj = _dt.datetime.strptime(m.group(1), "%Y%m%d").date()
        if not today <= date_obj <= last_day:
            continue  # keep only the desired window

        date_text = date_obj.isoformat()

        for li in panel.select("ul > li"):
            title_tag = li.select_one("div.title h4")
            time_tag = li.select_one("div.time b.starttime")
            if not (title_tag and time_tag):
                continue

            showtime = time_tag.get_text(strip=True)
            if showtime.startswith("00"):        # “Coming soon” placeholders
                continue

            rows.append(
                {
                    "cinema": CINEMA_NAME,
                    "date_text": date_text,
                    "screen": "",               # single-screen venue
                    "title": title_tag.get_text(strip=True),
                    "showtime": showtime,
                }
            )

    _log.info("Collected %d showings total.", len(rows))
    return rows


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #


def scrape_theatreguild_daikanyama(days: int = DAYS_AHEAD) -> List[Dict]:
    """
    Main entry point used by the master scraper.
    `days` can be overridden for a longer / shorter window if desired.
    """
    global DAYS_AHEAD
    DAYS_AHEAD = days
    html = _fetch_html()
    return _parse_schedule(html)


# --------------------------------------------------------------------------- #
# CLI test
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    data = scrape_theatreguild_daikanyama()
    for row in data:
        print(row)
