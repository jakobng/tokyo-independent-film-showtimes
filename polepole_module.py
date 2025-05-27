"""polepole_module.py — scraper for ポレポレ東中野 (Pole‑Pole Higashi‑Nakano)

Scrapes the daily timetable without Selenium and returns **only the showings
from today through the next 6 days** (a 7‑day rolling window). Strategy:
  1. Parse the fully server‑rendered Jorudan schedule.
  2. If that yields zero rows, fall back to the eiga.com page.

Each returned dict has the canonical keys used by your other scrapers:
    cinema     – ポレポレ東中野
    date_text  – ISO date (YYYY‑MM‑DD)
    screen     – "Screen 1" (single‑screen)
    title      – Japanese title
    showtime   – HH:MM 24‑hour string

Dependencies: `requests`, `beautifulsoup4`.
"""

from __future__ import annotations

import datetime as dt
import itertools
import re
import sys
from typing import List, Dict, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup, Tag

__all__ = ["scrape_polepole"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CINEMA_NAME = "ポレポレ東中野"
SCREEN_NAME = "Screen 1"
JORUDAN_URL = "https://movie.jorudan.co.jp/theater/1000506/schedule/"
EIGA_URL = "https://eiga.com/theater/13/130612/3292/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}

TODAY: dt.date = dt.date.today()
WINDOW_END: dt.date = TODAY + dt.timedelta(days=6)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_DATE_PAT = re.compile(r"(?<![\d])(?P<m>\d{1,2})/(?:|0)(?P<d>\d{1,2})|(?P<m2>\d{1,2})月(?P<d2>\d{1,2})日")
_TIME_PAT = re.compile(r"\b\d{1,2}:\d{2}\b")


def _iso_date(month: int, day: int, *, ref: dt.date | None = None) -> str:
    """Convert M/D near *ref* (today) to an ISO YYYY‑MM‑DD string."""
    base = ref or TODAY
    year = base.year
    # Handle year rollover (Dec shown in Jan, Jan shown in Dec)
    if month == 12 and base.month == 1:
        year -= 1
    elif month == 1 and base.month == 12:
        year += 1
    return dt.date(year, month, day).isoformat()


def _clean(txt: str | Tag | None) -> str:
    if txt is None:
        return ""
    if isinstance(txt, Tag):
        txt = txt.get_text(" ")
    return re.sub(r"\s+", " ", txt).strip()


def _fetch(url: str) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.content, "html.parser")
    except requests.RequestException as exc:
        print(f"[polepole] fetch error {url}: {exc}", file=sys.stderr)
        return None

# ---------------------------------------------------------------------------
# Jorudan parser (primary)
# ---------------------------------------------------------------------------

def _parse_jorudan(soup: BeautifulSoup) -> List[Dict]:
    rows: List[Dict] = []

    for h2 in soup.find_all("h2"):
        title = _clean(h2)
        if not title or "ページをシェア" in title or "ランキング" in title:
            continue

        # Collect text until next <h2>
        parts: List[str] = []
        for sib in itertools.takewhile(lambda n: not (isinstance(n, Tag) and n.name == "h2"), h2.find_all_next(string=False, limit=60)):
            parts.append(_clean(sib))
        blob = " ".join(parts)
        if not blob:
            continue

        date_matches = list(_DATE_PAT.finditer(blob))
        if not date_matches:
            continue
        dates_iso = [_iso_date(int(m.group("m") or m.group("m2") or 0),
                               int(m.group("d") or m.group("d2") or 0))
                     for m in date_matches]
        times = _TIME_PAT.findall(blob)
        if not times:
            continue

        per_day = max(1, len(times) // len(dates_iso))
        matrix = [times[i:i+per_day] for i in range(0, len(times), per_day)]
        for iso, tlist in zip(dates_iso, matrix):
            for t in tlist:
                rows.append({
                    "cinema": CINEMA_NAME,
                    "date_text": iso,
                    "screen": SCREEN_NAME,
                    "title": title,
                    "showtime": t,
                })
    return rows

# ---------------------------------------------------------------------------
# eiga.com fallback
# ---------------------------------------------------------------------------

def _parse_eiga(soup: BeautifulSoup) -> List[Dict]:
    rows: List[Dict] = []
    for h2 in soup.find_all("h2"):
        link = h2.find("a")
        if not link or "/movie" not in (link.get("href") or ""):
            continue
        title = _clean(link)
        node: Optional[Tag] = h2
        while node and (node := node.find_next_sibling()):
            if isinstance(node, Tag) and node.name == "h2":
                break
            blob = _clean(node)
            if not blob:
                continue
            for dm in _DATE_PAT.finditer(blob):
                month = int(dm.group("m") or dm.group("m2"))
                day = int(dm.group("d") or dm.group("d2"))
                iso = _iso_date(month, day)
                for t in _TIME_PAT.findall(blob):
                    rows.append({
                        "cinema": CINEMA_NAME,
                        "date_text": iso,
                        "screen": SCREEN_NAME,
                        "title": title,
                        "showtime": t,
                    })
    return rows

# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------

def _within_window(iso: str) -> bool:
    d = dt.date.fromisoformat(iso)
    return TODAY <= d <= WINDOW_END


def _deduplicate(items: List[Dict]) -> List[Dict]:
    seen: Set[Tuple[str, str, str, str]] = set()
    out: List[Dict] = []
    for row in items:
        key = (row["date_text"], row["showtime"], row["title"], row["screen"])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape_polepole() -> List[Dict]:
    """Return showings for the next 7 days (inclusive)."""
    soup = _fetch(JORUDAN_URL)
    rows = _parse_jorudan(soup) if soup else []

    if not rows:
        soup = _fetch(EIGA_URL)
        rows = _parse_eiga(soup) if soup else []

    # Keep only rows in the 7‑day window and deduplicate
    rows = [r for r in rows if _within_window(r["date_text"])]
    rows = _deduplicate(rows)

    rows.sort(key=lambda r: (r["date_text"], r["showtime"], r["title"]))
    print(f"[polepole] Collected {len(rows)} showings (next 7 days).")
    return rows

# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json, argparse
    parser = argparse.ArgumentParser(description="Scrape Pole‑Pole Higashi‑Nakano showtimes (7‑day window)")
    parser.add_argument("--json", action="store_true", help="print rows as JSON")
    args = parser.parse_args()
    data = scrape_polepole()
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    else:
        from pprint import pprint
        pprint(data)
