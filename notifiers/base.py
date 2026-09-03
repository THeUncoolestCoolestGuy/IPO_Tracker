"""
Base notifier class interface.
All notification channels inherit from this class.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


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
