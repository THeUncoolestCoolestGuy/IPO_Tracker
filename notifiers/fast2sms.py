"""
Fast2SMS Notifier (India-specific SMS gateway).
API Docs: https://docs.fast2sms.com/
Sends SMS directly to Indian mobile numbers (+91) via Quick SMS route.
"""

import re
import logging
from typing import List, Dict, Any
import requests
from .base import BaseNotifier
from config import Config

logger = logging.getLogger("ipo_tracker.notifiers.fast2sms")


class Fast2SMSNotifier(BaseNotifier):
    API_URL = "https://www.fast2sms.com/dev/bulkV2"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or Config.FAST2SMS_API_KEY

    @property
    def name(self) -> str:
        return "fast2sms"

    def _clean_phone_number(self, phone: str) -> str:
        """Strip +91, spaces, hyphens, and leading zero to obtain 10-digit number."""
        clean = re.sub(r"\D", "", phone)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        elif clean.startswith("0") and len(clean) == 11:
            clean = clean[1:]
        return clean

    def send(self, recipients: List[str], message: str) -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_fast2sms_api_key_here":
            logger.warning("Fast2SMS API key is not configured in .env. Skipping SMS dispatch.")
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": recipients,
                "error": "FAST2SMS_API_KEY is not configured in .env"
            }

        # Filter and clean valid 10-digit Indian mobile numbers
        cleaned_numbers = []
        for r in recipients:
            cleaned = self._clean_phone_number(r)
            if len(cleaned) == 10 and cleaned.isdigit():
                cleaned_numbers.append(cleaned)
            else:
                logger.warning(f"Invalid Indian phone number for Fast2SMS: {r}")

        if not cleaned_numbers:
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": recipients,
                "error": "No valid 10-digit numbers found"
            }

        numbers_str = ",".join(cleaned_numbers)
        headers = {
            "authorization": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache"
        }
        payload = {
            "route": "q",  # Quick SMS route for direct personal messages
            "message": message,
            "language": "english",
            "flash": 0,
            "numbers": numbers_str
        }

        try:
            response = requests.post(self.API_URL, headers=headers, data=payload, timeout=15)
            res_data = response.json()
            logger.info(f"Fast2SMS API response: {res_data}")

            if res_data.get("return") is True:
                return {
                    "channel": self.name,
                    "success": True,
                    "delivered": cleaned_numbers,
                    "failed": [],
                    "error": None,
                    "message_id": res_data.get("request_id")
                }
            else:
                error_msg = res_data.get("message", ["Unknown Fast2SMS error"])[0] if isinstance(res_data.get("message"), list) else str(res_data.get("message"))
                return {
                    "channel": self.name,
                    "success": False,
                    "delivered": [],
                    "failed": cleaned_numbers,
                    "error": error_msg
                }
        except Exception as e:
            logger.error(f"Fast2SMS request failed: {e}")
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": cleaned_numbers,
                "error": str(e)
            }
