#!/usr/bin/env python3
# main_scraper2.py

import json
import sys

# --- All cinema scraper modules ---
import cinemart_shinjuku_module        # NEW: Cinemart Shinjuku
import eurospace_module
import image_forum_module
import ks_cinema_module
import musashino_kan_module            # Shinjuku Musashino-kan
import shin_bungeiza_module
import stranger_module
import cinema_qualite_module
import theatre_shinjuku_module
import human_shibuya_module
import cine_quinto_module
import yebisu_garden_module
import theatreguild_daikanyama_module  # Theatre Guild Daikanyama
import meguro_cinema_module

# -----------------------------------------------------------------------------
# Ensure UTF-8 output on Windows consoles
# -----------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        if sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Wrapper for each scraper: logs start/end, catches exceptions
# -----------------------------------------------------------------------------
def _run_scraper(label: str, func):
    print(f"\nScraping {label} …")
    try:
        rows = func() or []
        print(f"→ {len(rows)} showings from {label}.")
        return rows
    except Exception as e:
        print(f"⚠️ Error in {label}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []

# -----------------------------------------------------------------------------
# Main: invoke every scraper in turn
# -----------------------------------------------------------------------------
def run_all_scrapers():
    print("Starting all scrapers…")
    all_listings = []

    all_listings += _run_scraper("Cinemart Shinjuku",         cinemart_shinjuku_module.scrape_cinemart_shinjuku)
    all_listings += _run_scraper("Theatre Image Forum",       image_forum_module.scrape_image_forum)
    all_listings += _run_scraper("Eurospace",                 eurospace_module.scrape_eurospace)
    all_listings += _run_scraper("K's Cinema",                ks_cinema_module.scrape_ks_cinema)
    all_listings += _run_scraper("Shinjuku Musashino-kan",    musashino_kan_module.scrape_musashino_kan)
    all_listings += _run_scraper("Shin-Bungeiza",             shin_bungeiza_module.scrape_shin_bungeiza)
    all_listings += _run_scraper("Stranger",                  stranger_module.scrape_stranger)
    all_listings += _run_scraper("Cinema Qualite",            cinema_qualite_module.scrape_cinema_qualite)
    all_listings += _run_scraper("Theatre Shinjuku",          theatre_shinjuku_module.scrape_theatre_shinjuku)
    all_listings += _run_scraper("Human Trust Cinema Shibuya", human_shibuya_module.scrape_human_shibuya)
    all_listings += _run_scraper("Cine Quinto Shibuya",       cine_quinto_module.scrape_cinequinto_shibuya)
    all_listings += _run_scraper("YEBISU GARDEN CINEMA",       yebisu_garden_module.scrape_ygc)
    all_listings += _run_scraper("Theatre Guild Daikanyama",  theatreguild_daikanyama_module.scrape_theatreguild_daikanyama)
    all_listings += _run_scraper("Meguro Cinema",            meguro_cinema_module.scrape_meguro_cinema)

    print(f"\nCollected a total of {len(all_listings)} showings.")
    return all_listings

# -----------------------------------------------------------------------------
# Dump to JSON file
# -----------------------------------------------------------------------------
def save_to_json(data, filename="showtimes.json"):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved to {filename}")
    except Exception as e:
        print(f"⚠️ Failed to save {filename}: {e}", file=sys.stderr)

# -----------------------------------------------------------------------------
# Entry-point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    listings = run_all_scrapers()
    # optional: sort by cinema, date, time
    try:
        listings.sort(key=lambda x: (
            x.get("cinema", ""),
            x.get("date_text", ""),
            x.get("showtime", "")
        ))
    except Exception:
        pass
    save_to_json(listings)
