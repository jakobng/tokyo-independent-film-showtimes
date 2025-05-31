"""nfaj_calendar_module.py — scraper for 国立映画アーカイブ mini‑calendar
Updated 2025‑05‑31 (film‑screenings‑only variant)

Changes in this revision
------------------------
* **Film screenings only** – exhibition rooms, library hours and other
  non‑screening items are no longer collected.
* **Skip talks / Q&A** – within the film blocks, list items containing the
  substring "トーク" (Japanese "talk") or its roman spelling "talk" are ignored.
  This drops things like ギャラリートーク or stage‑talk announcements while
  keeping the actual film titles.
* **API identical** – `get_events()` still returns a list of `Event` objects;
  each is guaranteed to be a film screening.
"""
from __future__ import annotations

import datetime as _dt
import os as _os
import re as _re
import time as _time
from dataclasses import dataclass
from typing import List, Optional

import requests
from bs4 import BeautifulSoup, Tag

__all__ = ["Event", "get_events"]

# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class Event:
    date: _dt.date
    time: str  # "14:00" etc.
    hall: str  # 長瀬記念ホール OZU / 小ホール …
    title: str  # Film title only
    url: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.date:%Y‑%m‑%d} {self.time:<5} {self.hall} {self.title}"


# ─────────────────────────────────────────────────────────────────────────────
# Constants & helpers
# ─────────────────────────────────────────────────────────────────────────────

_CAL_URL = "https://www.nfaj.go.jp/"
_SKIP_TITLE_PAT = _re.compile(r"トーク|talk", _re.I)
_TIME_PAT = _re.compile(r"\d{1,2}:\d{2}")

try:
    from selenium import webdriver  # type: ignore
    from selenium.webdriver.chrome.options import Options  # type: ignore
    from selenium.webdriver.common.by import By  # type: ignore
    from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
    from selenium.webdriver.support import expected_conditions as EC  # type: ignore

    _SELENIUM_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    _SELENIUM_AVAILABLE = False


def _guess_year(month: int, today: _dt.date) -> int:
    """Return the most plausible calendar year for *month* relative to *today*."""
    if today.month == 12 and month == 1:
        return today.year + 1
    if today.month == 1 and month == 12:
        return today.year - 1
    return today.year


# ─────────────────────────────────────────────────────────────────────────────
# Core extractors (HTML → List[Event])
# ─────────────────────────────────────────────────────────────────────────────


def _extract_events(html: str, days_ahead: int, *, today: _dt.date) -> List[Event]:
    """Parse the homepage HTML (with all tab panels present) and return only
    *film screening* events within *days_ahead* days.
    """
    soup = BeautifulSoup(html, "lxml")
    cal_sec: Optional[Tag] = soup.find("section", id="calendar")
    if not cal_sec:
        return []

    # Map panel id → absolute date
    id_to_date: dict[str, _dt.date] = {}
    for btn in cal_sec.select(".tab_list button"):
        pid = btn.get("aria-controls")
        span = btn.find("span")
        if not (pid and span):
            continue
        try:
            month, day = map(int, span.get_text(strip=True).split("/"))
        except ValueError:
            continue
        id_to_date[pid] = _dt.date(_guess_year(month, today), month, day)

    horizon = today + _dt.timedelta(days=days_ahead)
    events: list[Event] = []

    for panel in cal_sec.select("div[role='tabpanel']"):
        pid = panel.get("id")
        date = id_to_date.get(pid)
        if not date or date > horizon:
            continue

        # Skip full closure days
        if panel.find(class_="close_day"):
            continue

        # Extract film screenings only
        for film_div in panel.select("div.film"):
            hall = film_div.find("h2").get_text(" ", strip=True)
            # Skip休映 (no screenings)
            h3 = film_div.find("h3")
            if h3 and h3.get_text(strip=True) == "休映":
                continue

            for li in film_div.select("ul li"):
                # Time
                time_tag = li.find("time")
                if not time_tag:
                    continue
                time_txt = time_tag["datetime"]

                # Title
                a_tag = li.find("a")
                if not a_tag:
                    continue
                title = a_tag.get_text(" ", strip=True)
                if _SKIP_TITLE_PAT.search(title):
                    # Ignore gallery talks, stage talks, etc.
                    continue
                url = a_tag["href"]

                events.append(Event(date, time_txt, hall, title, url))

    return sorted(events, key=lambda e: (e.date, e.time))


# ─────────────────────────────────────────────────────────────────────────────
# Selenium helper (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_with_selenium(timeout: int) -> str:
    if not _SELENIUM_AVAILABLE:
        raise RuntimeError("selenium or a webdriver is not installed")

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(timeout)

    try:
        driver.get(_CAL_URL)
        wait = WebDriverWait(driver, timeout)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section#calendar .tab_list button")))

        # Iterate through date tabs to force JS to render panels
        for btn in driver.find_elements(By.CSS_SELECTOR, "section#calendar .tab_list button"):
            pid = btn.get_attribute("aria-controls")
            if not pid:
                continue
            driver.execute_script("arguments[0].click();", btn)
            try:
                wait.until(EC.attribute_contains((By.ID, pid), "class", "on"))
            except Exception:
                pass
            _time.sleep(0.15)

        html = driver.page_source
    finally:
        driver.quit()
    return html


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_events(
    days_ahead: int = 7,
    *,
    timeout: int = 30,
    use_selenium: bool | None = None,
) -> List[Event]:
    """Return film screenings within *days_ahead* days.  See docstring for
    behaviour of *use_selenium* (True / False / None→auto).
    """
    today = _dt.date.today()
    auto_mode = use_selenium is None

    # Forced or env‑var Selenium path
    if use_selenium or (_os.getenv("NFAJ_USE_SELENIUM") == "1"):
        html = _fetch_with_selenium(timeout)
        return _extract_events(html, days_ahead, today=today)

    # Try plain HTTP first
    html = requests.get(_CAL_URL, timeout=timeout).text
    events = _extract_events(html, days_ahead, today=today)

    # Fallback to browser if we only captured ≤1 date (likely first tab only)
    if auto_mode and len({e.date for e in events}) <= 1 and _SELENIUM_AVAILABLE:
        html = _fetch_with_selenium(timeout)
        events = _extract_events(html, days_ahead, today=today)

    return events


# ─────────────────────────────────────────────────────────────────────────────
# CLI helper
# ─────────────────────────────────────────────────────────────────────────────

def _main(argv: list[str] | None = None) -> None:  # pragma: no cover
    import sys
    from itertools import islice

    args = argv or sys.argv
    try:
        n = int(args[1])
    except (IndexError, ValueError):
        n = 7
    use_sel = "--selenium" in args

    evs = get_events(n, use_selenium=use_sel)
    print(f"Found {len(evs)} film screenings across {len({e.date for e in evs})} days. First 20:\n")
    for ev in islice(evs, 20):
        print(ev)


if __name__ == "__main__":  # pragma: no cover
    _main()
