import logging
import urllib.parse
import requests
from typing import Dict, Any, List
from .base import BaseNotifier
from config import Config

logger = logging.getLogger("ipo_tracker.notifiers.callmebot")


class CallMeBotNotifier(BaseNotifier):
    """
    Notifier for 100% Free WhatsApp alerts via CallMeBot API.
    Works both locally and 24/7 in GitHub Actions cloud.

    Configuration format in .env:
      CALLMEBOT_RECIPIENTS=+919999999999:APIKEY1,+918888888888:APIKEY2
    """

    @property
    def name(self) -> str:
        return "callmebot"

    def _parse_recipients(self, recipients_override: List[str] = None) -> List[Dict[str, str]]:
        raw = getattr(Config, "CALLMEBOT_RECIPIENTS", "")
        if not raw:
            return []

        recipients = []
        for pair in raw.split(","):
            pair = pair.strip()
            if ":" in pair:
                phone, apikey = pair.split(":", 1)
                phone = phone.strip().replace(" ", "").replace("-", "")
                apikey = apikey.strip()
                if phone and apikey:
                    recipients.append({"phone": phone, "apikey": apikey})
        return recipients

    def send(self, recipients: List[str], message: str) -> Dict[str, Any]:
        targets = self._parse_recipients()
        if not targets:
            logger.warning("CallMeBot: No valid recipients found in CALLMEBOT_RECIPIENTS.")
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": recipients or [],
                "error": "No valid phone:apikey pairs in CALLMEBOT_RECIPIENTS"
            }

        encoded_text = urllib.parse.quote(message)
        delivered = []
        failed = []

        for rec in targets:
            phone = rec["phone"]
            apikey = rec["apikey"]
            url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_text}&apikey={apikey}"

            try:
                response = requests.get(url, timeout=20)
                if response.status_code == 200:
                    logger.info(f"CallMeBot WhatsApp alert delivered to {phone}")
                    delivered.append(phone)
                else:
                    logger.warning(f"CallMeBot response status {response.status_code} for {phone}: {response.text[:120]}")
                    failed.append(phone)
            except Exception as e:
                logger.error(f"CallMeBot network error for {phone}: {e}")
                failed.append(phone)

        return {
            "channel": self.name,
            "success": len(delivered) > 0,
            "delivered": delivered,
            "failed": failed
        }

