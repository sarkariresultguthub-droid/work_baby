# ============================================================
#  run_once.py  —  GitHub Actions / cron ke liye
#  main.py ki tarah hi check karta hai, lekin EK BAAR chalega
#  aur exit ho jayega (infinite loop nahi) — kyunki scheduling
#  ab GitHub Actions khud (cron se) sambhalta hai.
# ============================================================
import logging
from datetime import datetime
from config import SITES
from scraper import check_and_scrape_category
from telegram_bot import notify_change_detected, notify_error
from ai_formatter import format_and_publish_folder

log = logging.getLogger(__name__)


def main():
    log.info(f"\n{'='*60}")
    log.info(f"🔍 [run_once] Check started at {datetime.utcnow().isoformat()}Z")
    log.info(f"{'='*60}")

    any_new = False

    for site_config in SITES:
        categories = site_config.get("categories") or {}
        if not categories:
            categories = {site_config["name"]: site_config["url"]}

        for category_label, category_url in categories.items():
            try:
                result = check_and_scrape_category(site_config, category_label, category_url)
                if result:
                    any_new = True
                    notify_change_detected(result)
                    log.info(
                        f"✅ [{result['site']}] [{result['category']}] "
                        f"{result['items_count']} naye posts saved -> {result['folder']}"
                    )

                    # ---- AI format (Groq / template fallback) + CareerFlora draft publish ----
                    try:
                        summary = format_and_publish_folder(result["folder"], category_label)
                        log.info(
                            f"📝 [{category_label}] Format+Publish: "
                            f"{summary['published']}/{summary['total']} drafts saved. "
                            f"Failed: {summary['failed']}"
                        )
                    except Exception as fe:
                        log.error(f"❌ [{category_label}] Format/Publish step error: {fe}")
                        notify_error(f"{site_config['name']} / {category_label} (formatter)", str(fe))
                else:
                    log.info(f"⏭️  [{site_config['name']}] [{category_label}] No new post.")
            except Exception as e:
                err_msg = str(e)
                log.error(f"❌ [{site_config['name']}] [{category_label}] Error: {err_msg}")
                notify_error(f"{site_config['name']} / {category_label}", err_msg)

    log.info(f"{'='*60}")
    log.info(f"✅ [run_once] Check complete. any_new_post={any_new}")
    log.info(f"{'='*60}\n")


if __name__ == "__main__":
    main()
