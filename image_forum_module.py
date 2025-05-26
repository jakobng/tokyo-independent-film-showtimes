import requests
from bs4 import BeautifulSoup
import re
import sys
import io

# --- Start: Configure stdout and stderr for UTF-8 on Windows (Optional for module, but good if testing directly) ---
if __name__ == "__main__" and sys.platform == "win32": # Only run if script is executed directly
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        print("Note: stdout/stderr reconfigured to UTF-8 for Windows for direct testing.", file=sys.__stderr__)
    except Exception:
        pass # Ignore errors if reconfiguration fails in module context
# --- End: Configure stdout and stderr ---

CINEMA_NAME_IF = "シアター・イメージフォーラム" # Theatre Image Forum (Specific to this module)
URL_IF = "https://www.imageforum.co.jp/theatre/schedule/"

def clean_text(text_element):
    if text_element:
        return ' '.join(text_element.get_text(strip=True).split())
    return ""

def extract_specific_title_from_span(span_text):
    if not span_text:
        return None
    match = re.search(r'"([^"]+)"', span_text)
    if match:
        return match.group(1).strip()
    return None

def scrape_image_forum(): # Renamed function for clarity
    """
    Scrapes the movie schedule from the Theatre Image Forum website
    and returns a list of Pshowings.
    """
    all_showings = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(URL_IF, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        content_area = soup.find('section', class_='content-area')
        if not content_area:
            print(f"Error ({CINEMA_NAME_IF}): Could not find main content area.", file=sys.stderr)
            return all_showings # Return empty list

        daily_schedule_boxes = content_area.find_all('div', class_='schedule-day-box')
        if not daily_schedule_boxes:
            print(f"Error ({CINEMA_NAME_IF}): Could not find daily schedule boxes.", file=sys.stderr)
            return all_showings

        for day_box in daily_schedule_boxes:
            date_tag = day_box.find('h2', class_='schedule-day-title')
            date_str = clean_text(date_tag) if date_tag else "Unknown Date"
            date_str = date_str.replace(" schedule", "").strip()

            schedule_boxes_for_day = day_box.find_all('div', class_='schedule-box')
            for schedule_box in schedule_boxes_for_day:
                theatre_name_img = schedule_box.find('caption img')
                theatre_info_alt = clean_text(theatre_name_img.get('alt', '')) if theatre_name_img else ""
                # You might want to parse specific theatre name (e.g., "Theater 1") if available

                movie_entries = schedule_box.find_all('td', class_='schebox')
                for entry in movie_entries:
                    showtime_tag = entry.find('a').find('div') if entry.find('a') else None
                    showtime = clean_text(showtime_tag) if showtime_tag else "N/A"

                    primary_title_tag = entry.find('a').find('p') if entry.find('a') else None
                    primary_title = clean_text(primary_title_tag) if primary_title_tag else "Unknown Film"
                    
                    span_tags = entry.find('a').find_all('span') if entry.find('a') else []
                    actual_film_title = primary_title
                    specific_title_found_in_span = False

                    for span in span_tags:
                        span_text_cleaned = clean_text(span)
                        extracted_specific_title = extract_specific_title_from_span(span_text_cleaned)
                        if extracted_specific_title:
                            specific_title_found_in_span = True
                            if "Feature screening" in primary_title or "特集" in primary_title or "Director" in primary_title:
                                actual_film_title = f"{primary_title}: {extracted_specific_title}"
                            else:
                                actual_film_title = extracted_specific_title
                            break 
                    
                    # If no specific title was found in spans with quotes, but primary title looks like a series
                    # and there's other text in spans (like "「...」を上映" - needs original Japanese check if so)
                    # This part might need refinement based on more examples of special programs
                    
                    # Clean up possible "<font>" tag remnants
                    actual_film_title = actual_film_title.replace("<font style=\"vertical-align: inherit;\">", "").replace("</font>", "").strip()
                    showtime = showtime.replace("<font style=\"vertical-align: inherit;\">", "").replace("</font>", "").strip()

                    showing_info = {
                        "cinema": CINEMA_NAME_IF,
                        "date_text": date_str, # Raw date string from site
                        # "theatre_screen": theatre_info_alt, # Optional screen info
                        "title": actual_film_title,
                        "showtime": showtime
                    }
                    all_showings.append(showing_info)
        
        return all_showings

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {URL_IF} for {CINEMA_NAME_IF}: {e}", file=sys.stderr)
        return all_showings # Return whatever was collected so far, or empty
    except Exception as e:
        print(f"An unexpected error occurred while scraping {CINEMA_NAME_IF}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return all_showings

if __name__ == '__main__':
    # This part is for testing the module directly
    # The UTF-8 configuration for stdout/stderr is above this block for this direct execution.
    print(f"Testing {CINEMA_NAME_IF} scraper module...")
    showings = scrape_image_forum()
    if showings:
        print(f"Found {len(showings)} showings for {CINEMA_NAME_IF}:")
        for i, showing in enumerate(showings):
            if i < 5: # Print first 5 for brevity
                print(f"  {showing['cinema']} - {showing['date_text']} - {showing['title']} - {showing['showtime']}")
            elif i == 5:
                print(f"  ... and {len(showings) - 5} more.")
                break
    else:
        print(f"No showings found by {CINEMA_NAME_IF} scraper during test.")
