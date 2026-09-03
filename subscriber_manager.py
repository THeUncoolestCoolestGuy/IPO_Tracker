"""
Subscriber Manager for Telegram Bot.
Auto-detects when new users start the bot, enrolls them,
and notifies the admin immediately.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any
import requests
from config import Config

logger = logging.getLogger("ipo_tracker.subscribers")
SUBSCRIBERS_FILE = Config.DATA_DIR / "subscribers.json"


def load_subscribers_registry() -> Dict[str, Dict[str, Any]]:
    """Load the subscriber registry from data/subscribers.json."""
    if SUBSCRIBERS_FILE.exists():
        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading subscribers.json: {e}")

    # Default baseline with known initial subscribers
    baseline = {
        "2056597708": {"name": "The uncoolest coolest guy", "role": "admin"},
        "443423364": {"name": "Dr. Chirag Paunwala (@cpaunwala)", "role": "member"},
        "810585239": {"name": "Mita Paunwala (@Mpaunwala)", "role": "member"}
    }
    save_subscribers_registry(baseline)
    return baseline


def save_subscribers_registry(registry: Dict[str, Dict[str, Any]]):
    """Save the subscriber registry to data/subscribers.json."""
    try:
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving subscribers.json: {e}")


def sync_new_subscribers(notify_admin: bool = True) -> List[Dict[str, Any]]:
    """
    Poll Telegram getUpdates to detect any users who started the bot.
    Enrolls them, sends a welcome message, and informs the admin.
    Returns list of newly registered subscribers.
    """
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        return []

    registry = load_subscribers_registry()
    admin_id = getattr(Config, "ADMIN_CHAT_ID", "2056597708")
    new_subscribers = []

    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        res = requests.get(url, timeout=10)
        data = res.json()
        updates = data.get("result", [])
    except Exception as e:
        logger.error(f"Error checking Telegram getUpdates: {e}")
        return []

    for update in updates:
        msg = update.get("message") or update.get("my_chat_member") or {}
        chat = msg.get("chat") or {}
        cid = str(chat.get("id", "")).strip()

        if not cid:
            continue

        first = chat.get("first_name", "")
        last = chat.get("last_name", "")
        uname = chat.get("username", "")
        full_name = f"{first} {last}".strip()
        display_name = f"{full_name} (@{uname})" if uname else full_name

        if cid not in registry:
            logger.info(f"New Telegram subscriber detected: {display_name} (ID: {cid})")
            user_info = {
                "name": display_name,
                "role": "member"
            }
            registry[cid] = user_info
            new_subscribers.append({"id": cid, "name": display_name})

            # 1. Send welcome message to the new user
            welcome_msg = (
                f"🎉 Welcome to Paunwala IPO Alerts, {first or 'Investor'}!\n\n"
                "You are now subscribed to receive daily Indian Mainboard IPO alerts:\n"
                "• 08:00 AM IST: Morning Alert (GMP > 10%)\n"
                "• 02:30 PM IST: Reminder Alert (IPOs closing today)\n\n"
                "You'll get direct 1-click apply links for Kite, Upstox, and Sharekhan!"
            )
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": cid, "text": welcome_msg},
                    timeout=10
                )
            except Exception as e:
                logger.error(f"Failed to send welcome to {cid}: {e}")

            # 2. Inform the Admin
            if notify_admin and admin_id:
                admin_alert = (
                    "🔔 [ADMIN NOTIFICATION] New Subscriber Joined!\n\n"
                    f"👤 Name: {display_name}\n"
                    f"🆔 Chat ID: {cid}\n\n"
                    "✅ They have been automatically enrolled to receive daily IPO & GMP alerts!"
                )
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": admin_id, "text": admin_alert},
                        timeout=10
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin about {cid}: {e}")

    if new_subscribers:
        save_subscribers_registry(registry)
        logger.info(f"Registered and saved {len(new_subscribers)} new subscriber(s).")

    return new_subscribers


def get_all_active_chat_ids() -> List[str]:
    """
    Get all active Telegram Chat IDs combining .env and subscribers.json.
    Also runs sync to catch any newly joined users.
    """
    sync_new_subscribers(notify_admin=True)
    registry = load_subscribers_registry()

    all_ids = set(registry.keys())
    for cid in Config.TELEGRAM_CHAT_IDS:
        if cid:
            all_ids.add(str(cid).strip())

    return list(all_ids)

