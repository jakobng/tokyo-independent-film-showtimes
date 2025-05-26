import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime # Not strictly needed for date parsing from this page, but good to have
import sys # For error printing

CINEMA_NAME_ES = "ユーロスペース" # Eurospace
URL_ES = "http://www.eurospace.co.jp/schedule/" # Updated URL for the 7-day schedule

def clean_text_es(element_or_string):
    """Helper function to get clean text, removing extra spaces and font tags."""
    if hasattr(element_or_string, 'get_text'):
        text = ' '.join(element_or_string.get_text(strip=True).split())
    elif isinstance(element_or_string, str): # For NavigableString
        text = ' '.join(element_or_string.strip().split())
    else:
        return ""
    text = re.sub(r'<font[^>]*>', '', text) # Remove <font...> tags
    text = text.replace('</font>', '')    # Remove </font> tags
    return text.strip()

def extract_specific_title_es(text_content):
    """Extracts a film title from text, looking for 『...』 pattern."""
    if not text_content:
        return None
    match = re.search(r'『([^』]+)』', text_content) # Japanese single quotes
    if match:
        return match.group(1).strip()
    return None

def scrape_eurospace():
    """
    Scrapes the 7-day schedule from the Eurospace schedule page.
    Returns a list of showings.
    """
    all_showings = []
    print(f"Debug ({CINEMA_NAME_ES}): Starting scrape_eurospace function.", file=sys.stderr)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(URL_ES, headers=headers, timeout=15)
        print(f"Debug ({CINEMA_NAME_ES}): HTTP GET request to {URL_ES} status: {response.status_code}", file=sys.stderr)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        schedule_section = soup.find('section', id='schedule')
        if not schedule_section:
            print(f"Error ({CINEMA_NAME_ES}): Could not find schedule section (section#schedule).", file=sys.stderr)
            return all_showings
        print(f"Debug ({CINEMA_NAME_ES}): Found schedule section (section#schedule).", file=sys.stderr)

        daily_articles = schedule_section.find_all('article', recursive=False)
        print(f"Debug ({CINEMA_NAME_ES}): Found {len(daily_articles)} <article> tags directly under section#schedule.", file=sys.stderr)

        if not daily_articles:
            print(f"Error ({CINEMA_NAME_ES}): No <article> tags found in schedule section.", file=sys.stderr)
            return all_showings

        for i, article in enumerate(daily_articles):
            print(f"\nDebug ({CINEMA_NAME_ES}): Processing article {i+1}/{len(daily_articles)}.", file=sys.stderr)
            date_tag = article.find('h3')
            if not date_tag:
                print(f"Debug ({CINEMA_NAME_ES}): Article {i+1} has no <h3> tag, skipping (likely ticket info).", file=sys.stderr)
                continue
            
            schedule_date_str = clean_text_es(date_tag)
            if not schedule_date_str or not re.search(r'\d{4}年\d{1,2}月\d{1,2}日', schedule_date_str):
                print(f"Debug ({CINEMA_NAME_ES}): Article {i+1} <h3> content '{schedule_date_str}' does not look like a date, skipping.", file=sys.stderr)
                continue
            print(f"Debug ({CINEMA_NAME_ES}): Found date: {schedule_date_str}", file=sys.stderr)

            current_screen_name_from_text = "Unknown Screen (default)"
            # Iterate through the direct children of the article to find screen names and tables
            for child_node in article.children: # .children gives an iterator, .contents gives a list
                if isinstance(child_node, str): # It's a NavigableString (loose text)
                    text_content = clean_text_es(child_node)
                    if "スクリーン1" in text_content:
                        current_screen_name_from_text = "スクリーン1 (Screen 1)"
                        print(f"Debug ({CINEMA_NAME_ES}): Identified screen name: {current_screen_name_from_text}", file=sys.stderr)
                    elif "スクリーン2" in text_content:
                        current_screen_name_from_text = "スクリーン2 (Screen 2)"
                        print(f"Debug ({CINEMA_NAME_ES}): Identified screen name: {current_screen_name_from_text}", file=sys.stderr)
                    # Add more screen names if necessary (e.g., スクリーン3)
                
                elif child_node.name == 'div' and 'scrolltable' in child_node.get('class', []):
                    print(f"Debug ({CINEMA_NAME_ES}): Found a div.scrolltable for screen '{current_screen_name_from_text}' on date '{schedule_date_str}'.", file=sys.stderr)
                    table = child_node.find('table')
                    if not table:
                        print(f"Warning ({CINEMA_NAME_ES}): div.scrolltable for {current_screen_name_from_text} on {schedule_date_str} has no table.", file=sys.stderr)
                        continue

                    # --- MODIFIED ROW FINDING LOGIC ---
                    rows = table.find_all('tr', recursive=False) # Get <tr> directly from <table>
                    if not rows: # If no rows are found directly under table
                        print(f"Warning ({CINEMA_NAME_ES}): table for {current_screen_name_from_text} on {schedule_date_str} has no <tr> rows directly under <table>. Trying tbody...", file=sys.stderr)
                        # As a fallback, try finding tbody again, then rows, in case the structure is strict
                        tbody = table.find('tbody')
                        if not tbody:
                             print(f"Warning ({CINEMA_NAME_ES}): Still no tbody found for {current_screen_name_from_text} on {schedule_date_str}.", file=sys.stderr)
                             continue
                        rows = tbody.find_all('tr', recursive=False)
                        if not rows:
                            print(f"Warning ({CINEMA_NAME_ES}): Found tbody but no <tr> rows within it for {current_screen_name_from_text} on {schedule_date_str}.", file=sys.stderr)
                            continue
                    # --- END OF MODIFIED ROW FINDING LOGIC ---
                        
                    print(f"Debug ({CINEMA_NAME_ES}): Found {len(rows)} rows in table for {current_screen_name_from_text} on {schedule_date_str}.", file=sys.stderr)

                    if len(rows) < 2:
                        if not (len(rows) == 1 and not rows[0].find_all('td')) and not (len(rows) == 2 and not rows[0].find_all('td') and not rows[1].find_all('td')):
                             print(f"Info ({CINEMA_NAME_ES} - {current_screen_name_from_text} on {schedule_date_str}): Table has less than 2 rows or rows are empty, assuming no movies.", file=sys.stderr)
                        continue

                    time_tds = rows[0].find_all('td')
                    film_tds = rows[1].find_all('td')
                    print(f"Debug ({CINEMA_NAME_ES}): Found {len(time_tds)} time cells and {len(film_tds)} film cells.", file=sys.stderr)


                    num_films_on_screen = min(len(time_tds), len(film_tds))
                    if num_films_on_screen == 0 and (len(time_tds) > 0 or len(film_tds) > 0) : # If one has cells but the other doesn't match
                        print(f"Warning ({CINEMA_NAME_ES} - {current_screen_name_from_text} on {schedule_date_str}): Mismatch in time/film cells. Times: {len(time_tds)}, Films: {len(film_tds)}", file=sys.stderr)


                    for j in range(num_films_on_screen):
                        showtime = clean_text_es(time_tds[j])
                        if not showtime:
                            print(f"Debug ({CINEMA_NAME_ES}): Empty showtime cell at index {j}, skipping.", file=sys.stderr)
                            continue
                        
                        film_cell = film_tds[j]
                        a_tag = film_cell.find('a')
                        primary_title = clean_text_es(a_tag) if a_tag else "Unknown Film"
                        
                        # Replace <br> with a separator to handle text parts
                        for br_tag in film_cell.find_all('br'):
                            br_tag.replace_with(" [BR_SEP] ") 
                        
                        full_cell_text = clean_text_es(film_cell)
                        parts = full_cell_text.split(" [BR_SEP] ")
                        
                        actual_film_title = primary_title
                        specific_title_from_parts = None

                        for part_text in parts: # Iterate through parts split by <br>
                            extracted_specific = extract_specific_title_es(part_text)
                            if extracted_specific:
                                specific_title_from_parts = extracted_specific
                                break # Found the specific title for this entry
                        
                        if specific_title_from_parts:
                            # If primary title indicates a series, append specific.
                            if "特集" in primary_title or "監督特集" in primary_title: # "Feature", "Director Special"
                                actual_film_title = f"{primary_title}: {specific_title_from_parts}"
                            else: # Otherwise, specific title from 『』 is likely the main one
                                 actual_film_title = specific_title_from_parts
                        
                        print(f"Debug ({CINEMA_NAME_ES}): Adding: Cinema='{CINEMA_NAME_ES}', Date='{schedule_date_str}', Screen='{current_screen_name_from_text}', Title='{actual_film_title.strip()}', Time='{showtime.strip()}'", file=sys.stderr)
                        all_showings.append({
                            "cinema": CINEMA_NAME_ES,
                            "date_text": schedule_date_str,
                            "screen": current_screen_name_from_text,
                            "title": actual_film_title.strip(),
                            "showtime": showtime.strip()
                        })
        
        print(f"Debug ({CINEMA_NAME_ES}): scrape_eurospace function finished. Total showings collected: {len(all_showings)}", file=sys.stderr)
        return all_showings

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {URL_ES} for {CINEMA_NAME_ES}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"An unexpected error occurred while scraping {CINEMA_NAME_ES}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []

if __name__ == '__main__':
    if sys.platform == "win32":
        try:
            if sys.stdout.encoding != 'utf-8':
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if sys.stderr.encoding != 'utf-8': # Make sure stderr is also configured for debug prints
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass # Silently ignore if reconfiguration fails
            
    print(f"Testing {CINEMA_NAME_ES} scraper module...")
    showings = scrape_eurospace()
    if showings:
        print(f"\nFound {len(showings)} showings for {CINEMA_NAME_ES}:") # Main output to stdout
        for i, showing in enumerate(showings):
            if i < 20: # Print more for 7-day schedule
                print(f"  {showing['cinema']} - {showing['date_text']} - {showing['screen']} - {showing['title']} - {showing['showtime']}")
            elif i == 20:
                print(f"  ... and {len(showings) - 20} more.")
                break
    else:
        print(f"\nNo showings found by {CINEMA_NAME_ES} scraper during test.")
