import requests
from bs4 import BeautifulSoup, NavigableString
import re
import sys

CINEMA_NAME_SB = "新文芸坐" # Shin-Bungeiza
URL_SB = "https://www.shin-bungeiza.com/"

def clean_text_sb(element_or_string):
    """Helper function to get clean text."""
    if hasattr(element_or_string, 'get_text'):
        text = ' '.join(element_or_string.get_text(strip=True).split())
    elif isinstance(element_or_string, str):
        text = ' '.join(element_or_string.strip().split())
    else:
        return ""
    return text.strip()

def extract_film_title_sb(p_tag):
    """
    Extracts the film title from a <p> tag, attempting to remove known prefix spans.
    Example: <p><span class="hon-date">2本目割</span> はなれ瞽女おりん</p> -> "はなれ瞽女おりん"
    """
    if not p_tag:
        return "Unknown Film"

    # Clone the p_tag to avoid modifying the original soup during iteration
    p_clone = BeautifulSoup(str(p_tag), 'html.parser').p
    
    # Remove known prefix spans by class
    for span_class in ['hon-date', 'r-tag', 'b-tag']: # Add more classes if needed
        for span in p_clone.find_all('span', class_=span_class):
            span.decompose() # Remove the span and its content

    # Get the remaining text, which should be the title
    title = clean_text_sb(p_clone)
    return title if title else "Unknown Film"


def scrape_shin_bungeiza():
    """
    Scrapes the weekly schedule from the Shin-Bungeiza website.
    Returns a list of showings.
    """
    all_showings = []
    print(f"Debug ({CINEMA_NAME_SB}): Starting scrape_shin_bungeiza function.", file=sys.stderr)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(URL_SB, headers=headers, timeout=15)
        print(f"Debug ({CINEMA_NAME_SB}): HTTP GET request to {URL_SB} status: {response.status_code}", file=sys.stderr)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        tab_schedule_div = soup.find('div', class_='tab-schedule')
        if not tab_schedule_div:
            print(f"Error ({CINEMA_NAME_SB}): Could not find main schedule container (div.tab-schedule).", file=sys.stderr)
            return all_showings
        print(f"Debug ({CINEMA_NAME_SB}): Found div.tab-schedule.", file=sys.stderr)

        # Find all date tab labels to get the date and link to content
        date_labels = tab_schedule_div.find_all('label', class_='tab-label')
        print(f"Debug ({CINEMA_NAME_SB}): Found {len(date_labels)} date labels.", file=sys.stderr)

        for i, label in enumerate(date_labels):
            input_id = label.get('for') # e.g., "d2025-05-26"
            if not input_id or not input_id.startswith('d'):
                print(f"Debug ({CINEMA_NAME_SB}): Label {i+1} has invalid 'for' attribute: {input_id}", file=sys.stderr)
                continue
            
            schedule_date_str = input_id[1:] # Remove the leading 'd' to get "YYYY-MM-DD"
            print(f"\nDebug ({CINEMA_NAME_SB}): Processing date: {schedule_date_str}", file=sys.stderr)

            # Find the corresponding input tag (to then find its next sibling tab-content)
            input_tag = tab_schedule_div.find('input', id=input_id, class_='tab-switch')
            if not input_tag:
                print(f"Debug ({CINEMA_NAME_SB}): Could not find input tag for id {input_id}", file=sys.stderr)
                continue
                
            tab_content_div = input_tag.find_next_sibling('div', class_='tab-content')
            if not tab_content_div:
                print(f"Debug ({CINEMA_NAME_SB}): Could not find tab-content for date {schedule_date_str}", file=sys.stderr)
                continue
            print(f"Debug ({CINEMA_NAME_SB}): Found tab-content for {schedule_date_str}", file=sys.stderr)

            # Movie showings are direct <div> children of tab_content_div
            # Each such div contains a div.tab-img and a div.tab-txt
            movie_blocks = []
            for child_div in tab_content_div.find_all('div', recursive=False):
                 if child_div.find('div', class_='tab-txt'): # Check if it's a movie block
                    movie_blocks.append(child_div)
            
            print(f"Debug ({CINEMA_NAME_SB}): Found {len(movie_blocks)} movie blocks for {schedule_date_str}", file=sys.stderr)

            for movie_block in movie_blocks:
                tab_txt_div = movie_block.find('div', class_='tab-txt')
                if not tab_txt_div:
                    continue

                title_p_tag = tab_txt_div.find('p')
                film_title = extract_film_title_sb(title_p_tag)
                
                times_ul = tab_txt_div.find('ul')
                if not times_ul:
                    print(f"Debug ({CINEMA_NAME_SB}): No <ul> for times found for film '{film_title}' on {schedule_date_str}", file=sys.stderr)
                    # Add with N/A time if title found but no UL
                    if film_title != "Unknown Film":
                         all_showings.append({
                            "cinema": CINEMA_NAME_SB,
                            "date_text": schedule_date_str,
                            "title": film_title,
                            "showtime": "N/A"
                        })
                    continue

                showtime_lis = times_ul.find_all('li')
                if not showtime_lis:
                    print(f"Debug ({CINEMA_NAME_SB}): No <li> items for times found for film '{film_title}' on {schedule_date_str}", file=sys.stderr)
                    if film_title != "Unknown Film":
                         all_showings.append({
                            "cinema": CINEMA_NAME_SB,
                            "date_text": schedule_date_str,
                            "title": film_title,
                            "showtime": "N/A"
                        })
                    continue
                
                for li in showtime_lis:
                    time_a_tag = li.find('a')
                    showtime = clean_text_sb(time_a_tag) if time_a_tag else "N/A"
                    
                    if film_title != "Unknown Film" or showtime != "N/A": # Add if we have at least a title or a time
                        print(f"Debug ({CINEMA_NAME_SB}): Adding: Cinema='{CINEMA_NAME_SB}', Date='{schedule_date_str}', Title='{film_title}', Time='{showtime}'", file=sys.stderr)
                        all_showings.append({
                            "cinema": CINEMA_NAME_SB,
                            "date_text": schedule_date_str,
                            "title": film_title,
                            "showtime": showtime
                        })
        
        print(f"Debug ({CINEMA_NAME_SB}): scrape_shin_bungeiza function finished. Total showings collected: {len(all_showings)}", file=sys.stderr)
        return all_showings

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {URL_SB} for {CINEMA_NAME_SB}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"An unexpected error occurred while scraping {CINEMA_NAME_SB}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []

if __name__ == '__main__':
    if sys.platform == "win32":
        try:
            if sys.stdout.encoding != 'utf-8':
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if sys.stderr.encoding != 'utf-8':
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
            
    print(f"Testing {CINEMA_NAME_SB} scraper module...")
    showings = scrape_shin_bungeiza()
    if showings:
        print(f"\nFound {len(showings)} showings for {CINEMA_NAME_SB}:")
        for i, showing in enumerate(showings):
            if i < 20: 
                print(f"  {showing['cinema']} - {showing['date_text']} - {showing['title']} - {showing['showtime']}")
            elif i == 20:
                print(f"  ... and {len(showings) - 20} more.")
                break
    else:
        print(f"\nNo showings found by {CINEMA_NAME_SB} scraper during test.")

