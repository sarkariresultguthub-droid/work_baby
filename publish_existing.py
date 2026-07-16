# ============================================================
#  publish_existing.py  —  Already scraped hue (data/<date>/<category>/)
#  posts ko manually format+publish karne ke liye. Naya post detect
#  nahi karta — jo bhi files already scraped pade hain unhi ko
#  CareerFlora par publish try karta hai.
#
#  Usage:  python publish_existing.py 2026-07-16
#  (date folder ka naam do — data/2026-07-16/ ke andar jitni bhi
#   category folders hain sabko process karega)
# ============================================================

import os
import sys
import logging

from ai_formatter import format_and_publish_folder
from config import DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def main():
    if len(sys.argv) < 2:
        print("Usage: python publish_existing.py <date-folder>")
        print("  e.g. python publish_existing.py 2026-07-16")
        sys.exit(1)

    date_folder = sys.argv[1]
    base_path = os.path.join(DATA_DIR, date_folder)

    if not os.path.isdir(base_path):
        print(f"❌ Folder nahi mila: {base_path}")
        sys.exit(1)

    category_folders = [
        d for d in sorted(os.listdir(base_path))
        if os.path.isdir(os.path.join(base_path, d))
    ]

    if not category_folders:
        print(f"❌ {base_path} ke andar koi category folder nahi mila.")
        sys.exit(1)

    log.info(f"📂 {len(category_folders)} category folders milin: {category_folders}")

    grand_total = {"total": 0, "formatted": 0, "published": 0, "failed": []}

    for category_label in category_folders:
        folder_path = os.path.join(base_path, category_label)
        log.info(f"\n{'='*60}\n▶️  Processing: {category_label}\n{'='*60}")

        result = format_and_publish_folder(folder_path, category_label)

        grand_total["total"] += result["total"]
        grand_total["formatted"] += result["formatted"]
        grand_total["published"] += result["published"]
        grand_total["failed"].extend(result["failed"])

    log.info(f"\n{'='*60}")
    log.info(
        f"🏁 GRAND TOTAL: {grand_total['published']}/{grand_total['total']} published, "
        f"{len(grand_total['failed'])} failed."
    )
    if grand_total["failed"]:
        log.info(f"Failed titles: {grand_total['failed']}")
    log.info(f"{'='*60}")


if __name__ == "__main__":
    main()
