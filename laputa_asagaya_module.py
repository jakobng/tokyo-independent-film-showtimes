from __future__ import annotations

"""Laputa Asagaya programme scraper – **rev-M 2025-06-25**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
✅ Final bugfix for critical showtime assignment error.
✅ Main grid parser now checks all cells in a row for a header, not just
   the first one. This correctly handles headers that appear after a rowspan cell.
✅ All known bugs should now be resolved.
"""

import datetime as dt
import json
import re
import sys
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urldefrag

import requests
from bs4 import BeautifulSoup, Tag

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────
CINEMA_NAME    = "ラピュタ阿佐ヶ谷"
SCHEDULE_URL   = "https://www.laputa-jp.com/laputa/main/index.html"
BASE_URL       = "https://www.laputa-jp.com/"
LOOKAHEAD_DAYS = 7

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}
TIMEOUT = 20
JUNK_KEYWORDS = ["スケジュール", "会場", "特集", "休映"]

_soup_cache: Dict[str, BeautifulSoup] = {}

# ──────────────────────────────────────────────────────────
# Generic Helpers
# ──────────────────────────────────────────────────────────

def _fetch_soup(url: str) -> Optional[BeautifulSoup]:
    base_url = urldefrag(url).url
    if base_url in _soup_cache:
        return _soup_cache[base_url]
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        _soup_cache[base_url] = soup
        return soup
    except requests.RequestException as exc:
        print(f"ERROR fetching {base_url}: {exc}", file=sys.stderr)
        return None

def _is_junk(text: str) -> bool:
    if not text or len(text) < 2:
        return True
    if any(keyword in text for keyword in JUNK_KEYWORDS):
        return True
    if text.startswith("＜") or text.endswith("＞"):
        return True
    return False

def _clean_text(text: str) -> str:
    return text.strip().replace(' ', '').replace('　', '').strip("、・") if text else ""

def _parse_time(raw: str) -> str:
    match = re.search(r"(\d{1,2}):(\d{2})", raw)
    if not match: return ""
    h, m = map(int, match.groups())
    if ("午後" in raw or "pm" in raw.lower()) and h != 12: h += 12
    if ("午前" in raw or "am" in raw.lower()) and h == 12: h = 0
    return f"{h:02d}:{m:02d}"

_date_pat = re.compile(r"(\d{1,2})")
def _expand_date_range(text: str, month: int, year: int) -> List[dt.date]:
    nums = list(map(int, _date_pat.findall(text)))
    if not nums: return []
    dates = []
    if ("～" in text or "・" in text) and len(nums) >= 2:
        start_day, end_day = nums[0], nums[-1]
        try:
            start_date = dt.date(year, month, start_day)
            end_date = dt.date(year, month, end_day)
            if end_date < start_date:
                 end_date = dt.date(year, month + 1, end_day) if month < 12 else dt.date(year + 1, 1, end_day)
        except ValueError: return []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date)
            current_date += dt.timedelta(days=1)
    else:
        for day in nums:
            try: dates.append(dt.date(year, month, day))
            except ValueError: continue
    return dates

def _iter_rowspan(table: Tag):
    rowspans: List[int] = [0] * 64
    for tr in table.find_all("tr"):
        cells_info: List[Tuple[Tag, int, int, int]] = []
        col = 0
        for td in tr.find_all(["td", "th"], recursive=False):
            while col < len(rowspans) and rowspans[col] > 0: col += 1
            colspan_match = re.search(r'\d+', str(td.get("colspan", "1")))
            colspan = int(colspan_match.group(0)) if colspan_match else 1
            rowspan_match = re.search(r'\d+', str(td.get("rowspan", "1")))
            rowspan = int(rowspan_match.group(0)) if rowspan_match else 1
            cells_info.append((td, col, colspan, rowspan))
            for c in range(col, col + colspan): rowspans[c] = rowspan
            col += colspan
        rowspans = [max(0, x - 1) for x in rowspans]
        yield tr, cells_info

# ──────────────────────────────────────────────────────────
# Stage 3: Scrape sakuhin.html for Rich Metadata
# ──────────────────────────────────────────────────────────
def _fetch_rich_metadata(url: str) -> Dict:
    soup = _fetch_soup(url)
    if not soup: return {}
    fragment = urldefrag(url).fragment
    if not fragment: return {}

    anchor_tag = soup.find("a", attrs={"name": fragment})
    if not anchor_tag: return {}
    
    work_div = anchor_tag.find_next("div", class_="works")
    if not work_div: return {}

    metadata = {}
    title_tag = work_div.find("h3", class_="title")
    metadata["movie_title"] = _clean_text(title_tag.get_text(strip=True)) if title_tag else ""

    data_p = work_div.find("p", class_="data")
    if data_p:
        raw_data = data_p.get_text(" ", strip=True)
        year_m = re.search(r"(\d{4})年", raw_data)
        runtime_m = re.search(r"(\d+)分", raw_data)
        metadata["year"] = year_m.group(1) if year_m else ""
        metadata["runtime_min"] = int(runtime_m.group(1)) if runtime_m else None
    
    staff_p = work_div.find("p", class_="staff")
    if staff_p:
        raw_staff = staff_p.get_text(" ", strip=True)
        director_m = re.search(r"監督：([^／\s]+)", raw_staff)
        if director_m:
            metadata["director"] = _clean_text(director_m.group(1))
        else:
            script_m = re.search(r"脚本：([^／\s]+)", raw_staff)
            metadata["director"] = _clean_text(script_m.group(1)) if script_m else ""
    return metadata

# ──────────────────────────────────────────────────────────
# Stage 2: Scrape sc.html for Schedules and Links to Stage 3
# ──────────────────────────────────────────────────────────
def _scrape_program_schedule_page(url: str, today: dt.date) -> List[Dict]:
    soup = _fetch_soup(url)
    if not soup: return []

    shows = []
    laputa_header = soup.find(lambda tag: "ラピュタ阿佐ヶ谷" in tag.get_text() and "h2subText" in tag.get("class", []))
    if not laputa_header: return []
    schedule_table = laputa_header.find_next("table", class_="sc_table")
    if not schedule_table: return []

    current_month, current_year = today.month, today.year
    for tr, cells in _iter_rowspan(schedule_table):
        if not cells: continue

        if "item2" in cells[0][0].get("class", []):
            month_m = _date_pat.search(cells[0][0].get_text())
            if month_m:
                new_month = int(month_m.group(1))
                if new_month < current_month: current_year += 1
                current_month = new_month
            cells.pop(0)

        if not cells or "item1" not in cells[0][0].get("class", []): continue
        date_text = cells[0][0].get_text(" ", strip=True)
        dates = _expand_date_range(date_text, current_month, current_year)
        
        for cell_info in cells[1:]:
            td = cell_info[0]
            if not td.get_text(strip=True): continue
            
            time_raw, *_ = td.get_text("\n", strip=True).split("\n")
            showtime = _parse_time(time_raw)
            
            link_tag = td.find("a", href=re.compile(r"sakuhin\d+\.html"))
            if not link_tag: continue
            
            detail_url = urljoin(url, link_tag['href'])
            metadata = _fetch_rich_metadata(detail_url)
            if not metadata or _is_junk(metadata.get("movie_title", "")): continue

            for d in dates:
                shows.append({
                    "movie_title": metadata.get("movie_title"), "date_text": d.isoformat(),
                    "showtime": showtime, "director": metadata.get("director", ""),
                    "year": metadata.get("year", ""), "country": None,
                    "runtime_min": metadata.get("runtime_min"), "synopsis": None,
                    "detail_page_url": detail_url,
                })
    return shows

# ──────────────────────────────────────────────────────────
# Stage 1: Scrape Main Grid for Direct Listings & Program Links
# ──────────────────────────────────────────────────────────
def scrape_laputa_asagaya() -> List[Dict]:
    main_soup = _fetch_soup(SCHEDULE_URL)
    if not main_soup: return []

    all_shows = []
    program_urls_to_visit = set()
    today = dt.date.today()
    
    anchor = main_soup.find("a", attrs={"name": "2"})
    table = anchor.find_next("table", class_="px12") if anchor else None
    if not table: return []

    header_tr = table.find("tr")
    iso_dates: List[Optional[dt.date]] = []
    year, month, last_day = today.year, 0, 0
    for td in header_tr.find_all("td"):
        t = td.get_text(strip=True)
        if "/" in t:
            month_str, day_str = t.split("/"); month, day = int(month_str), int(day_str)
        elif t.isdigit():
            day = int(t)
            if month == 0: month = today.month
            if 0 < day < last_day:
                month += 1
                if month == 13: month, year = 1, year + 1
        else:
            iso_dates.append(None); continue
        try:
            iso_dates.append(dt.date(year, month, day)); last_day = day
        except ValueError: iso_dates.append(None)

    active_showtime = ""
    for tr, cells in _iter_rowspan(table):
        is_movie_row = True
        
        # FIX: Check all cells in a row for a header, not just the first one.
        for cell, _, _, _ in cells:
            header_font = cell.find("font", color="#FFFFFF")
            if cell.get("colspan") and header_font:
                is_movie_row = False  # This row contains a header, so don't process for movies
                header_text = header_font.get_text(strip=True)
                parsed_time = _parse_time(header_text)
                if parsed_time:
                    active_showtime = parsed_time # Update showtime
        
        if is_movie_row:
            for cell, col_start, colspan, _ in cells:
                link = cell.find("a", href=re.compile("sc.html"))
                if link:
                    program_urls_to_visit.add(urljoin(BASE_URL, link["href"])); continue

                raw_cell_text = cell.get_text(strip=True)
                if _is_junk(raw_cell_text): continue
                
                title_p = cell.find("p")
                if not title_p: continue
                
                title = _clean_text(title_p.get_text(strip=True))
                if _is_junk(title): continue
                
                year_m = re.search(r"(\d{4})年", cell.decode_contents())
                director_m = re.search(r"監督：([^<\n]*)", cell.decode_contents())
                
                for i in range(colspan):
                    idx = col_start + i
                    if idx < len(iso_dates) and iso_dates[idx]:
                        all_shows.append({
                            "movie_title": title, "date_text": iso_dates[idx].isoformat(), 
                            "showtime": active_showtime,
                            "director": _clean_text(director_m.group(1)) if director_m else "",
                            "year": year_m.group(1) if year_m else "", "country": None, 
                            "runtime_min": None, "synopsis": None, "detail_page_url": "",
                        })
    
    for url in program_urls_to_visit:
        print(f"INFO: Scraping program page: {url}")
        all_shows.extend(_scrape_program_schedule_page(url, today))
        
    limit = today + dt.timedelta(days=LOOKAHEAD_DAYS)
    final_shows, seen = [], set()
    all_shows.sort(key=lambda x: (x.get("date_text", ""), x.get("showtime", ""), x.get("movie_title", "")))
    
    for show in all_shows:
        if not show.get("date_text") or not show.get("movie_title"): continue
        show_date = dt.date.fromisoformat(show["date_text"])
        if not (today <= show_date <= limit): continue
        key = (show["date_text"], show["showtime"], show["movie_title"])
        if key in seen: continue
        seen.add(key)
        show["cinema_name"] = CINEMA_NAME
        final_shows.append(show)
        
    print(f"Wrote {len(final_shows)} unique showings → laputa_asagaya_showtimes.json")
    return final_shows

# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception: pass

    data = scrape_laputa_asagaya()
    if not data:
        sys.exit("No showings found :(")
    
    with open("laputa_asagaya_showtimes.json", "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)