"""
bacchus_calendar_module.py — scraper for Theater Bacchus (高円寺シアターバッカス)
Last updated: 2025-05-28

Returns a list of dicts with keys:
    cinema, date_text (YYYY-MM-DD), screen, title, showtime

Fetches the public Google Calendar ICS feed and expands multi-day events (via DTEND)
into individual daily entries. Ignores recurrence rules for now. Plugs into main_scraper3.py.
"""

from __future__ import annotations

import sys
from datetime import datetime, date as date_class, time, timedelta
from typing import Dict, List

import requests
from icalendar import Calendar

# ---------------------------------------------------------------------------
# Config / constants
# ---------------------------------------------------------------------------

CINEMA_NAME = "Theater Bacchus"
ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "koenjibacchus%40gmail.com/public/basic.ics"
)
LOOKAHEAD_DAYS = 9  # today + 9 days = next 10 days inclusive
TIMEOUT = 20  # seconds

__all__ = ["scrape_bacchus_calendar"]

# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def scrape_bacchus_calendar() -> List[Dict[str, str]]:
    """
    Scrape Theater Bacchus via its public Google Calendar ICS feed.

    Returns:
        List of dicts: cinema, date_text (ISO YYYY-MM-DD), screen, title, showtime.
        Expands multi-day events (DTEND), listing each day in the run individually.
    """
    # Fetch and parse ICS
    try:
        resp = requests.get(ICS_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        cal = Calendar.from_ical(resp.text)
    except Exception as e:
        print(f"Error ({CINEMA_NAME}): failed to fetch/parse ICS: {e}", file=sys.stderr)
        return []

    today = datetime.today().date()
    cutoff = today + timedelta(days=LOOKAHEAD_DAYS)
    results: List[Dict[str, str]] = []
    seen: set[tuple] = set()

    # Iterate events
    for comp in cal.walk():
        if comp.name != 'VEVENT':
            continue
        # Get start
        dtstart_val = comp.get('DTSTART').dt
        # Get end (may be date or datetime)
        dtend_prop = comp.get('DTEND') or comp.get('DTSTART')
        dtend_val = dtend_prop.dt if dtend_prop else dtstart_val

        # Normalize to datetime
        if isinstance(dtstart_val, date_class) and not isinstance(dtstart_val, datetime):
            start_dt = datetime.combine(dtstart_val, time.min)
        else:
            start_dt = dtstart_val
        if isinstance(dtend_val, date_class) and not isinstance(dtend_val, datetime):
            # Google ICS DTEND is non-inclusive for all-day events
            end_dt = datetime.combine(dtend_val, time.min)
        else:
            end_dt = dtend_val

        # Expand each day in [start_dt.date(), end_dt.date())
        cur_date = start_dt.date()
        while cur_date < end_dt.date():
            if today <= cur_date <= cutoff:
                # Build datetime with original time of DTSTART
                show_time = start_dt.time() if start_dt.time() != time.min else None
                dt_occ = datetime.combine(cur_date, show_time or time.min)
                title = str(comp.get('SUMMARY') or '').strip()
                showtime_str = dt_occ.strftime('%H:%M') if show_time else ''
                key = (cur_date.isoformat(), title, showtime_str)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        'cinema': CINEMA_NAME,
                        'date_text': cur_date.isoformat(),
                        'screen': '',
                        'title': title,
                        'showtime': showtime_str,
                    })
            cur_date += timedelta(days=1)

    # Sort chronologically
    results.sort(key=lambda x: (x['date_text'], x['showtime'], x['title']))
    return results

# ---------------------------------------------------------------------------
# CLI test harness
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print(f"Testing {CINEMA_NAME} calendar scraper…")
    shows = scrape_bacchus_calendar()
    if not shows:
        print("No showings found — check warnings above.")
        sys.exit(0)
    print(f"Found {len(shows)} showings. First {min(10, len(shows))}:\n")
    for s in shows[:10]:
        print(f"  {s['date_text']}  {s['showtime']}  {s['title']} | {s['screen']}")
