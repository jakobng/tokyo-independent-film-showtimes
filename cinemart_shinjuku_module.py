import datetime as _dt
from typing import List, Dict

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ────────────────────────────────────────────────────────────────────────────────
# Cinemart Shinjuku (シネマート新宿) – Selenium scraper
# URL *must* be the one below.  The timetable is rendered client‑side, so we use
# Selenium to click through each date tab and extract the showings.
# ────────────────────────────────────────────────────────────────────────────────
__all__ = ["scrape_cinemart_shinjuku"]

URL = "https://cinemart.cineticket.jp/theater/shinjuku/schedule"
CINEMA_NAME = "シネマート新宿"
DAY_TAB_CSS = "div[id^='dateSlider']"              # clickable date boxes at top
SCHEDULE_CONTAINER_ID_TPL = "dateJouei{date}"      # hidden/visible schedule divs
PANEL_CSS = "div.panel.movie-panel"               # each movie block
SCHEDULE_ITEM_CSS = "div.movie-schedule"          # within panel – individual showings


# ╭──────────────────────────────────────────────────────────────────────────────╮
# │ Helpers                                                                     │
# ╰──────────────────────────────────────────────────────────────────────────────╯

def _init_driver(headless: bool = True) -> webdriver.Chrome:
    """Spin up a Chrome/Chromium WebDriver (headless by default)."""
    chrome_opts = Options()
    if headless:
        chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--window-size=1920,1080")

    # Allow calling script to inject custom binary / driver via env if needed.
    return webdriver.Chrome(options=chrome_opts)


def _iso_date_from_tab(el) -> str:
    """Parse the YYYY‑MM‑DD date encoded in the dateSlider element id."""
    # id looks like dateSlider20250528 ⇒ take last 8 chars and format.
    id_text = el.get_attribute("id")
    ymd = id_text[-8:]
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


def _click_via_js(driver, element):
    driver.execute_script("arguments[0].click();", element)


def _extract_showings_for_date(driver, date_iso: str) -> List[Dict]:
    """Given driver on page where the schedule for *date_iso* is visible, parse it."""
    container_id = SCHEDULE_CONTAINER_ID_TPL.format(date=date_iso.replace("-", ""))
    try:
        container = driver.find_element(By.ID, container_id)
    except Exception:
        # container may be hidden until we click the date tab; caller ensures it.
        return []

    rows: List[Dict] = []
    panels = container.find_elements(By.CSS_SELECTOR, PANEL_CSS)
    for panel in panels:
        try:
            title = panel.find_element(By.CSS_SELECTOR, ".title-jp").text.strip()
        except Exception:
            # fallback to any header text
            title = panel.text.split("\n", 1)[0].strip()

        # each showing inside
        for sched in panel.find_elements(By.CSS_SELECTOR, SCHEDULE_ITEM_CSS):
            try:
                showtime = sched.find_element(By.CSS_SELECTOR, ".movie-schedule-begin").text.strip()
                screen = sched.find_element(By.CSS_SELECTOR, ".screen-name").text.strip()
            except Exception:
                continue  # malformed row – skip

            rows.append({
                "cinema": CINEMA_NAME,
                "date_text": date_iso,
                "screen": screen,
                "title": title,
                "showtime": showtime,
            })
    return rows


# ╭──────────────────────────────────────────────────────────────────────────────╮
# │ Public API                                                                  │
# ╰──────────────────────────────────────────────────────────────────────────────╯

def scrape_cinemart_shinjuku(max_days: int = 7, headless: bool = True) -> List[Dict]:
    """Return a list of showings for up to *max_days* starting today.

    Args:
        max_days: how many date tabs to process (starting with the first one in
                   the slider, which is usually today).
        headless: run Chrome in headless mode.
    """
    rows: List[Dict] = []
    driver = _init_driver(headless=headless)
    driver.set_page_load_timeout(30)
    try:
        driver.get(URL)
        # Wait for date tabs to appear
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, DAY_TAB_CSS))
        )

        date_tabs = driver.find_elements(By.CSS_SELECTOR, DAY_TAB_CSS)
        for idx, tab in enumerate(date_tabs[:max_days]):
            date_iso = _iso_date_from_tab(tab)

            if idx == 0:
                # First tab is already selected on page load – no click needed.
                pass
            else:
                _click_via_js(driver, tab)
                # Wait until the corresponding schedule container becomes
                # visible (display != 'none').
                container_id = SCHEDULE_CONTAINER_ID_TPL.format(date=date_iso.replace("-", ""))
                try:
                    WebDriverWait(driver, 8).until(
                        EC.visibility_of_element_located((By.ID, container_id))
                    )
                except TimeoutException:
                    # Sometimes the container never shows (maintenance days).
                    continue

            rows.extend(_extract_showings_for_date(driver, date_iso))

    finally:
        driver.quit()

    # Deduplicate rows (same title/time/screen) just in case
    unique = { (r["cinema"], r["date_text"], r["screen"], r["title"], r["showtime"]): r for r in rows }
    return list(unique.values())


if __name__ == "__main__":
    print("INFO: Running Cinemart Shinjuku scraper standalone …")
    showings = scrape_cinemart_shinjuku()
    print(f"Collected {len(showings)} showings from {CINEMA_NAME}.")
    for row in showings[:10]:
        print(row)
