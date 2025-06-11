"""
waseda_shochiku_module.py — Waseda-Shochiku (English and Japanese pages) scraper
Site   : http://www.wasedashochiku.co.jp/english/ (English)
         http://www.wasedashochiku.co.jp/ (Japanese)
Author : you :-)
Last   : 2025-06-11
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
URL_EN      = "http://www.wasedashochiku.co.jp/english/"
URL_JA      = "http://www.wasedashochiku.co.jp/"
HEADERS     = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_DOT_WEEK_RE = re.compile(r"\.\w{3}", re.I)

# ─────────────────────── helpers: date handling ─────────────────────────────
def _date_iter(start: _dt.date, end: _dt.date):
    d = start
    one = _dt.timedelta(days=1)
    while d <= end:
        yield d
        d += one

def _parse_header_dates(text: str, year_hint: int) -> List[_dt.date]:
    txt = _DOT_WEEK_RE.sub("", text).replace(" ", "")
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

    dates = []
    current_month = -1
    parts = txt.split("･")
    for part in parts:
        if "/" in part:
            m_str, d_str = part.split("/")
            current_month = int(m_str)
            day = int(d_str)
        else:
            if not part: continue
            day = int(part)

        if current_month != -1:
            dates.append(_dt.date(year_hint, current_month, day))
    return dates

def _clean_times(cell: Tag) -> List[str]:
    txt = cell.get_text(" ", strip=True)
    if "～" in txt:
        txt = txt.split("～")[0]
    return _TIME_RE.findall(txt)

# ───────────────────────── main scraper ─────────────────────────────────────
def scrape_waseda_shochiku(max_days: int = 14) -> List[Dict[str, str]]:
    """
    Scrapes the English and Japanese pages and returns listings for the coming *max_days*.
    """
    soup_en, soup_ja = None, None

    try:
        resp_en = requests.get(URL_EN, headers=HEADERS, timeout=25)
        resp_en.raise_for_status()
        soup_en = BeautifulSoup(resp_en.content, "html.parser")
    except Exception as exc:
        print(f"[{CINEMA_NAME}] English page fetch error: {exc}", file=sys.stderr)
        return []

    try:
        resp_ja = requests.get(URL_JA, headers=HEADERS, timeout=25)
        resp_ja.raise_for_status()
        soup_ja = BeautifulSoup(resp_ja.content, "html.parser")
    except Exception as exc:
        print(f"[{CINEMA_NAME}] Japanese page fetch error: {exc}", file=sys.stderr)
        pass

    today  = _dt.date.today()
    window = today + _dt.timedelta(days=max_days)
    rows: List[Dict[str, str]] = []

    tables_en = soup_en.select("table.top-schedule-area")
    tables_ja = soup_ja.select("table.top-schedule-area") if soup_ja else [None] * len(tables_en)

    if soup_ja and len(tables_en) != len(tables_ja):
        print(f"[{CINEMA_NAME}] Warning: Mismatch in number of schedule tables between English ({len(tables_en)}) and Japanese ({len(tables_ja)}) pages.", file=sys.stderr)
        if len(tables_en) > len(tables_ja):
            tables_ja.extend([None] * (len(tables_en) - len(tables_ja)))

    for tbl_idx, tbl_en in enumerate(tables_en):
        tbl_ja = tables_ja[tbl_idx] if tbl_idx < len(tables_ja) else None
        head_en = tbl_en.find("thead")
        if not head_en: continue
        header_text_en = head_en.get_text(" ", strip=True)
        dates = _parse_header_dates(header_text_en, today.year)
        if not dates: continue

        trs_en = tbl_en.select("tr.schedule-item")
        trs_ja = tbl_ja.select("tr.schedule-item") if tbl_ja else [None] * len(trs_en)

        if tbl_ja and len(trs_en) != len(trs_ja):
            print(f"[{CINEMA_NAME}] Warning: Mismatch in film rows for table {tbl_idx+1} ('{header_text_en}'). EN: {len(trs_en)}, JA: {len(trs_ja)}.", file=sys.stderr)
            if len(trs_en) > len(trs_ja):
                trs_ja.extend([None] * (len(trs_en) - len(trs_ja)))

        for tr_idx, tr_en in enumerate(trs_en):
            title_en_tag = tr_en.th
            title_en = title_en_tag.get_text(" ", strip=True) if title_en_tag else ""
            if not title_en: continue

            title_ja = ""
            if tr_idx < len(trs_ja):
                tr_ja_current = trs_ja[tr_idx]
                if tr_ja_current and tr_ja_current.th:
                    title_ja = tr_ja_current.th.get_text(" ", strip=True)

            tds_en = tr_en.find_all("td")
            if not tds_en: continue

            for td_en in tds_en:
                for t in _clean_times(td_en):
                    for date_obj in dates:
                        if today <= date_obj <= window:
                            primary_title = title_en if title_en else title_ja
                            rows.append({
                                "cinema": CINEMA_NAME,
                                "title": primary_title,
                                "date_text": date_obj.isoformat(),
                                "screen": "",
                                "title_en": title_en,
                                "title_ja": title_ja,
                                "showtime": t,
                            })

    unique = {(r["date_text"], r["title"], r["showtime"]): r for r in rows}
    return list(unique.values())

# ──────────────────────────── self-test ─────────────────────────────────────
if __name__ == "__main__":
    if sys.platform == "win32":
        for s in (sys.stdout, sys.stderr):
            try: s.reconfigure(encoding="utf-8", errors="replace")
            except Exception: pass

    print(f"Testing {CINEMA_NAME} scraper …")
    data = scrape_waseda_shochiku(max_days=21)
    data.sort(key=lambda r: (r["date_text"], r["showtime"], r["title_en"]))
    print(f"Found {len(data)} showings.\n")
    print(f"{'Date':<12} {'Time':<7} {'Primary Title':<40} {'English Title':<40} {'Japanese Title'}")
    print(f"{'-'*12} {'-'*7} {'-'*40} {'-'*40} {'-'*40}")
    for r in data[:25]:
        print(f'{r["date_text"]}  {r["showtime"]}  {r.get("title", "N/A"):<40} {r.get("title_en", "N/A"):<40} {r.get("title_ja", "N/A")}')