"""
Tracker engine for filtering high-GMP IPOs and building alert messages.
Orchestrates the 8:00 AM IST Morning Alert and 12:30 PM IST Reminder Alert.
"""

import sys
import logging
from datetime import datetime
from typing import List, Dict, Tuple
from config import Config
from scraper import get_all_mainboard_ipos
from notifiers import dispatch_alert

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("ipo_tracker.tracker")

BROKER_APP_LINKS = {
    "Kite": "https://play.google.com/store/apps/details?id=com.zerodha.kite3",
    "Upstox": "https://play.google.com/store/apps/details?id=in.upstox.app",
    "Sharekhan": "https://play.google.com/store/apps/details?id=com.sharekhan.androidsharemobile"
}


def get_eligible_ipos(threshold: float = None) -> List[Dict]:
    """
    Fetch Mainboard IPOs and filter for:
    - Status is NOT 'Closed' (Open or Upcoming)
    - GMP % >= threshold (default 10.0%)
    Sorted by GMP % descending.
    """
    if threshold is None:
        threshold = Config.GMP_THRESHOLD_PERCENT

    all_ipos = get_all_mainboard_ipos()
    eligible = []

    for ipo in all_ipos:
        status = ipo.get("status", "").lower()
        # Exclude closed IPOs
        if status == "closed":
            continue

        gmp_pct = ipo.get("gmp_percent", 0.0)
        if gmp_pct >= threshold:
            eligible.append(ipo)

    # Sort descending by GMP percentage
    eligible.sort(key=lambda x: x.get("gmp_percent", 0.0), reverse=True)
    return eligible


def format_morning_alert(ipos: List[Dict]) -> str:
    """
    Format the 8:00 AM IST Morning Alert message.
    Specifies IPO Name, Price, GMP (₹ and %), Last Filing Date, and Status.
    """
    today_str = datetime.now().strftime("%d %b %Y")
    lines = [
        f"🔔 [8:00 AM] MAINBOARD IPO ALERT ({today_str})",
        f"Threshold: GMP > {Config.GMP_THRESHOLD_PERCENT}%\n",
        f"Found {len(ipos)} Mainboard IPO(s) with high GMP:\n"
    ]

    for idx, ipo in enumerate(ipos, 1):
        name = ipo['name']
        price = ipo['price_band']
        gmp_rs = f"₹{ipo['gmp_rs']:.0f}" if ipo['gmp_rs'].is_integer() else f"₹{ipo['gmp_rs']:.1f}"
        gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
        last_date = ipo['last_filing_date']
        status = ipo['status'].upper()

        closing_note = " ⚠️ (CLOSING TODAY!)" if ipo.get("closing_today") else ""

        lines.append(f"{idx}. {name}")
        lines.append(f"   • GMP: {gmp_rs} ({gmp_pct})")
        lines.append(f"   • Price: {price}")
        lines.append(f"   • Last Filing Date: {last_date}{closing_note}")
        lines.append(f"   • Status: {status}")
        if ipo.get("status", "").lower() == "open":
            lines.append("   📲 Open App to Apply:")
            lines.append(f"   • Kite: {BROKER_APP_LINKS['Kite']}")
            lines.append(f"   • Upstox: {BROKER_APP_LINKS['Upstox']}")
            lines.append(f"   • Sharekhan: {BROKER_APP_LINKS['Sharekhan']}\n")
        else:
            lines.append("")

    lines.append("Apply via ASBA/UPI before 5:00 PM on the closing date.\n")
    lines.append("📲 Direct Broker Launchers:")
    lines.append(f"• Kite: {BROKER_APP_LINKS['Kite']}")
    lines.append(f"• Upstox: {BROKER_APP_LINKS['Upstox']}")
    lines.append(f"• Sharekhan: {BROKER_APP_LINKS['Sharekhan']}")
    return "\n".join(lines).strip()


def format_reminder_alert(ipos: List[Dict]) -> Tuple[str, bool]:
    """
    Format the 2:30 PM IST Reminder message.
    Prioritizes IPOs closing TODAY or currently OPEN.
    Returns (message_text, has_urgent_closing).
    """
    today_str = datetime.now().strftime("%d %b %Y")
    closing_today = [ipo for ipo in ipos if ipo.get("closing_today")]
    currently_open = [ipo for ipo in ipos if ipo.get("status", "").lower() == "open"]

    lines = [
        f"⚠️ [2:30 PM] IPO REMINDER ALERT ({today_str})"
    ]

    if closing_today:
        lines.append("\n🚨 IPOs CLOSING TODAY (Last Chance to Apply!):")
        for ipo in closing_today:
            name = ipo['name']
            gmp_rs = f"₹{ipo['gmp_rs']:.0f}" if ipo['gmp_rs'].is_integer() else f"₹{ipo['gmp_rs']:.1f}"
            gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
            lines.append(f" • {name}: GMP {gmp_rs} ({gmp_pct}) | Price: {ipo['price_band']}")
            lines.append(f"   Last Filing Cut-off: TODAY 5:00 PM IST")
            lines.append("   📲 Open App to Apply:")
            lines.append(f"   • Kite: {BROKER_APP_LINKS['Kite']}")
            lines.append(f"   • Upstox: {BROKER_APP_LINKS['Upstox']}")
            lines.append(f"   • Sharekhan: {BROKER_APP_LINKS['Sharekhan']}\n")
        lines.append("Submit your ASBA / UPI bid before 5:00 PM IST today!")
        return "\n".join(lines).strip(), True

    elif currently_open:
        lines.append("\n📋 Active IPOs currently OPEN with GMP > 10%:")
        for ipo in currently_open:
            name = ipo['name']
            gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
            lines.append(f" • {name}: GMP {gmp_pct} | Last Filing Date: {ipo['last_filing_date']}")
            lines.append("   📲 Open App to Apply:")
            lines.append(f"   • Kite: {BROKER_APP_LINKS['Kite']}")
            lines.append(f"   • Upstox: {BROKER_APP_LINKS['Upstox']}")
            lines.append(f"   • Sharekhan: {BROKER_APP_LINKS['Sharekhan']}\n")
        lines.append("Plan your bidding before the closing date 5:00 PM.")
        return "\n".join(lines).strip(), False

    elif ipos:
        lines.append("\nUpcoming High-GMP Mainboard IPOs:")
        for ipo in ipos:
            lines.append(f" • {ipo['name']}: GMP +{ipo['gmp_percent']:.1f}% | Opens: {ipo['start_date']} | Closes: {ipo['last_filing_date']}")
        return "\n".join(lines).strip(), False

    return "", False


def run_morning_check(dry_run: bool = False) -> Dict:
    """
    Execute the 8:00 AM IST Morning Workflow.
    Automatically checks for new Telegram subscribers and notifies admin every day.
    """
    logger.info("Executing 8:00 AM Morning IPO Check...")

    # Check for newly joined users every day
    try:
        from subscriber_manager import sync_new_subscribers
        sync_new_subscribers(notify_admin=True)
    except Exception as e:
        logger.error(f"Error syncing subscribers in morning check: {e}")

    eligible_ipos = get_eligible_ipos()

    if not eligible_ipos:
        logger.info(f"No Mainboard IPOs found with GMP > {Config.GMP_THRESHOLD_PERCENT}%.")
        if not Config.SILENT_ON_EMPTY:
            msg = f"ℹ️ [8:00 AM] IPO Update: No Mainboard IPOs currently meet the {Config.GMP_THRESHOLD_PERCENT}% GMP criteria today."
            if not dry_run:
                dispatch_alert(msg)
            return {"status": "silent_empty", "count": 0, "message": msg}
        return {"status": "silent_empty", "count": 0, "message": None}

    message = format_morning_alert(eligible_ipos)

    if dry_run:
        print("\n--- [DRY-RUN] MORNING ALERT PREVIEW ---")
        print(message)
        print("---------------------------------------\n")
        return {"status": "dry_run", "count": len(eligible_ipos), "message": message}

    dispatch_results = dispatch_alert(message)
    return {
        "status": "dispatched",
        "count": len(eligible_ipos),
        "message": message,
        "results": dispatch_results
    }


def run_reminder_check(dry_run: bool = False) -> Dict:
    """
    Execute the 2:30 PM IST Reminder Workflow.
    Automatically checks for new Telegram subscribers and notifies admin every day.
    """
    logger.info("Executing 2:30 PM Reminder IPO Check...")

    # Check for newly joined users every day
    try:
        from subscriber_manager import sync_new_subscribers
        sync_new_subscribers(notify_admin=True)
    except Exception as e:
        logger.error(f"Error syncing subscribers in reminder check: {e}")

    eligible_ipos = get_eligible_ipos()

    if not eligible_ipos:
        logger.info(f"No Mainboard IPOs with GMP > {Config.GMP_THRESHOLD_PERCENT}% for reminder.")
        return {"status": "silent_empty", "count": 0, "message": None}

    message, has_urgent = format_reminder_alert(eligible_ipos)
    if not message:
        return {"status": "no_reminder_needed", "count": 0, "message": None}

    if dry_run:
        print("\n--- [DRY-RUN] 2:30 PM REMINDER PREVIEW ---")
        print(message)
        print("------------------------------------------\n")
        return {"status": "dry_run", "count": len(eligible_ipos), "message": message}

    dispatch_results = dispatch_alert(message)
    return {
        "status": "dispatched",
        "count": len(eligible_ipos),
        "message": message,
        "results": dispatch_results
    }
