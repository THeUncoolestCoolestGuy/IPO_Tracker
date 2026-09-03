"""
Console and File Log Notifier.
Outputs formatted messages to terminal and appends to logs/alerts.log.
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Any
from .base import BaseNotifier
from config import Config


class ConsoleNotifier(BaseNotifier):
    @property
    def name(self) -> str:
        return "console"

    def send(self, recipients: List[str], message: str) -> Dict[str, Any]:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        divider = "=" * 70

        output = f"\n{divider}\n[NOTIFICATION DISPATCH] at {timestamp}\nRecipients: {', '.join(recipients)}\n{divider}\n{message}\n{divider}\n"
        print(output)

        # Log to file
        log_file = Config.LOGS_DIR / "alerts.log"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(output + "\n")
        except Exception as e:
            print(f"Warning: Could not write alert to log file: {e}")

        return {
            "channel": self.name,
            "success": True,
            "delivered": recipients,
            "failed": [],
            "error": None
        }
