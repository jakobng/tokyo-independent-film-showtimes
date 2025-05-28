"""
waseda_shochiku_module.py — Waseda-Shochiku (English page) scraper
Site   : http://wasedashochiku.co.jp/english
Author : you :-)
Last   : 2025-05-28
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
from typing import Dict, List

import requests
from bs4 import BeautifulSoup, Tag

# ──────────────────────────── constants ──────────────────────────────────────
CINEMA_NAME = "早稲田松竹"
URL         = "http://wasedashochiku.co.jp/english"
HEADERS     = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")   # any “hh:mm”

# weekday abbreviations sometimes appear as “.sat .sun …”
_DOT_WEEK_RE = re.compile(r"\.\w{3}", re.I)

# ─────────────────────── helpers: date handling ─────────────────────────────
def _date_iter(start: _dt.date, end: _dt.date):
    d = start
    one = _dt.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def _parse_header_dates(text: str, year_hint: int) -> List[_dt.date]:
    """
    Converts table-header strings such as…

        5/24～5/29
        5/30
        6/21･23･25･27
        5/24.sat - 5/30.fri

    …into a list[date].
    """

    txt = _DOT_WEEK_RE.sub("", text).replace(" ", "")   # strip “.sat” etc.
    if "～" in txt or "-" in txt:
        sep = "～" if "～" in txt else "-"
        a, b = [p for p in txt.split(sep) if p]
        m1, d1 = map(int, a.split("/"))
        m2, d2 = map(int, b.split("/"))
        y1 = year_hint
        y2 = year_hint if (m2 > m1 or (m2 == m1 and d2 >= d1)) else year_hint + 1
        start = _dt.date(y1, m1, d1)
        end   = _dt.date(y2, m2, d2)
        return list(_date_iter(start, end))

    # patterns with “･” (Japanese middle dot) or a single day
    m, rest = txt.split("/", 1)
    m = int(m)
    days = [int(x) for x in rest.split("･")]
    return [_dt.date(year_hint, m, d) for d in days]


def _clean_times(cell: Tag) -> List[str]:
    """Return every hh:mm in the <td>, ignoring ‘～end’ times."""
    txt = cell.get_text(" ", strip=True)
    # keep only the part before an “～” dash if present
    if "～" in txt:
        txt = txt.split("～")[0]
    return _TIME_RE.findall(txt)

# ───────────────────────── main scraper ─────────────────────────────────────
def scrape_waseda_shochiku(max_days: int = 14) -> List[Dict[str, str]]:
    """
    Scrapes the English page and returns listings for the coming *max_days*
    (default 14).  Output rows:

        {
            "cinema":    "早稲田松竹",
            "date_text": "YYYY-MM-DD",
            "screen":    "",
            "title":     "Film title",
            "showtime":  "HH:MM",
        }
    """
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=25)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[{CINEMA_NAME}] fetch error: {exc}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.content, "html.parser")
    today  = _dt.date.today()
    window = today + _dt.timedelta(days=max_days)

    rows: List[Dict[str, str]] = []

    # each programme block lives in a <table class="top-schedule-area">
    for tbl in soup.select("table.top-schedule-area"):
        # header text → list[date]
        head = tbl.find("thead")
        if not head:
            continue
        header_text = head.get_text(" ", strip=True)
        dates = _parse_header_dates(header_text, today.year)

        # table rows
        for tr in tbl.select("tr.schedule-item"):
            title = tr.th.get_text(" ", strip=True) if tr.th else ""
            if not title:
                continue
            for td in tr.find_all("td"):
                for t in _clean_times(td):
                    for date_obj in dates:
                        if today <= date_obj <= window:
                            rows.append(
                                {
                                    "cinema": CINEMA_NAME,
                                    "date_text": date_obj.isoformat(),
                                    "screen": "",
                                    "title": title,
                                    "showtime": t,
                                }
                            )

    # de-duplicate
    unique = {(r["date_text"], r["title"], r["showtime"]): r for r in rows}
    return list(unique.values())


# ──────────────────────────── self-test ─────────────────────────────────────
if __name__ == "__main__":
    if sys.platform == "win32":
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    print(f"Testing {CINEMA_NAME} scraper …")
    data = scrape_waseda_shochiku()
    data.sort(key=lambda r: (r["date_text"], r["showtime"]))
    print(f"Found {len(data)} showings.\n")
    for r in data[:15]:
        print(f'{r["date_text"]}  {r["showtime"]}  {r["title"]}')
