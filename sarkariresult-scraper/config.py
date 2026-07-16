# ============================================================
#  config.py  —  Sabhi settings ek jagah
# ============================================================
import os

# ---------- Telegram ----------
# Pehle environment variable check karta hai (GitHub Actions secrets ke
# liye) — agar nahi mila to neeche wali default value use hoti hai
# (local testing ke liye yahan apna token/chat-id daal sakte ho).
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# ---------- Scheduler ----------
CHECK_INTERVAL_MINUTES = 30   # har 30 min check (auto mode ke liye)

# ---------- Sites to watch ----------
# NOTE: Ab selectors ki zaroorat nahi — universal_extractor.py
# khud auto-detect kar leta hai (WordPress ya koi bhi normal site).
#
# Har site ke andar "categories" bhi diye hain — yeh site ke khud
# ke alag-alag listing pages hain (jaise SarkariResult pe "Latest Job",
# "Admit Card", "Results" sab alag URL hain). manual_scrape.py mein
# pehle site choose hoga, fir us site ke andar category choose hogi.
#
# Agar kisi site ke liye categories nahi pata / nahi diye, toh wahan
# sirf "Home" category hogi jo us site ke main listing page (url) ko
# scrape karegi — purana behavior intact rehta hai.
SITES = [
    {
        "name": "SarkariResult",
        "url": "https://www.sarkariresult.com/",
        "category": "government_jobs",
        "categories": {
            "Latest Job": "https://www.sarkariresult.com/latestjob/",
            "Admit Card": "https://www.sarkariresult.com/admitcard/",
            "Results": "https://www.sarkariresult.com/result/",
            "Answer Key": "https://www.sarkariresult.com/answerkey/",
            "Syllabus": "https://www.sarkariresult.com/syllabus/",
            "Admission": "https://www.sarkariresult.com/admission/",
            "Certificate": "https://www.sarkariresult.com/certificate/",
            "Outsourcing / Offline Jobs": "https://www.sarkariresult.com/outsourcing/",
            "Important": "https://www.sarkariresult.com/important/",
        },
    },
]

# ---------- CareerFlora category mapping ----------
# SarkariResult category_label -> CareerFlora ke `categories` table ka id.
# Apne phpMyAdmin mein categories table check karke ye IDs match karo.
CATEGORY_MAP = {
    "Latest Job": 1,                       # Jobs
    "Outsourcing / Offline Jobs": 1,        # Jobs
    "Admit Card": 21,                       # Admit Card
    "Results": 8,                           # Results
    "Answer Key": 8,                        # Results (koi alag category nahi)
    "Syllabus": 16,                         # Syllabus
    "Admission": 12,                        # Admissions
    "Certificate": 17,                      # Blog (fallback)
    "Important": 17,                        # Blog (fallback)
}
DEFAULT_CATEGORY_ID = 1  # Jobs — agar category_label CATEGORY_MAP mein na mile

# ---------- Output paths ----------
DATA_DIR      = "data"
LOGS_DIR      = "logs"
SNAPSHOTS_DIR = "snapshots"
