"""cinemart_shinjuku_module.py – scraper for Cinemart Shinjuku
Author: ChatGPT assistant (2025‑05‑27)

This module scrapes the schedule page of **シネマート新宿 (Cinemart Shinjuku)** on the COASYSTEMS ticketing site.  
It returns a list of dictionaries with the following keys:

```
{
    "cinema": str,       # always "シネマート新宿"
    "date_text": str,    # ISO date (YYYY‑MM‑DD)
    "screen": str,       # e.g. "スクリーン１"
    "title": str,        # Japanese title (title‑jp)
    "showtime": str      # HH:MM (24‑hour)
}
```

The HTML is **fully rendered server‑side** – no JavaScript execution is required.  
The page structure is almost identical to 新宿武蔵野館, so the parser largely mirrors that scraper.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from typing import List, Dict

import requests
from bs4 import BeautifulSoup, SoupStrainer

# ---------------------------------------------------------------------------
#  Config / constants
# ---------------------------------------------------------------------------
CINEMA_NAME_CM = "シネマート新宿"

# NB: the root URL *lacks* the brand prefix ("cm/") used in the PR sub‑domain.
CANDIDATE_URLS = [
    "https://cinemart.cineticket.jp/theater/shinjuku/schedule",          # primary
    "https://cinemart.cineticket.jp/cm/theater/shinjuku/schedule",       # historical pattern
    "https://cinemart.cineticket.jp/theater/shinjuku/early_schedule",    # early‑booking – sometimes the only page available
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

TIMEOUT = 15

# ---------------------------------------------------------------------------
#  Core scraping helpers
# ---------------------------------------------------------------------------

def _iso_date_from_id(id_text: str) -> str:
    """Convert id like 'dateJouei20250527' to '2025-05-27'."""
    m = re.match(r"dateJouei(\d{4})(\d{2})(\d{2})", id_text)
    if not m:
        raise ValueError(f"Unrecognised date id: {id_text}")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _collect_showings(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract showings from a parsed soup tree."""
    showings: List[Dict[str, str]] = []

    # Each date's schedules live inside div#dateJoueiYYYYMMDD (often with class 'hidden').
    for date_div in soup.find_all("div", id=re.compile(r"^dateJouei\d{8}")):
        date_text = _iso_date_from_id(date_div["id"])

        # Each movie panel contains title & one or more .movie-schedule blocks
        for panel in date_div.select("div.movie-panel"):
            title_tag = panel.select_one(".title-jp")
            if not title_tag:
                continue  # skip malformed panels
            title = title_tag.get_text(strip=True)

            # Gather all schedules within this movie panel
            for sched in panel.select("div.movie-schedule"):
                # Screen name (e.g. 'スクリーン１')
                screen_tag = sched.select_one(".screen-name")
                screen = screen_tag.get_text(strip=True) if screen_tag else ""

                # Showtime as displayed (\d{2}:\d{2})
                time_tag = sched.select_one(".movie-schedule-begin")
                if not time_tag:
                    continue
                showtime = time_tag.get_text(strip=True)

                showings.append({
                    "cinema": CINEMA_NAME_CM,
                    "date_text": date_text,
                    "screen": screen,
                    "title": title,
                    "showtime": showtime,
                })

    return showings

# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def fetch_showings() -> List[Dict[str, str]]:
    """Fetch the schedule page (trying fallbacks) and return parsed showings."""
    last_exc: Exception | None = None

    # Only parse nodes we need for speed.
    strainer = SoupStrainer(["div"], {"id": re.compile(r"^(dateJouei|schedule)")})

    for url in CANDIDATE_URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser", parse_only=strainer)
            return _collect_showings(soup)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"WARNING: Failed to fetch {url} → {exc}", file=sys.stderr)
            continue

    raise RuntimeError("All candidate URLs failed to fetch/parse") from last_exc

# ---------------------------------------------------------------------------
#  CLI test harness
# ---------------------------------------------------------------------------

def _main() -> None:
    print(f"Testing {CINEMA_NAME_CM} scraper …")
    try:
        data = fetch_showings()
        if not data:
            print("No showings found — check parser.")
        else:
            print(f"Found {len(data)} showtimes. Sample:")
            for row in data[:10]:
                print(row)
    except Exception as exc:  # noqa: BLE001
        print(f"Error ({CINEMA_NAME_CM}): {exc}")


if __name__ == "__main__":
    _main()
