import datetime as _dt
import json
from typing import List, Dict, Any
import requests

# --- Constants ---
BASE_URL = "https://ttcg.jp"
SCHEDULE_DATA_URL = f"{BASE_URL}/data/theatre_shinjuku.js"
PURCHASABLE_DATA_URL = f"{BASE_URL}/data/purchasable.js"
CINEMA_NAME = "テアトル新宿"
THEATRE_CODE = "theatre_shinjuku" # Used as a key in purchasable.js

# --- Helper Functions ---

def _fetch_json_data(url: str) -> Any:
    """Fetches data from a URL and parses it as JSON."""
    try:
        response = requests.get(url, timeout=15) # Increased timeout
        response.raise_for_status()
        content = response.text
        
        # Attempt to strip common JS variable assignments or JSONP wrappers
        if content.endswith(';'):
            content = content[:-1]
        
        # Handle "var variableName = jsonContent;"
        if '=' in content:
            parts = content.split('=', 1)
            if len(parts) > 1:
                potential_json = parts[1].strip()
                # Basic check if it looks like JSON
                if (potential_json.startswith('{') and potential_json.endswith('}')) or \
                   (potential_json.startswith('[') and potential_json.endswith(']')):
                    content = potential_json
        
        # Handle potential callback(jsonContent)
        if content.startswith('callback(') and content.endswith(')'):
            content = content[len('callback('):-1]
            
        return json.loads(content)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {url}: {e}")
        print(f"Content snippet: {content[:500]}...")
    return None

def _format_time(hour_str: str, minute_str: str) -> str:
    """Formats hour and minute strings into HH:MM format."""
    return f"{str(hour_str).zfill(2)}:{str(minute_str).zfill(2)}"

def _get_availability_status_and_url(time_info: Dict, theatre_purchasable: bool) -> (str, str | None):
    """Determines human-readable status and purchase URL."""
    available_code = time_info.get('available')
    url = time_info.get('url') 

    status_text = "情報なし"
    can_purchase_online_now = False

    if theatre_purchasable:
        if available_code == 0:
            status_text = "オンライン購入可" 
            can_purchase_online_now = True
        elif available_code == 1:
            status_text = "窓口販売" 
        elif available_code == 2:
            status_text = "オンライン残席わずか" 
            can_purchase_online_now = True
        elif available_code == 4:
            status_text = "窓口残席わずか" 
        elif available_code == 5:
            status_text = "満席" 
        else: 
            status_text = "販売期間外／終了"
    else: 
        if available_code in [0, 1, 2, 4]:
            status_text = "窓口にてご確認ください"
            if available_code == 5:
                 status_text = "満席"
        else:
            status_text = "販売期間外／終了"

    purchase_url = url if can_purchase_online_now and url and str(url).startswith("http") else None
    return status_text, purchase_url

def _get_screen_display_name(json_screen_name: str) -> str:
    """Maps JSON screen name to display name."""
    if json_screen_name == "座席券": 
        return "odessaシアター"
    return json_screen_name 

# --- Main Scraper Function ---

def scrape_theatre_shinjuku(max_days: int = 7) -> List[Dict]:
    """
    Scrapes movie showings for Theatre Shinjuku for up to max_days.
    """
    fetched_schedule_data = _fetch_json_data(SCHEDULE_DATA_URL)
    purchasable_info = _fetch_json_data(PURCHASABLE_DATA_URL)

    actual_schedule_data = None
    if isinstance(fetched_schedule_data, list):
        if len(fetched_schedule_data) == 1 and isinstance(fetched_schedule_data[0], dict):
            actual_schedule_data = fetched_schedule_data[0]
        else:
            print(f"DEBUG: Fetched schedule_data is a list but not in expected format. Len: {len(fetched_schedule_data)}")
            return []
    elif isinstance(fetched_schedule_data, dict):
        actual_schedule_data = fetched_schedule_data
    
    if not actual_schedule_data or not purchasable_info:
        print("Failed to fetch or parse critical schedule or purchasable data correctly. Aborting.")
        return []

    is_theatre_purchasable = purchasable_info.get(THEATRE_CODE, False)
    all_showings: List[Dict] = []
    
    dates_data = actual_schedule_data.get('dates', [])
    dates_to_process = dates_data[:max_days] if max_days is not None and max_days > 0 else dates_data

    movies_map = actual_schedule_data.get('movies', {})
    screens_map = actual_schedule_data.get('screens', {})

    for date_obj in dates_to_process:
        try:
            # Ensure date components are strings for key creation and formatting
            raw_year = str(date_obj['date_year'])
            raw_month = str(date_obj['date_month']) # Keep raw for key
            raw_day = str(date_obj['date_day'])   # Keep raw for key
            
            # For display/output, ensure padding
            display_month = raw_month.zfill(2)
            display_day = raw_day.zfill(2)
            current_date_str = f"{raw_year}-{display_month}-{display_day}"
            
            movie_ids_for_date = date_obj.get('movie', [])

            for movie_id_key in movie_ids_for_date:
                movie_data_for_id = movies_map.get(str(movie_id_key)) # Ensure movie_id_key is string for dict lookup
                
                processed_movie_details = None
                if isinstance(movie_data_for_id, list):
                    if movie_data_for_id and isinstance(movie_data_for_id[0], dict):
                        processed_movie_details = movie_data_for_id[0] 
                    else:
                        # print(f"Info: Movie details for ID {movie_id_key} is a list, but not in expected format.")
                        pass # Continue to next movie_id_key if format is not as expected
                elif isinstance(movie_data_for_id, dict):
                    processed_movie_details = movie_data_for_id
                
                if not processed_movie_details:
                    # print(f"Info: Movie details not found or in unexpected format for ID {movie_id_key} on {current_date_str}")
                    continue

                movie_title = processed_movie_details.get('title_short') or processed_movie_details.get('title', 'タイトル不明')
                image_path = processed_movie_details.get('image_path')
                movie_image_url = f"{BASE_URL}{image_path}" if image_path and image_path.startswith('/') else image_path
                remarks_html = processed_movie_details.get('remarks_pc', '')
                duration_label = processed_movie_details.get('label_text_type_a', '')

                # Revised key for screens data, using raw month/day from date_obj
                screens_data_key = f"{movie_id_key}-{raw_year}-{raw_month}-{raw_day}"
                screen_schedules_for_movie_date = screens_map.get(screens_data_key, [])
                
                if not screen_schedules_for_movie_date:
                    # Fallback for YYYYMMDD key format if the above fails (common in their URLs)
                    screens_data_key_alt = f"{movie_id_key}-{raw_year}{display_month}{display_day}"
                    screen_schedules_for_movie_date = screens_map.get(screens_data_key_alt, [])
                    # if screen_schedules_for_movie_date:
                    #    print(f"DEBUG: Used ALT key {screens_data_key_alt} for {movie_title} on {current_date_str}")
                    # else:
                    #    print(f"DEBUG: No screen schedules for keys {screens_data_key} or {screens_data_key_alt} (Movie: {movie_title}) on {current_date_str}")


                for screen_info in screen_schedules_for_movie_date:
                    if not isinstance(screen_info, dict): # Ensure screen_info is a dict
                        # print(f"Warning: screen_info is not a dict for {movie_title} on {current_date_str}. Type: {type(screen_info)}")
                        continue

                    raw_screen_name = screen_info.get('name', 'スクリーン情報なし')
                    screen_display_name = _get_screen_display_name(raw_screen_name)
                    
                    for time_info in screen_info.get('time', []):
                        if not isinstance(time_info, dict): # Ensure time_info is a dict
                            # print(f"Warning: time_info is not a dict for {movie_title} on {current_date_str}. Type: {type(time_info)}")
                            continue

                        start_hour = time_info.get('start_time_hour')
                        start_minute = time_info.get('start_time_minute')
                        
                        if start_hour is None or start_minute is None:
                            continue 

                        showtime_str = _format_time(start_hour, start_minute)
                        
                        end_hour = time_info.get('end_time_hour')
                        end_minute = time_info.get('end_time_minute')
                        end_time_str = _format_time(end_hour, end_minute) if end_hour is not None and end_minute is not None else None
                        
                        status_text, purchase_url = _get_availability_status_and_url(time_info, is_theatre_purchasable)

                        showing_info = {
                            "cinema_name": CINEMA_NAME,
                            "movie_title": movie_title,
                            "date": current_date_str,
                            "showtime": showtime_str,
                            "end_time": end_time_str,
                            "screen_name": screen_display_name,
                            "availability_status": status_text,
                            "purchase_url": purchase_url,
                            "movie_image_url": movie_image_url,
                            "duration_label": duration_label,
                            "remarks_html": remarks_html.strip()
                        }
                        all_showings.append(showing_info)
        except Exception as e:
            print(f"Error processing date object {date_obj} for {CINEMA_NAME}: {e}")
            import traceback
            traceback.print_exc() # Print full traceback for debugging
            continue
            
    unique_showings_dict = {}
    for s_item in all_showings:
        key = (s_item["cinema_name"], s_item["movie_title"], s_item["date"], s_item["showtime"], s_item["screen_name"])
        if key not in unique_showings_dict:
            unique_showings_dict[key] = s_item
            
    return list(unique_showings_dict.values())

# --- Main Execution ---
if __name__ == "__main__":
    print(f"INFO: Scraping {CINEMA_NAME} for up to 7 days...")
    showings = scrape_theatre_shinjuku(max_days=7)
    
    print(f"\nCollected {len(showings)} showings.")
    if showings:
        print("\nFirst few showings:")
        for i, showing in enumerate(showings[:5]):
            print(f"--- Showing {i+1} ---")
            for key, value in showing.items():
                print(f"  {key}: {value}")
        
        print(f"\n--- Example of a showing with purchase URL (if any) ---")
        found_purchasable = False
        for showing in showings:
            if showing["purchase_url"]:
                for key, value in showing.items():
                    print(f"  {key}: {value}")
                found_purchasable = True
                break
        if not found_purchasable:
            print("  No showings with an active online purchase URL found in the sample.")
    else:
        print("No showings collected or an error occurred during scraping.")

