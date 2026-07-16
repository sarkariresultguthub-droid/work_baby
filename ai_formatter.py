# ============================================================
#  ai_formatter.py  —  Scraped JSON -> CareerFlora draft post
#  Pipeline: raw scraped JSON -> [Groq AI (SOP format)] OR
#            [no-AI template fallback] -> POST to CareerFlora
#            save_scraped_post.php (status=draft)
#
#  Groq keys GitHub Actions secrets se aati hain: GROQ_KEY_1,
#  GROQ_KEY_2, GROQ_KEY_3 ... (jitni bhi ho). Ek key fail/rate-limit
#  ho to agli try hoti hai. Sab fail ho jayein to bina AI ke bhi
#  post ban jaata hai (template_format) — pipeline kabhi rukta nahi.
# ============================================================

import json
import os
import re
import logging

import requests

from config import DATA_DIR, CATEGORY_MAP, DEFAULT_CATEGORY_ID

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def _load_groq_keys() -> list[str]:
    """GROQ_KEY_1, GROQ_KEY_2, ... env vars se load karo."""
    keys = []
    i = 1
    while True:
        k = os.environ.get(f"GROQ_KEY_{i}")
        if not k:
            break
        keys.append(k)
        i += 1
    single = os.environ.get("GROQ_API_KEY")
    if single and single not in keys:
        keys.append(single)
    return keys


GROQ_KEYS = _load_groq_keys()

CAREERFLORA_API_URL = os.environ.get(
    "CAREERFLORA_API_URL",
    "https://careerflora.com/api/save_scraped_post.php",
)
CAREERFLORA_API_KEY = os.environ.get("CAREERFLORA_API_KEY", "")

FORMATTED_DIR = os.path.join(DATA_DIR, "careerflora_ready")
os.makedirs(FORMATTED_DIR, exist_ok=True)

# ------------------------------------------------------------
#  CareerFlora Universal Publishing Template (Actual) — prompt
#  (Same structure/order Shiv uses for manual posts in admin panel)
# ------------------------------------------------------------
SOP_PROMPT_TEMPLATE = """
You are a senior content writer for CareerFlora.com, following CareerFlora's
Universal Publishing Template exactly (the same template used for manual
posts). Convert the RAW SCRAPED DATA below into a publication-ready
CareerFlora article in strict JSON.

WRITING RULES (follow exactly):
- British English, active voice, simple vocabulary, no grammar mistakes.
- Never hallucinate. Only use facts present in RAW SCRAPED DATA. If a field
  is not present, write "As per official notification" instead of
  inventing it.
- 90-95% of information must be in 2-column HTML tables
  (<table><tr><td>...</td><td>...</td></tr></table>). Every table has only
  2 columns.
- Every heading starts with <h2> (no <h1> inside content - the H1/post
  title is handled separately by CareerFlora).
- Paragraphs: maximum 2 short paragraphs per section.
- Bold important words using <strong>: opportunity name, organization,
  deadline, amounts, country.
- Italic subtitle right after the value-prop line.
- No emojis, no clickbait, no "Are you looking for...", no long walls of text.
- Official links only.
- Include ALL of these sections, IN THIS EXACT ORDER, using <h2> headings
  (skip a section only if RAW SCRAPED DATA has genuinely nothing relevant):
  1. Quick Highlights (table: Programme Name, Organization, Opportunity Type,
     Funding Type, Eligible Applicants, Country, Duration, Deadline, Status)
  2. Opportunity Overview (table: Host Organization, Programme, Programme
     Type, Funding Category, Eligible Applicants, Location, Application Mode)
  3. About Organization (max 2 short paragraphs - only relevant facts)
  4. About the Programme (max 2 short paragraphs - objective, why launched,
     who benefits)
  5. Benefits (table: Tuition, Stipend, Accommodation, Airfare, Mentorship,
     Networking, Certification, Other Benefits - adjust fields to category)
  6. Programme Objectives / Key Features (table: Objective | Status/Details)
  7. Eligibility Criteria (table: Nationality, Degree, Experience, Age,
     Language, Other Requirements)
  8. Eligible Fields / Eligible Applicants (table, if relevant)
  9. Required Documents (table: Document | Required)
  10. Programme Timeline (table: Event | Date)
  11. How to Apply (table: Step | Action - normally 5 steps)
  12. Important Links (table: Description | Official Link)
  13. FAQs (table: Question | Answer - usually 5 FAQs, use raw data FAQs if
      present, else write relevant ones strictly from the facts given)
  14. CareerFlora Expert Insight (exactly 2 paragraphs - real value,
      competition level, best strategy, recommendation - never generic)
  15. Best Opportunity For (table: Category | Suitable)
  16. Competition Level (table: Category | Level)
  17. CareerFlora Recommendation (table: Recommendation Area | Details -
      Overall Rating, Funding Opportunity, Learning Value, Career Growth,
      Networking, Apply Early)

RAW SCRAPED DATA:
{raw_data}

CATEGORY LABEL (source site's own category): {category_label}

Return ONLY this strict JSON object, no markdown fences, no explanation:
{{
  "title": "H1 title, formula: Opportunity Name + Funding/Type + Country/State + Year + soft CTA",
  "slug": "lowercase-hyphen-slug-under-60-chars",
  "excerpt": "2-3 line summary for listing pages",
  "value_prop": "One-line italic value-proposition subtitle shown right under the H1",
  "secondary_subtitle": "Short italic supporting statement shown under value_prop",
  "content": "Full HTML: starts with the italic value_prop + secondary_subtitle lines, then ALL 17 <h2> sections above in exact order, tables only where specified",
  "meta_title": "under 70 chars",
  "meta_description": "150-160 chars",
  "focus_keyword": "primary keyword",
  "seo_keywords": "comma-separated secondary/LSI keywords, 10-20 tags",
  "schema_type": "JobPosting | Article | Scholarship | Event (pick the best fit)",
  "deadline": "YYYY-MM-DD or null if not stated",
  "image_alt": "descriptive alt text including focus keyword",
  "tg_caption": "Telegram description (always first, before SEO): opportunity name, 7-10 quick highlight bullet points starting with a check character, 2-3 line summary, bold deadline, ends with 'Read Full Details Below'",
  "wa_caption": "short 2-3 line WhatsApp message with opportunity name and deadline",
  "ig_caption": "short Instagram caption with 3-5 relevant hashtags"
}}
"""


def _resolve_category_id(category_label: str) -> int:
    return CATEGORY_MAP.get(category_label, DEFAULT_CATEGORY_ID)


def _make_slug(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:80]


# ------------------------------------------------------------
#  STEP 1 — Groq AI formatting (key rotation ke saath)
# ------------------------------------------------------------
def _call_groq(prompt: str) -> str | None:
    """GROQ_KEYS mein se ek-ek key try karo. Jo bhi pehli kaam kare,
    uska response return karo. Sab fail -> None (caller fallback karega)."""
    if not GROQ_KEYS:
        log.warning("Koi GROQ_KEY_* env var nahi mila — AI formatting skip, template fallback use hoga.")
        return None

    for idx, key in enumerate(GROQ_KEYS, 1):
        try:
            resp = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 4000,
                },
                timeout=45,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            elif resp.status_code in (401, 429):
                log.warning(f"Groq key #{idx} failed [{resp.status_code}], next key try karo...")
                continue
            else:
                log.warning(f"Groq key #{idx} unexpected [{resp.status_code}]: {resp.text[:200]}")
                continue
        except Exception as e:
            log.warning(f"Groq key #{idx} error: {e}")
            continue

    log.error("Saari Groq keys fail ho gayin — template fallback use ho raha hai.")
    return None


def _groq_format(item: dict, category_label: str) -> dict | None:
    prompt = SOP_PROMPT_TEMPLATE.format(
        raw_data=json.dumps(item, ensure_ascii=False, indent=2),
        category_label=category_label,
    )
    raw_response = _call_groq(prompt)
    if not raw_response:
        return None

    if raw_response.startswith("```"):
        raw_response = raw_response.split("```")[1]
        if raw_response.startswith("json"):
            raw_response = raw_response[4:]

    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as e:
        log.error(f"Groq JSON parse failed: {e}")
        return None


# ------------------------------------------------------------
#  STEP 2 — No-AI template fallback
#  (Raw scraped 'tables' data ko seedha 2-column HTML tables mein
#   arrange karta hai — koi AI writing nahi, bas structuring.)
# ------------------------------------------------------------
_DATE_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")


def _extract_deadline(item: dict) -> str | None:
    """'Last Date for Apply : 29/07/2026' jaisi lines dhoondh ke
    YYYY-MM-DD format mein deadline nikalta hai."""
    text_blobs = [item.get("full_text", ""), item.get("raw_text", "")]
    for table in item.get("tables", []):
        for row in table:
            text_blobs.append(" | ".join(str(c) for c in row))

    for blob in text_blobs:
        if not blob:
            continue
        idx = blob.lower().find("last date")
        if idx != -1:
            m = _DATE_RE.search(blob[idx: idx + 60])
            if m:
                d, mo, y = m.groups()
                return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def _tables_to_html(item: dict) -> str:
    """Scraper ke 'tables' array (list of rows, har row list of cells)
    ko seedha 2-column HTML tables mein convert karta hai."""
    html_parts = []
    for table in item.get("tables", []):
        rows_html = []
        for row in table:
            cells = [str(c) for c in row]
            if len(cells) == 1:
                rows_html.append(f"<tr><td colspan='2'>{cells[0]}</td></tr>")
            else:
                label, value = cells[0], " — ".join(cells[1:])
                rows_html.append(f"<tr><td><strong>{label}</strong></td><td>{value}</td></tr>")
        if rows_html:
            html_parts.append("<table>" + "".join(rows_html) + "</table>")
    return "".join(html_parts)


def template_format(item: dict, category_label: str) -> dict:
    """Bina AI ke — raw data ko seedha CareerFlora-ready structure mein
    daal deta hai. Basic hota hai lekin pipeline kabhi rukta nahi."""
    title = item.get("full_title") or item.get("title") or "Untitled Post"
    link = item.get("link") or item.get("source_url") or ""
    site_name = item.get("site_name") or item.get("source_site") or ""
    deadline = _extract_deadline(item)

    quick_highlights = (
        "<h2>Quick Highlights</h2><table>"
        f"<tr><td><strong>Programme Name</strong></td><td>{title}</td></tr>"
        f"<tr><td><strong>Organization</strong></td><td>{site_name}</td></tr>"
        f"<tr><td><strong>Opportunity Type</strong></td><td>{category_label}</td></tr>"
        f"<tr><td><strong>Deadline</strong></td><td>{deadline or 'As per official notification'}</td></tr>"
        f"<tr><td><strong>Status</strong></td><td>Active</td></tr>"
        "</table>"
    )

    details_html = (
        "<h2>Opportunity Details</h2>" + _tables_to_html(item)
        if item.get("tables")
        else "<h2>Opportunity Details</h2><p>As per official notification.</p>"
    )

    links_html = (
        "<h2>Important Links</h2><table>"
        f"<tr><td>Official Notification</td><td><a href='{link}' target='_blank' rel='nofollow noopener'>Click Here</a></td></tr>"
        "</table>"
    )

    expert_insight = (
        "<h2>CareerFlora Expert Insight</h2>"
        f"<p>This <strong>{title}</strong> opportunity is currently active under the "
        f"<strong>{category_label}</strong> category. Candidates are advised to read the "
        "official notification carefully before applying.</p>"
        "<p>Apply well before the deadline to avoid last-minute technical issues on the "
        "official portal.</p>"
    )

    content = quick_highlights + details_html + links_html + expert_insight

    excerpt = f"{title} — full details, eligibility and how to apply on CareerFlora."
    meta_title = title[:65]
    meta_description = (excerpt[:157] + "...") if len(excerpt) > 160 else excerpt
    keyword_words = title.split(" ")

    return {
        "title": title,
        "slug": _make_slug(title),
        "excerpt": excerpt,
        "content": content,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "focus_keyword": " ".join(keyword_words[:4]),
        "seo_keywords": ", ".join(keyword_words[:10]),
        "schema_type": "JobPosting" if "job" in category_label.lower() else "Article",
        "deadline": deadline,
        "image_alt": title,
        "tg_caption": f"{title}\n\nDeadline: {deadline or 'Check official notification'}\n\nRead Full Details Below",
        "wa_caption": f"{title} — Deadline: {deadline or 'check notification'}",
        "ig_caption": f"{title} #Jobs #CareerFlora #SarkariResult",
    }


# ------------------------------------------------------------
#  Combined entry point: Groq try -> fallback to template
# ------------------------------------------------------------
def format_item_for_careerflora(item: dict, category_label: str) -> dict | None:
    formatted = _groq_format(item, category_label)
    used = "groq"
    if not formatted:
        formatted = template_format(item, category_label)
        used = "template"

    formatted["category_id"] = _resolve_category_id(category_label)
    formatted["source_url"] = item.get("link") or item.get("source_url")
    formatted["source_site"] = item.get("site_name") or item.get("source_site")
    log.info(f"Formatted via: {used} — {formatted.get('title')}")
    return formatted


def publish_draft(formatted: dict) -> bool:
    """CareerFlora ke save_scraped_post.php par POST karo (status=draft)."""
    if not CAREERFLORA_API_KEY:
        log.error("CAREERFLORA_API_KEY set nahi hai (env var) - publish skip.")
        return False
    try:
        resp = requests.post(
            CAREERFLORA_API_URL,
            json=formatted,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": CAREERFLORA_API_KEY,
            },
            timeout=30,
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 200 and data.get("success"):
            log.info(f"✅ Draft saved: {formatted.get('title')} (post_id={data.get('post_id')})")
            return True
        log.error(f"❌ Publish failed [{resp.status_code}]: {resp.text[:300]}")
        return False
    except Exception as e:
        log.error(f"Publish error: {e}")
        return False


def _load_items_from_path(filepath: str) -> list[dict]:
    """Naya structure (data/<date>/<category>/<post-title>.json — har
    post alag file) aur combined-file structure ('items' array) — dono
    support karta hai."""
    if os.path.isdir(filepath):
        items = []
        for fname in sorted(os.listdir(filepath)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(filepath, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    item = json.load(f)
                item["_source_filename"] = fname
                items.append(item)
            except Exception as e:
                log.error(f"Skip {fpath}: {e}")
        return items

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "items" in data:
        return data.get("items", [])

    return [data]


def format_and_publish_folder(folder_path: str, category_label: str) -> dict:
    items = _load_items_from_path(folder_path)
    summary = {"total": len(items), "formatted": 0, "published": 0, "failed": []}

    for item in items:
        title = item.get("full_title") or item.get("title", "untitled")
        formatted = format_item_for_careerflora(item, category_label)
        if not formatted:
            summary["failed"].append(title)
            continue
        summary["formatted"] += 1

        safe_name = re.sub(r"[^\w\- ]", "", title)[:100] + ".json"
        with open(os.path.join(FORMATTED_DIR, safe_name), "w", encoding="utf-8") as f:
            json.dump(formatted, f, ensure_ascii=False, indent=2)

        if publish_draft(formatted):
            summary["published"] += 1
        else:
            summary["failed"].append(title)

    log.info(
        f"📊 Format+Publish summary: {summary['formatted']}/{summary['total']} formatted, "
        f"{summary['published']}/{summary['total']} published as draft."
    )
    return summary


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 3:
        print("Usage: python ai_formatter.py <scraped_folder_or_file> <category_label>")
        print('  e.g. python ai_formatter.py "data/2026-07-16/Latest Job" "Latest Job"')
        sys.exit(1)

    result = format_and_publish_folder(sys.argv[1], sys.argv[2])
    print(f"\n📊 {result}")
