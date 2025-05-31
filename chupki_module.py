# chupki_module.py — scraper for Chupki Cinematheque
# https://chupki.jpn.org/#screen-area
# Returns rows with keys: cinema, date_text (YYYY-MM-DD), screen, title, showtime

from __future__ import annotations
import sys
import re
from datetime import date, timedelta
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

__all__ = ["scrape_chupki"]

CINEMA_NAME = "Chupki"
BASE_URL = "https://chupki.jpn.org/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

def _fetch(url: str) -> requests.Response | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        print(f"[Chupki] fetch error: {e}", file=sys.stderr)
        return None

def _parse_timetable(html: str, max_days: int) -> List[Dict[str,str]]:
    soup = BeautifulSoup(html, "html.parser")
    tt = soup.find("div", class_="timetable")
    if not tt:
        print("[Chupki] timetable div not found", file=sys.stderr)
        return []

    # 1) parse the header date-range, e.g. "5月31日(土)〜6月7日(土) ＊4日(水)休映"
    hdr = tt.find("h3", class_="timetable__ttl")
    if not hdr:
        print("[Chupki] timetable header not found", file=sys.stderr)
        return []
    txt = hdr.get_text(" ", strip=True)

    m = re.search(r"(\d{1,2})月(\d{1,2})日.*?([～〜])\s*(?:(\d{1,2})月)?(\d{1,2})日", txt)
    if not m:
        print(f"[Chupki] could not parse date range from '{txt}'", file=sys.stderr)
        return []

    start_month_str, start_day_str, _, end_month_str, end_day_str = m.groups()
    start_month = int(start_month_str)
    start_day = int(start_day_str)
    end_day = int(end_day_str)
    end_month = int(end_month_str) if end_month_str else start_month

    closed = set(int(d) for d in re.findall(r"(\d{1,2})日.*?休映", txt))

    year = date.today().year
    start_date = date(year, start_month, start_day)
    end_date = date(year, end_month, end_day)

    if start_date > end_date:
        end_date = date(year + 1, end_month, end_day)

    raw_dates = []
    current_date = start_date
    while current_date <= end_date:
        if current_date.day not in closed:
            raw_dates.append(current_date)
        current_date += timedelta(days=1)

    today = date.today()
    cutoff = today + timedelta(days=max_days)
    dates = [d for d in raw_dates if today <= d < cutoff]

    # 2) parse each <tr><th>time</th><td>title</td></tr>
    table = tt.find("table")
    if not table:
        print("[Chupki] timetable table not found", file=sys.stderr)
        return []

    results: List[Dict[str,str]] = []
    for row in table.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if not (th and td):
            continue

        # FIX: Clean the showtime to extract only the start time (e.g., "17:10")
        raw_showtime_text = th.get_text(" ", strip=True)
        time_match = re.search(r"(\d{1,2}:\d{2})", raw_showtime_text)
        showtime = time_match.group(1) if time_match else raw_showtime_text

        title = td.get_text(" ", strip=True)
        for d in dates:
            results.append({
                "cinema": CINEMA_NAME,
                "date_text": d.isoformat(),
                "screen": "",
                "title": title,
                "showtime": showtime
            })

    return results

def scrape_chupki(max_days: int = 10) -> List[Dict[str,str]]:
    """
    Scrape Chupki timetable for today + next `max_days` days.
    """
    resp = _fetch(BASE_URL)
    if not resp:
        return []
    resp.encoding = resp.apparent_encoding or "utf-8"
    return _parse_timetable(resp.text, max_days)

if __name__ == "__main__":
    shows = scrape_chupki()
    if not shows:
        print("No showings found.")
    else:
        print(f"Found {len(shows)} showings at {CINEMA_NAME}:")
        for s in shows:
            print(s)
