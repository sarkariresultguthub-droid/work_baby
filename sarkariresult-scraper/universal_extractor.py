# ============================================================
#  universal_extractor.py  —  Auto-detect listing items on
#  ANY site (WordPress ya normal HTML, koi fixed selector nahi)
# ============================================================
#
# Idea: Fixed CSS selectors guess karne ke bajaye, page khud
# "repeated pattern" dhoondta hai — jaise ek WordPress listing
# mein 20 <article> ya <li> tags same class ke saath repeat
# hote hain. Hum sabse zyada repeat hone wala group dhoondte
# hain aur usi ko "items" maan lete hain.
# ============================================================

import re
import time
import logging
from collections import defaultdict
from urllib.parse import urljoin, urlparse
from datetime import datetime

import requests
from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)

# Post detail page fetch ke liye headers (scraper.py wale jaisa hi)
DETAIL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# In tags ko content ke liye consider nahi karte (noise — menu, footer, ads, etc.)
NOISE_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "iframe", "form"]

# Common WordPress / CMS patterns — pehle inko try karo (fast path)
KNOWN_PATTERNS = [
    "article",
    ".post", ".entry", ".post-item", ".entry-item",
    ".card", ".job-item", ".opportunity-item",
    "li.post", "div.post",
    ".latest-jobs li", ".latest-job-list li",
    "table tr",
]

DATE_REGEX = re.compile(
    r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})|"      # 12/06/2026, 12-06-26
    r"(\d{4}-\d{2}-\d{2})|"                            # 2026-06-12
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)


# ============================================================
#  STEP 1: Known selectors try karo (fast path — WordPress etc)
# ============================================================
def try_known_patterns(soup: BeautifulSoup) -> list[Tag]:
    for pattern in KNOWN_PATTERNS:
        found = soup.select(pattern)
        # Kam se kam 3 honi chahiye taaki "real listing" lage,
        # warna single random match ho sakta hai
        if len(found) >= 3:
            return found
    return []


# ============================================================
#  STEP 2: Auto-detect — repeated sibling pattern dhoondo
# ============================================================
def auto_detect_items(soup: BeautifulSoup) -> list[Tag]:
    """
    Har <a> tag ke parent ka "signature" banao (tag + class).
    Jo signature sabse zyada baar repeat ho (aur uska text
    reasonably lamba ho), wahi "listing items" hain.
    """
    signature_groups: dict[str, list[Tag]] = defaultdict(list)

    # Saare candidate container tags check karo
    candidates = soup.find_all(["li", "div", "article", "tr", "section"])

    for tag in candidates:
        # Tag ke andar kam se kam ek link ya heading hona chahiye
        if not tag.find("a") and not tag.find(["h1", "h2", "h3", "h4"]):
            continue

        text_len = len(tag.get_text(strip=True))
        if text_len < 10 or text_len > 600:
            # Bahut chhota (noise) ya bahut bada (poora page) skip karo
            continue

        classes = tag.get("class") or []
        signature = f"{tag.name}.{'.'.join(classes)}" if classes else tag.name
        signature_groups[signature].append(tag)

    # Sabse bada group dhoondo jisme kam se kam 4 items ho
    best_group: list[Tag] = []
    for sig, group in signature_groups.items():
        if len(group) >= 4 and len(group) > len(best_group):
            # Nested duplicates avoid karo (parent-child dono na aa jaye)
            best_group = group

    return best_group


# ============================================================
#  STEP 3: Single item se data nikalo (generic, no selectors)
# ============================================================
def extract_item_data(tag: Tag, page_url: str, source_name: str, category: str) -> dict:
    base_url = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"

    # --- Title: pehli heading, warna sabse lamba link text ---
    title = None
    heading = tag.find(["h1", "h2", "h3", "h4", "h5"])
    if heading:
        title = heading.get_text(strip=True)
    if not title:
        links = tag.find_all("a")
        if links:
            title = max((a.get_text(strip=True) for a in links), key=len, default=None)
    if not title:
        title = tag.get_text(strip=True)[:120]

    # --- Link: pehla valid href (heading ke andar wala preferred) ---
    link = None
    a_in_heading = heading.find("a") if heading else None
    a_tag = a_in_heading or tag.find("a", href=True)
    if a_tag and a_tag.get("href"):
        href = a_tag["href"]
        link = href if href.startswith("http") else urljoin(base_url, href)

    # --- Date: text mein date pattern dhoondo ---
    full_text = tag.get_text(separator=" ", strip=True)
    date_match = DATE_REGEX.search(full_text)
    date = date_match.group(0) if date_match else None

    # --- Description: title hata ke bacha hua text ---
    description = full_text
    if title and description.startswith(title):
        description = description[len(title):].strip(" -|:")
    description = description[:400] if description else None

    # --- All links + images (extra context AI ke liye) ---
    all_links = []
    for a in tag.find_all("a", href=True)[:15]:
        href = a["href"]
        full = href if href.startswith("http") else urljoin(base_url, href)
        txt = a.get_text(strip=True)
        if txt:
            all_links.append({"text": txt, "url": full})

    all_images = []
    for img in tag.find_all("img")[:5]:
        src = img.get("src") or img.get("data-src")
        if src:
            full_src = src if src.startswith("http") else urljoin(base_url, src)
            all_images.append({"src": full_src, "alt": img.get("alt", "")})

    return {
        "source_site": source_name,
        "source_url": page_url,
        "category": category,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "title": title,
        "link": link,
        "date": date,
        "description": description,
        "raw_text": full_text[:1000],
        "all_links": all_links,
        "all_images": all_images,
    }


# ============================================================
#  STEP 3.5: Post ke link pe jaake poora detail page nikalo
#  (PDF links ke liye sirf note daal dete hain — PDF parse nahi karte)
# ============================================================
def fetch_full_post(link: str, timeout: int = 15) -> dict:
    """
    Diye gaye 'link' (post detail page) ko fetch karke uska poora
    content nikalta hai: heading, saare paragraphs/list-items, aur
    agar koi table hai (jaise result/dates table) toh wo bhi.
    """
    result = {
        "full_title": None,
        "full_text": None,
        "tables": [],
        "important_dates": None,
        "fetch_error": None,
    }

    if not link:
        result["fetch_error"] = "No link to fetch"
        return result

    if link.lower().endswith(".pdf"):
        result["fetch_error"] = "Link is a PDF — skipping HTML parse"
        return result

    try:
        resp = requests.get(link, headers=DETAIL_HEADERS, timeout=timeout)
        if resp.status_code != 200:
            result["fetch_error"] = f"HTTP {resp.status_code}"
            return result
    except requests.RequestException as e:
        result["fetch_error"] = str(e)
        return result

    soup = BeautifulSoup(resp.content, "lxml")

    # Noise hata do (script, style, nav, footer, etc.)
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    # --- Main content area dhoondo (agar specific container mile) ---
    main = (
        soup.select_one("article")
        or soup.select_one(".entry-content")
        or soup.select_one(".post-content")
        or soup.select_one("#content")
        or soup.select_one("main")
        or soup.body
        or soup
    )

    # --- Title ---
    h1 = soup.find("h1")
    result["full_title"] = h1.get_text(strip=True) if h1 else None

    # --- Saara readable text — POORA, koi length-limit nahi ---
    # Strategy: tables ke andar wala text yahin se collect nahi karte
    # (tables alag se neeche poori tarah collect honge — taaki duplicate
    # na ho aur table ka data dono jagah alag-alag tarike se mil jaye).
    # Isliye text collection ke liye hum table content ko temporarily
    # nikaal ke ek copy par kaam karte hain.
    text_source = BeautifulSoup(str(main), "lxml")
    for tbl in text_source.find_all("table"):
        tbl.decompose()

    text_parts = []
    seen_texts = set()  # consecutive-duplicate avoid karne ke liye (nested tags)
    for el in text_source.find_all(["p", "li", "h2", "h3", "h4", "h5", "h6", "div", "span", "blockquote"]):
        # Agar is element ke andar koi block-level child hai, to iska text
        # uske parent mein already aa jaayega — to skip karo taaki double na ho
        if el.find(["p", "li", "h2", "h3", "h4", "h5", "h6", "div", "blockquote"]):
            continue
        txt = el.get_text(separator=" ", strip=True)
        if txt and len(txt) > 1 and txt not in seen_texts:
            text_parts.append(txt)
            seen_texts.add(txt)
    # full_text — ab COMPLETE hai, koi [:6000] cut nahi
    result["full_text"] = "\n".join(text_parts)

    # --- Tables — SAARI tables (limit hata di, [:5] nahi)---
    for table in main.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(separator=" ", strip=True) for c in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(cells)
        if rows:
            result["tables"].append(rows)

    # --- "Important Dates" wala section specifically dhoondne ki koshish ---
    dates_heading = None
    for h in main.find_all(["h2", "h3", "h4", "strong", "b"]):
        if "important date" in h.get_text(strip=True).lower():
            dates_heading = h
            break
    if dates_heading:
        # Heading ke baad wali table ya list dhoondo
        sibling_table = dates_heading.find_next("table")
        if sibling_table:
            rows = []
            for tr in sibling_table.find_all("tr"):
                cells = [c.get_text(separator=" ", strip=True) for c in tr.find_all(["td", "th"])]
                if any(cells):
                    rows.append(cells)
            result["important_dates"] = rows

    # --- Important links: Apply Online, Notification PDF, Official Website,
    #     Download Admit Card / Result, etc. — in sab links ka text + URL ---
    important_keywords = [
        "apply online", "apply now", "notification", "advertisement",
        "official website", "official site", "download", "admit card",
        "result", "answer key", "syllabus", "merit list", "click here",
        "registration", "login", "print application",
    ]
    important_links = []
    seen_urls = set()
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        link_text = a.get_text(strip=True)
        full_url = urljoin(link, href)
        if full_url in seen_urls:
            continue
        haystack = (link_text + " " + href).lower()
        if any(kw in haystack for kw in important_keywords):
            important_links.append({
                "text": link_text or "(no text)",
                "url": full_url,
            })
            seen_urls.add(full_url)
    result["important_links"] = important_links

    return result


# ============================================================
#  MAIN ENTRY: Universal extraction — koi bhi site chalegi
# ============================================================
def extract_listing(
    soup: BeautifulSoup,
    page_url: str,
    source_name: str,
    category: str,
    limit: int | None = None,
    fetch_full: bool = False,
) -> list[dict]:
    """
    limit: agar diya gaya toh sirf utne hi latest items nikalo
           (manual scraping mode ke liye — "kitne latest posts chahiye")
    fetch_full: True hone par har item ke 'link' pe jaake uska poora
                detail-page content bhi nikalega (slower — ek extra
                HTTP request per item).
    """
    # Pehle known patterns try karo (fast, accurate WordPress ke liye)
    raw_items = try_known_patterns(soup)

    # Nahi mila toh auto-detect karo (kisi bhi normal site ke liye)
    if not raw_items:
        raw_items = auto_detect_items(soup)

    # Fallback: kuch bhi nahi mila toh page ke saare links se kaam chalao
    if not raw_items:
        raw_items = soup.find_all("a", href=True, limit=50)

    items = []
    for tag in raw_items:
        try:
            data = extract_item_data(tag, page_url, source_name, category)
            # Sirf valid items rakho (title ya link hona chahiye)
            if data["title"] or data["link"]:
                items.append(data)
        except Exception:
            continue  # ek item fail ho toh poora scrape mat roko

    # Duplicate links hata do (same item do baar na aaye)
    seen_links = set()
    unique_items = []
    for item in items:
        key = item["link"] or item["title"]
        if key not in seen_links:
            seen_links.add(key)
            unique_items.append(item)

    # Agar limit diya hai (manual mode), sirf utne hi latest do
    if limit:
        unique_items = unique_items[:limit]

    # fetch_full=True hone par har FINAL item (limit ke baad) ke link
    # pe jaake poora detail-page content bhi nikal ke item mein merge karo.
    # Limit ke baad isliye kar rahe hain — taaki sirf jitne items chahiye
    # utne hi extra requests lagein (saare 100 raw candidates pe nahi).
    if fetch_full:
        for item in unique_items:
            log.info(f"  -> Fetching full post: {item['title'][:60] if item['title'] else item['link']}")
            full_data = fetch_full_post(item["link"])
            item["full_title"] = full_data["full_title"]
            item["full_text"] = full_data["full_text"]
            item["tables"] = full_data["tables"]
            item["important_dates"] = full_data["important_dates"]
            item["fetch_error"] = full_data["fetch_error"]
            time.sleep(1)  # detail page server pe load kam rakhne ke liye

    return unique_items
