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


import time

def _telegram_post_with_retry(token: str, payload: Dict[str, Any], max_retries: int = 3, timeout: int = 60) -> bool:
    """Send a POST request to Telegram sendMessage with retry and backoff."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.post(url, json=payload, timeout=timeout)
            data = res.json()
            if data.get("ok"):
                return True
            code = data.get("error_code")
            if code in (400, 403):
                logger.warning(f"Telegram permanent failure for {payload.get('chat_id')}: {data.get('description')}")
                return False
            if code == 429:
                retry_after = data.get("parameters", {}).get("retry_after", 3)
                time.sleep(retry_after)
                continue
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.warning(f"Telegram network issue sending to {payload.get('chat_id')} (attempt {attempt}/{max_retries}): {e}")
        except Exception as e:
            logger.error(f"Telegram unexpected error: {e}")
            return False

        if attempt < max_retries:
            time.sleep(attempt * 2)
    return False


def load_subscribers_registry() -> Dict[str, Dict[str, Any]]:
    """Load the subscriber registry from data/subscribers.json."""
    if SUBSCRIBERS_FILE.exists():
        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
        except Exception as e:
            logger.error(f"Error loading subscribers.json: {e}")

    # Baseline with all verified subscribers
    baseline = {
        "2056597708": {"name": "The uncoolest coolest guy", "role": "admin"},
        "443423364": {"name": "Dr. Chirag Paunwala (@cpaunwala)", "role": "member"},
        "810585239": {"name": "Mita Paunwala (@Mpaunwala)", "role": "member"},
        "424851606": {"name": "K", "role": "member"},
        "516357277": {"name": "Paresh Bardolia", "role": "member"},
        "1293713981": {"name": "Sarthak", "role": "member"},
        "1400902994": {"name": "Dobby", "role": "member"}
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
    max_update_id = 0

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    updates = []
    for attempt in range(1, 4):
        try:
            res = requests.get(url, timeout=60)
            data = res.json()
            if data.get("ok"):
                updates = data.get("result", [])
                break
            else:
                logger.warning(f"getUpdates returned error: {data.get('description')}")
        except Exception as e:
            logger.warning(f"Error checking Telegram getUpdates (attempt {attempt}/3): {e}")
            time.sleep(attempt * 2)

    for update in updates:
        uid = update.get("update_id", 0)
        if uid > max_update_id:
            max_update_id = uid

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
                "• 12:30 PM IST: Reminder Alert (IPOs closing today)\n\n"
                "📲 You'll get direct 1-click apply links for Kite, Upstox, Groww, and Sharekhan!\n\n"
                "🎁 Don't have a Demat Account yet? Open free & start applying:\n"
                f"• Zerodha Kite: {Config.ZERODHA_REFERRAL_URL}\n"
                f"• Upstox (Zero AMC & Margin perks): {Config.UPSTOX_REFERRAL_URL}\n"
                f"• Groww (Code: {Config.GROWW_REFERRAL_CODE}): {Config.GROWW_REFERRAL_URL}"
            )
            _telegram_post_with_retry(token, {"chat_id": cid, "text": welcome_msg})

            # 2. Inform the Admin
            if notify_admin and admin_id and cid != admin_id:
                admin_alert = (
                    "🔔 [ADMIN NOTIFICATION] New Subscriber Joined!\n\n"
                    f"👤 Name: {display_name}\n"
                    f"🆔 Chat ID: {cid}\n\n"
                    "✅ They have been automatically enrolled to receive daily IPO & GMP alerts!"
                )
                _telegram_post_with_retry(token, {"chat_id": admin_id, "text": admin_alert})

    # Acknowledge processed updates with Telegram server so they are never returned again
    if max_update_id > 0:
        try:
            requests.get(f"{url}?offset={max_update_id + 1}&limit=1", timeout=60)
            logger.debug(f"Acknowledged Telegram updates up to {max_update_id}")
        except Exception as e:
            logger.debug(f"Could not acknowledge getUpdates offset {max_update_id + 1}: {e}")

    if new_subscribers:
        save_subscribers_registry(registry)
        logger.info(f"Registered and saved {len(new_subscribers)} new subscriber(s).")

    return new_subscribers


def deactivate_subscriber(chat_id: str, reason: str = "blocked"):
    """Mark a subscriber as inactive / blocked so we don't attempt sending to them."""
    cid = str(chat_id).strip()
    registry = load_subscribers_registry()
    if cid in registry:
        registry[cid]["status"] = reason
        save_subscribers_registry(registry)
        logger.info(f"Subscriber {cid} marked as {reason}.")


def get_all_active_chat_ids() -> List[str]:
    """
    Get all active Telegram Chat IDs combining .env and subscribers.json.
    Also runs sync to catch any newly joined users.
    Excludes any blocked/inactive users.
    """
    sync_new_subscribers(notify_admin=True)
    registry = load_subscribers_registry()

    all_ids = set()
    for cid, info in registry.items():
        if info.get("status") not in ("blocked", "inactive"):
            all_ids.add(str(cid).strip())

    for cid in Config.TELEGRAM_CHAT_IDS:
        cid_str = str(cid).strip()
        if cid_str and registry.get(cid_str, {}).get("status") not in ("blocked", "inactive"):
            all_ids.add(cid_str)

    return list(all_ids)

