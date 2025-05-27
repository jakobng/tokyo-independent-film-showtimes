'''cinema_qualite_module.py
Scraper for 新宿シネマカリテ (Cinema Qualité).

The schedule page delivers *all* dates' markup in the initial HTML as hidden
`<div id="dateJoueiYYYYMMDD">` blocks. Therefore we can scrape it with a
simple `requests + BeautifulSoup` pipeline – no Selenium required.

Returned rows follow the same dict schema used by the other modules:
    {
        'cinema':   '新宿シネマカリテ',
        'date_text': 'YYYY-MM-DD',
        'screen':   'スクリーン１',
        'title':    '映画タイトル',
        'showtime': 'HH:MM',
    }

Usage (stand‑alone test):
    python cinema_qualite_module.py
'''

from __future__ import annotations

import re
import datetime as _dt
from typing import List, Dict, Set, Tuple

import requests
from bs4 import BeautifulSoup

__all__ = [
    'scrape_cinema_qualite',
]

URL = "https://musashino.cineticket.jp/cq/theater/qualite/schedule"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; CinemaQualiteBot/1.0; +https://github.com/example)'
}
CINEMA_NAME = '新宿シネマカリテ'

_DATE_ID_RE = re.compile(r'^dateJouei(\d{8})$')
_MONTH_DAY_RE = re.compile(r'(\d{2})月(\d{2})日')  # e.g. 05月28日

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_html() -> str:
    """GET the schedule page HTML (raises for HTTP errors)."""
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def _parse_showings(html: str, max_days: int | None = None) -> List[Dict[str, str]]:
    """Parse showings from HTML.

    Args:
        html: Raw HTML from `_fetch_html()`.
        max_days: Optionally limit to *today + max_days* (helps the master
            scraper keep a 7‑day window).
    Returns:
        List of dict rows (deduped).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Collect divs that match id="dateJoueiYYYYMMDD"
    date_divs = [d for d in soup.find_all(id=_DATE_ID_RE)]
    rows: List[Dict[str, str]] = []
    seen: Set[Tuple[str, str, str, str]] = set()

    today = _dt.date.today()

    for div in date_divs:
        m = _DATE_ID_RE.match(div["id"])
        if not m:
            continue
        date_str = m.group(1)  # YYYYMMDD
        try:
            date_obj = _dt.datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            continue

        # Respect max_days window
        if max_days is not None and (date_obj - today).days > max_days:
            continue

        date_text = date_obj.isoformat()

        # Each movie block is a panel with class 'movie-panel'
        for panel in div.select("div.movie-panel"):
            # Japanese + English title live inside the header
            header = panel.select_one("div.panel-heading")
            if not header:
                continue
            # There are separate divs inside, but safest is to grab the Japanese
            # title <div class="title-jp">.
            title_jp_tag = header.select_one("div.title-jp")
            title_en_tag = header.select_one("div.title-eng")
            title_jp = (title_jp_tag.get_text(strip=True) if title_jp_tag else "").strip()
            title_en = (title_en_tag.get_text(strip=True) if title_en_tag else "").strip()
            title = title_jp if title_jp else title_en  # favour JP, fallback EN
            if not title:
                continue

            # "スクリーン１" etc. appear in each schedule time block and can vary
            # across showings of the same film, so we read them per‑showtime.
            for sched in panel.select("div.movie-schedule"):
                start_attr = sched.get("data-start")  # "1120" etc.
                if not start_attr or not start_attr.isdigit():
                    continue
                showtime = f"{start_attr[:2]}:{start_attr[2:]}"

                screen_no = sched.get("data-screen") or ""
                screen_name = f"スクリーン{screen_no}" if screen_no else "スクリーン?"

                key = (date_text, title, showtime, screen_name)
                if key in seen:
                    continue  # de‑duplicate
                seen.add(key)

                rows.append({
                    "cinema": CINEMA_NAME,
                    "date_text": date_text,
                    "screen": screen_name,
                    "title": title,
                    "showtime": showtime,
                })

    return rows

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape_cinema_qualite(max_days: int = 7) -> List[Dict[str, str]]:
    """Scrape showtimes for Cinema Qualité.

    Parameters
    ----------
    max_days : int, default 7
        Only include dates up to *today + max_days*.

    Returns
    -------
    list of dict
    """
    html = _fetch_html()
    return _parse_showings(html, max_days=max_days)


# ---------------------------------------------------------------------------
# Self‑test / demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("INFO: Running Cinema Qualité scraper standalone …", end="\n\n")
    try:
        showings = scrape_cinema_qualite()
    except Exception as exc:
        print("ERROR:", exc)
        raise

    print(f"Collected {len(showings)} showings from {CINEMA_NAME}.")
    for row in showings[:10]:
        print(row)
