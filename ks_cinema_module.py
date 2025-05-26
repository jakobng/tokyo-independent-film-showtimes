import requests
from bs4 import BeautifulSoup, NavigableString
import re
import sys
from datetime import datetime, date, timedelta # Added timedelta
import os

# --- Start: Configure stdout and stderr for UTF-8 on Windows (for direct script prints) ---
if __name__ == "__main__" and sys.platform == "win32":
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
# --- End: Configure stdout and stderr ---

CINEMA_NAME_KC = "K's Cinema (ケイズシネマ)"
IFRAME_SRC_URL_KC = "https://www.ks-cinema.com/calendar/index.html"

def clean_text_kc(element_or_string):
    if element_or_string is None:
        return ""
    if hasattr(element_or_string, 'get_text'):
        text = element_or_string.get_text(separator=' ', strip=True)
    elif isinstance(element_or_string, str):
        text = element_or_string.strip()
    else:
        return ""
    return ' '.join(text.split())

def parse_japanese_month(month_str):
    month_map = {
        '１月': 1, '２月': 2, '３月': 3, '４月': 4, '５月': 5, '６月': 6,
        '７月': 7, '８月': 8, '９月': 9, '１０月': 10, '１１月': 11, '１２月': 12,
        '1月': 1, '2月': 2, '3月': 3, '4月': 4, '5月': 5, '6月': 6,
        '7月': 7, '8月': 8, '9月': 9, '10月': 10, '11月': 11, '12月': 12
    }
    cleaned_month_str = re.sub(r'[^\d月]', '', month_str.strip())
    return month_map.get(cleaned_month_str)


def get_showtimes_from_cell(cell_element):
    """Extracts showtimes from a <td> element."""
    texts = []
    for content in cell_element.contents:
        if isinstance(content, NavigableString):
            txt = content.strip()
            if txt:
                texts.append(txt)
        elif content.name == 'span':
            if 'title_s' not in content.get('class', []) and \
               'period' not in content.get('class', []) and \
               not content.find('a'): 
                span_text = clean_text_kc(content)
                if span_text:
                    texts.append(span_text)
        elif content.name == 'br': 
            texts.append(" [BR] ")

    full_text_content = ' '.join(texts).replace(" [BR] ", " ") 
    full_text_content = clean_text_kc(full_text_content)
    
    if "作品案内参照" in full_text_content or "未定" in full_text_content:
        return ["N/A"]

    raw_times = []
    time_pattern = r'\d{1,2}:\d{2}' 
    
    potential_time_blocks = re.split(r'作品案内参照|未定|期間|～', full_text_content)
    time_block_to_parse = potential_time_blocks[-1].strip()

    found_times = re.findall(time_pattern, time_block_to_parse)
    if found_times:
        raw_times.extend(found_times)
    
    if not raw_times:
        raw_times = re.findall(time_pattern, full_text_content)
        
    cleaned_times = []
    for t in raw_times:
        t_cleaned = clean_text_kc(t)
        if re.fullmatch(time_pattern, t_cleaned): 
            cleaned_times.append(t_cleaned)
            
    return sorted(list(set(cleaned_times))) if cleaned_times else ["N/A"]


def scrape_ks_cinema():
    all_showings = []
    print(f"Debug ({CINEMA_NAME_KC}): Starting scrape_ks_cinema function.", file=sys.stderr)
    
    # --- Define "today" and the 7-day window dynamically ---
    today_date_obj = date.today() # Get the actual current date
    start_date_filter = today_date_obj
    end_date_filter = today_date_obj + timedelta(days=6) # 7 days including today
    
    print(f"Debug ({CINEMA_NAME_KC}): Filtering results for dates from {start_date_filter.strftime('%Y-%m-%d')} to {end_date_filter.strftime('%Y-%m-%d')}.", file=sys.stderr)
    
    # The assumed_year for parsing the calendar page should ideally also be dynamic,
    # especially if the script runs near year-end and the calendar spans across it.
    # For simplicity, if the calendar always starts around the current month,
    # using today_date_obj.year is a good start.
    assumed_year = today_date_obj.year 
    print(f"Debug ({CINEMA_NAME_KC}): Assuming base year for calendar parsing as {assumed_year}.", file=sys.stderr)


    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.ks-cinema.com/schedule/'
        }
        response = requests.get(IFRAME_SRC_URL_KC, headers=headers, timeout=20)
        print(f"Debug ({CINEMA_NAME_KC}): HTTP GET request to {IFRAME_SRC_URL_KC} status: {response.status_code}", file=sys.stderr)
        response.raise_for_status()
        
        page_content = response.content
        page_encoding = response.encoding if response.encoding else response.apparent_encoding
        
        effective_encoding = None
        if page_encoding and page_encoding.lower() in ['iso-8859-1', 'windows-1252']:
            try:
                page_content.decode('shift_jis', errors='strict')
                effective_encoding = 'shift_jis'
                print(f"Debug ({CINEMA_NAME_KC}): Detected Shift_JIS as likely encoding.", file=sys.stderr)
            except UnicodeDecodeError:
                try:
                    page_content.decode('euc-jp', errors='strict')
                    effective_encoding = 'euc-jp'
                    print(f"Debug ({CINEMA_NAME_KC}): Detected EUC-JP as likely encoding.", file=sys.stderr)
                except UnicodeDecodeError:
                    print(f"Debug ({CINEMA_NAME_KC}): Shift_JIS and EUC-JP failed. Using BS4 autodetect.", file=sys.stderr)
        elif page_encoding:
            effective_encoding = page_encoding
            print(f"Debug ({CINEMA_NAME_KC}): Using initially determined encoding: {effective_encoding}", file=sys.stderr)
        else:
            print(f"Debug ({CINEMA_NAME_KC}): No specific encoding detected by requests. Using BS4 autodetect.", file=sys.stderr)

        soup = BeautifulSoup(page_content, 'html.parser', from_encoding=effective_encoding)

        try:
            with open("ks_cinema_iframe_debug.html", "wb") as f:
                f.write(page_content)
            print(f"Debug ({CINEMA_NAME_KC}): Saved iframe HTML to ks_cinema_iframe_debug.html", file=sys.stderr)
        except Exception as e_save:
            print(f"Warning ({CINEMA_NAME_KC}): Could not save debug HTML: {e_save}", file=sys.stderr)

        slides = soup.find_all('div', class_='slide')
        if not slides:
            print(f"Warning ({CINEMA_NAME_KC}): No 'div.slide' elements found.", file=sys.stderr)
            return []

        for slide_idx, slide_div in enumerate(slides):
            table = slide_div.find('table')
            if not table:
                print(f"Warning ({CINEMA_NAME_KC}): No table found in slide {slide_idx+1}.", file=sys.stderr)
                continue
            
            print(f"\nDebug ({CINEMA_NAME_KC}): Processing slide {slide_idx + 1}", file=sys.stderr)

            month_row = table.find('tr', class_='month')
            day_header_row = table.find('tr', class_='day')

            if not month_row or not day_header_row:
                print(f"Warning ({CINEMA_NAME_KC}): Missing month or day header row in slide {slide_idx+1}.", file=sys.stderr)
                continue
            
            month_info_list = []
            month_ths_from_row = month_row.find_all('th')
            current_year_for_month_header = assumed_year # Use the dynamically determined year
            
            # Determine the year for each month in the header, handling year rollovers
            last_parsed_month_num = 0
            for m_th in month_ths_from_row:
                month_text_content = clean_text_kc(m_th.find('span') if m_th.find('span') else m_th)
                m_num = parse_japanese_month(month_text_content)
                if m_num:
                    # If current month is less than last parsed month (e.g. 1 after 12), increment year
                    if month_info_list and m_num < last_parsed_month_num : 
                        current_year_for_month_header +=1
                    
                    m_colspan = int(m_th.get('colspan', 1))
                    month_info_list.append({'month': m_num, 'year': current_year_for_month_header, 'colspan': m_colspan, 'days_processed_in_header': 0})
                    last_parsed_month_num = m_num # Update last parsed month
            
            print(f"Debug ({CINEMA_NAME_KC}): Month info for slide {slide_idx+1}: {month_info_list}", file=sys.stderr)

            day_ths = day_header_row.find_all('th', scope='col')
            column_dates = []
            
            if not month_info_list:
                print(f"Warning ({CINEMA_NAME_KC}): No valid month info for slide {slide_idx+1}. Cannot map days.", file=sys.stderr)
            else:
                day_th_iter = iter(day_ths)
                current_month_info_idx = 0
                for _ in range(len(day_ths)): 
                    if current_month_info_idx >= len(month_info_list):
                        column_dates.append(None) 
                        continue
                    current_m_info = month_info_list[current_month_info_idx]
                    try:
                        day_th_element = next(day_th_iter)
                        day_num_str = clean_text_kc(day_th_element)
                        day_num = int(day_num_str)
                        try:
                            full_date_str = date(current_m_info['year'], current_m_info['month'], day_num).strftime('%Y-%m-%d')
                            column_dates.append(full_date_str)
                        except ValueError: 
                            column_dates.append(None)
                        current_m_info['days_processed_in_header'] += 1
                        if current_m_info['days_processed_in_header'] >= current_m_info['colspan']:
                            current_month_info_idx += 1
                    except (StopIteration, ValueError):
                        column_dates.append(None) 
            
            # print(f"Debug ({CINEMA_NAME_KC}): Column date map (slide {slide_idx+1}), first 5: {column_dates[:5]}", file=sys.stderr)

            movie_rows = table.find_all('tr', class_='movie')
            for row_idx, movie_row in enumerate(movie_rows):
                first_cell_td = movie_row.find('td')
                if first_cell_td:
                    if "開場時間" in clean_text_kc(first_cell_td):
                        continue
                else: 
                    continue

                current_col_index_in_row = 0
                for cell_idx, cell in enumerate(movie_row.find_all('td')):
                    colspan = int(cell.get('colspan', 1))
                    if cell.get('bgcolor') == '#E9E9E9' or clean_text_kc(cell) == "":
                        current_col_index_in_row += colspan
                        continue
                    title_span = cell.find('span', class_='title_s')
                    if not title_span:
                        current_col_index_in_row += colspan
                        continue 
                    film_title = clean_text_kc(title_span)
                    if not film_title: 
                        current_col_index_in_row += colspan
                        continue
                    showtimes = get_showtimes_from_cell(cell)
                    if showtimes and showtimes != ["N/A"]:
                        for day_offset in range(colspan):
                            date_col_idx_for_showing = current_col_index_in_row + day_offset
                            if date_col_idx_for_showing < len(column_dates) and column_dates[date_col_idx_for_showing]:
                                event_date_str = column_dates[date_col_idx_for_showing]
                                try:
                                    event_date_obj = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                                    if start_date_filter <= event_date_obj <= end_date_filter:
                                        for st in showtimes:
                                            all_showings.append({
                                                "cinema": CINEMA_NAME_KC,
                                                "date_text": event_date_str,
                                                "title": film_title,
                                                "showtime": st
                                            })
                                except ValueError:
                                    pass 
                    current_col_index_in_row += colspan
        
        if not all_showings and slides: 
             print(f"Warning ({CINEMA_NAME_KC}): Showings list is empty after processing. This might be correct if no movies are in the 7-day window, or a parsing issue for relevant dates.", file=sys.stderr)


    except requests.exceptions.RequestException as e:
        print(f"Error ({CINEMA_NAME_KC}): Fetching URL {IFRAME_SRC_URL_KC} failed: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"An unexpected error occurred while scraping {CINEMA_NAME_KC}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []

    unique_showings_filtered = []
    seen = set()
    for showing in all_showings: 
        identifier = (showing['date_text'], showing['title'], showing['showtime'])
        if identifier not in seen:
            unique_showings_filtered.append(showing)
            seen.add(identifier)
    
    print(f"Debug ({CINEMA_NAME_KC}): scrape_ks_cinema finished. Total unique showings within 7-day window: {len(unique_showings_filtered)}", file=sys.stderr)
    return unique_showings_filtered

if __name__ == '__main__':
    print(f"Testing {CINEMA_NAME_KC} scraper module...")
    showings = scrape_ks_cinema()
    if showings:
        showings.sort(key=lambda x: (x.get('date_text', ''), x.get('title', ''), x.get('showtime', '')))
        print(f"\nFound {len(showings)} showings for {CINEMA_NAME_KC} (within the 7-day window):")
        for i, showing in enumerate(showings): 
            print(f"  {showing.get('cinema')} - {showing.get('date_text')} - {showing.get('title')} - {showing.get('showtime')}")
    else:
        print(f"\nNo showings found by {CINEMA_NAME_KC} scraper for the 7-day window. Please check 'ks_cinema_iframe_debug.html'.")

