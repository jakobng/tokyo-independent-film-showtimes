from __future__ import annotations

"""
Scraper for ヒューマントラストシネマ有楽町
-------------------------------------------------
* Fetches the theatre’s public JSON schedule feed.
* Uses a hybrid approach for detail scraping.
* Final version with the most robust parsing logic for year extraction.
"""

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# Selenium imports
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────── Constants ────────────────────────────
BASE_URL            = "https://ttcg.jp"
THEATER_CODE        = "human_yurakucho"
CINEMA_NAME         = "ヒューマントラストシネマ有楽町"
SCHEDULE_URL        = f"{BASE_URL}/data/{THEATER_CODE}.js"
PURCHASABLE_URL     = f"{BASE_URL}/data/purchasable.js"
DETAIL_URL_TEMPLATE = f"{BASE_URL}/{THEATER_CODE}/movie/{{movie_id}}.html"

# ─────────────────────── Helper functions ─────────────────────────

def _init_driver() -> webdriver.Chrome:
    """Initializes a headless Chrome WebDriver."""
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception:
        driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver


def _fetch_json(url: str) -> Optional[Any]:
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = "utf-8"
        text = response.text.strip().rstrip(";")
        if text.startswith(("var", "let", "const")) and "=" in text:
            text = text.split("=", 1)[1].strip()
        return json.loads(text)
    except Exception as e:
        print(f"[ERROR] Fetching JSON {url}: {e}", file=sys.stderr)
        return None


def _zfill(num: Any) -> str:
    return str(num).zfill(2)


def _fmt_hm(h: Any, m: Any) -> str:
    return f"{_zfill(h)}:{_zfill(m)}" if h is not None and m is not None else ""


def _normalize_screen_name(raw: str) -> str:
    return raw.translate(str.maketrans("１２３４", "1234"))

# ──────────────────── Detail-page scraping ───────────────────────
_detail_cache: Dict[str, Dict] = {}


def _parse_soup_for_details(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    """Shared parsing logic for a BeautifulSoup object."""
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
                director = dd.get_text(" ", strip=True).lstrip("：:").split('『')[0].strip()
            break

    year = None
    # --- FINAL CHANGE: Look for copyright symbol OR the word "COPYRIGHT" ---
    copyright_regex_symbol = re.compile(r"©︎?\s*(\d{4})")
    copyright_regex_word = re.compile(r"COPYRIGHT\s+.*(\d{4})", re.IGNORECASE)

    # Prioritized search in the specific copyright tag
    copyright_tag = soup.select_one("p.title-copyright")
    if copyright_tag:
        text = copyright_tag.text
        if m := copyright_regex_symbol.search(text):
            year = m.group(1)
        elif m := copyright_regex_word.search(text):
            year = m.group(1)

    # Fallback to searching the whole page if not found
    if not year:
        full_text = soup.get_text(" ", strip=True)
        if m := copyright_regex_symbol.search(full_text):
            year = m.group(1)
        elif m := copyright_regex_word.search(full_text):
            year = m.group(1)

    synopsis_parts = [p.get_text(" ", strip=True) for p in soup.select("div.mod-imageText-a-text p, div.mod-field p")]
    synopsis = "\n".join(synopsis_parts) or None

    return {
        "movie_title": jp_title, "movie_title_en": en_title, "director": director,
        "year": year, "country": country, "runtime_min": runtime_min, "synopsis": synopsis,
    }


def _scrape_details_hybrid(driver: webdriver.Chrome, movie_id: str) -> Dict[str, Optional[str]]:
    """Hybrid scraping function: tries fast requests first, then Selenium as a fallback."""
    if movie_id in _detail_cache:
        return _detail_cache[movie_id]

    url = DETAIL_URL_TEMPLATE.format(movie_id=movie_id)
    details = {}

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, "html.parser")
        details = _parse_soup_for_details(soup)
    except requests.RequestException as e:
        print(f"[WARN] Requests failed for {url}: {e}", file=sys.stderr)
    
    if not details.get('year'):
        print(f"[INFO] Year not found for {movie_id} via requests. Trying Selenium...", file=sys.stderr)
        try:
            if driver is None: # Should be initialized in the main loop, but as a safeguard
                driver = _init_driver()
            driver.get(url)
            WebDriverWait(driver, 15).until(lambda d: d.find_element(By.CSS_SELECTOR, "h2.movie-title"))
            soup = BeautifulSoup(driver.page_source, "html.parser")
            selenium_details = _parse_soup_for_details(soup)
            details.update({k: v for k, v in selenium_details.items() if v}) # Merge results
        except Exception as e:
            print(f"[WARN] Selenium fallback failed for {url}: {e}", file=sys.stderr)

    details["detail_page_url"] = url
    _detail_cache[movie_id] = details
    return details


# ─────────────────────── Main scraping ───────────────────────────

def scrape_human_yurakucho(max_days: int = 7) -> List[Dict]:
    schedule_js = _fetch_json(SCHEDULE_URL)
    purchasable_js = _fetch_json(PURCHASABLE_URL)
    if not schedule_js or not purchasable_js: return []

    if isinstance(schedule_js, list):
        schedule_js = next((x for x in schedule_js if isinstance(x, dict)), {})

    dates = schedule_js.get("dates", [])[:max_days]
    movies_map = schedule_js.get("movies", {})
    screens = schedule_js.get("screens", {})
    purchasable_flag = bool(purchasable_js.get(THEATER_CODE))
    result: List[Dict] = []
    
    driver = None
    try:
        for d in dates:
            y, m, day = map(str, (d["date_year"], d["date_month"], d["date_day"]))
            iso_date = f"{y}-{_zfill(m)}-{_zfill(day)}"
            for mid in map(str, d.get("movie", [])):
                for scr in screens.get(f"{mid}-{y}-{m}-{day}", []):
                    for t in scr.get("time", []):
                        sh, sm = t.get("start_time_hour"), t.get("start_time_minute")
                        if sh is None or sm is None: continue

                        if mid not in _detail_cache:
                             if driver is None: driver = _init_driver()

                        meta = _scrape_details_hybrid(driver, mid)
                        
                        if not meta.get("movie_title"):
                            mv_list = movies_map.get(mid, [])
                            mv = mv_list[0] if mv_list else {}
                            meta["movie_title"] = mv.get("name") or mv.get("cname") or mv.get("title")

                        result.append({
                            "cinema_name": CINEMA_NAME, "movie_title": meta.get("movie_title"),
                            "date_text": iso_date, "showtime": _fmt_hm(sh, sm),
                            "screen_name": _normalize_screen_name(scr.get("name", "スクリーン")),
                            "purchase_url": t.get("url") if purchasable_flag and str(t.get("url", "")).startswith("http") else None,
                            **meta
                        })
    finally:
        if driver: driver.quit()

    unique = [dict(t) for t in {tuple(sorted(d.items())) for d in result}]
    return sorted(unique, key=lambda x: (x["date_text"], x["showtime"], x.get("movie_title") or ""))

if __name__ == "__main__":
    shows = scrape_human_yurakucho()
    json_text = json.dumps(shows, ensure_ascii=False, indent=2)
    out_path = Path(__file__).with_suffix(".json")
    out_path.write_text(json_text, encoding="utf-8-sig")
    print(f"\n✓ Saved {len(shows)} showings → {out_path}")