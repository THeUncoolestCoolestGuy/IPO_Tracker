"""
Base notifier class interface.
All notification channels inherit from this class.
"""

import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any


def strip_html(text: str) -> str:
    """
    Convert HTML formatting to clean plain text for SMS and Console.
    Replaces <a href="url">text</a> with text (url), strips <b>, <i>, <code>, etc.
    """
    if not text:
        return ""
    # Convert <a href="url">label</a> to label (url)
    cleaned = re.sub(r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'\2 (\1)', text, flags=re.DOTALL)
    # Strip remaining HTML tags
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    # Decode basic entities
    cleaned = cleaned.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    return cleaned


class BaseNotifier(ABC):
    """Abstract interface for all notification providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the notification channel."""
        pass

    @abstractmethod
    def send(self, recipients: List[str], message: str) -> Dict[str, Any]:
        """
        Send a notification message to the list of recipients.
        
        Args:
            recipients: List of recipient phone numbers or chat IDs.
            message: Formatted text message to send.
            
        Returns:
            Dict containing status, delivered recipients, failed recipients, and details.
        """
        pass
