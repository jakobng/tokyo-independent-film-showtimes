# bluestudio_module.py
# Final, working version for Cinema Blue Studio.

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# --- Constants ---
CINEMA_NAME = "シネマブルースタジオ"
BASE_URL = "https://www.art-center.jp/tokyo/bluestudio/schedule.html"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# --- Helper Functions ---
def fetch_soup(url: str) -> Optional[BeautifulSoup]:
    """Fetches a URL and returns a BeautifulSoup object, handling Shift_JIS encoding."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        resp.encoding = "shift_jis"
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"ERROR: [{CINEMA_NAME}] Fetching/parsing failed: {e}", file=sys.stderr)
        return None

def _normalize_text(text: str) -> str:
    """Normalizes text by translating full-width characters and handling whitespace."""
    if not text: return ""
    trans_table = str.maketrans("０１２３４５６７８９：／（）～", "0123456789:/()~")
    text = text.replace('→', '->')
    text_no_space = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    return " ".join(text_no_space.translate(trans_table).strip().split())

def _extract_date_range(text: str) -> Optional[Tuple[dt.date, dt.date]]:
    """Extracts the first two valid dates found in a block of text."""
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    date_re = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
    parsed_dates = []
    for match in date_re.finditer(text):
        try:
            year, month, day = map(int, match.groups())
            if 1 <= month <= 12 and 1 <= day <= 31:
                parsed_dates.append(dt.date(year, month, day))
        except (ValueError, TypeError): continue
    return (parsed_dates[0], parsed_dates[1]) if len(parsed_dates) >= 2 else None

def _extract_times(text: str) -> List[str]:
    """Extracts a cluster of showtimes."""
    # This regex now correctly captures all times separated by slashes.
    time_cluster_re = re.compile(r"上映時間[^0-9０-９]*([0-9０-９：:／/]+)")
    if not (m := time_cluster_re.search(text)): return []
    
    # The rest of the function correctly splits the captured string.
    times_str = _normalize_text(m.group(1))
    times = [t.strip() for t in times_str.split('/') if t.strip()]
    
    return sorted(list(dict.fromkeys(times)))
def _parse_details_from_text(text: str) -> Dict:
    """Extracts detailed film info from the normalized text of a schedule table."""
    details = {"director": None, "year": None, "runtime_min": None, "country": None, "synopsis": None}
    normalized_text = _normalize_text(text)
    
    # Improved regex to handle "監督：" and "監督・脚本："
    director_pattern = r"監督(?:・脚本)?\s*:\s*([^\s／]+)"
    if m := re.search(director_pattern, normalized_text):
        details["director"] = m.group(1).strip()
    
    if m := re.search(r"\((\d+?)分\)", normalized_text): details["runtime_min"] = m.group(1)
    
    if m := re.search(r"(\d{4})年\s+([^\s(]+)", normalized_text):
        details["year"] = m.group(1)
        if '分' not in m.group(2): details["country"] = m.group(2)
    elif m := re.search(r"(\d{4})年", normalized_text):
        details["year"] = m.group(1)

    # Improved regex to find synopsis block
    synopsis_pattern = r"(監督(?:・脚本)?\s*:.*?)(?=\(c\)|©|\d{2}’)"
    if m := re.search(synopsis_pattern, normalized_text, re.DOTALL):
        details["synopsis"] = "\n".join(line.strip() for line in m.group(1).strip().splitlines())
    return details

def _interpret_notes_for_day(day: dt.date, base_times: List[str], notes: str) -> List[str]:
    """Adjusts showtimes for a specific day based on schedule notes."""
    times_for_day = list(base_times)
    normalized_notes = _normalize_text(notes)
    
    if m := re.search(r"毎週(.+?)曜.*?(\d{1,2}:\d{2})\s*->\s*(\d{1,2}:\d{2})", normalized_notes):
        days_jp, from_time, to_time = m.groups()
        jp_to_int = {"水": 2, "金": 4}
        if day.weekday() in [jp_to_int[d] for d in days_jp if d in jp_to_int]:
            times_for_day = [to_time if t == from_time else t for t in times_for_day]

    for m in re.finditer(r"(\d{1,2})/(\d{1,2})\s*\(\w\)\s*(\d{1,2}:\d{2}).*?休映", normalized_notes):
        month, day_num, time_cancel = m.groups()
        if day.month == int(month) and day.day == int(day_num):
            times_for_day = [t for t in times_for_day if t != time_cancel]
            
    return sorted(times_for_day)

# --- Main Scraper ---
def scrape_bluestudio(max_days: int = 14) -> List[Dict]:
    """Scrapes all movie showings and details from Cinema Blue Studio."""
    print(f"INFO: [{CINEMA_NAME}] Starting scrape...", file=sys.stderr)
    soup = fetch_soup(BASE_URL)
    if not soup: return []

    all_showings = []
    schedule_tables = [tbl for tbl in soup.find_all("table") if "上映期間" in tbl.get_text() and "上映時間" in tbl.get_text()]
    print(f"INFO: [{CINEMA_NAME}] Found {len(schedule_tables)} candidate schedule tables.", file=sys.stderr)

    for table in schedule_tables:
        table_text = table.get_text(separator="\n")
        
        title_tag = table.select_one('td[bgcolor="#E9E9E9"] b, td[bgcolor="#E9E9E9"] strong')
        if not title_tag: continue
        
        title = _normalize_text(title_tag.get_text().split("※")[0])
        if not title or len(title) < 2: continue
        
        date_range = _extract_date_range(table_text)
        if not date_range: continue
        start_date, end_date = date_range

        base_showtimes = _extract_times(table_text)
        if not base_showtimes: continue

        print(f"  -> Processing: '{title}' ({start_date} to {end_date})", file=sys.stderr)

        notes_text = " ".join(re.findall(r"※(.+)", table_text))
        details = _parse_details_from_text(table_text)

        today = dt.date.today()
        day_to_check = today
        cutoff = today + dt.timedelta(days=max_days)
        while day_to_check <= end_date and day_to_check < cutoff:
            if day_to_check >= start_date:
                times = _interpret_notes_for_day(day_to_check, base_showtimes, notes_text)
                for showtime in times:
                    all_showings.append({
                        "cinema_name": CINEMA_NAME, "movie_title": title,
                        "date_text": day_to_check.isoformat(), "showtime": showtime,
                        "screen_name": None, "detail_page_url": BASE_URL, **details
                    })
            day_to_check += dt.timedelta(days=1)
            
    all_showings.sort(key=lambda x: (x.get("date_text", ""), x.get("showtime", "")))
    print(f"INFO: [{CINEMA_NAME}] Scrape complete. Found {len(all_showings)} showings.", file=sys.stderr)
    return all_showings

# --- Main Execution ---
if __name__ == '__main__':
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    showings = scrape_bluestudio(max_days=10) 

    if showings:
        output_filename = "bluestudio_showtimes.json"
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(showings, f, ensure_ascii=False, indent=2)
        print(f"\nINFO: Successfully created '{output_filename}' with {len(showings)} records.", file=sys.stderr)
    else:
        print(f"\nNo showings found for {CINEMA_NAME}.")