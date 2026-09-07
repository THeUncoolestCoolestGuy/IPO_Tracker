"""
Allotment Tracker Engine for Indian IPOs.
Monitors Link Intime, KFintech, and Bigshare for newly declared allotments.
Maintains state in data/notified_allotments.json to prevent duplicate notifications.
"""

import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

from config import Config
from allotment_scraper import get_all_live_allotments
from notifiers import dispatch_alert

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("ipo_tracker.allotment_tracker")

ALLOTMENT_STATE_FILE = Config.DATA_DIR / "notified_allotments.json"


def normalize_key(name: str) -> str:
    """Normalize company name to lowercase alphanumeric key for reliable matching."""
    import re
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", name.lower())
    # Remove common filler words
    for word in ["limited", "ltd", "ipo", "sme"]:
        cleaned = cleaned.replace(word, "")
    return cleaned.strip()


def load_notified_allotments() -> Dict:
    """Load previously notified allotments registry."""
    if not ALLOTMENT_STATE_FILE.exists():
        return {}
    try:
        with open(ALLOTMENT_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load notified allotments state: {e}")
        return {}


def save_notified_allotments(registry: Dict):
    """Save notified allotments registry to disk."""
    try:
        with open(ALLOTMENT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save notified allotments state: {e}")


def format_allotment_alert(ipo: Dict) -> str:
    """Format an attractive allotment declared alert message."""
    name = ipo.get("name", "IPO")
    registrar = ipo.get("registrar", "Registrar")
    portal_url = ipo.get("portal_url", "")
    bse_url = ipo.get("bse_url", "https://www.bseindia.com/investors/appli_check.aspx")
    today_str = datetime.now().strftime("%d %b %Y")

    lines = [
        f"🎉 [ALLOTMENT DECLARED! - {today_str}]",
        f"\nAllotment status is now officially LIVE for:",
        f"📌 {name}",
        f"🏛️ Registrar: {registrar}\n",
        "📲 Check Your Allotment Status Now:",
        f"👉 {registrar} Portal: {portal_url}",
        f"👉 BSE Central Portal: {bse_url}\n",
        "💡 Have your PAN Number or Application Number ready!\n",
        "📲 Direct Broker Launchers:",
        "• Kite: https://play.google.com/store/apps/details?id=com.zerodha.kite3",
        "• Upstox: https://play.google.com/store/apps/details?id=in.upstox.app",
        "• Groww: https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        "• Sharekhan: https://play.google.com/store/apps/details?id=com.sharekhan.androidsharemobile"
    ]
    return "\n".join(lines).strip()


def check_and_notify_new_allotments(dry_run: bool = False, force_check: bool = False) -> Dict:
    """
    Check all registrars for newly published IPO allotments.
    If run for the first time without an existing state file, seeds current IPOs to avoid spamming historical allotments.
    """
    logger.info("Scanning registrars for newly declared IPO allotments...")
    live_ipos = get_all_live_allotments()
    if not live_ipos:
        logger.warning("No live IPOs fetched from registrars.")
        return {"status": "no_data", "count": 0, "new_allotments": []}

    registry = load_notified_allotments()
    is_first_run = len(registry) == 0 and not force_check

    # If first run, seed all currently active IPOs so users aren't spammed with dozens of past IPOs
    if is_first_run:
        logger.info(f"First run: Seeding {len(live_ipos)} existing allotments to state registry.")
        for ipo in live_ipos:
            key = normalize_key(ipo["name"])
            registry[key] = {
                "name": ipo["name"],
                "registrar": ipo["registrar"],
                "portal_url": ipo["portal_url"],
                "first_seen": datetime.now().isoformat()
            }
        save_notified_allotments(registry)
        return {
            "status": "seeded_initial",
            "count": len(live_ipos),
            "new_allotments": []
        }

    new_allotments = []
    for ipo in live_ipos:
        key = normalize_key(ipo["name"])
        if key not in registry:
            new_allotments.append(ipo)

    logger.info(f"Detected {len(new_allotments)} newly declared allotment(s).")

    if not new_allotments:
        return {"status": "no_new_allotments", "count": 0, "new_allotments": []}

    results = []
    for ipo in new_allotments:
        alert_msg = format_allotment_alert(ipo)
        if dry_run:
            print("\n--- [DRY-RUN] ALLOTMENT ALERT PREVIEW ---")
            print(alert_msg)
            print("-----------------------------------------\n")
        else:
            dispatch_results = dispatch_alert(alert_msg)
            results.append(dispatch_results)

        # Update registry
        key = normalize_key(ipo["name"])
        registry[key] = {
            "name": ipo["name"],
            "registrar": ipo["registrar"],
            "portal_url": ipo["portal_url"],
            "notified_at": datetime.now().isoformat()
        }

    if not dry_run:
        save_notified_allotments(registry)

    return {
        "status": "notified",
        "count": len(new_allotments),
        "new_allotments": [i["name"] for i in new_allotments],
        "dispatch_results": results
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Allotment Tracker...")
    res = check_and_notify_new_allotments(dry_run=True, force_check=False)
    print("Result:", res)
