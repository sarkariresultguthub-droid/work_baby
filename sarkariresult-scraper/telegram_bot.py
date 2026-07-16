# ============================================================
#  telegram_bot.py  —  Telegram Notifications
# ============================================================
import logging
import requests
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


def send_telegram(message: str) -> bool:
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.warning("Telegram token set nahi hai — skipping notification.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            log.info("✅ Telegram notification sent!")
            return True
        log.error(f"Telegram error: {resp.status_code} — {resp.text}")
        return False
    except Exception as e:
        log.error(f"Telegram exception: {e}")
        return False


def notify_change_detected(result: dict):
    items = result.get("items", [])

    posts_text = ""
    if items:
        lines = []
        for it in items[:15]:  # zyada posts hone par message lamba na ho, max 15 dikhao
            title = it.get("title", "Untitled")
            link = it.get("link", "")
            if link:
                lines.append(f"• <a href=\"{link}\">{title}</a>")
            else:
                lines.append(f"• {title}")
        posts_text = "\n".join(lines)
        if len(items) > 15:
            posts_text += f"\n...and {len(items) - 15} more"

    msg = (
        f"🔔 <b>New Post Detected!</b>\n\n"
        f"🌐 <b>Site:</b> {result['site']}\n"
        f"🏷️ <b>Category:</b> {result.get('category', '-')}\n"
        f"📦 <b>New Posts:</b> {result['items_count']}\n\n"
        f"{posts_text}\n\n"
        f"🕐 <b>Time:</b> {result['changed_at']}"
    )
    return send_telegram(msg)


def notify_scraper_started(sites: list):
    names = "\n".join([f"  • {s['name']}" for s in sites])
    msg = (
        f"🚀 <b>Scraper Started!</b>\n\n"
        f"📋 <b>Watching {len(sites)} sites:</b>\n{names}\n\n"
        f"⏰ Check interval: every 30 minutes"
    )
    return send_telegram(msg)


def notify_error(site_name: str, error: str):
    msg = (
        f"❌ <b>Scraper Error</b>\n\n"
        f"🌐 Site: {site_name}\n"
        f"💬 Error: <code>{error[:200]}</code>\n"
        f"🕐 Time: {datetime.utcnow().isoformat()}Z"
    )
    return send_telegram(msg)


def notify_daily_summary(results: list):
    if not results:
        msg = "📊 <b>Daily Summary</b>\n\nAaj koi changes detect nahi hue. Sab sites same hain."
    else:
        lines = "\n".join([f"  ✅ {r['site']}: {r['items_count']} items" for r in results])
        msg = (
            f"📊 <b>Daily Summary</b>\n\n"
            f"<b>Changes detected on {len(results)} site(s):</b>\n"
            f"{lines}\n\n"
            f"🕐 {datetime.utcnow().strftime('%Y-%m-%d')}"
        )
    return send_telegram(msg)