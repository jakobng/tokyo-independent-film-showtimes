"""
musashino_kan_module.py — scraper for Shinjuku Musashino‑kan
Last updated: 2025‑05‑27

Returns a list of dicts with keys:
    cinema, date_text (YYYY‑MM‑DD), screen, title, showtime (HH:MM‑HH:MM)

Designed to mirror the structure used by the other cinema modules so it can be
plugged straight into `main_scraper2.py`.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
#  Config / constants
# ---------------------------------------------------------------------------

CINEMA_NAME = "新宿武蔵野館"

# Some installs block one variant of the URL (returning 404), so we try both.
URL_CANDIDATES: list[str] = [
    # Primary ticket engine domain (works without cookies)
    "https://musashino.cineticket.jp/mk/theater/shinjuku/schedule",
    "https://musashino.cineticket.jp/mk/theater/shinjuku/schedule/",  # trailing slash
    # Legacy PR sub‑domain. Some regions may still resolve this one.
    "https://shinjuku.musashino-k.jp/mk/theater/shinjuku/schedule",
    "https://shinjuku.musashino-k.jp/mk/theater/shinjuku/schedule/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
#  Helper utilities
# ---------------------------------------------------------------------------

def _clean(element) -> str:
    """Collapse whitespace inside an element to a single space."""
    if element is None:
        return ""
    text = element.get_text(" ", strip=True) if hasattr(element, "get_text") else str(element)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_first_ok(urls: List[str]) -> requests.Response | None:
    """Return the first successfully fetched response or None."""
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp
        except requests.exceptions.RequestException:
            continue
    return None

# ---------------------------------------------------------------------------
#  Core scraper
# ---------------------------------------------------------------------------

def scrape_musashino_kan() -> List[Dict[str, str]]:
    """Download and parse the schedule page."""

    response = _fetch_first_ok(URL_CANDIDATES)
    if response is None:
        print(f"Error ({CINEMA_NAME}): all candidate URLs failed.", file=sys.stderr)
        return []

    soup = BeautifulSoup(response.content, "html.parser")

    results: List[Dict[str, str]] = []

    # Each date section has id="dateJoueiYYYYMMDD".
    for block in soup.find_all("div", id=re.compile(r"^dateJouei(\d{8})$")):
        m = re.match(r"dateJouei(\d{8})", block["id"])
        if not m:
            continue
        try:
            date_iso = datetime.strptime(m.group(1), "%Y%m%d").date().isoformat()
        except ValueError:
            date_iso = m.group(1)

        # A movie panel lists one film, potentially with several showtime rows.
        for panel in block.find_all("div", class_="movie-panel"):
            title_jp = _clean(panel.find("div", class_="title-jp"))
            if not title_jp:
                continue  # skip banners or malformed blocks

            schedule_rows = panel.find_all("div", class_="movie-schedule")
            for sched in schedule_rows:
                # Screen name
                screen = _clean(sched.find("span", class_="screen-name")) or "スクリーン?"

                # Times
                beg = _clean(sched.find("span", class_="movie-schedule-begin"))
                end = _clean(sched.find("span", class_="movie-schedule-end"))

                if not beg:
                    # Fallback to data-start attribute like "1215".
                    raw = sched.get("data-start", "")
                    if re.match(r"^\d{3,4}$", raw):
                        beg = f"{int(raw)//100:02d}:{int(raw)%100:02d}"

                showtime = f"{beg}-{end}" if beg and end else beg or "?"

                results.append(
                    {
                        "cinema": CINEMA_NAME,
                        "date_text": date_iso,
                        "screen": screen,
                        "title": title_jp,
                        "showtime": showtime,
                    }
                )

    # De‑duplicate using (date,title,showtime) key.
    unique: List[Dict[str, str]] = []
    seen: set[tuple] = set()
    for row in results:
        key = (row["date_text"], row["title"], row["showtime"])
        if key not in seen:
            unique.append(row)
            seen.add(key)

    return unique

# ---------------------------------------------------------------------------
#  CLI test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print(f"Testing {CINEMA_NAME} scraper…")
    shows = scrape_musashino_kan()
    if not shows:
        print("No showings found — check warnings above.")
        sys.exit(0)

    shows.sort(key=lambda x: (x["date_text"], x["title"], x["showtime"]))
    print(f"Found {len(shows)} showings. First 10:\n")
    for s in shows[:10]:
        print(f"  {s['date_text']}  {s['showtime']}  {s['title']} | {s['screen']}")
