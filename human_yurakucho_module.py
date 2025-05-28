import datetime as _dt
import json
from typing import List, Dict, Any
import requests
import traceback
import sys # Added for sys.stderr and platform check

# --- Constants ---
BASE_URL = "https://ttcg.jp"
THEATRE_CODE = "human_yurakucho" # Specific code for Yurakucho
SCHEDULE_DATA_URL = f"{BASE_URL}/data/{THEATRE_CODE}.js"
CINEMA_NAME = "ヒューマントラストシネマ有楽町" # Specific name for Yurakucho
PURCHASABLE_DATA_URL = f"{BASE_URL}/data/purchasable.js"

__all__ = ["scrape_human_yurakucho"]

# --- Configure stdout and stderr for UTF-8 on Windows ---
# (This is good practice if the module is ever run directly on Windows)
if __name__ == "__main__" and sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
# --- End: Configure stdout and stderr ---

# --- Helper Functions (Identical to human_shibuya_module.py) ---

def _fetch_json_data(url: str) -> Any:
    """Fetches data from a URL and parses it as JSON."""
    content = ""
    original_content_for_debug = "" # Initialize here for broader scope in case of early error
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        request_url = f"{url}?t={_dt.datetime.now().timestamp()}" # Cache-busting
        # Use sys.stderr for debug prints to separate from potential JSON output if run directly
        print(f"Debug ({CINEMA_NAME}): Fetching: {request_url}", file=sys.stderr)
        response = requests.get(request_url, timeout=15, headers=headers)
        response.raise_for_status()
        content = response.text.strip()
        original_content_for_debug = content # Store original content after successful fetch

        if not content:
            print(f"Warning ({CINEMA_NAME}): Fetched empty content from {url}", file=sys.stderr)
            return None

        if content.endswith(';'):
            content = content[:-1].strip()

        if '=' in content:
            parts = content.split('=', 1)
            if len(parts) > 1:
                potential_json = parts[1].strip()
                if (potential_json.startswith('{') and potential_json.endswith('}')) or \
                   (potential_json.startswith('[') and potential_json.endswith(']')):
                    content = potential_json

        if '(' in content and content.endswith(')'):
            first_paren = content.find('(')
            if first_paren != -1:
                potential_json_in_paren = content[first_paren+1:-1].strip()
                if (potential_json_in_paren.startswith('{') and potential_json_in_paren.endswith('}')) or \
                   (potential_json_in_paren.startswith('[') and potential_json_in_paren.endswith(']')):
                    content = potential_json_in_paren

        return json.loads(content)
    except requests.exceptions.RequestException as e:
        print(f"Error ({CINEMA_NAME}): Fetching URL {url} failed: {e}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Error ({CINEMA_NAME}): Decoding JSON from {url} failed: {e}", file=sys.stderr)
        print(f"Error ({CINEMA_NAME}): Attempted to parse (up to 500 chars): {content[:500]}...", file=sys.stderr)
        if original_content_for_debug: # Print original if available
             print(f"Error ({CINEMA_NAME}): Original fetched content (up to 500 chars): {original_content_for_debug[:500]}...", file=sys.stderr)
    return None

def _format_time(hour_str: Any, minute_str: Any) -> str:
    """Formats hour and minute strings/numbers into HH:MM format."""
    return f"{str(hour_str).zfill(2)}:{str(minute_str).zfill(2)}"

def _get_availability_status_and_url(time_info: Dict, theatre_purchasable: bool) -> (str, str | None):
    """Determines human-readable status and purchase URL."""
    available_code = time_info.get('available')
    url = time_info.get('url')

    status_text = "情報なし"
    can_purchase_online_now = False

    if theatre_purchasable:
        if available_code == 0: status_text, can_purchase_online_now = "オンライン購入可", True
        elif available_code == 1: status_text = "窓口販売"
        elif available_code == 2: status_text, can_purchase_online_now = "オンライン残席わずか", True
        elif available_code == 4: status_text = "窓口残席わずか"
        elif available_code == 5: status_text = "満席"
        else: status_text = "販売期間外／終了"
    else:
        if available_code == 5: status_text = "満席"
        elif available_code in [0, 1, 2, 4]: status_text = "劇場窓口にてご確認ください"
        else: status_text = "販売期間外／終了"

    purchase_url = url if can_purchase_online_now and url and str(url).startswith("http") else None
    return status_text, purchase_url

def _get_screen_display_name(json_screen_name: str) -> str:
    """Cleans up screen names."""
    if "(座席券)" in json_screen_name:
        return json_screen_name.replace("(座席券)", "").strip()
    return json_screen_name.strip()


# --- Main Scraper Function ---

def scrape_human_yurakucho(max_days: int = 7) -> List[Dict]:
    """
    Scrapes movie showings for Human Trust Cinema Yurakucho for up to max_days.
    """
    print(f"Debug ({CINEMA_NAME}): Starting scrape for {CINEMA_NAME}.", file=sys.stderr) # Added debug print
    fetched_schedule_data_wrapper = _fetch_json_data(SCHEDULE_DATA_URL)
    purchasable_info = _fetch_json_data(PURCHASABLE_DATA_URL)

    actual_schedule_data = None
    if isinstance(fetched_schedule_data_wrapper, list):
        if len(fetched_schedule_data_wrapper) > 0 and isinstance(fetched_schedule_data_wrapper[0], dict):
            actual_schedule_data = fetched_schedule_data_wrapper[0]
        elif fetched_schedule_data_wrapper:
            for item in fetched_schedule_data_wrapper:
                if isinstance(item, dict) and 'dates' in item and 'movies' in item:
                    actual_schedule_data = item
                    break
    elif isinstance(fetched_schedule_data_wrapper, dict): # If it's already a dict
        actual_schedule_data = fetched_schedule_data_wrapper

    if not actual_schedule_data:
        print(f"Error ({CINEMA_NAME}): Failed to extract actual schedule data. Wrapper type: {type(fetched_schedule_data_wrapper)}. Data (first 200 chars): {str(fetched_schedule_data_wrapper)[:200]}", file=sys.stderr)
    if not purchasable_info:
        print(f"Warning ({CINEMA_NAME}): Failed to fetch or parse purchasable data. Availability info might be limited.", file=sys.stderr)

    if not actual_schedule_data: # Purchasable info is optional for basic scraping
        print(f"Error ({CINEMA_NAME}): Aborting scrape due to missing critical schedule data.", file=sys.stderr)
        return []

    is_theatre_purchasable = purchasable_info.get(THEATRE_CODE, False) if purchasable_info else False
    all_showings: List[Dict] = []

    dates_data = actual_schedule_data.get('dates', [])
    if not dates_data:
        print(f"Warning ({CINEMA_NAME}): No 'dates' array found in schedule data.", file=sys.stderr)
        return []

    dates_to_process = dates_data[:max_days] if max_days is not None and max_days > 0 else dates_data

    movies_map = actual_schedule_data.get('movies', {})
    screens_map = actual_schedule_data.get('screens', {})

    for date_obj in dates_to_process:
        try:
            raw_year = str(date_obj['date_year'])
            raw_month = str(date_obj['date_month'])
            raw_day = str(date_obj['date_day'])

            display_month = raw_month.zfill(2)
            display_day = raw_day.zfill(2)
            current_date_iso_str = f"{raw_year}-{display_month}-{display_day}"

            movie_ids_for_date = date_obj.get('movie', [])

            for movie_id_key_any_type in movie_ids_for_date:
                movie_id_key = str(movie_id_key_any_type)
                movie_data_for_id_list_or_dict = movies_map.get(movie_id_key)

                processed_movie_details = None
                if isinstance(movie_data_for_id_list_or_dict, list):
                    if movie_data_for_id_list_or_dict and isinstance(movie_data_for_id_list_or_dict[0], dict):
                        processed_movie_details = movie_data_for_id_list_or_dict[0]
                elif isinstance(movie_data_for_id_list_or_dict, dict):
                    processed_movie_details = movie_data_for_id_list_or_dict

                if not processed_movie_details:
                    print(f"Warning ({CINEMA_NAME}): No movie details found for movie_id '{movie_id_key}' on {current_date_iso_str}.", file=sys.stderr)
                    continue

                title_from_name_field = processed_movie_details.get('name')
                title_from_cname_field = processed_movie_details.get('cname')
                title_from_short_field = processed_movie_details.get('title_short')
                title_from_title_field = processed_movie_details.get('title')

                final_movie_title = title_from_name_field \
                                     or title_from_cname_field \
                                     or title_from_short_field \
                                     or title_from_title_field \
                                     or 'タイトル不明'

                if not final_movie_title.strip():
                    final_movie_title = 'タイトル不明'
                
                if final_movie_title == 'タイトル不明' and not (title_from_name_field or title_from_cname_field or title_from_short_field or title_from_title_field) :
                    print(f"Debug ({CINEMA_NAME}): Movie ID {movie_id_key} (Date: {current_date_iso_str}) defaulted to 'タイトル不明'. Movie Data: {str(processed_movie_details)[:200]}", file=sys.stderr)


                image_path = processed_movie_details.get('image_path')
                movie_image_url = None
                if image_path:
                    if str(image_path).startswith('http'): movie_image_url = image_path
                    elif str(image_path).startswith('/'): movie_image_url = f"{BASE_URL}{image_path}"
                    else: movie_image_url = f"{BASE_URL}/{image_path}"

                remarks_html = processed_movie_details.get('remarks_pc', '')

                duration_label_data = processed_movie_details.get('label_text_type_a', [])
                duration_label = ""
                if isinstance(duration_label_data, list) and duration_label_data:
                    duration_label = str(duration_label_data[0])
                elif isinstance(duration_label_data, str):
                    duration_label = duration_label_data

                screen_schedules_for_movie_date = None
                keys_tried_for_screen_map = []
                key_formats_to_try_for_screen_map = [
                    f"{movie_id_key}-{raw_year}-{raw_month}-{raw_day}",
                    f"{movie_id_key}-{raw_year}-{display_month}-{display_day}",
                    f"{movie_id_key}-{raw_year}{display_month}{display_day}"
                ]
                for key_attempt in key_formats_to_try_for_screen_map:
                    keys_tried_for_screen_map.append(key_attempt)
                    screen_schedules_for_movie_date = screens_map.get(key_attempt)
                    if screen_schedules_for_movie_date:
                        break

                if not screen_schedules_for_movie_date:
                    # This can be normal if a movie is listed for a date but has no showtimes yet.
                    # print(f"Debug ({CINEMA_NAME}): No screen schedules in screens_map for movie ID '{movie_id_key}' on {current_date_iso_str}. Tried keys: {keys_tried_for_screen_map}", file=sys.stderr)
                    continue

                for screen_info in screen_schedules_for_movie_date:
                    if not isinstance(screen_info, dict): continue

                    raw_screen_name = screen_info.get('screen_name_short') or screen_info.get('name', 'スクリーン情報なし')
                    screen_display_name = _get_screen_display_name(raw_screen_name)

                    for time_info in screen_info.get('time', []):
                        if not isinstance(time_info, dict): continue

                        start_hour = time_info.get('start_time_hour')
                        start_minute = time_info.get('start_time_minute')

                        if start_hour is None or start_minute is None: continue

                        showtime_str = _format_time(start_hour, start_minute)

                        end_hour = time_info.get('end_time_hour')
                        end_minute = time_info.get('end_time_minute')
                        end_time_str = _format_time(end_hour, end_minute) if end_hour is not None and end_minute is not None else None

                        status_text, purchase_url = _get_availability_status_and_url(time_info, is_theatre_purchasable)

                        showing_info = {
                            "cinema_name": CINEMA_NAME,
                            "movie_title": final_movie_title,
                            "date_text": current_date_iso_str,
                            "showtime": showtime_str,
                            "end_time": end_time_str,
                            "screen_name": screen_display_name,
                            "availability_status": status_text,
                            "purchase_url": purchase_url,
                            "movie_image_url": movie_image_url,
                            "duration_label": duration_label,
                            "remarks_html": remarks_html.strip() if isinstance(remarks_html, str) else ""
                        }
                        all_showings.append(showing_info)
        except Exception as e:
            print(f"Error ({CINEMA_NAME}): Processing date object {date_obj} failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            continue

    unique_showings_dict = {}
    for s_item in all_showings:
        # Key for uniqueness
        key = (s_item["cinema_name"], s_item["movie_title"], s_item["date_text"], s_item["showtime"], s_item["screen_name"])
        if key not in unique_showings_dict:
            unique_showings_dict[key] = s_item

    return list(unique_showings_dict.values())

# --- Main Execution (for testing this module directly) ---
if __name__ == "__main__":
    # Use sys.stderr for print statements in __main__ to avoid interfering with potential stdout redirection of JSON
    print(f"INFO: Scraping {CINEMA_NAME} (code: {THEATRE_CODE}) for up to 7 days...", file=sys.stderr)
    print(f"     Using schedule URL: {SCHEDULE_DATA_URL}", file=sys.stderr)
    showings = scrape_human_yurakucho(max_days=7)

    print(f"\nCollected {len(showings)} showings for {CINEMA_NAME}.", file=sys.stderr)

    if showings:
        print(f"\n--- First 2 Showings Collected for {CINEMA_NAME} (Example) ---", file=sys.stderr)
        for i, showing in enumerate(showings[:2]):
            print(f"Showing {i+1}:", file=sys.stderr)
            for key, value in showing.items():
                print(f"  {key}: {value}", file=sys.stderr)
            print("-" * 10, file=sys.stderr)

        unknown_title_count = 0
        known_title_examples = []
        for showing_item in showings:
            if showing_item["movie_title"] == "タイトル不明":
                unknown_title_count += 1
            elif len(known_title_examples) < 3 and showing_item["movie_title"] != "タイトル不明":
                 known_title_examples.append(showing_item)

        print(f"\n--- Title Summary for {CINEMA_NAME} ---", file=sys.stderr)
        print(f"Number of showings with 'タイトル不明': {unknown_title_count} out of {len(showings)}", file=sys.stderr)
        if known_title_examples:
            print("Examples of showings with specific titles found:", file=sys.stderr)
            for i, ex_showing in enumerate(known_title_examples):
                print(f"  Example {i+1} - Title: {ex_showing['movie_title']}", file=sys.stderr)
        else:
            print(f"No showings with specific titles (other than 'タイトル不明') were found by this scraper for {CINEMA_NAME}.", file=sys.stderr)

        # To output the JSON to stdout if run directly and piped:
        # json.dump(showings, sys.stdout, ensure_ascii=False, indent=2)
        # print("\nJSON output above is for piping. Debug messages are on stderr.", file=sys.stderr)

    else:
        print(f"No showings collected for {CINEMA_NAME}, or an error occurred during scraping.", file=sys.stderr)