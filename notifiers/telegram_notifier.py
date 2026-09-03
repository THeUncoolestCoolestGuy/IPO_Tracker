"""
Telegram Bot Notifier.
Sends instant free push notifications to mobile phones via Telegram.
"""

import logging
from typing import List, Dict, Any
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

    def send(self, recipients: List[str], message: str) -> Dict[str, Any]:
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

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        delivered = []
        failed = []
        last_error = None

        for chat_id in target_ids:
            payload = {
                "chat_id": chat_id,
                "text": message
            }
            try:
                res = requests.post(api_url, json=payload, timeout=10)
                data = res.json()
                if data.get("ok"):
                    delivered.append(chat_id)
                else:
                    failed.append(chat_id)
                    last_error = data.get("description", "Unknown Telegram error")
            except Exception as e:
                failed.append(chat_id)
                last_error = str(e)
                logger.error(f"Telegram error sending to {chat_id}: {e}")

        return {
            "channel": self.name,
            "success": len(delivered) > 0,
            "delivered": delivered,
            "failed": failed,
            "error": last_error
        }
