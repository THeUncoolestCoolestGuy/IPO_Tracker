"""
Telegram Bot Notifier.
Sends instant free push notifications to mobile phones via Telegram.
Supports HTML formatting and disabled link previews for clean, airy, visually appealing alerts.
"""

import time
import logging
from typing import List, Dict, Any, Optional
import requests
from .base import BaseNotifier
from config import Config

logger = logging.getLogger("ipo_tracker.notifiers.telegram")


class TelegramNotifier(BaseNotifier):
    def __init__(self, bot_token: str = None, chat_ids: List[str] = None):
        self.bot_token = bot_token or Config.TELEGRAM_BOT_TOKEN
        self.chat_ids = chat_ids or Config.TELEGRAM_CHAT_IDS

    @property
    def name(self) -> str:
        return "telegram"

    def send_direct(
        self,
        chat_id: str,
        message: str,
        parse_mode: Optional[str] = "HTML",
        disable_preview: bool = True,
        max_retries: int = 3,
        timeout: int = 60
    ) -> bool:
        """
        Send a direct message to an individual Telegram chat ID.
        Attempts HTML formatting first; gracefully falls back to plain text if markup fails.
        """
        if not self.bot_token:
            return False

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": str(chat_id).strip(),
            "text": message,
            "disable_web_page_preview": disable_preview
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        for attempt in range(1, max_retries + 1):
            try:
                res = requests.post(api_url, json=payload, timeout=timeout)
                data = res.json()
                if data.get("ok"):
                    return True

                error_code = data.get("error_code")
                desc = data.get("description", "")

                # Fallback to plain text if Telegram cannot parse HTML entities
                if error_code == 400 and "can't parse" in desc.lower() and "parse_mode" in payload:
                    logger.warning(f"Telegram parse error for {chat_id}: {desc}. Retrying as plain text.")
                    payload.pop("parse_mode", None)
                    continue

                if error_code in (400, 403):
                    logger.warning(f"Telegram permanent failure for {chat_id} (code {error_code}): {desc}")
                    if error_code == 403:
                        try:
                            from subscriber_manager import deactivate_subscriber
                            deactivate_subscriber(chat_id, "blocked")
                        except Exception:
                            pass
                    return False

                if error_code == 429:
                    retry_after = data.get("parameters", {}).get("retry_after", 3)
                    time.sleep(retry_after)
                    continue

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logger.warning(f"Telegram network issue sending to {chat_id} (attempt {attempt}/{max_retries}): {e}")
            except Exception as e:
                logger.error(f"Telegram unexpected error for {chat_id}: {e}")
                return False

            if attempt < max_retries:
                time.sleep(attempt * 2)

        return False

    def send(self, recipients: List[str], message: str) -> Dict[str, Any]:
        """Broadcast alert to all active subscribers."""
        if not self.bot_token:
            logger.warning("Telegram bot token not configured in .env. Skipping Telegram.")
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": recipients,
                "error": "TELEGRAM_BOT_TOKEN is missing in .env"
            }

        # Dynamically fetch all active subscribers and auto-detect new users
        try:
            from subscriber_manager import get_all_active_chat_ids
            target_ids = get_all_active_chat_ids()
        except Exception as e:
            logger.warning(f"Could not load subscriber registry: {e}. Using fallback IDs.")
            target_ids = self.chat_ids if self.chat_ids else recipients

        if not target_ids:
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": [],
                "error": "No Telegram chat IDs configured"
            }

        delivered = []
        failed = []

        for chat_id in target_ids:
            ok = self.send_direct(chat_id, message, parse_mode="HTML", disable_preview=True)
            if ok:
                delivered.append(chat_id)
            else:
                failed.append(chat_id)

        return {
            "channel": self.name,
            "success": len(delivered) > 0,
            "delivered": delivered,
            "failed": failed,
            "error": None if len(delivered) > 0 else "All dispatches failed"
        }
