#!/usr/bin/env python3
# main_scraper2.py (amended with Google Gemini integration)

import json
import sys
import os
import time
import importlib # Though not used in this direct import style, good to have if refactoring later
import google.generativeai as genai
import traceback

# --- All cinema scraper modules ---
import cinemart_shinjuku_module
import eurospace_module
import image_forum_module
import ks_cinema_module
import musashino_kan_module
import shin_bungeiza_module
import stranger_module
import cinema_qualite_module
import theatre_shinjuku_module
import human_shibuya_module
import cine_quinto_module
import yebisu_garden_module
import theatreguild_daikanyama_module
import meguro_cinema_module

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
OUTPUT_FILE = 'showtimes.json'
GEMINI_API_CALL_DELAY = 1.5  # Delay between Gemini API calls (in seconds)

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

# --- Gemini Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_model = None

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel(model_name='gemini-1.5-flash-latest')
        print("INFO: Google Gemini model configured successfully ('gemini-1.5-flash-latest').")
    except Exception as e:
        print(f"ERROR: Could not configure Google Gemini: {e}")
        print("INFO: Gemini calls will be skipped.")
else:
    print("WARNING: GEMINI_API_KEY environment variable not set. Gemini calls will be skipped.")

def get_english_title_from_gemini(japanese_title: str) -> str | None:
    """
    Queries the configured Gemini model for the localized English title.
    Returns the English title or None if not found/error.
    """
    if not gemini_model or not japanese_title or not japanese_title.strip():
        if gemini_model and (not japanese_title or not japanese_title.strip()):
            print("  Skipping Gemini: Japanese title is empty or whitespace.")
        return None

    prompt_parts = [
        "You are an expert movie database assistant.",
        "What is the official, commonly recognized, localized English release title for the following Japanese movie?",
        f"Japanese Movie Title: \"{japanese_title}\"",
        "Provide only the English title itself and nothing else. Do not add any extra phrases like 'The English title is'.",
        "If you are unsure, or if no official localized English title exists (e.g., it's only known by its Japanese title or a direct romanization internationally), then respond with only the single word 'UNKNOWN'.",
        "Do not provide a literal translation of the Japanese title unless that happens to be its official and commonly used localized English release title."
    ]
    prompt = "\n".join(prompt_parts)

    try:
        print(f"  Querying Gemini for Japanese title: \"{japanese_title}\"")
        response = gemini_model.generate_content(prompt)

        if not response.parts:
            print(f"  Gemini API returned no parts for '{japanese_title}'.")
            return None
        
        english_title = response.text.strip()

        if not english_title or english_title.upper() == "UNKNOWN" or len(english_title) < 2:
            print(f"  Gemini responded UNKNOWN or empty/too short for '{japanese_title}'.")
            return None
        
        is_problematic_response = False
        if japanese_title == english_title or \
           (len(japanese_title) > 3 and japanese_title.lower() in english_title.lower() and abs(len(english_title) - len(japanese_title)) < 5):
            print(f"  Gemini response for \"{japanese_title}\" (\"{english_title}\") is too similar to original; considering UNKNOWN.")
            is_problematic_response = True
        
        if not is_problematic_response:
            if any('\u3040' <= char <= '\u309F' for char in english_title) or \
               any('\u30A0' <= char <= '\u30FF' for char in english_title) or \
               any('\u4E00' <= char <= '\u9FFF' for char in english_title):
                print(f"  Gemini response for \"{japanese_title}\" (\"{english_title}\") contains Japanese characters; considering UNKNOWN.")
                is_problematic_response = True
        
        if is_problematic_response:
            return None

        print(f"  Gemini suggested English title: \"{english_title}\" for \"{japanese_title}\"")
        return english_title
    except Exception as e:
        print(f"  Error calling Gemini API for \"{japanese_title}\": {type(e).__name__} - {e}")
        return None

# -----------------------------------------------------------------------------
# Wrapper for each scraper: logs start/end, catches exceptions, adds English titles
# -----------------------------------------------------------------------------
def _run_scraper_and_enrich(label: str, func):
    print(f"\n--- Scraping and Enriching: {label} ---")
    enriched_rows = []
    try:
        raw_rows = func() or []
        print(f"  Scraped {len(raw_rows)} raw showings from {label}.")

        for item in raw_rows:
            processed_item = item.copy()
            # Your modules use "title" or "movie_title" for the Japanese title.
            # Some modules like yebisu_garden and cine_quinto use "title".
            # Human Trust Cinema Shibuya used "movie_title" in the original JSON.
            # We need to standardize or check for multiple possible keys.
            japanese_title = item.get("title") or item.get("movie_title") # Check common keys
            english_title = None

            if isinstance(japanese_title, str) and japanese_title.strip():
                # TODO: Here you could add other lookup methods first if desired:
                # 1. Your manual mapping file (check first for overrides)
                #    english_title = get_from_manual_map(japanese_title)
                # 2. TMDb API call (good primary source)
                #    if not english_title:
                #        english_title = get_from_tmdb(japanese_title)

                # 3. Try Gemini if not found by other means (or as primary if preferred)
                if not english_title: # Only call Gemini if not found by other means
                    english_title = get_english_title_from_gemini(japanese_title)
                    if gemini_model: # Add delay only if Gemini was actually called
                         time.sleep(GEMINI_API_CALL_DELAY)
            elif japanese_title: # If it's not a string or is empty
                 print(f"  Warning: Japanese title is not a string or is empty for an item in {label}: {japanese_title}")

            processed_item['movie_title_japanese'] = japanese_title if isinstance(japanese_title, str) else None
            processed_item['movie_title_english'] = english_title if isinstance(english_title, str) else None
            
            # Optional: Standardize by removing original title key if now using the new ones
            # if 'title' in processed_item and 'movie_title_japanese' in processed_item:
            #     del processed_item['title']
            # if 'movie_title' in processed_item and 'movie_title_japanese' in processed_item:
            #     del processed_item['movie_title']

            enriched_rows.append(processed_item)
        
        print(f"  → Finished enriching. Returning {len(enriched_rows)} showings for {label}.")
        return enriched_rows
    except Exception as e:
        print(f"⚠️ Error in {label} during scraping or enrichment: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return [] # Return empty list on error for this module

# -----------------------------------------------------------------------------
# Main: invoke every scraper in turn
# -----------------------------------------------------------------------------
def run_all_scrapers_and_enrich():
    print("=============================================")
    print("   Starting All Scrapers & Enriching Titles  ")
    print("=============================================")
    start_time = time.time()
    all_listings = []

    # Calling each scraper using the new wrapper
    # Make sure the function names from your modules are correct here
    all_listings.extend(_run_scraper_and_enrich("Cinemart Shinjuku", cinemart_shinjuku_module.scrape_cinemart_shinjuku))
    all_listings.extend(_run_scraper_and_enrich("Theatre Image Forum", image_forum_module.scrape_image_forum))
    all_listings.extend(_run_scraper_and_enrich("Eurospace", eurospace_module.scrape_eurospace))
    all_listings.extend(_run_scraper_and_enrich("K's Cinema", ks_cinema_module.scrape_ks_cinema))
    all_listings.extend(_run_scraper_and_enrich("Shinjuku Musashino-kan", musashino_kan_module.scrape_musashino_kan))
    all_listings.extend(_run_scraper_and_enrich("Shin-Bungeiza", shin_bungeiza_module.scrape_shin_bungeiza))
    all_listings.extend(_run_scraper_and_enrich("Stranger", stranger_module.scrape_stranger))
    all_listings.extend(_run_scraper_and_enrich("Cinema Qualite", cinema_qualite_module.scrape_cinema_qualite))
    all_listings.extend(_run_scraper_and_enrich("Theatre Shinjuku", theatre_shinjuku_module.scrape_theatre_shinjuku))
    all_listings.extend(_run_scraper_and_enrich("Human Trust Cinema Shibuya", human_shibuya_module.scrape_human_shibuya))
    all_listings.extend(_run_scraper_and_enrich("Cine Quinto Shibuya", cine_quinto_module.scrape_cinequinto_shibuya))
    all_listings.extend(_run_scraper_and_enrich("YEBISU GARDEN CINEMA", yebisu_garden_module.scrape_ygc))
    all_listings.extend(_run_scraper_and_enrich("Theatre Guild Daikanyama", theatreguild_daikanyama_module.scrape_theatreguild_daikanyama))
    all_listings.extend(_run_scraper_and_enrich("Meguro Cinema", meguro_cinema_module.scrape_meguro_cinema))

    end_time = time.time()
    total_time = end_time - start_time
    print(f"\n--- All Scraping and Enrichment Complete ---")
    print(f"Collected a total of {len(all_listings)} enriched showings.")
    print(f"Total execution time: {total_time:.2f} seconds")
    return all_listings

# -----------------------------------------------------------------------------
# Dump to JSON file
# -----------------------------------------------------------------------------
def save_to_json(data, filename=OUTPUT_FILE):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved to {filename}")
    except Exception as e:
        print(f"⚠️ Failed to save {filename}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

# -----------------------------------------------------------------------------
# Entry-point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    final_listings = run_all_scrapers_and_enrich()
    
    # Optional: sort by cinema, date, time before saving
    # Ensure your items consistently have these keys for sorting to work reliably
    try:
        final_listings.sort(key=lambda x: (
            x.get("cinema", x.get("cinema_name", "")), # Check for 'cinema' or 'cinema_name'
            x.get("date_text", ""),
            x.get("showtime", "")
        ))
        print("INFO: Listings sorted by cinema, date, and showtime.")
    except Exception as e:
        print(f"WARNING: Could not sort listings due to missing keys or other error: {e}")
    
    save_to_json(final_listings)
    print("=============================================")
    print("                 Script Finished             ")
    print("=============================================")
