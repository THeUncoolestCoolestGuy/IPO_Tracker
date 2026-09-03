"""
Twilio Notifier for SMS and WhatsApp messages.
Supports both standard international SMS and Twilio WhatsApp messages.
"""

import logging
from typing import List, Dict, Any
from .base import BaseNotifier
from config import Config

logger = logging.getLogger("ipo_tracker.notifiers.twilio")


class TwilioNotifier(BaseNotifier):
    def __init__(self, mode: str = "sms"):
        """
        mode: 'sms' or 'whatsapp'
        """
        self.mode = mode.lower()
        self.account_sid = Config.TWILIO_ACCOUNT_SID
        self.auth_token = Config.TWILIO_AUTH_TOKEN
        self.from_phone = Config.TWILIO_PHONE_NUMBER
        self.from_whatsapp = Config.TWILIO_WHATSAPP_NUMBER

    @property
    def name(self) -> str:
        return f"twilio_{self.mode}"

    def send(self, recipients: List[str], message: str) -> Dict[str, Any]:
        if not self.account_sid or not self.auth_token:
            logger.warning(f"Twilio credentials not configured in .env. Skipping {self.name}.")
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": recipients,
                "error": "TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN missing in .env"
            }

        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
        except ImportError:
            logger.error("twilio package is not installed. Please run: pip install twilio")
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": recipients,
                "error": "twilio package not installed"
            }
        except Exception as e:
            return {
                "channel": self.name,
                "success": False,
                "delivered": [],
                "failed": recipients,
                "error": str(e)
            }

        delivered = []
        failed = []
        last_error = None

        for phone in recipients:
            target = phone.strip()
            if not target.startswith("+"):
                target = "+" + target

            try:
                if self.mode == "whatsapp":
                    from_addr = self.from_whatsapp
                    if not from_addr.startswith("whatsapp:"):
                        from_addr = f"whatsapp:{from_addr}"
                    to_addr = f"whatsapp:{target}"
                else:
                    from_addr = self.from_phone
                    to_addr = target

                msg = client.messages.create(
                    body=message,
                    from_=from_addr,
                    to=to_addr
                )
                delivered.append(target)
                logger.info(f"Twilio {self.mode} sent to {target}: SID {msg.sid}")
            except Exception as e:
                failed.append(target)
                last_error = str(e)
                logger.error(f"Failed to send Twilio {self.mode} to {target}: {e}")

        return {
            "channel": self.name,
            "success": len(delivered) > 0,
            "delivered": delivered,
            "failed": failed,
            "error": last_error
        }
