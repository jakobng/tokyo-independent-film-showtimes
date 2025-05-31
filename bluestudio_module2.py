# bluestudio_module.py (Finds "二十四の瞳", extracts notes, needs note interpretation next)
"""bluestudio_module.py — scraper for シネマブルースタジオ (Blue Studio)
Schedule page: https://www.art-center.jp/tokyo/bluestudio/schedule.html
Last updated: 2025‑05‑31 (Finds all relevant films, extracts notes for them)
"""
from __future__ import annotations

import datetime as _dt 
import re
import sys
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup, Tag

__all__ = ["scrape_bluestudio"]

# ──────────────────────────────────────────────────────────────
CINEMA_NAME = "シネマブルースタジオ"
URL         = "https://www.art-center.jp/tokyo/bluestudio/schedule.html"

_TRANS = str.maketrans("０１２３４５６７８９：／", "0123456789:/")
_DATE_RE = re.compile(r"(\d(?:\s*\d){3})/(\d{1,2})/(\d{1,2})")
_TIME_CLUSTER_RE = re.compile(
    r"上映時間[^0-9０-９]*([0-9０-９]{1,2}[：:][0-9０-９]{2}(?:[／/][0-9０-９]{1,2}[：:][0-9０-９]{2})*)"
)
_COLON_RE = re.compile(r"[：:]")
_NOTE_MARKER = "※"

# ──────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────

def _norm(txt: str) -> str:
    return re.sub(r"\s+", " ", txt.translate(_TRANS)).strip()

def _extract_date_range(block_text: str) -> Tuple[_dt.date, _dt.date] | None:
    parsed_dates = []
    for match in _DATE_RE.finditer(block_text):
        year_str_raw, month_str, day_str = match.groups()
        year_str_cleaned = year_str_raw.replace(" ", "")
        try:
            year = int(year_str_cleaned)
            month = int(month_str)
            day = int(day_str)
            parsed_dates.append(_dt.date(year, month, day))
        except ValueError:
            continue 
    if len(parsed_dates) < 2:
        return None
    return parsed_dates[0], parsed_dates[1]

def _extract_times(block_text: str) -> List[str]:
    m = _TIME_CLUSTER_RE.search(block_text)
    if not m: return []
    cluster = m.group(1).translate(_TRANS)
    out: List[str] = []
    for part in cluster.split('/'):
        hh_mm = _COLON_RE.sub(':', part.strip())
        if ':' not in hh_mm: continue
        try:
            hh, mm_part = hh_mm.split(':', 1)
            out.append(f"{int(hh):02d}:{int(mm_part):02d}")
        except ValueError: continue
    return list(dict.fromkeys(out))

def _extract_notes(table_element: Tag) -> str | None:
    note_lines = []
    raw_text_for_notes = table_element.get_text("\n", strip=True)
    for line in raw_text_for_notes.splitlines():
        normalized_line = _norm(line)
        if normalized_line.startswith(_NOTE_MARKER):
            note_lines.append(normalized_line)
    if not note_lines: # Fallback
        block_text_content = _norm(table_element.get_text(" ", strip=True))
        notes_in_block = re.findall(r"(※(?:(?!※).)+)", block_text_content)
        if notes_in_block:
            note_lines.extend([note.strip() for note in notes_in_block])
    return " ".join(note_lines).strip() if note_lines else None

def _date_iter(start: _dt.date, end: _dt.date):
    d = start
    while d <= end: yield d; d += _dt.timedelta(days=1)

def _is_schedule_table(tbl: Tag) -> bool:
    txt = _norm(tbl.get_text("\n", strip=True))
    # Check for both markers; also, a very short table is unlikely to be a movie schedule
    return "上映期間" in txt and "上映時間" in txt and len(txt) > 100 # Added length check

# ──────────────────────────────────────────────────────────────
# core scraper
# ──────────────────────────────────────────────────────────────

def scrape_bluestudio(days: int | None = 10, today_override: _dt.date | None = None) -> List[Dict[str, str]]:
    headers = {"User-Agent": "Mozilla/5.0"}
    print(f"Debug ({CINEMA_NAME}): Starting scrape function, days={days}", file=sys.stderr)
    try:
        resp = requests.get(URL, headers=headers, timeout=25)
        resp.raise_for_status()
        resp.encoding = "shift_jis" 
        soup = BeautifulSoup(resp.text, "html.parser")
        print(f"Debug ({CINEMA_NAME}): Successfully fetched and parsed URL.", file=sys.stderr)
    except Exception as e:
        print(f"Error ({CINEMA_NAME}): Fetching/parsing {URL} failed: {e}", file=sys.stderr)
        return []

    today = today_override if today_override else _dt.date.today()
    last_day = today + _dt.timedelta(days=days - 1) if days is not None else None
    if days is not None:
        print(f"Debug ({CINEMA_NAME}): Filtering for dates: {today.isoformat()} to {last_day.isoformat() if last_day else 'None'}", file=sys.stderr)

    items: List[Dict[str, str]] = []
    seen: set[Tuple[str, str, str, str | None]] = set()
    all_found_tables = soup.find_all("table")
    print(f"Debug ({CINEMA_NAME}): Found {len(all_found_tables)} <table> tags in total.", file=sys.stderr)
    
    processed_movie_tables = 0
    candidate_schedule_tables = 0

    for tbl_idx, tbl in enumerate(all_found_tables):
        if not _is_schedule_table(tbl):
            continue
        candidate_schedule_tables +=1
        # Nested table check was disabled as it seemed to filter out valid movie tables.
        # If re-enabled, ensure it correctly distinguishes layout vs. content tables.
        processed_movie_tables += 1
        
        print(f"\n--- Debug ({CINEMA_NAME}): Processing Table Index {tbl_idx} (Candidate {candidate_schedule_tables}, Processed {processed_movie_tables}) ---", file=sys.stderr)
        
        block_txt_for_date_time = _norm(tbl.get_text("\n", strip=True))
        print(f"Debug ({CINEMA_NAME}): Table Block Text (first 300 chars): {block_txt_for_date_time[:300]}", file=sys.stderr)

        # Title Extraction Logic (from user's script with slight enhancement)
        title_cell = tbl.find("td", bgcolor=re.compile("#E9E9E9", re.I)) or tbl.find("b") or tbl.find("strong")
        raw_title = _norm(title_cell.get_text(" ", strip=True)) if title_cell else ""
        title_parts = re.split(r"[※\n]", raw_title) # Split by ※ or newline
        title = title_parts[0].lstrip("　 ").rstrip("　 ") if title_parts else ""
        
        if not title or len(title) < 2 or title == CINEMA_NAME : # Avoid using cinema name as title
            # Fallback: Try to find a prominent bold tag not in a tiny cell, not starting with ※
            # This is to avoid the first table (index 0) picking up "シネマブルースタジオ" as title
            b_tags = tbl.find_all(['b', 'strong'])
            candidate_titles = []
            for b_tag in b_tags:
                parent_td = b_tag.find_parent('td')
                if parent_td and len(_norm(parent_td.get_text())) < 10: continue # Skip bold in very short cells
                
                potential_title_text = _norm(b_tag.get_text(" ", strip=True))
                if potential_title_text.startswith("※"): continue # Skip notes
                if CINEMA_NAME in potential_title_text and len(potential_title_text) < len(CINEMA_NAME) + 10: continue # Skip if it's just cinema name

                cleaned_potential_title = re.split(r"[※\n]", potential_title_text)[0].lstrip("　 ").rstrip("　 ")
                if cleaned_potential_title and len(cleaned_potential_title) >= 2:
                    candidate_titles.append(cleaned_potential_title)
            
            if candidate_titles:
                title = candidate_titles[0] # Take the first good candidate
            elif not title or len(title) < 2: # If still no good title
                title = "Unknown Film"


        print(f"Debug ({CINEMA_NAME}): Extracted Title: '{title}'", file=sys.stderr)

        date_rng = _extract_date_range(block_txt_for_date_time)
        if not date_rng:
            print(f"Debug ({CINEMA_NAME}): No date range extracted for '{title}'. Skipping this table.", file=sys.stderr)
            continue
        start_dt, end_dt = date_rng
        print(f"Debug ({CINEMA_NAME}): Extracted Date Range for '{title}': {start_dt.isoformat()} to {end_dt.isoformat()}", file=sys.stderr)

        times = _extract_times(block_txt_for_date_time)
        if not times:
            print(f"Debug ({CINEMA_NAME}): No showtimes extracted for '{title}'. Skipping this table.", file=sys.stderr)
            continue
        print(f"Debug ({CINEMA_NAME}): Extracted Base Times for '{title}': {times}", file=sys.stderr)
            
        schedule_notes = _extract_notes(tbl)
        if schedule_notes:
            print(f"Debug ({CINEMA_NAME}): Extracted Notes for '{title}': '{schedule_notes}'", file=sys.stderr)

        showings_added_for_this_table = 0
        for day in _date_iter(start_dt, end_dt):
            if last_day is not None and not (today <= day <= last_day): continue
            date_iso = day.isoformat()
            for st in times: # Current version uses base times; note interpretation would go here
                key = (date_iso, title, st, schedule_notes) 
                if key in seen: continue
                seen.add(key)
                items.append({
                    "cinema": CINEMA_NAME, "date_text": date_iso, "screen": "",
                    "title": title, "showtime": st, "schedule_notes": schedule_notes
                })
                showings_added_for_this_table += 1
        print(f"Debug ({CINEMA_NAME}): Added {showings_added_for_this_table} showings for '{title}' within the date window.", file=sys.stderr)

    print(f"\nDebug ({CINEMA_NAME}): Total candidate schedule tables: {candidate_schedule_tables}", file=sys.stderr)
    print(f"Debug ({CINEMA_NAME}): Total movie tables fully processed (attempted title/date/time extraction): {processed_movie_tables}", file=sys.stderr)
    return items

# ──────────────────────────────────────────────────────────────
# CLI test
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    fixed_today_date = _dt.date(2025, 5, 31) 
    
    DAYS_TO_SCRAPE = 10
    print(f"Testing {CINEMA_NAME} scraper… (window: {DAYS_TO_SCRAPE} days from {fixed_today_date})")
    rows = scrape_bluestudio(days=DAYS_TO_SCRAPE, today_override=fixed_today_date)
    print(f"Found {len(rows)} showings.")

    if not rows: print("No rows returned by scraper.")
    else:
        target_film_title_segment = "二十四の瞳"
        found_target_film_in_results = False
        print(f"\nDisplaying up to 20 results (or all if less). Searching for '{target_film_title_segment}':")
        
        for i, r in enumerate(rows):
            if target_film_title_segment in r.get("title", ""):
                print(f"  TARGET FOUND: {r}")
                found_target_film_in_results = True
            elif i < 20: 
                print(f"  {r}") 
        
        if found_target_film_in_results:
            print(f"\nSUCCESS: '{target_film_title_segment}' was found in the results.")
        else:
            print(f"\nINFO: '{target_film_title_segment}' was NOT found in the {len(rows)} results for the current date window.")
            print("      Please check the detailed debug output above for each processed table.")