import json
import os
import importlib  # To dynamically import scraper modules if you have many
import time
import google.generativeai as genai
import traceback # For more detailed error logging

# --- Configuration ---
# List your scraper module names here (without .py)
# Ensure these .py files exist in the same directory and are updated
# to use webdriver-manager and the correct _init_driver function.
SCRAPER_MODULE_NAMES = [
    "yebisu_garden_module",
    "cine_quinto_module",
    # "stranger_module", # Add other modules as needed
    # "another_cinema_module",
]

OUTPUT_FILE = 'showtimes.json'

# --- Gemini Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_model = None # Initialize

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Consider using 'gemini-1.5-flash-latest' for speed and cost-effectiveness
        # or 'gemini-1.0-pro-latest' / 'gemini-1.5-pro-latest' for potentially better quality
        gemini_model = genai.GenerativeModel(model_name='gemini-1.5-flash-latest')
        print("INFO: Google Gemini model configured successfully.")
    except Exception as e:
        print(f"ERROR: Could not configure Google Gemini: {e}")
        print("INFO: Gemini calls will be skipped.")
else:
    print("WARNING: GEMINI_API_KEY environment variable not set. Gemini calls will be skipped.")

def get_english_title_from_gemini(japanese_title: str) -> str | None:
    """
    Queries the configured Gemini model for the localized English title.
    Returns the English title or None if not found/error.
    """
    if not gemini_model or not japanese_title:
        return None

    # Prompt designed to get localized titles and handle unknowns
    prompt_parts = [
        "You are an expert movie database assistant.",
        "What is the official, commonly recognized, localized English release title for the following Japanese movie?",
        f"Japanese Movie Title: \"{japanese_title}\"",
        "Provide only the English title itself and nothing else. Do not add any extra phrases like 'The English title is'.",
        "If you are unsure, or if no official localized English title exists (e.g., it's only known by its Japanese title or a direct romanization internationally), then respond with only the single word 'UNKNOWN'.",
        "Do not provide a literal translation of the Japanese title unless that happens to be its official and commonly used localized English release title."
    ]
    prompt = "\n".join(prompt_parts)

    try:
        print(f"  Querying Gemini for: \"{japanese_title}\"")
        # Adding a timeout and retry could be beneficial for production
        response = gemini_model.generate_content(
            prompt,
            # Optional: Add safety_settings if needed
            # safety_settings=[
            #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            # ]
            )

        # Check for valid response parts
        if not response.parts:
            print(f"  Gemini API returned no parts for '{japanese_title}'.")
            return None
        
        english_title = response.text.strip()

        if not english_title or english_title.upper() == "UNKNOWN" or len(english_title) < 2:
            print(f"  Gemini responded UNKNOWN or empty for '{japanese_title}'.")
            return None
        
        # Heuristic: Check if the response is too similar to Japanese title or contains Japanese chars
        # This helps filter out cases where LLM doesn't find a proper English title
        # and just repeats the input or gives a non-English response.
        is_likely_not_english = False
        if japanese_title in english_title and abs(len(english_title) - len(japanese_title)) < 5:
            is_likely_not_english = True
        # Check for common Japanese character ranges (Hiragana, Katakana, CJK Unified Ideographs)
        if any('\u3040' <= char <= '\u309F' for char in english_title) or \
           any('\u30A0' <= char <= '\u30FF' for char in english_title) or \
           any('\u4E00' <= char <= '\u9FFF' for char in english_title):
            is_likely_not_english = True
        
        if is_likely_not_english:
            print(f"  Gemini response for \"{japanese_title}\" (\"{english_title}\") seems to be original or non-English; considering UNKNOWN.")
            return None

        print(f"  Gemini suggested: \"{english_title}\" for \"{japanese_title}\"")
        return english_title
    except Exception as e:
        print(f"  Error calling Gemini API for \"{japanese_title}\": {type(e).__name__} - {e}")
        # print(traceback.format_exc()) # Uncomment for detailed traceback during debugging
        return None

def run_scraper_module(module_name: str, all_data_list: list):
    """
    Imports and runs a scraper module, then processes its results.
    """
    try:
        print(f"\n--- Attempting to scrape data from: {module_name} ---")
        module = importlib.import_module(module_name)
        
        # Assuming each module has a primary scraping function, e.g., "scrape()" or "scrape_module_name()"
        # Adjust the function name as per your module's API
        scraper_function_name = None
        if hasattr(module, f"scrape_{module_name.split('_module')[0]}"): # e.g. scrape_yebisu_garden
            scraper_function_name = f"scrape_{module_name.split('_module')[0]}"
        elif hasattr(module, "scrape"): # Generic fallback
             scraper_function_name = "scrape"
        
        if not scraper_function_name or not hasattr(module, scraper_function_name):
            print(f"ERROR: Could not find a suitable scrape function in {module_name}.")
            return

        scrape_function = getattr(module, scraper_function_name)
        raw_data = scrape_function() # Call the module's main scraping function

        if raw_data:
            print(f"  Successfully scraped {len(raw_data)} raw entries from {module_name}.")
            for item in raw_data:
                # Ensure consistent key for Japanese title.
                # Your modules seem to use "title" as the key for the Japanese title.
                japanese_title = item.get("title")
                english_title = None

                if japanese_title:
                    # Here you could add other lookup methods first if desired:
                    # 1. Manual mapping file
                    # 2. TMDb API call

                    # Try Gemini
                    english_title = get_english_title_from_gemini(japanese_title)
                    time.sleep(1) # Add a small delay to respect potential API rate limits (adjust as needed)

                # Prepare the final item structure
                processed_item = item.copy() # Start with original data
                processed_item['movie_title_japanese'] = japanese_title
                processed_item['movie_title_english'] = english_title if english_title else None # Store None if not found

                # Remove original "title" if you only want the new keys, or keep it.
                # If keeping, ensure your HTML knows which one to prioritize.
                # if 'title' in processed_item and japanese_title:
                #     del processed_item['title']
                
                all_data_list.append(processed_item)
        else:
            print(f"  No data returned from {module_name}.")

    except ModuleNotFoundError:
        print(f"ERROR: Scraper module {module_name}.py not found.")
    except Exception as e:
        print(f"ERROR processing module {module_name}: {type(e).__name__} - {e}")
        print(traceback.format_exc()) # Detailed error for debugging this module's failure
        # Optionally add a placeholder error object for this cinema to all_data_list
        all_data_list.append({
            "cinema_name": module_name.replace("_module", "").replace("_", " ").title(), # Best guess for cinema name
            "error": f"Failed to scrape: {type(e).__name__} - {e}",
            "showtimes": [] # Or whatever structure your HTML expects for an error
        })

def main():
    """
    Main function to orchestrate scraping from all modules and write to JSON.
    """
    print("Starting main scraping process...")
    all_showtimes_data = []

    for module_name in SCRAPER_MODULE_NAMES:
        run_scraper_module(module_name, all_showtimes_data)

    print(f"\nTotal combined processed entries: {len(all_showtimes_data)}")

    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_showtimes_data, f, ensure_ascii=False, indent=2)
        print(f"Successfully wrote all data to {OUTPUT_FILE}")
    except Exception as e:
        print(f"ERROR writing final data to {OUTPUT_FILE}: {e}")

if __name__ == '__main__':
    main()
