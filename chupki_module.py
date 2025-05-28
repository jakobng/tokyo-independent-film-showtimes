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

    # 1) parse the header date-range, e.g. "5月24日(土)～30日(金) ＊28日(水)休映"
    hdr = tt.find("h3", class_="timetable__ttl")
    if not hdr:
        print("[Chupki] timetable header not found", file=sys.stderr)
        return []
    txt = hdr.get_text(" ", strip=True)

    # extract start-month, start-day, end-day
    m = re.search(r"(\d{1,2})月(\d{1,2})日.*?～(\d{1,2})日", txt)
    if not m:
        print(f"[Chupki] could not parse date range from '{txt}'", file=sys.stderr)
        return []
    month, start_day, end_day = map(int, m.groups())

    # extract any closed-days (e.g. "＊28日(水)休映")
    closed = set(int(d) for d in re.findall(r"(\d{1,2})日.*?休映", txt))

    # build the list of actual dates in the range
    year = date.today().year
    raw_dates = [
        date(year, month, d)
        for d in range(start_day, end_day + 1)
        if d not in closed
    ]

    # filter to [today .. today+max_days]
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
        showtime = th.get_text(" ", strip=True)
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
    # assume UTF-8
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
