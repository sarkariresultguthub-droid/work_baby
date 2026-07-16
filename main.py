# ============================================================
#  main.py  —  Scheduler: har 30 min sab sites check karo (AUTO MODE)
#  Manual mode ke liye: python manual_scrape.py chalao
# ============================================================
import logging
import time
import schedule
from datetime import datetime
from config import SITES, CHECK_INTERVAL_MINUTES
from scraper import check_and_scrape_category
from telegram_bot import (
    notify_change_detected,
    notify_scraper_started,
    notify_error,
    notify_daily_summary,
)

log = logging.getLogger(__name__)
daily_results = []


def run_check():
    log.info(f"\n{'='*60}")
    log.info(f"🔍 Check started at {datetime.utcnow().isoformat()}Z")
    log.info(f"{'='*60}")

    for site_config in SITES:
        categories = site_config.get("categories") or {}
        # Agar categories defined hain, har category ko alag check karo.
        # Agar nahi (categories khali hai), to site ke main url ko hi
        # ek single "Home" category maan ke check karo.
        if not categories:
            categories = {site_config["name"]: site_config["url"]}

        for category_label, category_url in categories.items():
            try:
                result = check_and_scrape_category(site_config, category_label, category_url)
                if result:
                    notify_change_detected(result)
                    daily_results.append(result)
                    log.info(
                        f"✅ [{result['site']}] [{result['category']}] "
                        f"{result['items_count']} naye posts saved -> {result['folder']}"
                    )
                else:
                    log.info(f"⏭️  [{site_config['name']}] [{category_label}] No new post.")
            except Exception as e:
                err_msg = str(e)
                log.error(f"❌ [{site_config['name']}] [{category_label}] Error: {err_msg}")
                notify_error(f"{site_config['name']} / {category_label}", err_msg)
            time.sleep(3)

    log.info(f"{'='*60}")
    log.info(f"✅ Check complete. Next check in {CHECK_INTERVAL_MINUTES} min.")
    log.info(f"{'='*60}\n")


def send_daily_summary():
    global daily_results
    notify_daily_summary(daily_results)
    daily_results.clear()


if __name__ == "__main__":
    log.info("🚀 Professional Web Scraper starting (AUTO MODE)...")
    log.info(f"   Watching {len(SITES)} sites")
    log.info(f"   Check interval: every {CHECK_INTERVAL_MINUTES} minutes")

    notify_scraper_started(SITES)

    log.info("Running initial check...")
    run_check()

    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(run_check)
    schedule.every().day.at("23:00").do(send_daily_summary)

    log.info(f"\n⏰ Scheduler running. Next check in {CHECK_INTERVAL_MINUTES} min.")
    log.info("Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)
