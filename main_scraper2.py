#!/usr/bin/env python3
# main_scraper2.py

import json
import sys
import traceback # For detailed error printing
import re # For title cleaning and href validation

# --- All cinema scraper modules ---
import cinemart_shinjuku_module
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
import theatreguild_daikanyama_module
import meguro_cinema_module
import polepole_module

# --- External API functionality imports ---
import requests
# from bs4 import BeautifulSoup # No longer needed as Eiga.com HTML parsing is out
# import urllib.parse # No longer needed as Eiga.com HTML parsing is out
import time
import os

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

# --- Start: Configuration and Functions for TMDB/Letterboxd Links ---

# TMDB API Configuration
TMDB_API_KEY = 'da2b1bc852355f12a86dd5e7ec48a1ee' # Your TMDB API Key
TMDB_API_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_CACHE_FILE = "tmdb_cache.json"
LETTERBOXD_TMDB_BASE_URL = "https://letterboxd.com/tmdb/"

REQUEST_HEADERS = { 
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Cache Functions ---
def load_json_cache(cache_file_path, cache_name="Cache"):
    """Generic function to load a JSON cache file."""
    if os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
                print(f"Loaded {len(cache)} items from {cache_name} ({cache_file_path}).")
                return cache
        except Exception as e:
            print(f"Error loading {cache_name} from {cache_file_path}: {e}", file=sys.stderr)
    return {}

def save_json_cache(data, cache_file_path, cache_name="Cache"):
    """Generic function to save data to a JSON cache file."""
    try:
        with open(cache_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {cache_name} to {cache_file_path}: {e}", file=sys.stderr)

# --- Title Cleaning Function ---
def clean_title_for_search(title):
    """Cleans film titles to improve search results."""
    if not title:
        return ""
    
    cleaned_title = title
    
    cleaned_title = re.sub(r'^[\[\(（【][^\]\)）】]*[\]\)）】]', '', cleaned_title).strip()
    cleaned_title = re.sub(r'[\[\(（【][^\]\)）】]*[\]\)）】]$', '', cleaned_title).strip()
    cleaned_title = re.sub(r'^[\[\(（【][^\]\)）】]+[\]\)）】]', '', cleaned_title).strip()
    cleaned_title = re.sub(r'[\[\(（【][^\]\)）】]+[\]\)）】]$', '', cleaned_title).strip()

    suffixes_to_remove = [
        r'★トークショー付き', r'35mmフィルム上映', r'4Kレストア5\.1chヴァージョン',r'4Kデジタルリマスター版',
        r'4Kレストア版', r'４Kレーザー上映', r'４K版', r'４K', r'4K',
        r'（字幕版）', r'（字幕）', r'（吹替版）', r'（吹替）',
        r'\s*THE MOVIE$', 
        r'\[受賞感謝上映］', r'★上映後トーク付', r'トークイベント付き',
        r'vol\.\s*\d+', 
        r'［[^］]+(?:ｲﾍﾞﾝﾄ|イベント)］',
        r'ライブ音響上映', r'特別音響上映', r'字幕付き上映',
        r'デジタルリマスター版', r'【完成披露試写会】',
        r'Blu-ray発売記念上映', r'公開記念舞台挨拶', r'上映後舞台挨拶', r'初日舞台挨拶', r'２日目舞台挨拶',
        r'トークショー', r'一挙上映',
    ]
    for suffix_pattern in suffixes_to_remove:
        cleaned_title = re.sub(suffix_pattern, '', cleaned_title, flags=re.IGNORECASE).strip()

    cleaned_title = re.sub(r'\s*[ァ-ヶА-я一-龠々]+公開版$', '', cleaned_title).strip()
    
    if cleaned_title:
        cleaned_title = re.sub(r'^[^\w\'"]+', '', cleaned_title)
        cleaned_title = re.sub(r'[^\w\'"]+$', '', cleaned_title)
        cleaned_title = cleaned_title.replace('　', ' ').strip()
        cleaned_title = re.sub(r'\s{2,}', ' ', cleaned_title)

    return cleaned_title.strip()

# --- TMDB Film Details Fetching Function ---
def get_tmdb_film_details(cleaned_film_title, api_key, session, year=None):
    if not cleaned_film_title:
        print("Skipping TMDB search for empty (cleaned) title.")
        return None
    if not api_key: 
        print("TMDB API Key not provided. Skipping TMDB search.", file=sys.stderr)
        return None

    search_params = {
        'api_key': api_key,
        'query': cleaned_film_title,
        'language': 'ja-JP', 
        'include_adult': 'false'
    }
    # if year: # Year parameter is ready for future use
    #     search_params['year'] = year

    search_url = f"{TMDB_API_BASE_URL}/search/movie"
    print(f"Searching TMDB for (cleaned): '{cleaned_film_title}' (Year: {year or 'Any'})")

    try:
        response = session.get(search_url, params=search_params, headers=REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['results']:
            best_match = None
            for result in data['results'][:3]: 
                if result.get('original_title', '').strip().lower() == cleaned_film_title.lower():
                    best_match = result
                    print(f"TMDB: Exact original_title match for '{cleaned_film_title}'.")
                    break
            
            if not best_match:
                for result in data['results'][:3]:
                    if result.get('title', '').strip().lower() == cleaned_film_title.lower():
                        best_match = result
                        print(f"TMDB: Exact title match for '{cleaned_film_title}'.")
                        break
            
            if not best_match:
                first_result_title_lower = data['results'][0].get('title', '').lower()
                cleaned_film_title_lower = cleaned_film_title.lower()
                if cleaned_film_title_lower in first_result_title_lower or \
                   (len(cleaned_film_title_lower) > 3 and first_result_title_lower in cleaned_film_title_lower):
                    best_match = data['results'][0]
                    print(f"TMDB: Fallback to first result (substring/similarity) for '{cleaned_film_title}'. TMDB Title: '{data['results'][0].get('title')}'")
                else:
                    print(f"TMDB: First result title ('{data['results'][0].get('title')}') not a strong substring match for '{cleaned_film_title}'. No TMDB ID assigned.")
                    return None

            if best_match:
                tmdb_id = best_match.get('id')
                tmdb_title = best_match.get('title') # This is usually the most common title, often English
                tmdb_original_title = best_match.get('original_title')
                print(f"Selected TMDB match for '{cleaned_film_title}': ID={tmdb_id}, Title='{tmdb_title}' (Original: '{tmdb_original_title}')")
                # Return the ID and the title TMDB uses (often English or most common)
                return {"id": tmdb_id, "tmdb_title": tmdb_title} 
        else:
            print(f"No TMDB results found for (cleaned): '{cleaned_film_title}'.")
            
    except requests.exceptions.Timeout:
        print(f"Timeout searching TMDB for (cleaned): '{cleaned_film_title}'", file=sys.stderr)
    except requests.exceptions.RequestException as e:
        print(f"Error searching TMDB for (cleaned): '{cleaned_film_title}': {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error processing TMDB for (cleaned): '{cleaned_film_title}': {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return None

# --- Main Enrichment Function (TMDB/Letterboxd only) ---
def enrich_listings_with_tmdb_links(all_listings, tmdb_cache, session, tmdb_api_key_param):
    if not all_listings:
        return []

    unique_cleaned_titles_to_fetch = set()
    processing_details = [] 

    for listing in all_listings:
        listing['letterboxd_link'] = None
        listing['tmdb_display_title'] = None # Initialize new field

        original_title = (listing.get('title') or listing.get('movie_title') or "").strip()
        if not original_title or original_title.lower() in ["unknown title", "unknown film", "n/a"]:
            continue

        cleaned_title = clean_title_for_search(original_title)
        if not cleaned_title:
            print(f"Original title '{original_title}' cleaned to empty. Skipping TMDB link.")
            continue
        
        processing_details.append({
            'listing_obj': listing,
            'cleaned_title': cleaned_title
        })
        
        if tmdb_api_key_param and cleaned_title not in tmdb_cache:
            unique_cleaned_titles_to_fetch.add(cleaned_title)

    if unique_cleaned_titles_to_fetch:
        print(f"\nNeed to fetch TMDB data for {len(unique_cleaned_titles_to_fetch)} new unique cleaned titles.")
        fetched_count_this_run = 0
        for cleaned_title_to_search in sorted(list(unique_cleaned_titles_to_fetch)):
            
            if tmdb_api_key_param:
                tmdb_details = get_tmdb_film_details(cleaned_title_to_search, tmdb_api_key_param, session)
                tmdb_cache[cleaned_title_to_search] = tmdb_details # Cache now stores dict: {"id": ..., "tmdb_title": ...} or None
                save_json_cache(tmdb_cache, TMDB_CACHE_FILE, "TMDB Cache")
                fetched_count_this_run +=1
                time.sleep(0.6) 
        
        if fetched_count_this_run > 0:
             print(f"Fetched and cached TMDB data for {fetched_count_this_run} titles.")
    else:
        print("\nNo new unique cleaned titles to fetch TMDB data for; all should be from cache.")
        
    for item_detail in processing_details:
        tmdb_details_from_cache = tmdb_cache.get(item_detail['cleaned_title'])
        letterboxd_url_to_assign = None
        tmdb_title_to_assign = None

        if tmdb_details_from_cache and isinstance(tmdb_details_from_cache, dict) and tmdb_details_from_cache.get('id'):
            letterboxd_url_to_assign = f"{LETTERBOXD_TMDB_BASE_URL}{tmdb_details_from_cache['id']}"
            tmdb_title_to_assign = tmdb_details_from_cache.get('tmdb_title') # Get the display title from TMDB
        
        item_detail['listing_obj']['letterboxd_link'] = letterboxd_url_to_assign
        item_detail['listing_obj']['tmdb_display_title'] = tmdb_title_to_assign # Add to listing
            
    for listing in all_listings:
        if 'letterboxd_link' not in listing:
             listing['letterboxd_link'] = None
        if 'tmdb_display_title' not in listing: 
             listing['tmdb_display_title'] = None
            
    return all_listings

# --- End: Code for TMDB/Letterboxd Links ---

# -----------------------------------------------------------------------------
# Wrapper for each scraper
# -----------------------------------------------------------------------------
def _run_scraper(label: str, func):
    print(f"\nScraping {label} …")
    try:
        rows = func() or []
        print(f"→ {len(rows)} showings from {label}.")
        return rows
    except Exception as e:
        print(f"⚠️ Error in {label}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return []

# -----------------------------------------------------------------------------
# Main: invoke every scraper
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
    all_listings += _run_scraper("YEBISU GARDEN CINEMA",      yebisu_garden_module.scrape_ygc)
    all_listings += _run_scraper("Theatre Guild Daikanyama",  theatreguild_daikanyama_module.scrape_theatreguild_daikanyama)
    all_listings += _run_scraper("Meguro Cinema",             meguro_cinema_module.scrape_meguro_cinema)
    all_listings += _run_scraper("Pole-Pole Higashi-Nakano",   polepole_module.scrape_polepole)
   
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
    tmdb_data_cache = load_json_cache(TMDB_CACHE_FILE, "TMDB Cache")
    
    external_api_session = requests.Session() 

    active_tmdb_api_key = TMDB_API_KEY
    if not active_tmdb_api_key: 
        print("---")
        print("!!! TMDB API KEY IS MISSING in main_scraper2.py. !!!")
        print("!!! TMDB/Letterboxd links will NOT be fetched.    !!!")
        print("---")
    
    listings = run_all_scrapers()

    print(f"\nEnriching {len(listings)} listings with Letterboxd links (via TMDB)...")
    enriched_listings = enrich_listings_with_tmdb_links(
        listings, 
        tmdb_data_cache,
        external_api_session,
        active_tmdb_api_key
    )

    try:
        enriched_listings.sort(key=lambda x: (
            x.get("cinema_name") or x.get("cinema", ""), 
            x.get("date_text", ""),
            x.get("showtime", "")
        ))
    except Exception as e:
        print(f"Warning: Could not sort listings after enrichment: {e}", file=sys.stderr)
        pass

    save_to_json(enriched_listings)
    print("TMDB/Letterboxd link enrichment process complete. TMDB Cache saved during enrichment if new data fetched.")