#!/usr/bin/env python3
# eurospace_module.py — Rev-11 (2025-06-25)
#
#  • FINAL: Complete rewrite of the _scrape_detail function for robust,
#    intelligent parsing.
#  • It no longer assumes a fixed order for metadata. Instead, it inspects
#    each piece of data to identify if it is a year, runtime, or country.
#  • This fixes swapped/incorrect data for all previously failing films.
# ---------------------------------------------------------------------

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

import bs4
import requests

BASE_URL = "http://www.eurospace.co.jp"
SCHEDULE_URL = f"{BASE_URL}/schedule/"
OUTPUT = Path(__file__).with_name("eurospace_showtimes.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (EurospaceScraper/2025)"}
TIMEOUT = 30

TODAY = dt.date.today()
WINDOW_DAYS = 7

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_SUB_TITLE_RE = re.compile(r"『(.+?)』")
_RUNTIME_RE = re.compile(r"(\d+)\s*分")
# More flexible year regex that doesn't require '年'
_YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b')


def _clean(text: str) -> str:
    """Collapse whitespace, trim, and normalize characters."""
    if not text:
        return ""
    normalized_text = unicodedata.normalize("NFKC", text).strip()
    return re.sub(r"\s+", " ", normalized_text)


def _parse_date(h3_tag: bs4.Tag) -> dt.date | None:
    m = DATE_RE.search(h3_tag.get_text())
    if not m:
        return None
    y, mth, d = map(int, m.groups())
    return dt.date(y, mth, d)


def _scrape_detail(url: str) -> Dict[str, str | int | None]:
    """
    Pull director, runtime, country, and year by intelligently parsing the
    structured <p class="work-caption"> tag on the detail page.
    """
    defaults = {"director": None, "runtime": None, "country": None, "year": None}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        resp.encoding = 'utf-8' # Ensure correct encoding
    except Exception:
        return defaults

    soup = bs4.BeautifulSoup(resp.text, "html.parser")
    caption_p = soup.select_one("p.work-caption")
    if not caption_p:
        return defaults

    lines = [line.strip() for line in caption_p.get_text(separator="\n").split("\n") if line.strip()]

    meta = defaults.copy()
    
    # Find and parse the slash-delimited line for most metadata
    for line in lines:
        if "／" in line:
            parts = [p.strip() for p in line.split("／")]
            
            # Intelligently identify each part instead of assuming order
            countries = []
            for part in parts:
                runtime_match = _RUNTIME_RE.search(part)
                year_match = _YEAR_RE.search(part)

                if runtime_match:
                    meta["runtime"] = int(runtime_match.group(1))
                elif year_match:
                    meta["year"] = year_match.group(0)
                else:
                    # If it's not a year or runtime, assume it's a country.
                    # Filter out common non-country noise.
                    if not any(noise in part for noise in ["日本語", "カラー", "DCP", "分", "年"]):
                        cleaned_part = _clean(part)
                        if cleaned_part:
                             countries.append(cleaned_part)
            
            if countries:
                meta["country"] = ", ".join(countries)
            break
            
    # Find the director on its own specific line
    for line in lines:
        if line.startswith("監督"):
            director_text = line.split("：", 1)[-1]
            meta["director"] = _clean(director_text.split("/")[0].split("、")[0])
            break

    return meta


# ---------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------

def scrape() -> List[Dict[str, str | int | None]]:
    try:
        resp = requests.get(SCHEDULE_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
    except Exception as e:
        sys.exit(f"Failed to GET schedule page: {e}")

    soup = bs4.BeautifulSoup(resp.text, "html.parser")
    schedule_sec = soup.find("section", id="schedule")
    if not schedule_sec:
        sys.exit("Schedule section not found in HTML")

    shows: List[Dict[str, str | int | None]] = []
    meta_cache: Dict[str, Dict[str, str | int | None]] = {}

    for art in schedule_sec.find_all("article"):
        h3 = art.find("h3")
        if not h3: continue
        d = _parse_date(h3)
        if not d or not (TODAY <= d < TODAY + dt.timedelta(days=WINDOW_DAYS)):
            continue

        for table in art.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2: continue
            
            times_row, titles_row = rows[0], rows[1]
            times = [_clean(td.get_text()) for td in times_row.find_all("td")]
            cells = titles_row.find_all("td")
            
            for idx, cell in enumerate(cells):
                a_tag = cell.find("a")
                if not a_tag: continue

                cell_text = cell.get_text(separator=" ")
                sub_title_match = _SUB_TITLE_RE.search(cell_text)

                title = _clean(sub_title_match.group(1)) if sub_title_match else _clean(a_tag.get_text())
                
                url = urljoin(BASE_URL, a_tag.get("href", ""))
                time_str = times[idx] if idx < len(times) else ""
                if not title or not url or not time_str: continue

                if url not in meta_cache:
                    meta_cache[url] = _scrape_detail(url)

                shows.append({
                    "cinema": "ユーロスペース",
                    "title": title,
                    "date": d.isoformat(),
                    "time": time_str,
                    "url": url,
                    **meta_cache[url],
                })

    seen = set()
    uniq_shows = []
    for s in shows:
        key = (s["title"], s["date"], s["time"])
        if key not in seen:
            seen.add(key)
            uniq_shows.append(s)

    return sorted(uniq_shows, key=lambda x: (x.get("date", ""), x.get("time", ""), x.get("title", "")))


# ---------------------------------------------------------------------
# CLI entry‑point
# ---------------------------------------------------------------------

if __name__ == "__main__":
    data = scrape()
    text = json.dumps(data, ensure_ascii=False, indent=2)
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"Wrote {len(data)} showtime records → {OUTPUT}")