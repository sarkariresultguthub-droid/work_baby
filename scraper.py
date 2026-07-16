# ============================================================
#  scraper.py  —  Change Detection + Universal Page Scraper
#  (WordPress + normal sites dono pe kaam karta hai)
# ============================================================

import hashlib
import io
import json
import os
import sys
import time
import logging
from datetime import datetime

import random
import re
import requests
from bs4 import BeautifulSoup

from config import SITES, DATA_DIR, SNAPSHOTS_DIR, LOGS_DIR
from universal_extractor import extract_listing, fetch_full_post, proxied_get, SCRAPERAPI_KEY

# ---------- Logging setup ----------
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Windows ka default terminal encoding (cp1252) emojis handle nahi kar pata,
# isliye stdout/stderr ko UTF-8 pe force kar rahe hain (Windows-only fix).
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOGS_DIR}/scraper.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------- Rotating User-Agents (anti-403) ----------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

def _get_headers(url: str) -> dict:
    """Har request ke liye fresh realistic headers banao."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8,hi;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-CH-UA": '"Chromium";v="125", "Google Chrome";v="125", "Not.A/Brand";v="24"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Referer": origin + "/",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }


# ============================================================
#  Fetch page content (with retry + anti-403 tricks)
# ============================================================
def fetch_page(url: str, retries: int = 4) -> requests.Response | None:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    home_url = f"{parsed.scheme}://{parsed.netloc}/"

    for attempt in range(1, retries + 1):
        session = requests.Session()
        try:
            # Pehle site ka homepage visit karo — cookies set ho jaaye
            # aur site ko lagey real browser hai. (Proxy mode mein ye
            # skip ho jaata hai — ScraperAPI khud isko handle karta hai.)
            if not SCRAPERAPI_KEY:
                try:
                    session.get(home_url, headers=_get_headers(home_url), timeout=10, allow_redirects=True)
                    time.sleep(random.uniform(1.5, 3.0))
                except Exception:
                    pass  # Homepage fail ho toh bhi actual URL try karo

            headers = _get_headers(url)
            # Same-site request lagey isliye Referer = homepage
            headers["Referer"] = home_url

            resp = proxied_get(url, headers=headers, timeout=25, session=session)
            if resp.status_code == 200:
                return resp
            log.warning(f"Attempt {attempt}: {url} returned {resp.status_code}")
        except requests.RequestException as e:
            log.warning(f"Attempt {attempt}: {url} error — {e}")

        # Har retry ke beech random delay — bot pattern se bachne ke liye
        wait = random.uniform(3.0, 7.0) * attempt
        log.info(f"Waiting {wait:.1f}s before retry...")
        time.sleep(wait)

    log.error(f"Failed to fetch after {retries} attempts: {url}")
    return None


# ============================================================
#  Change detection (hash compare)
# ============================================================
def get_page_hash(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def load_previous_hash(site_name: str) -> str | None:
    path = os.path.join(SNAPSHOTS_DIR, f"{site_name}.hash")
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return None


def save_current_hash(site_name: str, hash_val: str):
    path = os.path.join(SNAPSHOTS_DIR, f"{site_name}.hash")
    with open(path, "w") as f:
        f.write(hash_val)


def has_page_changed(site_name: str, current_hash: str) -> bool:
    prev = load_previous_hash(site_name)
    if prev is None:
        log.info(f"[{site_name}] First run — baseline save kar raha hun.")
        return True
    return prev != current_hash


# ============================================================
#  Page-level metadata
# ============================================================
def scrape_page_metadata(soup: BeautifulSoup, url: str) -> dict:
    meta = {
        "page_url": url,
        "page_title": soup.title.get_text(strip=True) if soup.title else None,
        "meta_description": None,
        "total_links": len(soup.find_all("a")),
        "total_images": len(soup.find_all("img")),
        "h1_tags": [h.get_text(strip=True) for h in soup.find_all("h1")],
    }
    for tag in soup.find_all("meta"):
        if tag.get("name", "").lower() == "description":
            meta["meta_description"] = tag.get("content", "")
    return meta


# ============================================================
#  Filename-safe text banao (post title se file/folder naam)
# ============================================================
def sanitize_filename(name: str, max_len: int = 120) -> str:
    if not name:
        return "untitled"
    name = name.strip()
    # Windows/Linux dono mein invalid chars hata do
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name[:max_len].strip(" .")
    return name or "untitled"


# ============================================================
#  Save scraped data — EK FILE PER POST, category = folder naam
#  data/<date>/<category>/<post-title>.json
# ============================================================
def save_items_by_category(site_name: str, category_label: str, items: list[dict]) -> tuple[str, list[str]]:
    # Date-wise folder: data/<YYYY-MM-DD>/<category>/<post-title>.json
    date_folder = datetime.utcnow().strftime("%Y-%m-%d")
    folder = os.path.join(DATA_DIR, date_folder, sanitize_filename(category_label))
    os.makedirs(folder, exist_ok=True)

    saved_files = []
    for item in items:
        title = item.get("full_title") or item.get("title") or "untitled"
        fname = sanitize_filename(title) + ".json"
        fpath = os.path.join(folder, fname)

        # Agar same title ki file pehle se hai (duplicate post), naam
        # ke aage source_url ka chhota hash laga dete hain taaki overwrite
        # na ho aur dono saved rahein.
        if os.path.exists(fpath):
            existing_link = None
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    existing_link = json.load(f).get("link")
            except Exception:
                pass
            if existing_link and existing_link != item.get("link"):
                short_hash = hashlib.md5((item.get("link") or title).encode()).hexdigest()[:6]
                fname = f"{sanitize_filename(title)}-{short_hash}.json"
                fpath = os.path.join(folder, fname)

        item_to_save = dict(item)
        item_to_save["site_name"] = site_name
        item_to_save["category_label"] = category_label
        item_to_save["scraped_date"] = date_folder

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(item_to_save, f, ensure_ascii=False, indent=2)
        saved_files.append(fpath)

    log.info(f"[{site_name}] {len(saved_files)} posts saved -> {folder}/")
    return folder, saved_files


# ============================================================
#  Save scraped data (OLD — single combined file, auto-mode ke liye)
# ============================================================
def save_data(site_name: str, metadata: dict, items: list[dict]) -> str:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    filename = f"{site_name}_{timestamp}.json"
    filepath = os.path.join(DATA_DIR, filename)

    output = {
        "scrape_session": {
            "site": site_name,
            "scraped_at": datetime.utcnow().isoformat() + "Z",
            "total_items": len(items),
        },
        "page_metadata": metadata,
        "items": items,
        "_ai_instructions": {
            "task": "Convert each item in 'items' to CareerFlora post format",
            "category_hint": items[0]["category"] if items else "general",
        },
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"[{site_name}] Data saved → {filepath}")
    return filepath


# ============================================================
#  NEW-POST TRACKING (per category) — taaki sirf naye posts hi
#  detect/scrape ho, purane baar-baar scrape na ho
# ============================================================
def _seen_links_path(site_name: str, category_label: str) -> str:
    safe_cat = sanitize_filename(category_label)
    return os.path.join(SNAPSHOTS_DIR, f"{site_name}__{safe_cat}__seen_links.json")


def load_seen_links(site_name: str, category_label: str) -> set:
    path = _seen_links_path(site_name, category_label)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen_links(site_name: str, category_label: str, links: set):
    path = _seen_links_path(site_name, category_label)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(links), f, ensure_ascii=False, indent=2)


# ============================================================
#  AUTO MODE v2: ek category check karo — sirf NAYE posts
#  (jo pehle kabhi nahi dekhe) detect + full-scrape + save karo
# ============================================================
def check_and_scrape_category(
    site_config: dict,
    category_label: str,
    category_url: str,
) -> dict | None:
    """
    Ek specific category-page (jaise 'Latest Job') check karta hai.
    Listing mein jitne bhi posts hain unke links nikalta hai, fir
    pehle se "seen" links ke set se compare karta hai — jo links
    NAYE hain (pehle kabhi save nahi hue) sirf unhi ko fetch_full_post()
    se poora scrape karke save karta hai. Purane posts dobara fetch
    nahi hote — fast bhi hai aur safe bhi.

    Returns None agar koi naya post nahi mila, warna result dict.
    """
    name = site_config["name"]
    log.info(f"[{name}] [{category_label}] Checking {category_url} ...")

    resp = fetch_page(category_url)
    if not resp:
        log.error(f"[{name}] [{category_label}] Fetch failed.")
        return None

    soup = BeautifulSoup(resp.content, "lxml")
    # Pehle FAST pass — sirf listing nikalo, full detail abhi nahi
    # (fetch_full=False) taaki check sasta/fast rahe.
    items = extract_listing(
        soup, category_url, name, site_config["category"], fetch_full=False
    )

    if not items:
        log.warning(f"[{name}] [{category_label}] 0 items found on listing page.")
        return None

    seen_links = load_seen_links(name, category_label)
    current_links = {it.get("link") for it in items if it.get("link")}

    new_items = [it for it in items if it.get("link") and it["link"] not in seen_links]

    # Pehli baar (koi seen_links file nahi thi) — sab links baseline
    # ke roop mein save kar do, lekin posts ko "naya" maan ke notify/scrape
    # mat karo (warna pehli baar 50 posts ek saath "new" keh ke aa jaayenge).
    is_first_run = len(seen_links) == 0
    if is_first_run:
        save_seen_links(name, category_label, current_links)
        log.info(
            f"[{name}] [{category_label}] First run — {len(current_links)} posts "
            f"baseline mein save kiye (notify nahi honge)."
        )
        return None

    if not new_items:
        log.info(f"[{name}] [{category_label}] No new post. Skipping.")
        return None

    log.info(f"[{name}] [{category_label}] ✅ {len(new_items)} NAYA post mila! Full data fetch kar raha hun...")

    # Ab sirf NAYE items ke liye full detail page fetch karo
    for item in new_items:
        full_data = fetch_full_post(item["link"])
        item["full_title"] = full_data["full_title"]
        item["full_text"] = full_data["full_text"]
        item["tables"] = full_data["tables"]
        item["important_dates"] = full_data["important_dates"]
        item["important_links"] = full_data["important_links"]
        item["fetch_error"] = full_data["fetch_error"]
        time.sleep(1)

    folder, saved_files = save_items_by_category(name, category_label, new_items)

    # Seen-links set update karo (purane + naye sab current links)
    save_seen_links(name, category_label, seen_links | current_links)

    return {
        "site": name,
        "category": category_label,
        "url": category_url,
        "items_count": len(new_items),
        "folder": folder,
        "files": saved_files,
        "items": [
            {
                "title": it.get("full_title") or it.get("title") or "Untitled",
                "link": it.get("link"),
            }
            for it in new_items
        ],
        "changed_at": datetime.utcnow().isoformat() + "Z",
    }


# ============================================================
#  AUTO MODE: change-detect + scrape (scheduler ke liye)
# ============================================================
def check_and_scrape(site_config: dict) -> dict | None:
    """Returns result dict if change detected, None otherwise."""
    name = site_config["name"]
    url = site_config["url"].strip()

    log.info(f"[{name}] Checking {url} ...")
    resp = fetch_page(url)
    if not resp:
        return None

    current_hash = get_page_hash(resp.content)
    if not has_page_changed(name, current_hash):
        log.info(f"[{name}] No change detected. Skipping.")
        return None

    log.info(f"[{name}] ✅ CHANGE DETECTED! Scraping full page...")
    save_current_hash(name, current_hash)

    soup = BeautifulSoup(resp.content, "lxml")
    metadata = scrape_page_metadata(soup, url)
    items = extract_listing(soup, url, name, site_config["category"])

    if not items:
        log.warning(f"[{name}] Change detected but 0 items scraped.")
        return None

    filepath = save_data(name, metadata, items)
    return {
        "site": name,
        "url": url,
        "items_count": len(items),
        "file": filepath,
        "changed_at": datetime.utcnow().isoformat() + "Z",
    }


# ============================================================
#  MANUAL MODE: site choose karo, N latest posts scrape karo
#  (hash check skip karta hai — chahe change ho ya na ho, scrape karega)
# ============================================================
def manual_scrape(
    site_config: dict,
    num_posts: int,
    category_label: str | None = None,
    category_url: str | None = None,
) -> dict | None:
    """
    Site config aur "kitne latest posts chahiye" lo,
    utne hi items scrape karke save karo. Change detection
    yahan skip hoti hai (user manually trigger kar raha hai).

    category_label / category_url: agar diya gaya (jaise "Latest Job" ->
    https://www.sarkariresult.com/latestjob/), toh site ke us specific
    listing page ko scrape karte hain, aur posts us category ke naam
    se bani folder (data/<category_label>/) mein, har post ALAG file
    mein (post title se naam) save hote hain.

    Agar nahi diya (custom URL / categories na hone wali site), toh
    purana behavior — site ke main url ko scrape karke site-name wali
    folder mein save karte hain.
    """
    name = site_config["name"]
    url = (category_url or site_config["url"]).strip()
    folder_label = category_label or name

    log.info(f"[{name}] Manual scrape — {url} (category: {folder_label}, latest {num_posts} posts)")
    resp = fetch_page(url)
    if not resp:
        log.error(f"[{name}] Fetch failed.")
        return None

    soup = BeautifulSoup(resp.content, "lxml")
    metadata = scrape_page_metadata(soup, url)
    items = extract_listing(
        soup, url, name, site_config["category"], limit=num_posts, fetch_full=True
    )

    if not items:
        log.warning(f"[{name}] 0 items found.")
        return None

    folder, saved_files = save_items_by_category(name, folder_label, items)
    log.info(f"[{name}] ✅ {len(items)} items scraped (requested: {num_posts}) → {folder}/")

    return {
        "site": name,
        "category": folder_label,
        "url": url,
        "items_count": len(items),
        "folder": folder,
        "files": saved_files,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
    }