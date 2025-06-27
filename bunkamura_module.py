# -*- coding: utf-8 -*-
"""
bunkamura_module.py — scraper for **Bunkamura ル・シネマ 渋谷宮下**

This version adds **richer metadata parsing** (director, year, country, runtime)
so the output JSON matches the other scrapers in your project.

Strategy
--------
1. Use the public JSON feed for the daily schedule as before.
2. For every film, hit the lineup detail page **once** and extract metadata
   from the structured <dl class="information"> table. This is more
   reliable than previous methods.
3. The movie title is cleaned to remove suffixes like "4Kレストア".
4. `scrape_bunkamura(days_ahead=7)` returns a list of dictionaries that
   downstream code can ingest unchanged.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
#  Config
# ---------------------------------------------------------------------------

BASE           = "https://www.bunkamura.co.jp"
CINEMA_NAME    = "Bunkamura ル・シネマ 渋谷宮下"
JSON_FEED      = f"{BASE}/data/json/pickup/movie.json"
HEADERS        = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT        = 20

# regex helpers -------------------------------------------------------------
_TIME_RE       = re.compile(r"(\d{1,2}:\d{2})")
_YEAR_RE       = re.compile(r"(19\d{2}|20\d{2})")
_RUNTIME_RE    = re.compile(r"(\d+)\s*分")

# ---------------------------------------------------------------------------
#  HTTP helpers
# ---------------------------------------------------------------------------

def _fetch(url: str, *, binary: bool = False) -> str | bytes:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.content if binary else resp.text


def _soup(html: str | bytes) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")

# ---------------------------------------------------------------------------
#  Detail‑page scraping (rich metadata)
# ---------------------------------------------------------------------------

def _parse_detail_page(url: str) -> Dict[str, str]:
    """
    Return dict with director / year / country / runtime / synopsis by
    parsing the structured <dl class="information"> list on the detail page.
    This version also cleans the movie title.
    """
    out = {
        "director": "",
        "year": "",
        "country": "",
        "runtime_min": "",
        "synopsis": "",
        "movie_title": "",
        "movie_title_en": "",
        "detail_page_url": url,
    }
    try:
        soup = _soup(_fetch(url))
    except Exception as exc:
        print(f"WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
        return out

    # --- Title Extraction and Cleaning ---
    if title_tag := soup.select_one("h2 > span.ttl"):
        # Clean title by splitting on the full-width space to remove "4K" etc.
        out["movie_title"] = title_tag.get_text(" ", strip=True).split('　')[0]

    if en_title_tag := soup.select_one("h2 > span.en"):
        out["movie_title_en"] = en_title_tag.get_text(" ", strip=True)

    # --- Information DL Parsing ---
    if info_dl := soup.select_one("dl.information"):
        # Create a dictionary of all DT:DD pairs for easy lookup
        labels = [dt.get_text(" ", strip=True) for dt in info_dl.select("dt")]
        values = [dd.get_text(" ", strip=True) for dd in info_dl.select("dd")]
        info_dict = dict(zip(labels, values))

        # --- Director ---
        out["director"] = info_dict.get("監督", "").strip()

        # --- "作品情報" (Work Info) Parsing ---
        if work_info := info_dict.get("作品情報"):
            # Example: "2001年／イギリス、アメリカ／97分／PG12"
            parts = work_info.split('／')
            if len(parts) >= 3:
                # Year (from first part)
                if m := _YEAR_RE.search(parts[0]):
                    out["year"] = m.group(1)
                # Country (from second part)
                out["country"] = parts[1].strip()
                # Runtime (from third part)
                if m := _RUNTIME_RE.search(parts[2]):
                    out["runtime_min"] = m.group(1)

    # --- Synopsis ---
    # Targets the first paragraph in the main text block
    if syn_p := soup.select_one("div.text > p:first-of-type"):
        out["synopsis"] = syn_p.get_text("\n", strip=True)

    return out

# ---------------------------------------------------------------------------
#  Timetable snippet helper
# ---------------------------------------------------------------------------

def _grab_times(snippet_rel: str) -> List[str]:
    if not snippet_rel:
        return []
    url = urljoin(BASE, snippet_rel)
    try:
        html = _fetch(url)
    except requests.HTTPError as exc:
        if exc.response.status_code == 404:
            return []  # snippet not yet published
        raise
    return _TIME_RE.findall(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))

# ---------------------------------------------------------------------------
#  Main scraper
# ---------------------------------------------------------------------------

def scrape_bunkamura(days_ahead: int = 7) -> List[Dict[str, str]]:
    feed = json.loads(_fetch(JSON_FEED))
    today = date.today()
    wanted = {(today + timedelta(days=i)).isoformat() for i in range(days_ahead)}

    rows: List[Dict[str, str]] = []
    detail_cache: Dict[str, Dict[str, str]] = {}
    times_cache: Dict[str, List[str]] = {}

    for item in feed:
        if item.get("hall") != "cinema":
            continue

        dates = item.get("date_all", "").split(", ") if item.get("date_all") else []
        active = [d for d in dates if d in wanted]
        if not active:
            continue

        snippet_rel = item.get("time_todays", "")
        if snippet_rel not in times_cache:
            times_cache[snippet_rel] = _grab_times(snippet_rel)
        times = times_cache[snippet_rel]
        if not times:
            continue

        lineup_url = urljoin(BASE, item.get("url", ""))
        if lineup_url not in detail_cache:
            detail_cache[lineup_url] = _parse_detail_page(lineup_url)
        meta = detail_cache[lineup_url]

        # Use the cleaned title from the detail page instead of the feed title
        # This handles cases where the feed has "Movie A / Movie B"
        if meta.get("movie_title"):
            item["title"] = meta["movie_title"]
        if meta.get("movie_title_en"):
            item["title_en"] = meta["movie_title_en"]


        for ymd in active:
            for t in times:
                # Assemble the record, now using the cleaned data from `meta`
                record = {
                    "cinema_name":    CINEMA_NAME,
                    "movie_title":    item["title"],
                    "movie_title_en": item.get("title_en", ""),
                    "date_text":      ymd,
                    "showtime":       t,
                    "hall":           item.get("hall", ""),
                    "place":          item.get("place", ""),
                    **meta,
                }
                # Ensure the primary movie title field is consistent
                record["movie_title"] = item["title"]
                rows.append(record)

    # deduplicate & sort
    uniq: Dict[tuple, Dict[str, str]] = {}
    for r in rows:
        uniq[(r["date_text"], r["movie_title"], r["showtime"])] = r
    return sorted(uniq.values(), key=lambda r: (r["date_text"], r["movie_title"], r["showtime"]))

# ---------------------------------------------------------------------------
#  CLI for quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print(f"Testing {CINEMA_NAME} scraper …")
    data = scrape_bunkamura(days_ahead=7)
    outfile = "bunkamura_showtimes.json"
    print(f"Writing {len(data)} records → {outfile}")
    with open(outfile, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("Done.")