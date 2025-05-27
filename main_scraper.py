import json
import image_forum_module
import eurospace_module 
import shin_bungeiza_module
import stranger_module  
import ks_cinema_module # <-- ADDED IMPORT FOR K'S CINEMA
import sys 
import io  

# --- Start: Configure stdout and stderr for UTF-8 on Windows (for this script's prints) ---
if sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        print("Note: main_scraper stdout/stderr reconfigured to UTF-8 for Windows.", file=sys.__stderr__)
    except Exception:
        pass 
# --- End: Configure stdout and stderr ---

def run_all_scrapers():
    print("Starting all scrapers...")
    all_movie_listings = []

    # Scrape Theatre Image Forum
    print("\nScraping Theatre Image Forum...")
    try:
        image_forum_showings = image_forum_module.scrape_image_forum()
        if image_forum_showings:
            all_movie_listings.extend(image_forum_showings)
            print(f"Found {len(image_forum_showings)} listings for Theatre Image Forum.")
        else:
            print("No listings found for Theatre Image Forum.")
    except Exception as e:
        print(f"Error during Image Forum scraping: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)


    # Scrape Eurospace
    print("\nScraping Eurospace...")
    try:
        eurospace_showings = eurospace_module.scrape_eurospace()
        if eurospace_showings:
            all_movie_listings.extend(eurospace_showings)
            print(f"Found {len(eurospace_showings)} listings for Eurospace.")
        else:
            print("No listings found for Eurospace.")
    except Exception as e:
        print(f"Error during Eurospace scraping: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)

    # Scrape Shin-Bungeiza
    print("\nScraping Shin-Bungeiza...")
    try:
        shin_bungeiza_showings = shin_bungeiza_module.scrape_shin_bungeiza()
        if shin_bungeiza_showings:
            all_movie_listings.extend(shin_bungeiza_showings)
            print(f"Found {len(shin_bungeiza_showings)} listings for Shin-Bungeiza.")
        else:
            print("No listings found for Shin-Bungeiza.")
    except Exception as e:
        print(f"Error during Shin-Bungeiza scraping: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        
    # Scrape Stranger
    print("\nScraping Stranger cinema...")
    try:
        stranger_showings = stranger_module.scrape_stranger() 
        if stranger_showings:
            all_movie_listings.extend(stranger_showings)
            print(f"Found {len(stranger_showings)} listings for Stranger cinema.")
        else:
            print("No listings found for Stranger cinema.")
    except Exception as e:
        print(f"Error during Stranger cinema scraping: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)

    # Scrape K's Cinema  <-- ADDED SECTION FOR K'S CINEMA
    print("\nScraping K's Cinema...")
    try:
        ks_cinema_showings = ks_cinema_module.scrape_ks_cinema() 
        if ks_cinema_showings:
            all_movie_listings.extend(ks_cinema_showings)
            print(f"Found {len(ks_cinema_showings)} listings for K's Cinema.")
        else:
            print("No listings found for K's Cinema.")
    except Exception as e:
        print(f"Error during K's Cinema scraping: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        
    # --- LATER, YOU WILL ADD CALLS TO OTHER CINEMA SCRAPERS HERE ---

    print(f"\nTotal listings collected from all scrapers: {len(all_movie_listings)}")
    return all_movie_listings

def save_to_json(data, filename="showtimes.json"):
    """Saves the provided data to a JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Data successfully saved to {filename}")
    except IOError as e:
        print(f"Error saving data to {filename}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred while saving to JSON: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == '__main__':
    collected_data = run_all_scrapers()
    if collected_data:
        try:
            collected_data.sort(key=lambda x: (x.get('cinema', ''), x.get('date_text', ''), x.get('showtime', '')))
        except Exception as e_sort:
            print(f"Note: Could not sort collected data due to an error: {e_sort}. Proceeding with unsorted data.", file=sys.stderr)
            
        save_to_json(collected_data)
        print("\n--- First few aggregated results (if any) ---")
        for i, item in enumerate(collected_data[:5]): 
             print(f"  {item.get('cinema')} - {item.get('date_text')} - {item.get('title')} - {item.get('showtime')}")
        if len(collected_data) > 5:
            print(f"  ... and {len(collected_data) - 5} more.")

    else:
        print("No data collected from any scraper, JSON file not created.")
