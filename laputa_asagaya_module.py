# laputa_asagaya_selenium_module.py — Selenium + BeautifulSoup scraper for Laputa Asagaya

from __future__ import annotations
import sys
import re
from datetime import date
from typing import List, Dict

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

__all__ = ["scrape_laputa_asagaya_selenium"]

CINEMA_NAME = "ラピュタ阿佐ヶ谷"
BASE_URL = "https://www.laputa-jp.com/laputa/main/index.html"
# (we still use requests for any non-JS fetches if needed)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

def _fetch_with_selenium(url: str, timeout: int = 10) -> str:
    """Load the URL in headless Chrome and return the rendered HTML."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    # suppress logging
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        # wait until at least one schedule table is present
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.px12"))
        )
        return driver.page_source
    finally:
        driver.quit()

def _parse_schedule(html: str) -> List[Dict[str, str]]:
    """Parse the schedule table (class px12) into records."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="px12")
    if not tables:
        print("[Laputa ASAGAYA] no px12 tables found", file=sys.stderr)
        return []
    tbl = tables[-1]

    # 1) Build ISO dates from header
    header_cells = tbl.find("tr").find_all("td")
    dates: List[str] = []
    today = date.today()
    year = today.year
    month = None
    prev_day = 0
    for cell in header_cells:
        txt = cell.get_text(strip=True)
        if "/" in txt:
            m, d = map(int, txt.split("/"))
            month, day = m, d
        else:
            day = int(txt)
            if month is None:
                month = today.month
            elif prev_day and day < prev_day:
                month = month % 12 + 1
        prev_day = day
        dates.append(date(year, month, day).isoformat())

    # 2) Walk each program header + detail
    results: List[Dict[str, str]] = []
    rows = tbl.find_all("tr")[1:]
    i = 0
    while i < len(rows):
        prog_cells = rows[i].find_all("td", colspan=True)
        # program header if single <td> with white text
        if len(prog_cells) == 1 and prog_cells[0].find("font", color="#FFFFFF"):
            td = prog_cells[0]
            title = td.find("a").get_text(strip=True)
            # fetch 午前/午後 if present
            time_of_day = ""
            for f in td.find_all("font", color=True):
                t = f.get_text(strip=True)
                if "午前" in t or "午後" in t:
                    time_of_day = t
                    break
            span = int(td["colspan"])

            # if next row is just “スケジュール詳細”, emit placeholders
            if i+1 < len(rows):
                next_ft = rows[i+1].find("font", attrs={"color": "#FF0000"})
                if next_ft and "スケジュール詳細" in next_ft.get_text():
                    for dt in dates[:span]:
                        results.append({
                            "cinema": CINEMA_NAME,
                            "date_text": dt,
                            "screen": "",
                            "title": title,
                            "showtime": time_of_day,
                        })
                    i += 2
                    continue

            # otherwise parse detail row
            if i+1 < len(rows):
                detail_cells = rows[i+1].find_all("td", colspan=True)
                offset = 0
                for dc in detail_cells:
                    c = int(dc["colspan"])
                    # nested table => multiple film entries
                    if dc.find("table"):
                        for sub in dc.select("table td"):
                            film = "".join(sub.stripped_strings)
                            for o in range(c):
                                results.append({
                                    "cinema": CINEMA_NAME,
                                    "date_text": dates[offset+o],
                                    "screen": "",
                                    "title": film,
                                    "showtime": time_of_day,
                                })
                    else:
                        p = dc.find("p")
                        film = p.get_text(strip=True) if p else dc.get_text(" ", strip=True)
                        for o in range(c):
                            results.append({
                                "cinema": CINEMA_NAME,
                                "date_text": dates[offset+o],
                                "screen": "",
                                "title": film,
                                "showtime": time_of_day,
                            })
                    offset += c
                i += 2
                continue
        i += 1

    return results

def scrape_laputa_asagaya_selenium(max_days: int = 7) -> List[Dict[str, str]]:
    # 1) load rendered HTML via Selenium
    html = _fetch_with_selenium(BASE_URL)
    # 2) parse schedule grid
    all_rows = _parse_schedule(html)
    # 3) filter next max_days
    today = date.today()
    out: List[Dict[str, str]] = []
    for r in all_rows:
        try:
            d = date.fromisoformat(r["date_text"])
            if 0 <= (d - today).days < max_days:
                out.append(r)
        except ValueError:
            out.append(r)
    return out

if __name__ == "__main__":
    data = scrape_laputa_asagaya_selenium()
    if not data:
        print("No showings found.")
    else:
        print(f"Found {len(data)} showings at {CINEMA_NAME}:")
        for row in data:
            print(row)
