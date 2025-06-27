"""
cinema_qualite_module.py — 2025-06-25 (v2)
* Strips event text (e.g., ★) from titles.
* Robust synopsis extraction (longest text block, min 60 chars, no <h1>)
* Smarter director mining:
    監督：NAME ｜ NAME監督 ｜ NAMEを監督に  … etc.
    (Now handles names with spaces and middle-dots)
* Cleans adjective prefixes (鬼才/巨匠…)
* Empty English title → None
* Saves JSON out with today’s date.
"""

from __future__ import annotations
import datetime as _dt, json, re, unicodedata
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import requests
from bs4 import BeautifulSoup

# ─────────────────── constants
SCHEDULE_URL = "https://musashino.cineticket.jp/cq/theater/qualite/schedule"
LISTING_URL  = "https://qualite.musashino-k.jp/movies/"
HEADERS = {"User-Agent": "CinemaQualiteScraper/2.2 (+https://github.com/your-org/project)"}
CINEMA_NAME = "新宿シネマカリテ"

_RE_DATE_ID   = re.compile(r"^dateJouei(\d{8})$")
_RE_FW_NUM    = str.maketrans({chr(fw): str(d) for d, fw in enumerate(range(0xFF10, 0xFF1A))})
_RE_RT1       = re.compile(r"(\d+)\s*時間\s*(\d+)\s*分?")
_RE_RT2       = re.compile(r"(\d+)\s*分")
_ADJ_PREFIXES = ("鬼才", "巨匠", "世界的", "若き", "名匠")

# ─────────────────── helpers
def _fw2ascii(t:str)->str: return t.translate(_RE_FW_NUM).strip()
def _norm_title(t:str)->str:
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[『』「」【】〈〉《》]", "", t)
    return re.sub(r"[^\w\u3040-\u30FF\u4E00-\u9FFF]", "", t).lower()
def _parse_rt(txt:str)->Optional[str]:
    txt=_fw2ascii(txt)
    if (m:=_RE_RT1.search(txt)): return str(int(m.group(1))*60+int(m.group(2)))
    if (m:=_RE_RT2.search(txt)): return m.group(1).lstrip("0") or "0"
    return None
def _clean_name(n:str)->str:
    n = n.strip() # Strip whitespace first
    for adj in _ADJ_PREFIXES:
        if n.startswith(adj): n = n[len(adj):]
    return n.strip()

def _get(session,url): r=session.get(url,headers=HEADERS,timeout=20); r.raise_for_status(); return r.text

# ─────────────────── step-1 schedule
def _parse_schedule(html:str,today:_dt.date,max_days:int)->Tuple[List[dict],Set[str]]:
    soup = BeautifulSoup(html,"html.parser")
    out, titles, seen = [], set(), set()
    for div in soup.find_all(id=_RE_DATE_ID):
        date=_dt.datetime.strptime(_RE_DATE_ID.match(div["id"]).group(1),"%Y%m%d").date()
        if (date-today).days>max_days: continue
        date_iso=date.isoformat()
        for panel in div.select("div.movie-panel"):
            jp=panel.select_one("div.title-jp")
            en=panel.select_one("div.title-eng")
            title_raw = (jp or en).get_text(strip=True)
            # CHANGE #1: Strip event text (like ★...) from the title
            title = title_raw.split('★')[0].strip()
            title_en = (en.get_text(strip=True) if en else None) or None
            # Also clean the english title if it contains event text
            if title_en: title_en = title_en.split('★')[0].strip()

            for sch in panel.select("div.movie-schedule"):
                raw=sch.get("data-start","")
                if not raw.isdigit(): continue
                show=f"{raw[:2]}:{raw[2:]}"
                scr=sch.get("data-screen","") or sch.get("data-room","")
                scr_num=re.match(r"(\d+)",scr)
                if scr_num and scr_num.group(1).endswith("0"): scr_num=str(int(scr_num.group(1))//10)
                else: scr_num=scr or "?"
                screen=f"スクリーン{scr_num}"
                key=(date_iso,title,show)
                if key in seen: continue
                seen.add(key)
                out.append({
                    "cinema_name":CINEMA_NAME,"movie_title":title,"movie_title_en":title_en,
                    "date_text":date_iso,"showtime":show,"screen_name":screen,
                    "director":None,"year":None,"country":None,"runtime_min":None,
                    "synopsis":None,"detail_page_url":None,"purchase_url":None,
                })
                titles.add(title)
    return out,titles

# ─────────────────── step-2 map
def _map_titles(html:str)->Dict[str,str]:
    soup=BeautifulSoup(html,"html.parser")
    m={}
    for a in soup.select("article.movies a"):
        t=a.select_one("h4.title b")
        if not t: continue
        url=a["href"]; url=url if url.startswith("http") else f"https://qualite.musashino-k.jp{url}"
        m[_norm_title(t.get_text(strip=True))]=url
    return m

# ─────────────────── step-3 details
def _extract_synopsis(blocks)->Optional[str]:
    best=None; best_len=0
    for b in blocks:
        if b.find("dl") or b.find("h1"): continue
        txt=" ".join(p.get_text(" ",strip=True) for p in b.select("p")).strip()
        if len(txt)>=60 and len(txt)>best_len:
            best, best_len = txt, len(txt)
    return best or None

def _scrape_detail(session,url:str)->dict:
    soup=BeautifulSoup(_get(session,url),"html.parser")
    meta={"director":None,"year":None,"country":None,"runtime_min":None,"synopsis":None}
    # synopsis (longest meaningful module-text)
    meta["synopsis"]=_extract_synopsis(soup.select("div.module.module-text"))
    # dl rows
    for dl in soup.select("div.module.module-text dl"):
        dt=dl.dt.get_text(strip=True); dd=dl.dd.get_text(" ",strip=True)
        if "監督" in dt: meta["director"]=_clean_name(dd)
        elif "制作年" in dt or "製作年" in dt:
            parts=re.split(r"[／/]",_fw2ascii(dd))
            meta["year"]=re.sub(r"\D","",parts[0]) or None
            if len(parts)>1: meta["country"]=parts[1].strip()
        elif "上映時間" in dt:
            if rt:=_parse_rt(dd): meta["runtime_min"]=rt
    # runtime fallback
    if not meta["runtime_min"]:
        if (m:=re.search(r"上映時間[:：]\s*([0-9０-９]{1,3}[^<]{0,5})",str(soup))):
            meta["runtime_min"]=_parse_rt(m.group(1))
    # director fallback
    if not meta["director"]:
        text=soup.get_text(" ",strip=True)
        # CHANGE #2: Improved regex to capture names with spaces and middle dots
        for pat in (r"監督[:：]\s*([^、。\n<()（）]{2,30})",
                    r"([^、。\n<()（）]{2,30}?)\s*を[^、。.]{0,6}?監督に",
                    r"([^、。\n<()（）]{2,30}?)\s*監督が"):
            if (m:=re.search(pat,text)):
                cand=_clean_name(m.group(1))
                if 2<=len(cand)<=20 and "映画" not in cand:
                    meta["director"]=cand; break
    return meta

# ─────────────────── wrapper
def scrape_cinema_qualite(max_days:int=7)->List[dict]:
    today=_dt.date.today()
    with requests.Session() as s:
        sched,titles=_parse_schedule(_get(s,SCHEDULE_URL),today,max_days)
        mapping=_map_titles(_get(s,LISTING_URL))
        cache={}
        for norm in {_norm_title(t) for t in titles if _norm_title(t) in mapping}:
            cache[norm]=_scrape_detail(s,mapping[norm])
        for row in sched:
            norm=_norm_title(row["movie_title"])
            if norm in cache:
                row.update(cache[norm]); row["detail_page_url"]=mapping[norm]
    return sched

# ─────────────────── save helper
def _save(data:List[dict]):
    fp=Path(__file__).with_name(f"cinema_qualite_showings_v2.json")
    fp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\n✓ Saved {len(data)} rows → {fp.name}\n")

# ─────────────────── CLI
if __name__=="__main__":
    print("Running Cinema Qualité scraper (v2) …\n")
    try:
        rows=scrape_cinema_qualite()
    except Exception as e:
        print("ERROR:",e); raise
    print(f"Collected {len(rows)} rows; showing sample of previously failed items:\n")

    # Print specific examples to verify fixes
    for r in rows:
        if r['movie_title'] == '親友かよ' and r['director'] is not None:
            print(r)
            break
    for r in rows:
        if r['movie_title'] == 'ハイテンション　４K' and r['director'] is not None:
            print(r)
            break
    for r in rows:
        if "★" in r['movie_title']: # Should not happen anymore, but good for testing
             print("ERROR: Title not cleaned:", r)
    
    # Find a previously-special-event-title to check if details are now populated
    found_event_fix = False
    for r in rows:
        if r['date_text'] == '2025-06-27' and r['movie_title'] == 'フォーチュンクッキー' and r['showtime'] == '19:45':
            print("\nPreviously a special event, now showing details:")
            print(r)
            found_event_fix = True
            break
    if not found_event_fix: print("\nCould not find test case for special event fix.")

    _save(rows)