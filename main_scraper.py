# main_scraper.py – orchestrates all individual cinema scrapers
# Author: ChatGPT assistant (2025‑05‑27)
#
# Usage:
#     python main_scraper.py  # collects listings and writes showtimes.json
#
# ---------------------------------------------------------------------------
#  Standard library imports
# ---------------------------------------------------------------------------
import json
import sys
import io
from typing import List, Dict, Callable

# ---------------------------------------------------------------------------
#  Import individual cinema modules
# ---------------------------------------------------------------------------
# NOTE: Keep this list alphabetised for sanity!
import cinemart_shinjuku_module            # NEW: Cinemart Shinjuku
import eurospace_module
import image_forum_module
import ks_cinema_module
import musashino_kan_module                # Shinjuku Musashino‑kan
import shin_bungeiza_module
import stranger_module
import cinema_qualite_module
import theatre_shinjuku_module
import human_shibuya_module
import cine_quinto_module

# ---------------------------------------------------------------------------
#  Configure UTF‑8 stdout / stderr on Windows so Japanese prints correctly
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        if sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Fails on older Pythons – non‑fatal
        pass

# ---------------------------------------------------------------------------
#  Helper to run a single scraper with common error handling
# ---------------------------------------------------------------------------

def _run_scraper(label: str, func: Callable[[], List[Dict]]):
    """Run *func* (a scraper) and return its list of listing dicts.

    Any exceptions are caught and logged; the function then returns an empty
    list so that the rest of the scrapers continue to run.
    """
    print(f"\nScraping {label} …")
    try:
        rows = func() or []
        if rows:
            print(f"Found {len(rows)} listings for {label}.")
        else:
            print(f"No listings found for {label}.")
        return rows
    except Exception as exc:
        print(f"Error during {label} scraping: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []

# ---------------------------------------------------------------------------
#  Main orchestrator that executes every scraper
# ---------------------------------------------------------------------------

def run_all_scrapers() -> List[Dict]:
    print("Starting all scrapers …")
    all_rows: List[Dict] = []

    # Order loosely west‑to‑east across Tokyo, then alphabetical within area.
    all_rows += _run_scraper("Theatre Image Forum",      image_forum_module.scrape_image_forum)
    all_rows += _run_scraper("Eurospace",                eurospace_module.scrape_eurospace)
    all_rows += _run_scraper("Shin‑Bungeiza",            shin_bungeiza_module.scrape_shin_bungeiza)
    all_rows += _run_scraper("Stranger",                 stranger_module.scrape_stranger)
    all_rows += _run_scraper("K's Cinema",               ks_cinema_module.scrape_ks_cinema)
    all_rows += _run_scraper("Shinjuku Musashino‑kan",   musashino_kan_module.scrape_musashino_kan)
    all_rows += _run_scraper("Cinemart Shinjuku",        cinemart_shinjuku_module.scrape_cinemart_shinjuku)  # NEW
    all_rows += _run_scraper("Cinema Qualite",           cinema_qualite_module.scrape_cinema_qualite)  # NEW
    all_rows += _run_scraper("Theatre Shinjuku",         theatre_shinjuku_module.scrape_theatre_shinjuku)
    all_rows += _run_scraper("Human Trust Cinema Shibuya", human_shibuya_module.scrape_human_shibuya)
    all_rows += _run_scraper("Cine Quinto",              cine_quinto_module.scrape_cinequinto_shibuya)


    print(f"\nTotal listings collected from all cinemas: {len(all_rows)}")
    return all_rows

# ---------------------------------------------------------------------------
#  JSON output helper
# ---------------------------------------------------------------------------

def save_to_json(data: List[Dict], filename: str = "showtimes.json") -> None:
    """Write *data* to *filename* in UTF‑8 JSON."""
    try:
        with open(filename, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        print(f"Data successfully saved to {filename} (\u2192 {len(data)} rows).")
    except IOError as io_err:
        print(f"IO error saving {filename}: {io_err}", file=sys.stderr)
    except Exception as exc:
        print(f"Unexpected error while saving JSON: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)

# ---------------------------------------------------------------------------
#  Command‑line entry‑point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    dataset = run_all_scrapers()

    if dataset:
        try:
            # Primary sort to make diff‑ing easier between runs
            dataset.sort(key=lambda d: (
                d.get("cinema", ""),
                d.get("date_text", ""),
                d.get("showtime", ""),
            ))
        except Exception as sort_err:
            print(f"Note: could not sort dataset due to {sort_err}. Proceeding unsorted.")

    save_to_json(dataset)
