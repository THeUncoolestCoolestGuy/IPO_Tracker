"""
Notifier registry and dispatch coordinator.
"""

from typing import List, Dict, Any
import logging
from config import Config
from .base import BaseNotifier
from .console import ConsoleNotifier
from .fast2sms import Fast2SMSNotifier
from .twilio_notifier import TwilioNotifier
from .telegram_notifier import TelegramNotifier

logger = logging.getLogger("ipo_tracker.notifiers")


def get_configured_notifiers() -> List[BaseNotifier]:
    """Instantiate and return notifiers based on Config.NOTIFICATION_CHANNELS."""
    notifiers = []
    active_channels = Config.NOTIFICATION_CHANNELS

    for ch in active_channels:
        if ch == "console":
            notifiers.append(ConsoleNotifier())
        elif ch == "fast2sms":
            notifiers.append(Fast2SMSNotifier())
        elif ch in ("twilio_sms", "twilio"):
            notifiers.append(TwilioNotifier(mode="sms"))
        elif ch == "twilio_whatsapp":
            notifiers.append(TwilioNotifier(mode="whatsapp"))
        elif ch == "telegram":
            notifiers.append(TelegramNotifier())
        else:
            logger.warning(f"Unknown notification channel requested: {ch}")

    # Fallback to console if no valid notifiers enabled
    if not notifiers:
        notifiers.append(ConsoleNotifier())

    return notifiers


def dispatch_alert(message: str, recipients: List[str] = None) -> List[Dict[str, Any]]:
    """
    Send formatted alert message across all configured notification channels.
    """
    targets = recipients or Config.PHONE_NUMBERS
    notifiers = get_configured_notifiers()
    results = []

    for notifier in notifiers:
        try:
            res = notifier.send(targets, message)
            results.append(res)
        except Exception as e:
            logger.error(f"Error dispatching via {notifier.name}: {e}")
            results.append({
                "channel": notifier.name,
                "success": False,
                "delivered": [],
                "failed": targets,
                "error": str(e)
            })

    return results
