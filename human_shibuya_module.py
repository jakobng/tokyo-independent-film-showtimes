from __future__ import annotations

"""
Scraper for ヒューマントラストシネマ渋谷
----------------------------------------------------------------
* Fetches the theatre’s public JSON schedule feed (https://ttcg.jp/data/human_shibuya.js)
* Follows each movie’s detail page once to pull richer metadata.
* Emits a list[dict] in the standard schema.
---
v3 Final:
* Handles multiple copyright symbol variations (© and ©︎) for year extraction.
* Correctly handles missing detail pages for special events.
"""

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# ─────────────────────────── Constants ────────────────────────────
BASE_URL            = "https://ttcg.jp"
THEATER_CODE        = "human_shibuya"
CINEMA_NAME         = "ヒューマントラストシネマ渋谷"
SCHEDULE_URL        = f"{BASE_URL}/data/{THEATER_CODE}.js"
PURCHASABLE_URL     = f"{BASE_URL}/data/purchasable.js"
DETAIL_URL_TEMPLATE = f"{BASE_URL}/{THEATER_CODE}/movie/{{movie_id}}.html"

# single shared session with JP headers & theatre referer => avoids 403
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en;q=0.8",
        "Referer": f"{BASE_URL}/{THEATER_CODE}/",
    }
)

# ─────────────────────── Helper functions ─────────────────────────

def _get(url: str) -> requests.Response:
    """HTTP GET that forces UTF‑8 decoding (site always UTF‑8)."""
    resp = SESSION.get(url, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp


def _clean_json_js_like(text: str) -> Any:
    text = text.strip().rstrip(";")
    if text.startswith(("var", "let", "const")) and "=" in text:
        text = text.split("=", 1)[1].strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return json.loads(text)


def _fetch_json(url: str) -> Optional[Any]:
    try:
        return _clean_json_js_like(_get(url).text)
    except Exception as e:
        print(f"[ERROR] Fetch JSON {url}: {e}", file=sys.stderr)
        return None


def _zfill(num: Any) -> str:
    return str(num).zfill(2)


def _fmt_hm(h: Any, m: Any) -> str:
    return f"{_zfill(h)}:{_zfill(m)}" if h is not None and m is not None else ""


def _normalize_screen_name(raw: str) -> str:
    return raw.translate(str.maketrans("１２３４", "1234"))

# ──────────────────── Detail-page scraping (cached) ───────────────
_detail_cache: Dict[str, Dict] = {}


def _scrape_detail_page(movie_id: str) -> Dict[str, Optional[str]]:
    if movie_id in _detail_cache:
        return _detail_cache[movie_id]

    url = DETAIL_URL_TEMPLATE.format(movie_id=movie_id)
    try:
        soup = BeautifulSoup(_get(url).text, "html.parser")
    except Exception as e:
        print(f"[WARN] detail page {url}: {e}", file=sys.stderr)
        _detail_cache[movie_id] = {}
        return {}

    jp_title = en_title = None
    h2 = soup.select_one("h2.movie-title")
    if h2:
        jp_title = h2.get_text("|", strip=True).split("|", 1)[0]
        sub = h2.select_one("span.sub")
        en_title = sub.get_text(strip=True) if sub else None

    runtime_min = country = None
    label = soup.select_one("p.schedule-nowShowing-label")
    if label:
        bs = label.select("b")
        for b in bs:
            txt = b.get_text(strip=True)
            if "分" in txt and txt[:-1].isdigit():
                runtime_min = txt[:-1]
        if bs:
            potential_country = bs[-1].get_text(strip=True)
            if "分" not in potential_country:
                country = potential_country

    director = None
    for dt_tag in soup.select("dl.movie-staff dt"):
        if "監督" in dt_tag.text:
            dd = dt_tag.find_next_sibling("dd")
            if dd:
                director = dd.get_text(" ", strip=True).lstrip("：:")
            break

    year = None
    # --- V3 CHANGE: Updated regex to handle © and ©︎ ---
    copyright_regex = re.compile(r"©︎?\s*(\d{4})")
    
    # Prioritized search
    copyright_tag = soup.select_one("p.title-copyright")
    if copyright_tag and (m := copyright_regex.search(copyright_tag.text)):
        year = m.group(1)
    # Fallback to searching the whole page
    elif (m := copyright_regex.search(soup.get_text(" ", strip=True))):
        year = m.group(1)

    synopsis_parts = [p.get_text(" ", strip=True) for p in soup.select("div.mod-imageText-a-text p, div.mod-field p")]
    synopsis = "\n".join(synopsis_parts) or None

    info = {
        "movie_title": jp_title,
        "movie_title_en": en_title,
        "director": director,
        "year": year,
        "country": country,
        "runtime_min": runtime_min,
        "synopsis": synopsis,
        "detail_page_url": url,
    }
    _detail_cache[movie_id] = info
    return info

# ─────────────────────── Main scraping ───────────────────────────

def scrape_human_shibuya(max_days: int = 7) -> List[Dict]:
    schedule_js = _fetch_json(SCHEDULE_URL)
    purchasable_js = _fetch_json(PURCHASABLE_URL)
    if not schedule_js or not purchasable_js:
        return []

    if isinstance(schedule_js, list):
        schedule_js = next((x for x in schedule_js if isinstance(x, dict)), {})

    dates = schedule_js.get("dates", [])[:max_days]
    movies_map = schedule_js.get("movies", {})
    screens = schedule_js.get("screens", {})
    purchasable_flag = bool(purchasable_js.get(THEATER_CODE))

    result: List[Dict] = []

    for d in dates:
        y, m, day = map(str, (d["date_year"], d["date_month"], d["date_day"]))
        iso_date = f"{y}-{_zfill(m)}-{_zfill(day)}"
        for mid in map(str, d.get("movie", [])):
            key = f"{mid}-{y}-{m}-{day}"
            for scr in screens.get(key, []):
                screen_name = _normalize_screen_name(scr.get("name", "スクリーン"))
                for t in scr.get("time", []):
                    sh, sm = t.get("start_time_hour"), t.get("start_time_minute")
                    if sh is None or sm is None:
                        continue
                    showtime = _fmt_hm(sh, sm)
                    p_url = t.get("url") if purchasable_flag and str(t.get("url", "")).startswith("http") else None

                    meta = _scrape_detail_page(mid)
                    if not meta.get("movie_title"):
                        mv = movies_map.get(mid)
                        if isinstance(mv, list):
                            mv = mv[0] if mv else {}
                        if isinstance(mv, dict):
                            meta["movie_title"] = mv.get("name") or mv.get("cname") or mv.get("title")

                    result.append(
                        {
                            "cinema_name": CINEMA_NAME,
                            "movie_title": meta.get("movie_title"),
                            "date_text": iso_date,
                            "showtime": showtime,
                            "director": meta.get("director"),
                            "year": meta.get("year"),
                            "country": meta.get("country"),
                            "runtime_min": meta.get("runtime_min"),
                            "synopsis": meta.get("synopsis"),
                            "detail_page_url": meta.get("detail_page_url"),
                            "movie_title_en": meta.get("movie_title_en"),
                            "screen_name": screen_name,
                            "purchase_url": p_url,
                        }
                    )

    unique = [dict(t) for t in {tuple(sorted(d.items())) for d in result}]
    return sorted(unique, key=lambda x: (x["date_text"], x["showtime"], x.get("movie_title") or ""))


if __name__ == "__main__":
    shows = scrape_human_shibuya()

    json_text = json.dumps(shows, ensure_ascii=False, indent=2)

    out_path = Path(__file__).with_suffix(".json")
    out_path.write_text(json_text, encoding="utf-8-sig")

    print(f"✓ Saved {len(shows)} showings → {out_path}")