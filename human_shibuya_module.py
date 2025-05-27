import datetime as _dt
import json
from typing import List, Dict, Any
import requests

# --- Constants ---
BASE_URL = "https://ttcg.jp"
# Updated for Human Trust Cinema Shibuya
SCHEDULE_DATA_URL = f"{BASE_URL}/data/human_shibuya.js"
PURCHASABLE_DATA_URL = f"{BASE_URL}/data/purchasable.js" # This URL is common
CINEMA_NAME = "ヒューマントラストシネマ渋谷"
THEATRE_CODE = "human_shibuya" # Updated theatre code

__all__ = ["scrape_human_shibuya"]

# --- Helper Functions (identical to theatre_shinjuku_module) ---

def _fetch_json_data(url: str) -> Any:
    """Fetches data from a URL and parses it as JSON."""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        content = response.text
        
        if content.endswith(';'):
            content = content[:-1]
        
        if '=' in content:
            parts = content.split('=', 1)
            if len(parts) > 1:
                potential_json = parts[1].strip()
                if (potential_json.startswith('{') and potential_json.endswith('}')) or \
                   (potential_json.startswith('[') and potential_json.endswith(']')):
                    content = potential_json
        
        if content.startswith('callback(') and content.endswith(')'):
            content = content[len('callback('):-1]
            
        return json.loads(content)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url} for {CINEMA_NAME}: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {url} for {CINEMA_NAME}: {e}")
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

def _get_screen_display_name(json_screen_name: str, movie_title: str = "") -> str:
    """
    Maps JSON screen name to display name.
    For Human Trust Shibuya, screen names like "ｼｱﾀｰ1" (half-width) are common.
    We'll try to normalize them slightly if needed, but mostly use them as is.
    """
    # Example: "ｼｱﾀｰ1" -> "シアター1" (Full-width for consistency if desired)
    # However, the raw names from their JSON (e.g., screen_name_short) are often what's displayed.
    # For now, we'll assume the name from JSON is mostly usable.
    # If specific mappings are needed (like "座席券" for Theatre Shinjuku), they'd go here.
    # Human Trust Shibuya seems to use names like "ｼｱﾀｰ1", "ｼｱﾀｰ2", "ｼｱﾀｰ3" in screen_name_short.
    # The 'name' field in the screen object might be more descriptive.
    
    # Let's assume the 'name' field in screen_info is the one to use.
    # If it's like "ｼｱﾀｰ1(座席券)", we might want to simplify it.
    if "(座席券)" in json_screen_name:
        return json_screen_name.replace("(座席券)", "").strip()
    
    return json_screen_name


# --- Main Scraper Function ---

def scrape_human_shibuya(max_days: int = 7) -> List[Dict]:
    """
    Scrapes movie showings for Human Trust Cinema Shibuya for up to max_days.
    """
    fetched_schedule_data = _fetch_json_data(SCHEDULE_DATA_URL)
    purchasable_info = _fetch_json_data(PURCHASABLE_DATA_URL)

    actual_schedule_data = None
    # The .js file might be wrapped in a list containing one dictionary
    if isinstance(fetched_schedule_data, list):
        if len(fetched_schedule_data) == 1 and isinstance(fetched_schedule_data[0], dict):
            actual_schedule_data = fetched_schedule_data[0]
        else:
            print(f"DEBUG: Fetched schedule_data for {CINEMA_NAME} is a list but not in expected format. Len: {len(fetched_schedule_data)}")
            return []
    elif isinstance(fetched_schedule_data, dict):
        actual_schedule_data = fetched_schedule_data
    
    if not actual_schedule_data or not purchasable_info:
        print(f"Failed to fetch or parse critical schedule or purchasable data for {CINEMA_NAME}. Aborting.")
        return []

    is_theatre_purchasable = purchasable_info.get(THEATRE_CODE, False)
    all_showings: List[Dict] = []
    
    dates_data = actual_schedule_data.get('dates', [])
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

            for movie_id_key in movie_ids_for_date:
                movie_data_for_id = movies_map.get(str(movie_id_key)) 
                
                processed_movie_details = None
                if isinstance(movie_data_for_id, list):
                    if movie_data_for_id and isinstance(movie_data_for_id[0], dict):
                        processed_movie_details = movie_data_for_id[0] 
                elif isinstance(movie_data_for_id, dict):
                    processed_movie_details = movie_data_for_id
                
                if not processed_movie_details:
                    continue

                movie_title = processed_movie_details.get('title_short') or processed_movie_details.get('title', 'タイトル不明')
                image_path = processed_movie_details.get('image_path')
                movie_image_url = f"{BASE_URL}{image_path}" if image_path and image_path.startswith('/') else image_path
                remarks_html = processed_movie_details.get('remarks_pc', '')
                duration_label = processed_movie_details.get('label_text_type_a', '')

                screens_data_key = f"{movie_id_key}-{raw_year}-{raw_month}-{raw_day}"
                screen_schedules_for_movie_date = screens_map.get(screens_data_key, [])
                
                if not screen_schedules_for_movie_date:
                    screens_data_key_alt = f"{movie_id_key}-{raw_year}{display_month}{display_day}"
                    screen_schedules_for_movie_date = screens_map.get(screens_data_key_alt, [])

                for screen_info in screen_schedules_for_movie_date:
                    if not isinstance(screen_info, dict): 
                        continue

                    # Use 'screen_name_short' if 'name' is too verbose or includes "(座席券)"
                    raw_screen_name = screen_info.get('screen_name_short') or screen_info.get('name', 'スクリーン情報なし')
                    screen_display_name = _get_screen_display_name(raw_screen_name, movie_title)
                    
                    for time_info in screen_info.get('time', []):
                        if not isinstance(time_info, dict): 
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
                            "date_text": current_date_iso_str,
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
            traceback.print_exc() 
            continue
            
    unique_showings_dict = {}
    for s_item in all_showings:
        key = (s_item["cinema_name"], s_item["movie_title"], s_item["date_text"], s_item["showtime"], s_item["screen_name"])
        if key not in unique_showings_dict:
            unique_showings_dict[key] = s_item
            
    return list(unique_showings_dict.values())

# --- Main Execution (for testing this module directly) ---
if __name__ == "__main__":
    print(f"INFO: Scraping {CINEMA_NAME} for up to 7 days...")
    showings = scrape_human_shibuya(max_days=7)
    
    print(f"\nCollected {len(showings)} showings for {CINEMA_NAME}.")
    if showings:
        print("\nFirst few showings:")
        for i, showing in enumerate(showings[:5]):
            print(f"--- Showing {i+1} ({CINEMA_NAME}) ---")
            for key, value in showing.items():
                print(f"  {key}: {value}")
        
        print(f"\n--- Example of a showing with purchase URL (if any) from {CINEMA_NAME} ---")
        found_purchasable = False
        for showing in showings:
            if showing["purchase_url"]:
                for key, value in showing.items():
                    print(f"  {key}: {value}")
                found_purchasable = True
                break
        if not found_purchasable:
            print(f"  No showings with an active online purchase URL found in the sample for {CINEMA_NAME}.")
    else:
        print(f"No showings collected for {CINEMA_NAME} or an error occurred during scraping.")

