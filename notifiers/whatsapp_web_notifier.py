import os
import time
import logging
from typing import Dict, Any, List
from .base import BaseNotifier
from config import Config

logger = logging.getLogger("ipo_tracker.notifiers.whatsapp_web")


class WhatsAppWebNotifier(BaseNotifier):
    """
    Notifier using local WhatsApp Web automation via pywhatkit.
    Sends messages from the user's personal WhatsApp account on their laptop.

    Note:
      - Requires the laptop to be awake and WhatsApp Web logged in.
      - Automatically skips if running inside cloud CI (GitHub Actions).
    """

    @property
    def name(self) -> str:
        return "whatsapp_web"

    def send(self, recipients: List[str], message: str) -> Dict[str, Any]:
        # Gracefully skip if running in headless GitHub Actions cloud
        if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
            logger.info("Skipping WhatsApp Web automation in GitHub Actions cloud environment.")
            return {
                "channel": self.name,
                "success": True,
                "delivered": [],
                "failed": [],
                "note": "Skipped in GitHub Actions cloud (requires local desktop session)"
            }

        raw_targets = getattr(Config, "WHATSAPP_PHONE_NUMBERS", None) or recipients or Config.PHONE_NUMBERS
        if isinstance(raw_targets, str):
            targets = [p.strip() for p in raw_targets.split(",") if p.strip()]
        else:
            targets = list(raw_targets)

        # Normalize phone numbers with +91
        clean_targets = []
        for t in targets:
            clean = t.replace(" ", "").replace("-", "")
            if not clean.startswith("+"):
                clean = f"+91{clean}"
            clean_targets.append(clean)

        if not clean_targets:
            logger.warning("WhatsApp Web: No phone numbers provided.")
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": [],
                "error": "No phone numbers provided"
            }

        try:
            import pywhatkit
        except ImportError:
            logger.error("WhatsApp Web: 'pywhatkit' library is not installed.")
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": clean_targets,
                "error": "pywhatkit not installed"
            }

        delivered = []
        failed = []

        logger.info(f"WhatsApp Web: Initiating automated dispatch to {len(clean_targets)} recipient(s)...")

        for phone in clean_targets:
            try:
                logger.info(f"WhatsApp Web: Opening chat for {phone}...")
                # wait_time=15 allows WhatsApp Web tab to load completely
                # tab_close=True closes the tab 4 seconds after sending
                pywhatkit.sendwhatmsg_instantly(
                    phone_no=phone,
                    message=message,
                    wait_time=15,
                    tab_close=True,
                    close_time=4
                )
                logger.info(f"WhatsApp Web: Message dispatched to {phone}")
                delivered.append(phone)
                # Small delay between multiple recipients
                time.sleep(3)
            except Exception as e:
                logger.error(f"WhatsApp Web failed for {phone}: {e}")
                failed.append(phone)

        return {
            "channel": self.name,
            "success": len(delivered) > 0,
            "delivered": delivered,
            "failed": failed
        }

