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

        import time

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        delivered = []
        failed = []
        last_error = None
        max_retries = 3
        timeout_seconds = 35

        for chat_id in target_ids:
            payload = {
                "chat_id": chat_id,
                "text": message
            }
            sent = False
            for attempt in range(1, max_retries + 1):
                try:
                    res = requests.post(api_url, json=payload, timeout=timeout_seconds)
                    data = res.json()
                    if data.get("ok"):
                        delivered.append(chat_id)
                        sent = True
                        break
                    else:
                        error_code = data.get("error_code")
                        last_error = data.get("description", "Unknown Telegram error")
                        logger.warning(
                            f"Telegram error sending to {chat_id} (attempt {attempt}/{max_retries}, code {error_code}): {last_error}"
                        )
                        # Don't retry if user blocked bot or chat not found
                        if error_code in (400, 403):
                            break
                        if error_code == 429:
                            retry_after = data.get("parameters", {}).get("retry_after", 3)
                            time.sleep(retry_after)
                            continue
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    last_error = str(e)
                    logger.warning(
                        f"Telegram connection/timeout for {chat_id} (attempt {attempt}/{max_retries}): {e}"
                    )
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Telegram unexpected error for {chat_id}: {e}")
                    break

                if attempt < max_retries:
                    backoff = attempt * 2
                    time.sleep(backoff)

            if not sent:
                failed.append(chat_id)
                logger.error(f"Telegram failed to send to {chat_id} after {max_retries} attempts: {last_error}")

        return {
            "channel": self.name,
            "success": len(delivered) > 0,
            "delivered": delivered,
            "failed": failed,
            "error": last_error
        }
