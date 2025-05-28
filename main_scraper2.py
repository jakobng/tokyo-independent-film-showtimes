#!/usr/bin/env python3
# main_scraper3.py

import json
import sys
import traceback 
import re 
import requests
import time
import os
import urllib.parse

# --- All cinema scraper modules ---
# (ENSURE ALL YOUR MODULES ARE LISTED HERE AND ACCESSIBLE)
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
import polepole_module

# --- Google Gemini API Import ---
try:
    import google.generativeai as genai
except ImportError:
    print("google-generativeai library not installed. Gemini functionality will be disabled.", file=sys.stderr)
    genai = None

# -----------------------------------------------------------------------------
# UTF-8 Output
# -----------------------------------------------------------------------------
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding.lower() != "utf-8":
            try: stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception: pass

# --- Configuration ---
TMDB_API_KEY = 'da2b1bc852355f12a86dd5e7ec48a1ee' 
TMDB_API_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_CACHE_FILE = "tmdb_cache.json"
LETTERBOXD_TMDB_BASE_URL = "https://letterboxd.com/tmdb/"
GEMINI_API_KEY = 'YOUR_GEMINI_API_KEY' # <<< --- PASTE YOUR KEY HERE
GEMINI_MODEL_NAME = 'gemini-1.5-flash'
gemini_model = None
EIGA_SEARCH_BASE_URL = "https://eiga.com/search/"
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# API Call Delays (in seconds) - Be mindful of TMDB's overall rate limits (e.g., 40-50 per 10s)
TMDB_SEARCH_DELAY = 0.3       # After initial search
TMDB_DETAILS_DELAY = 0.3      # After fetching details by ID
TMDB_ALT_TITLES_DELAY = 0.3   # After fetching alternative titles
GEMINI_DELAY = 1.0            # After Gemini call

# --- Helper Functions ---
def python_is_predominantly_latin(text):
    if not text: 
        return False # Or True, depending on how you want to treat empty/None for "is English"
    
    # Check if there's at least one Latin alphabet character
    if not re.search(r'[a-zA-Z]', text):
        return False # No Latin characters means it's not predominantly Latin

    # Count Japanese CJK characters (Hiragana, Katakana, common Kanji range)
    # This range \u4E00-\u9FFF covers most common Kanji.
    # Hiragana: \u3040-\u309F, Katakana: \u30A0-\u30FF
    japanese_chars = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text)
    latin_chars = re.findall(r'[a-zA-Z]', text) # Only count alphabet characters for "Latin"

    if not japanese_chars: # No Japanese characters found, and we know it has Latin from the check above
        return True
    
    # If both are present, consider it "Latin" if Latin chars are more numerous
    # or if there are very few Japanese characters compared to Latin.
    if latin_chars: # Should always be true due to the earlier check
        # Heuristic: If Japanese characters are present, Latin characters should be clearly dominant
        # For example, more than twice the number of Japanese characters, or very few Japanese characters overall.
        if len(latin_chars) > len(japanese_chars) * 2:
            return True
        if len(japanese_chars) <= 2 and len(latin_chars) > japanese_chars_count: # Allow a couple of JP chars if Latin is still more
            return True
        return False # Otherwise, if JP chars are present and Latin aren't clearly dominant, assume it's Japanese-like
        
    return False # Should not be reached if it has Latin characters

# --- Cache Functions (Unchanged) ---
def load_json_cache(cache_file_path, cache_name="Cache"):
    if os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, "r", encoding="utf-8") as f: cache = json.load(f)
            print(f"Loaded {len(cache)} items from {cache_name} ({cache_file_path}).")
            return cache
        except Exception as e: print(f"Error loading {cache_name}: {e}", file=sys.stderr)
    return {}

def save_json_cache(data, cache_file_path, cache_name="Cache"):
    try:
        with open(cache_file_path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e: print(f"Error saving {cache_name}: {e}", file=sys.stderr)

# --- Title Cleaning Function (Unchanged) ---
def clean_title_for_search(title):
    if not title: return ""
    cleaned_title = title
    cleaned_title = re.sub(r'^[\[\(（【][^\]\)）】]*[\]\)）】]', '', cleaned_title).strip()
    cleaned_title = re.sub(r'[\[\(（【][^\]\)）】]*[\]\)）】]$', '', cleaned_title).strip()
    suffixes_to_remove = [
        r'★トークショー付き', r'35mmフィルム上映', r'4Kレストア5\.1chヴァージョン',r'4Kデジタルリマスター版',
        r'4Kレストア版', r'４Kレーザー上映', r'４K版', r'４K', r'4K',
        r'（字幕版）', r'（字幕）', r'（吹替版）', r'（吹替）',
        r'\s*THE MOVIE$', r'\[受賞感謝上映］', r'★上映後トーク付', r'トークイベント付き',
        r'vol\.\s*\d+', r'［[^］]+(?:ｲﾍﾞﾝﾄ|イベント)］', r'ライブ音響上映', r'特別音響上映',
        r'字幕付き上映', r'デジタルリマスター版', r'【完成披露試写会】', r'Blu-ray発売記念上映',
        r'公開記念舞台挨拶', r'上映後舞台挨拶', r'初日舞台挨拶', r'２日目舞台挨拶',
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

# --- TMDB Film Details Fetching Function (Enhanced for better English title retrieval) ---
def get_tmdb_film_details(search_title, api_key, session, year=None):
    default_return = {"id": None, "tmdb_title": None, "tmdb_original_title": None}
    if not search_title: return default_return
    if not api_key:
        print("TMDB API Key missing for TMDB search.", file=sys.stderr)
        return default_return

    # Step 1: Initial search using Japanese title
    search_params = {'api_key': api_key, 'query': search_title, 'language': 'ja-JP', 'include_adult': 'false'}
    if year: search_params['primary_release_year'] = year
    search_url = f"{TMDB_API_BASE_URL}/search/movie"
    print(f"Searching TMDB (JA) for: '{search_title}' (Year: {year or 'Any'})")
    
    tmdb_id = None
    id_found_search_title = None 
    id_found_search_original = None

    try:
        response = session.get(search_url, params=search_params, headers=REQUEST_HEADERS, timeout=10)
        time.sleep(TMDB_SEARCH_DELAY)
        response.raise_for_status()
        data = response.json()
        if data['results']:
            best_match = None
            for r_item in data['results'][:5]: # Check more results for better matching
                if r_item.get('original_title', '').strip().lower() == search_title.lower():
                    best_match = r_item; print(f"TMDB: Exact original_title match: '{search_title}'"); break
            if not best_match:
                for r_item in data['results'][:5]:
                    if r_item.get('title', '').strip().lower() == search_title.lower():
                        best_match = r_item; print(f"TMDB: Exact title match: '{search_title}'"); break
            if not best_match and data['results']: # Fallback
                r0_title = data['results'][0].get('title','').lower()
                st_lower = search_title.lower()
                if st_lower in r0_title or (len(st_lower) > 3 and r0_title in st_lower):
                    best_match = data['results'][0]; print(f"TMDB: Fallback substring match for '{search_title}'")
            
            if best_match:
                tmdb_id = best_match.get('id')
                id_found_search_title = best_match.get('title')
                id_found_search_original = best_match.get('original_title')
                print(f"TMDB ID {tmdb_id} found via JA search. Search Title: '{id_found_search_title}', Search Original: '{id_found_search_original}'")
    except Exception as e:
        print(f"Error TMDB JA search for '{search_title}': {e}", file=sys.stderr)
        return None # Indicates a fatal error in this stage, distinct from no results

    if not tmdb_id:
        print(f"No TMDB ID for '{search_title}' from JA search.")
        return default_return

    # Step 2: ID found, fetch details in English
    chosen_display_title = id_found_search_title # Fallback
    tmdb_api_original_title = id_found_search_original # Fallback
    
    try:
        details_url = f"{TMDB_API_BASE_URL}/movie/{tmdb_id}?api_key={api_key}&language=en-US"
        print(f"Fetching TMDB details (EN) for ID {tmdb_id}")
        details_response = session.get(details_url, headers=REQUEST_HEADERS, timeout=10)
        time.sleep(TMDB_DETAILS_DELAY)
        details_response.raise_for_status()
        details_data = details_response.json()
        
        api_en_title = details_data.get('title')
        api_en_original_title_from_details = details_data.get('original_title')
        
        chosen_display_title = api_en_title if api_en_title else chosen_display_title
        tmdb_api_original_title = api_en_original_title_from_details if api_en_original_title_from_details else tmdb_api_original_title

        # If en-US title still looks Japanese, AND en_us_original_title looks Latin and is different, prefer original.
        if chosen_display_title and not python_is_predominantly_latin(chosen_display_title):
            if tmdb_api_original_title and python_is_predominantly_latin(tmdb_api_original_title) and \
               tmdb_api_original_title.lower() != chosen_display_title.lower():
                print(f"TMDB en-US title ('{chosen_display_title}') non-Latin. Preferring original_title ('{tmdb_api_original_title}').")
                chosen_display_title = tmdb_api_original_title
        
        # Step 3: If chosen_display_title STILL looks Japanese, try alternative titles from TMDB
        if chosen_display_title and not python_is_predominantly_latin(chosen_display_title):
            print(f"Chosen title ('{chosen_display_title}') still non-Latin. Fetching TMDB alternative titles for {tmdb_id}.")
            alt_titles_url = f"{TMDB_API_BASE_URL}/movie/{tmdb_id}/alternative_titles?api_key={api_key}" # Get all countries' alt titles
            alt_titles_response = session.get(alt_titles_url, headers=REQUEST_HEADERS, timeout=10)
            time.sleep(TMDB_ALT_TITLES_DELAY)
            alt_titles_response.raise_for_status()
            alt_titles_data = alt_titles_response.json()
            
            found_alt_en_title = None
            if 'titles' in alt_titles_data:
                # Prioritize US, then GB, then any other predominantly Latin
                for country_code in ['US', 'GB']:
                    for alt_obj in alt_titles_data['titles']:
                        if alt_obj.get('iso_3166_1') == country_code and python_is_predominantly_latin(alt_obj.get('title')):
                            found_alt_en_title = alt_obj.get('title'); break
                    if found_alt_en_title: break
                
                if not found_alt_en_title: # If no specific US/GB, check other Latin alternatives
                    for alt_obj in alt_titles_data['titles']:
                        alt_t = alt_obj.get('title')
                        # Check if it's predominantly Latin and different from the current non-Latin chosen_display_title
                        if alt_t and python_is_predominantly_latin(alt_t) and alt_t.lower() != chosen_display_title.lower():
                            found_alt_en_title = alt_t; break 
            
            if found_alt_en_title:
                print(f"Found good alternative English title: '{found_alt_en_title}'")
                chosen_display_title = found_alt_en_title
        
        print(f"Final TMDB Display: '{chosen_display_title}', Original from API: '{tmdb_api_original_title}'")
        return {"id": tmdb_id, "tmdb_title": chosen_display_title, "tmdb_original_title": tmdb_api_original_title}

    except Exception as e:
        print(f"Error fetching EN details/alternatives for ID {tmdb_id}: {e}. Using JA search titles as fallback.", file=sys.stderr)
        return {"id": tmdb_id, "tmdb_title": id_found_search_title, "tmdb_original_title": id_found_search_original, "details_fetch_error": True}


# --- Gemini Function (Unchanged from your last script version) ---
def get_gemini_english_title(cleaned_film_title, original_title_for_context, session, year=None):
    global gemini_model
    if not gemini_model: return None
    if not cleaned_film_title and not original_title_for_context: return None
    title_to_use_for_prompt = original_title_for_context or cleaned_film_title 
    # print(f"Asking Gemini for English title of: '{title_to_use_for_prompt}' (Cleaned: '{cleaned_film_title}')")
    year_info = f" (believed to be released around {year})" if year else ""
    prompt = (
        f"What is the most common or official English title for the Japanese film titled: '{title_to_use_for_prompt}'{year_info}?\n"
        "If there are multiple English titles, provide the most widely recognized one.\n"
        "If no official or common English title is widely recognized, provide a direct, accurate English translation of the Japanese title if it makes sense as a film title.\n"
        "If the film is not Japanese, or if you absolutely cannot determine any English title or a reasonable translation that could be a film title, return the exact phrase 'NO_TITLE_FOUND'.\n"
        "Respond with ONLY the English title/translation OR 'NO_TITLE_FOUND'."
    )
    try:
        response = gemini_model.generate_content(prompt)
        english_title = response.text.strip()
        english_title = re.sub(r"^(English Title:|Title:|Translation:)\s*", "", english_title, flags=re.IGNORECASE).strip()
        english_title = english_title.replace('"', '').replace("'", "")
        if english_title.endswith('.') and english_title.count('.') == 1 and len(english_title) > 1:
            english_title = english_title[:-1].strip()
        if english_title and english_title.upper() != "NO_TITLE_FOUND" and len(english_title) > 2:
            if len(english_title) > 150 or '\n' in english_title: 
                print(f"Gemini: Unusual response for '{title_to_use_for_prompt}'. Treating as no title.", file=sys.stderr)
                return "NO_TITLE_FOUND"
            print(f"Gemini: Found for '{title_to_use_for_prompt}': '{english_title}'")
            return english_title
        print(f"Gemini: No usable title for '{title_to_use_for_prompt}'. Response: '{english_title}'")
        return "NO_TITLE_FOUND"
    except Exception as e:
        print(f"Error querying Gemini for '{title_to_use_for_prompt}': {e}", file=sys.stderr)
        return None

# --- Eiga.com Search Link Function (Unchanged) ---
def get_eiga_search_link(original_film_title):
    if not original_film_title: return None
    return f"{EIGA_SEARCH_BASE_URL}{urllib.parse.quote(original_film_title)}"

# --- Main Enrichment Function (Simplified Flow, using updated get_tmdb_film_details) ---
def enrich_listings_with_tmdb_links(all_listings, cache_data, session, tmdb_api_key_param):
    if not all_listings: return []
    items_to_process_details = []
    for listing in all_listings:
        listing.update({'letterboxd_link': None, 'tmdb_display_title': None, 
                        'gemini_english_title': None, 'eiga_search_link': None,
                        'tmdb_original_title': None})
        original_title = (listing.get('title') or listing.get('movie_title') or "").strip()
        year_match = re.search(r'\b(19[7-9]\d|20[0-2]\d)\b', original_title)
        year_for_context = year_match.group(1) if year_match else None
        if not original_title or original_title.lower() in ["unknown title", "unknown film", "n/a"]: continue
        cleaned_title = clean_title_for_search(original_title)
        if not cleaned_title:
            print(f"Original title '{original_title}' cleaned to empty. Skipping.")
            continue
        items_to_process_details.append({
            "listing_obj": listing, "original_title": original_title, 
            "cleaned_title": cleaned_title, "year_for_context": year_for_context
        })

    print(f"\nStarting enrichment for {len(items_to_process_details)} listings...")
    processed_or_fetched_count = 0

    for item_detail in items_to_process_details:
        cleaned_title = item_detail["cleaned_title"]
        original_title = item_detail["original_title"]
        year_for_context = item_detail["year_for_context"]
        listing_obj = item_detail["listing_obj"]
        
        cached_entry = cache_data.get(cleaned_title)
        needs_processing = False

        if not isinstance(cached_entry, dict):
            needs_processing = True
            log_msg = f"--- Cache entry for '{cleaned_title}' is invalid/missing. Re-fetching. ---" if cleaned_title in cache_data else f"--- Processing new title: '{cleaned_title}' (Original: '{original_title}') ---"
            print(log_msg)
        # Check if it's a non-error, no-ID entry that's missing Eiga link (might be from an older partial run)
        elif cached_entry.get("id") is None and not cached_entry.get("api_error") and "eiga_search_link" not in cached_entry:
            needs_processing = True
            print(f"--- Incomplete cache for '{cleaned_title}' (no TMDB ID, missing Eiga link). Re-evaluating. ---")

        if needs_processing:
            processed_or_fetched_count += 1
            current_cache_data_to_write = {"id": None, "tmdb_title": None, "tmdb_original_title": None} 

            tmdb_result = get_tmdb_film_details(cleaned_title, tmdb_api_key_param, session, year_for_context)
            # get_tmdb_film_details handles its own internal sleeps.
            
            if tmdb_result is None: 
                print(f"TMDB API call(s) critically failed for '{cleaned_title}'. Marking error.")
                current_cache_data_to_write["api_error"] = True
            elif tmdb_result.get("id"): 
                print(f"TMDB success for '{cleaned_title}'. ID: {tmdb_result['id']}, Display Title: {tmdb_result.get('tmdb_title')}")
                current_cache_data_to_write = tmdb_result 
            else: # No TMDB ID found (tmdb_result is not None, but id is None)
                current_cache_data_to_write.update(tmdb_result) 
            
            # If no TMDB ID after all attempts, OR TMDB API itself failed, get Eiga & Gemini
            if current_cache_data_to_write.get("id") is None or current_cache_data_to_write.get("api_error"):
                print(f"No TMDB ID for '{cleaned_title}' (or API error). Adding Eiga link and trying Gemini.")
                current_cache_data_to_write["eiga_search_link"] = get_eiga_search_link(original_title)
                
                gemini_title = get_gemini_english_title(cleaned_title, original_title, session, year_for_context)
                time.sleep(GEMINI_DELAY) 
                if gemini_title and gemini_title.upper() != "NO_TITLE_FOUND" and gemini_title is not None:
                    current_cache_data_to_write["gemini_english_title"] = gemini_title
                else:
                    print(f"Gemini did not provide a usable English title for '{cleaned_title}'.")
            
            cache_data[cleaned_title] = current_cache_data_to_write
            save_json_cache(cache_data, TMDB_CACHE_FILE, "TMDB/Extended Cache")
            cached_entry = current_cache_data_to_write 

        # Populate listing_obj
        if isinstance(cached_entry, dict):
            if cached_entry.get("id"):
                listing_obj['letterboxd_link'] = f"{LETTERBOXD_TMDB_BASE_URL}{cached_entry['id']}"
                listing_obj['tmdb_display_title'] = cached_entry.get('tmdb_title') or cached_entry.get('title') 
                listing_obj['tmdb_original_title'] = cached_entry.get('tmdb_original_title') 
            if not listing_obj.get('letterboxd_link'): 
                if cached_entry.get("eiga_search_link"):
                    listing_obj['eiga_search_link'] = cached_entry.get("eiga_search_link")
                if cached_entry.get("gemini_english_title"):
                    listing_obj['gemini_english_title'] = cached_entry.get("gemini_english_title")
        else:
            print(f"Warning: No valid cache entry for '{cleaned_title}' for final population.", file=sys.stderr)

    if processed_or_fetched_count > 0:
        print(f"\nData processed/fetched for {processed_or_fetched_count} titles this run.")
    else:
        print("\nNo new data processing triggered; all titles likely had complete cache entries.")
    return all_listings

# --- Scraper Invocation & Main Block ---
def _run_scraper(label: str, func): # ... (same as before)
    print(f"\nScraping {label} …")
    try:
        rows = func() or []
        print(f"→ {len(rows)} showings from {label}.")
        return rows
    except Exception as e:
        print(f"⚠️ Error in {label}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return []

def run_all_scrapers(): # ... (same as before, ensure all modules are listed)
    print("Starting all scrapers…")
    all_listings = []
    all_listings += _run_scraper("Cinemart Shinjuku", cinemart_shinjuku_module.scrape_cinemart_shinjuku)
    all_listings += _run_scraper("Eurospace", eurospace_module.scrape_eurospace) # Make sure this is imported
    all_listings += _run_scraper("Theatre Image Forum", image_forum_module.scrape_image_forum)
    all_listings += _run_scraper("K's Cinema", ks_cinema_module.scrape_ks_cinema)
    all_listings += _run_scraper("Shinjuku Musashino-kan", musashino_kan_module.scrape_musashino_kan)
    all_listings += _run_scraper("Shin-Bungeiza", shin_bungeiza_module.scrape_shin_bungeiza)
    all_listings += _run_scraper("Stranger", stranger_module.scrape_stranger)
    all_listings += _run_scraper("Cinema Qualite", cinema_qualite_module.scrape_cinema_qualite)
    all_listings += _run_scraper("Theatre Shinjuku", theatre_shinjuku_module.scrape_theatre_shinjuku)
    all_listings += _run_scraper("Human Trust Cinema Shibuya", human_shibuya_module.scrape_human_shibuya)
    all_listings += _run_scraper("Cine Quinto Shibuya", cine_quinto_module.scrape_cinequinto_shibuya)
    all_listings += _run_scraper("YEBISU GARDEN CINEMA", yebisu_garden_module.scrape_ygc)
    all_listings += _run_scraper("Theatre Guild Daikanyama", theatreguild_daikanyama_module.scrape_theatreguild_daikanyama)
    all_listings += _run_scraper("Meguro Cinema", meguro_cinema_module.scrape_meguro_cinema)
    all_listings += _run_scraper("Pole-Pole Higashi-Nakano", polepole_module.scrape_polepole)
    print(f"\nCollected a total of {len(all_listings)} showings.")
    return all_listings

def save_to_json(data, filename="showtimes.json"): # ... (same as before)
    try:
        with open(filename, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved to {filename}")
    except Exception as e: print(f"⚠️ Failed to save {filename}: {e}", file=sys.stderr)

if __name__ == "__main__": # ... (same as before)
    if genai and GEMINI_API_KEY and GEMINI_API_KEY != 'YOUR_GEMINI_API_KEY':
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            gemini_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
            print(f"Gemini AI model '{GEMINI_MODEL_NAME}' initialized.")
        except Exception as e:
            print(f"Could not initialize Gemini model: {e}", file=sys.stderr)
            gemini_model = None
    elif genai: print("--- WARNING: Gemini API KEY IS MISSING or placeholder. ---")
    else: print("--- WARNING: google-generativeai library not found. ---")

    tmdb_extended_cache = load_json_cache(TMDB_CACHE_FILE, "TMDB/Extended Cache")
    external_api_session = requests.Session()
    active_tmdb_api_key = TMDB_API_KEY
    if not active_tmdb_api_key: print("--- WARNING: TMDB API KEY IS MISSING. ---")
    
    listings = run_all_scrapers()
    enriched_listings = enrich_listings_with_tmdb_links(
        listings, tmdb_extended_cache, external_api_session, active_tmdb_api_key
    )
    try:
        enriched_listings.sort(key=lambda x: (
            x.get("cinema_name") or x.get("cinema", ""), x.get("date_text", ""), x.get("showtime", "")
        ))
    except Exception as e: print(f"Warning: Could not sort listings: {e}", file=sys.stderr)
    save_to_json(enriched_listings)
    print("Enrichment process complete.")
