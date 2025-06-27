#!/usr/bin/env python3
# main_scraper.py (Complete version calling all provided modules)

import json
import sys
import traceback
import re
import requests
import time
import os
import urllib.parse
from bs4 import BeautifulSoup

# --- All cinema scraper modules ---
# NOTE: This list now includes all modules you have provided code for.
import bluestudio_module
import cine_switch_ginza_module
import eurospace_module
import human_shibuya_module
import human_yurakucho_module
import image_forum_module
import ks_cinema_module
import laputa_asagaya_module
import meguro_cinema_module
import musashino_kan_module
import nfaj_calendar_module as nfaj_module  # Using the alias as requested
import polepole_module
import shin_bungeiza_module
import shimotakaido_module
import stranger_module
import theatre_shinjuku_module
import waseda_shochiku_module
import cinemart_shinjuku_module
import cinema_qualite_module
import cine_quinto_module
import yebisu_garden_module
import k2_cinema_module
import cinema_rosa_module
import chupki_module
import bunkamura_module

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
TMDB_API_KEY = 'da2b1bc852355f12a86dd5e7ec48a1ee' # Replace with your actual key if needed
TMDB_API_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_CACHE_FILE = "tmdb_cache.json"
LETTERBOXD_TMDB_BASE_URL = "https://letterboxd.com/tmdb/"
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
# ---
GEMINI_MODEL_NAME = 'gemini-2.5-flash'
gemini_model = None
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
TMDB_SEARCH_DELAY = 0.3
TMDB_DETAILS_DELAY = 0.3
TMDB_ALT_TITLES_DELAY = 0.3
GEMINI_DELAY = 1.0
LETTERBOXD_SCRAPE_DELAY = 0.5

# --- Helper Functions ---
def python_is_predominantly_latin(text):
    if not text: return False
    if not re.search(r'[a-zA-Z]', text): return False
    japanese_chars = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text)
    latin_chars = re.findall(r'[a-zA-Z]', text)
    if not japanese_chars: return True
    if latin_chars:
        if len(latin_chars) > len(japanese_chars) * 2: return True
        if len(japanese_chars) <= 2 and len(latin_chars) > len(japanese_chars): return True
        return False
    return False

# --- Schema Normalization for Eurospace ---
def _normalize_eurospace_schema(listings: list) -> list:
    """Converts the unique schema from Eurospace to the standard project schema."""
    normalized = []
    for show in listings:
        normalized.append({
            "cinema_name": show.get("cinema"),
            "movie_title": show.get("title"),
            "date_text": show.get("date"),
            "showtime": show.get("time"),
            "detail_page_url": show.get("url"),
            "director": show.get("director"),
            "year": str(show["year"]) if show.get("year") else "",
            "country": show.get("country"),
            "runtime_min": str(show["runtime"]) if show.get("runtime") else "",
            "synopsis": "",
            "movie_title_en": "",
        })
    return normalized

# --- Cache Functions ---
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

# --- Title Cleaning Function ---
def clean_title_for_search(title):
    if not title: return ""
    cleaned_title = title
    cleaned_title = re.sub(r'^[\[\(（【][^\]\)）】]*[\]\)）】]', '', cleaned_title).strip()
    
    suffixes_to_remove = [
        r'\s*★トークショー付き', r'\s*35mmフィルム上映', r'\s*4Kレストア5\.1chヴァージョン', r'\s*4Kデジタルリマスター版',
        r'\s*4Kレストア版', r'\s*４Kレーザー上映', r'\s*４K版', r'\s*４K', r'\s*4K', r'\s*（字幕版）', r'\s*（字幕）', 
        r'\s*（吹替版）', r'\s*（吹替）', r'\s*THE MOVIE$', r'\s*\[受賞感謝上映］', r'\s*★上映後トーク付', 
        r'\s*トークイベント付き', r'\s*vol\.\s*\d+', r'\s*［[^］]+(?:ｲﾍﾞﾝﾄ|イベント)］', r'\s*ライブ音響上映', 
        r'\s*特別音響上映', r'\s*字幕付き上映', r'\s*デジタルリマスター版', r'\s*【完成披露試写会】', r'\s*Blu-ray発売記念上映',
        r'\s*公開記念舞台挨拶', r'\s*上映後舞台挨拶', r'\s*初日舞台挨拶', r'\s*２日目舞台挨拶', r'\s*トークショー', r'\s*一挙上映',
    ]
    for suffix_pattern in suffixes_to_remove:
        cleaned_title = re.sub(f'{suffix_pattern}$', '', cleaned_title, flags=re.IGNORECASE).strip()

    cleaned_title = re.sub(r'\s*[ァ-ヶА-я一-龠々]+公開版$', '', cleaned_title).strip()
    if cleaned_title:
        cleaned_title = cleaned_title.replace('：', ':').replace('　', ' ').strip()
        cleaned_title = re.sub(r'\s{2,}', ' ', cleaned_title)
    return cleaned_title.strip()

# --- TMDB Film Details Fetching Function (MODIFIED) ---
def get_tmdb_film_details(search_title, api_key, session, year=None, language_code=None):
    default_return = {"id": None, "tmdb_title": None, "tmdb_original_title": None}
    if not search_title: return default_return
    if not api_key:
        return default_return

    # Dynamically build search params
    search_params = {'api_key': api_key, 'query': search_title, 'include_adult': 'false'}
    if year:
        search_params['primary_release_year'] = year
    # Only add the language parameter if it's provided
    if language_code:
        search_params['language'] = language_code
    
    search_url = f"{TMDB_API_BASE_URL}/search/movie"
    
    lang_info = f" (Language: {language_code})" if language_code else " (Language: Any)"
    print(f"Searching TMDB for: '{search_title}' (Year: {year or 'Any'}){lang_info}")
    
    try:
        response = session.get(search_url, params=search_params, headers=REQUEST_HEADERS, timeout=10)
        time.sleep(TMDB_SEARCH_DELAY)
        response.raise_for_status()
        search_data = response.json()
    except Exception as e:
        print(f"Error during TMDB search for '{search_title}': {e}", file=sys.stderr)
        return default_return

    if not search_data or not search_data.get('results'):
        print(f"No TMDB results for '{search_title}'.")
        return default_return

    best_match = None
    highest_score = -1
    st_lower = search_title.lower()

    for result in search_data['results'][:10]:
        score = 0
        res_title_ja = (result.get('title') or "").lower()
        res_title_orig = (result.get('original_title') or "").lower()
        
        if st_lower == res_title_ja or st_lower == res_title_orig:
            score += 100
        elif st_lower in res_title_ja or st_lower in res_title_orig:
            score += 50
        
        release_date = result.get('release_date', '')
        if year and release_date:
            try:
                release_year = int(release_date.split('-')[0])
                if release_year == int(year):
                    score += 200
                elif abs(release_year - int(year)) == 1:
                    score += 50
            except (ValueError, IndexError):
                pass

        score += result.get('popularity', 0) / 100

        if score > highest_score:
            highest_score = score
            best_match = result

    if not best_match or highest_score < 50:
        print(f"No confident match found for '{search_title}' (Highest Score: {highest_score:.2f}).")
        return default_return

    tmdb_id = best_match.get('id')
    id_found_search_title = best_match.get('title')
    id_found_search_original = best_match.get('original_title')
    print(f"Confident Match Found: '{search_title}' -> '{id_found_search_title}' (ID: {tmdb_id}, Score: {highest_score:.2f})")

    chosen_display_title = id_found_search_title
    tmdb_api_original_title = id_found_search_original
    
    try:
        details_url = f"{TMDB_API_BASE_URL}/movie/{tmdb_id}?api_key={api_key}&language=en-US"
        details_response = session.get(details_url, headers=REQUEST_HEADERS, timeout=10)
        time.sleep(TMDB_DETAILS_DELAY)
        details_response.raise_for_status()
        details_data = details_response.json()
        
        chosen_display_title = details_data.get('title') or chosen_display_title
        tmdb_api_original_title = details_data.get('original_title') or tmdb_api_original_title

        if chosen_display_title and not python_is_predominantly_latin(chosen_display_title):
            if tmdb_api_original_title and python_is_predominantly_latin(tmdb_api_original_title):
                chosen_display_title = tmdb_api_original_title
            else:
                alt_titles_url = f"{TMDB_API_BASE_URL}/movie/{tmdb_id}/alternative_titles?api_key={api_key}"
                alt_titles_response = session.get(alt_titles_url, headers=REQUEST_HEADERS, timeout=10)
                time.sleep(TMDB_ALT_TITLES_DELAY)
                alt_titles_response.raise_for_status()
                alt_titles_data = alt_titles_response.json()
                for alt in alt_titles_data.get('titles', []):
                    if alt.get('iso_3166_1') in ('US', 'GB') and python_is_predominantly_latin(alt.get('title')):
                        chosen_display_title = alt.get('title')
                        break
        
        print(f"Final TMDB Display: '{chosen_display_title}', Original from API: '{tmdb_api_original_title}'")
        return {"id": tmdb_id, "tmdb_title": chosen_display_title, "tmdb_original_title": tmdb_api_original_title}

    except Exception as e:
        print(f"Error fetching EN details for ID {tmdb_id}: {e}. Using JA search titles as fallback.", file=sys.stderr)
        return {"id": tmdb_id, "tmdb_title": id_found_search_title, "tmdb_original_title": id_found_search_original, "details_fetch_error": True}

# --- Letterboxd Title Scraping Function ---
def scrape_letterboxd_title(letterboxd_url, session):
    # ... (This function remains unchanged)
    if not letterboxd_url: return None
    print(f"Scraping Letterboxd page: {letterboxd_url}")
    try:
        response = session.get(letterboxd_url, headers=REQUEST_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        meta_title_tag = soup.find('meta', property='og:title')
        if meta_title_tag and meta_title_tag.get('content'):
            title = meta_title_tag['content'].strip()
            title = re.sub(r'\s+–\s+Letterboxd$', '', title, flags=re.IGNORECASE).strip()
            title = re.sub(r'\s+\([^)]*directed by[^)]*\)$', '', title, flags=re.IGNORECASE).strip()
            print(f"Letterboxd: Found title via meta tag: '{title}'")
            return title
        
        print(f"Letterboxd: Title not found in meta for {letterboxd_url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error scraping Letterboxd page {letterboxd_url}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred while scraping {letterboxd_url}: {e}", file=sys.stderr)
        return None

# --- Gemini Function ---
def get_alternative_title_with_gemini(cleaned_film_title, original_title_for_context, session, year=None, director=None, country=None):
    # ... (This function remains unchanged)
    global gemini_model
    if not gemini_model:
        return None
    
    if not cleaned_film_title and not original_title_for_context: return None
    
    title_to_use_for_prompt = original_title_for_context or cleaned_film_title
    
    context_parts = []
    if year:
        context_parts.append(f"released in or around {year}")
    if director:
        context_parts.append(f"directed by {director}")
    if country:
        context_parts.append(f"from {country}")
    
    context_str = ""
    if context_parts:
        context_str = f" ({', '.join(context_parts)})"

    prompt = (
        f"What is the official English title OR the original language title (e.g. French, German) for the film '{title_to_use_for_prompt}'{context_str}?\n"
        "If it's an English-language film, return its original English title.\n"
        "Respond with ONLY the single most common title. If you cannot determine a title, return the exact phrase 'NO_TITLE_FOUND'."
    )

    try:
        print(f"DEBUG: Calling Gemini for: '{title_to_use_for_prompt}'{context_str}...")
        start_time = time.time()

        response = gemini_model.generate_content(prompt)
        
        end_time = time.time()
        print(f"DEBUG: Gemini API call finished. Duration: {end_time - start_time:.2f} seconds.")

        alt_title = response.text.strip().replace('"', '')
        if alt_title and "NO_TITLE_FOUND" not in alt_title.upper() and len(alt_title) > 1:
            print(f"Gemini: Found for '{title_to_use_for_prompt}': '{alt_title}'")
            return alt_title
        
        print(f"Gemini: No usable title for '{title_to_use_for_prompt}'. Response: '{alt_title}'")
        return "NO_TITLE_FOUND"
        
    except Exception as e:
        print(f"Error querying Gemini for '{title_to_use_for_prompt}': {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None

# --- Main Enrichment Function (MODIFIED) ---
def enrich_listings_with_tmdb_links(all_listings, cache_data, session, tmdb_api_key, gemini_is_enabled):
    if not all_listings:
        return []

    unique_films = {}
    for listing in all_listings:
        original_title = (listing.get('movie_title') or listing.get('title') or "").strip()
        if not original_title or original_title.lower() in ["unknown title", "unknown film", "n/a"]:
            continue
        
        cleaned_title = clean_title_for_search(original_title)
        if not cleaned_title:
            continue

        year = listing.get('year') or (re.search(r'\b(19[7-9]\d|20[0-2]\d|203\d)\b', original_title) or [''])[0]
        film_key = (cleaned_title, year)
        
        if film_key not in unique_films:
            unique_films[film_key] = {
                "original_title": original_title,
                "english_title": listing.get("movie_title_en"), # Capture English title
                "director": listing.get("director"),
                "country": listing.get("country"),
            }

    print(f"\nFound {len(all_listings)} total listings, with {len(unique_films)} unique films to enrich.")

    enrichment_map = {}
    for film_key, film_info in unique_films.items():
        cleaned_title, year = film_key
        cache_key = f"{cleaned_title}|{year or ''}"
        
        if cache_key in cache_data and cache_data[cache_key].get("id"):
            enrichment_map[film_key] = cache_data[cache_key]
            continue
        
        print(f"--- Processing Unique Film: '{cleaned_title}' (Year: {year or 'Any'}) ---")
        
        tmdb_result = {} # Initialize as empty
        
        # STEP 1: Attempt search with pre-scraped English title (language-neutral)
        english_title_from_scrape = film_info.get("english_title")
        if tmdb_api_key and english_title_from_scrape:
            tmdb_result = get_tmdb_film_details(
                english_title_from_scrape, tmdb_api_key, session, year, language_code=None
            )

        # STEP 2: Fallback to Japanese title search if the first attempt failed
        if tmdb_api_key and (not tmdb_result or not tmdb_result.get("id")):
            if english_title_from_scrape:
                print("Language-neutral search failed. Falling back to Japanese title search.")
            
            tmdb_result = get_tmdb_film_details(
                cleaned_title, tmdb_api_key, session, year, language_code='ja-JP'
            )
            
        # STEP 3: Fallback to Gemini if both TMDb searches fail
        if gemini_is_enabled and (not tmdb_result or not tmdb_result.get("id")):
            print(f"TMDb search failed for '{cleaned_title}'. Attempting Gemini fallback.")
            alt_title = get_alternative_title_with_gemini(
                cleaned_title, film_info["original_title"], session,
                year=year, director=film_info["director"], country=film_info["country"]
            )
            time.sleep(GEMINI_DELAY)
            
            if alt_title and "NO_TITLE_FOUND" not in alt_title:
                print(f"Retrying TMDB with alternative title from Gemini: '{alt_title}'")
                tmdb_result_from_alt = get_tmdb_film_details(
                    alt_title, tmdb_api_key, session, year=None, language_code=None # Use neutral search for Gemini title
                )
                if tmdb_result_from_alt and tmdb_result_from_alt.get("id"):
                    tmdb_result = tmdb_result_from_alt
        
        current_enrichment_data = {}
        if tmdb_result and tmdb_result.get("id"):
            current_enrichment_data.update(tmdb_result)
            lb_url = f"{LETTERBOXD_TMDB_BASE_URL}{current_enrichment_data['id']}"
            lb_eng_title = scrape_letterboxd_title(lb_url, session)
            time.sleep(LETTERBOXD_SCRAPE_DELAY)
            if lb_eng_title:
                current_enrichment_data["letterboxd_english_title"] = lb_eng_title

        enrichment_map[film_key] = current_enrichment_data
        cache_data[cache_key] = current_enrichment_data
    
    save_json_cache(cache_data, TMDB_CACHE_FILE, "TMDB/Extended Cache")

    for listing in all_listings:
        original_title = (listing.get('movie_title') or listing.get('title') or "").strip()
        cleaned_title = clean_title_for_search(original_title)
        year = listing.get('year') or (re.search(r'\b(19[7-9]\d|20[0-2]\d|203\d)\b', original_title) or [''])[0]
        film_key = (cleaned_title, year)

        enriched_data = enrichment_map.get(film_key, {})
        if enriched_data.get("id"):
            listing['letterboxd_link'] = f"{LETTERBOXD_TMDB_BASE_URL}{enriched_data['id']}"
            listing['tmdb_display_title'] = enriched_data.get('tmdb_title')
            listing['tmdb_original_title'] = enriched_data.get('tmdb_original_title')
            listing['letterboxd_english_title'] = enriched_data.get('letterboxd_english_title')
    
    return all_listings

# --- Scraper Invocation & Main Block ---
def _run_scraper(label: str, func, normalize_func=None):
    print(f"\nScraping {label} …")
    try:
        rows = func() or []
        if normalize_func:
            rows = normalize_func(rows)
        print(f"→ {len(rows)} showings from {label}.")
        return rows
    except Exception as e:
        print(f"⚠️ Error in {label}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return []

def run_all_scrapers():
    print("Starting all scrapers…")
    all_listings = []
    
    all_listings += _run_scraper("K's Cinema", ks_cinema_module.scrape_ks_cinema)
    all_listings += _run_scraper("Shin-Bungeiza", shin_bungeiza_module.scrape_shin_bungeiza)
    all_listings += _run_scraper("Shimotakaido Cinema", shimotakaido_module.scrape_shimotakaido)
    all_listings += _run_scraper("Stranger", stranger_module.scrape_stranger)
    all_listings += _run_scraper("Meguro Cinema", meguro_cinema_module.scrape_meguro_cinema)
    all_listings += _run_scraper("Image Forum", image_forum_module.scrape)
    all_listings += _run_scraper("Theatre Shinjuku", theatre_shinjuku_module.scrape_theatre_shinjuku)
    all_listings += _run_scraper("Pole Pole Higashi-Nakano", polepole_module.scrape_polepole)
    all_listings += _run_scraper("Cinema Blue Studio", bluestudio_module.scrape_bluestudio)
    all_listings += _run_scraper("Human Trust Cinema Shibuya", human_shibuya_module.scrape_human_shibuya)
    all_listings += _run_scraper("Human Trust Cinema Yurakucho", human_yurakucho_module.scrape_human_yurakucho)
    all_listings += _run_scraper("Laputa Asagaya", laputa_asagaya_module.scrape_laputa_asagaya)
    all_listings += _run_scraper("Shinjuku Musashino-kan", musashino_kan_module.scrape_musashino_kan)
    all_listings += _run_scraper("Waseda Shochiku", waseda_shochiku_module.scrape_waseda_shochiku)
    all_listings += _run_scraper("National Film Archive", nfaj_module.scrape_nfaj_calendar)
    all_listings += _run_scraper("Eurospace", eurospace_module.scrape, normalize_func=_normalize_eurospace_schema)
    all_listings += _run_scraper("Cinemart Shinjuku", cinemart_shinjuku_module.scrape_cinemart_shinjuku)
    all_listings += _run_scraper("Cinema Qualite", cinema_qualite_module.scrape_cinema_qualite)
    all_listings += _run_scraper("Cine Quinto", cine_quinto_module.scrape_cine_quinto)
    all_listings += _run_scraper("Yebisu Garden Cinema", yebisu_garden_module.scrape_yebisu_garden_cinema)
    all_listings += _run_scraper("K2 Cinema", k2_cinema_module.scrape_k2_cinema)
    all_listings += _run_scraper("Cinema Rosa", cinema_rosa_module.scrape_cinema_rosa)
    all_listings += _run_scraper("Chupki", chupki_module.scrape_chupki)
    all_listings += _run_scraper("Bunkamura", bunkamura_module.scrape_bunkamura)

    print(f"\nCollected a total of {len(all_listings)} showings from regular scrapers.")
    return all_listings

def save_to_json(data, filename="showtimes.json"):
    try:
        with open(filename, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved to {filename}")
    except Exception as e: print(f"⚠️ Failed to save {filename}: {e}", file=sys.stderr)

if __name__ == "__main__":
    gemini_enabled = False
    if genai and GEMINI_API_KEY and 'YOUR_GEMINI_API_KEY' not in (GEMINI_API_KEY or ''):
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            gemini_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
            gemini_enabled = True
            print(f"Gemini AI model '{GEMINI_MODEL_NAME}' initialized successfully.")
        except Exception as e:
            print(f"Could not initialize Gemini model: {e}", file=sys.stderr)
    else:
        print("--- WARNING: Gemini API key is missing, a placeholder, or the library is not installed. Gemini functions will be disabled. ---")

    tmdb_cache = load_json_cache(TMDB_CACHE_FILE, "TMDB/Extended Cache")
    api_session = requests.Session()
    
    tmdb_key = TMDB_API_KEY
    if not tmdb_key or 'YOUR_TMDB_API_KEY' in tmdb_key:
        print("--- WARNING: TMDB API KEY is missing or a placeholder. TMDB functions will be disabled. ---")
        tmdb_key = None

    try:
        print("\nRunning Cine Switch Ginza module standalone to generate its JSON...")
        cine_switch_ginza_module.run_full_scrape_and_save()
    except Exception as e:
        print(f"Error running cine_switch_ginza_module.run_full_scrape_and_save(): {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    listings = run_all_scrapers()
    
    try:
        with open("cineswitch_showtimes.json", "r", encoding="utf-8") as f:
            csg_showings = json.load(f)
            print(f"→ {len(csg_showings)} showings from Cine Switch Ginza (loaded from JSON).")
            listings.extend(csg_showings)
            print(f"Total showings after adding Cine Switch Ginza: {len(listings)}")
    except FileNotFoundError:
        print("WARNING: cineswitch_showtimes.json not found, skipping.", file=sys.stderr)
    except Exception as e:
        print(f"Error loading cineswitch_showtimes.json: {e}", file=sys.stderr)

    enriched_listings = enrich_listings_with_tmdb_links(
        listings, tmdb_cache, api_session, tmdb_key, gemini_enabled
    )
    
    try:
        enriched_listings.sort(key=lambda x: (
            x.get("cinema_name") or x.get("cinema", ""), x.get("date_text", ""), x.get("showtime", "")
        ))
    except Exception as e: print(f"Warning: Could not sort listings: {e}", file=sys.stderr)

    save_to_json(enriched_listings)
    print("\nEnrichment process complete.")