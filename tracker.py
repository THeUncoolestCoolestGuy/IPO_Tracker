"""
Tracker engine for filtering high-GMP IPOs and building alert messages.
Orchestrates the 8:00 AM IST Morning Alert, 12:30 PM IST Reminder Alert,
and 10:00 PM IST Nightly Allotment Check.
Prioritizes GMP > 15% at the top, and displays 10% - 15% at the end.
"""

import sys
import json
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
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
    "Groww": "https://play.google.com/store/apps/details?id=com.nextbillion.groww",
    "Sharekhan": "https://play.google.com/store/apps/details?id=com.sharekhan.androidsharemobile"
}

DISPATCH_STATE_FILE = Config.DATA_DIR / "last_dispatch.json"


def get_eligible_ipos(threshold: float = 10.0) -> List[Dict]:
    """
    Fetch Mainboard IPOs and filter for:
    - Status is NOT 'Closed' (Open or Upcoming)
    - GMP % >= threshold (default 10.0% to capture both strong and moderate IPOs)
    Sorted by GMP % descending.
    """
    all_ipos = get_all_mainboard_ipos()
    eligible = []

    for ipo in all_ipos:
        status = ipo.get("status", "").lower()
        if status == "closed":
            continue

        gmp_pct = ipo.get("gmp_percent", 0.0)
        if gmp_pct >= threshold:
            eligible.append(ipo)

    eligible.sort(key=lambda x: x.get("gmp_percent", 0.0), reverse=True)
    return eligible


def format_morning_alert(ipos: List[Dict]) -> str:
    """
    Format clean, spacious, visually appealing 8:00 AM IST Morning Alert.
    Highlights GMP > 15% first with full details, followed by 10% - 15% at the end.
    """
    today_str = datetime.now().strftime("%d %b %Y")
    
    strong_ipos = [ipo for ipo in ipos if ipo.get("gmp_percent", 0.0) >= 15.0]
    moderate_ipos = [ipo for ipo in ipos if 10.0 <= ipo.get("gmp_percent", 0.0) < 15.0]

    lines = [
        f"🔔 <b>MAINBOARD IPO ALERT</b> • {today_str}",
        ""
    ]

    # Section 1: Strong GMP (>15%) shown first
    if strong_ipos:
        lines.append(f"🔥 <b>STRONG CONVICTION (GMP &gt; 15%):</b>")
        lines.append("")
        for idx, ipo in enumerate(strong_ipos, 1):
            name = ipo['name']
            price = ipo['price_band']
            gmp_rs = f"₹{ipo['gmp_rs']:.0f}" if ipo['gmp_rs'].is_integer() else f"₹{ipo['gmp_rs']:.1f}"
            gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
            last_date = ipo['last_filing_date']
            status = ipo['status'].upper()

            closing_note = "  ⚠️ <b>(CLOSES TODAY!)</b>" if ipo.get("closing_today") else ""

            lines.append(f"<b>{idx}. {name}</b>")
            lines.append(f"   • <b>GMP:</b> {gmp_rs} (<b>{gmp_pct}</b>) 🔥{closing_note}")
            lines.append(f"   • <b>Price:</b> {price}")
            lines.append(f"   • <b>Last Filing:</b> {last_date}")
            lines.append(f"   • <b>Status:</b> {status}")
            lines.append("")
    else:
        lines.append("ℹ️ <i>No Mainboard IPOs currently exceed 15% GMP.</i>")
        lines.append("")

    # Section 2: Moderate GMP (10% - 15%) shown last!
    if moderate_ipos:
        lines.append("────────────────────────")
        lines.append("📊 <b>MODERATE GMP (10% – 15%):</b>")
        lines.append("")
        for ipo in moderate_ipos:
            name = ipo['name']
            price = ipo['price_band']
            gmp_rs = f"₹{ipo['gmp_rs']:.0f}" if ipo['gmp_rs'].is_integer() else f"₹{ipo['gmp_rs']:.1f}"
            gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
            closing_note = " ⚠️ <b>(CLOSES TODAY!)</b>" if ipo.get("closing_today") else ""
            lines.append(f"• <b>{name}</b>: GMP <b>{gmp_pct}</b> ({gmp_rs}) | Price: {price}{closing_note}")
        lines.append("")

    lines.append("────────────────────────")
    lines.append("📲 <b>1-Click Apply:</b>")
    lines.append(
        f'<a href="{BROKER_APP_LINKS["Kite"]}">Kite</a>  •  '
        f'<a href="{BROKER_APP_LINKS["Upstox"]}">Upstox</a>  •  '
        f'<a href="{BROKER_APP_LINKS["Groww"]}">Groww</a>  •  '
        f'<a href="{BROKER_APP_LINKS["Sharekhan"]}">Sharekhan</a>'
    )
    lines.append("")
    lines.append("🎁 <b>Open Free Demat Account:</b>")
    lines.append(f'• <a href="{Config.ZERODHA_REFERRAL_URL}">Zerodha Kite</a>')
    lines.append(f'• <a href="{Config.UPSTOX_REFERRAL_URL}">Upstox</a> (Zero AMC)')
    lines.append(f'• <a href="{Config.GROWW_REFERRAL_URL}">Groww</a> (Code: <code>{Config.GROWW_REFERRAL_CODE}</code>)')
    return "\n".join(lines).strip()


def format_reminder_alert(ipos: List[Dict]) -> Tuple[str, bool]:
    """
    Format clean, spacious 12:30 PM IST Reminder Alert.
    Prioritizes IPOs closing TODAY or currently OPEN, with 10%-15% listed in secondary section.
    """
    today_str = datetime.now().strftime("%d %b %Y")
    closing_today = [ipo for ipo in ipos if ipo.get("closing_today")]
    currently_open = [ipo for ipo in ipos if ipo.get("status", "").lower() == "open"]

    lines = [
        f"⚠️ <b>IPO REMINDER ALERT</b> • {today_str}",
        ""
    ]

    if closing_today:
        lines.append("🚨 <b>CLOSING TODAY (Last Chance to Apply!):</b>")
        lines.append("")
        for ipo in closing_today:
            name = ipo['name']
            gmp_rs = f"₹{ipo['gmp_rs']:.0f}" if ipo['gmp_rs'].is_integer() else f"₹{ipo['gmp_rs']:.1f}"
            gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
            lines.append(f"<b>• {name}</b>")
            lines.append(f"   • <b>GMP:</b> {gmp_rs} (<b>{gmp_pct}</b>) 🔥")
            lines.append(f"   • <b>Price Band:</b> {ipo['price_band']}")
            lines.append("   • <b>Cut-off:</b> TODAY at 5:00 PM IST")
            lines.append("")

        lines.append("⏰ <i>Submit your ASBA / UPI bid before 5:00 PM IST today!</i>")
        lines.append("")
        lines.append("────────────────────────")
        lines.append("📲 <b>1-Click Apply:</b>")
        lines.append(
            f'<a href="{BROKER_APP_LINKS["Kite"]}">Kite</a>  •  '
            f'<a href="{BROKER_APP_LINKS["Upstox"]}">Upstox</a>  •  '
            f'<a href="{BROKER_APP_LINKS["Groww"]}">Groww</a>  •  '
            f'<a href="{BROKER_APP_LINKS["Sharekhan"]}">Sharekhan</a>'
        )
        lines.append("")
        lines.append("🎁 <b>Open Demat Account:</b>")
        lines.append(
            f'• <a href="{Config.ZERODHA_REFERRAL_URL}">Zerodha Kite</a>  •  '
            f'<a href="{Config.UPSTOX_REFERRAL_URL}">Upstox</a>  •  '
            f'<a href="{Config.GROWW_REFERRAL_URL}">Groww</a>'
        )
        return "\n".join(lines).strip(), True

    elif currently_open:
        strong_open = [ipo for ipo in currently_open if ipo.get("gmp_percent", 0.0) >= 15.0]
        moderate_open = [ipo for ipo in currently_open if 10.0 <= ipo.get("gmp_percent", 0.0) < 15.0]

        if strong_open:
            lines.append("🔥 <b>Active Mainboard IPOs OPEN (GMP &gt; 15%):</b>")
            lines.append("")
            for ipo in strong_open:
                name = ipo['name']
                gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
                lines.append(f"<b>• {name}</b>")
                lines.append(f"   • <b>GMP:</b> {gmp_pct}")
                lines.append(f"   • <b>Last Filing Date:</b> {ipo['last_filing_date']}")
                lines.append("")

        if moderate_open:
            lines.append("📊 <b>Moderate GMP OPEN (10% – 15%):</b>")
            lines.append("")
            for ipo in moderate_open:
                lines.append(f"• <b>{ipo['name']}</b>: GMP <b>+{ipo['gmp_percent']:.1f}%</b> | Closes: {ipo['last_filing_date']}")
            lines.append("")

        lines.append("────────────────────────")
        lines.append("📲 <b>1-Click Apply:</b>")
        lines.append(
            f'<a href="{BROKER_APP_LINKS["Kite"]}">Kite</a>  •  '
            f'<a href="{BROKER_APP_LINKS["Upstox"]}">Upstox</a>  •  '
            f'<a href="{BROKER_APP_LINKS["Groww"]}">Groww</a>  •  '
            f'<a href="{BROKER_APP_LINKS["Sharekhan"]}">Sharekhan</a>'
        )
        lines.append("")
        lines.append("🎁 <b>Open Demat Account:</b>")
        lines.append(
            f'• <a href="{Config.ZERODHA_REFERRAL_URL}">Zerodha Kite</a>  •  '
            f'<a href="{Config.UPSTOX_REFERRAL_URL}">Upstox</a>  •  '
            f'<a href="{Config.GROWW_REFERRAL_URL}">Groww</a>'
        )
        return "\n".join(lines).strip(), False

    elif ipos:
        lines.append("📋 <b>Upcoming High-GMP Mainboard IPOs:</b>")
        lines.append("")
        for ipo in ipos:
            lines.append(f"<b>• {ipo['name']}</b>")
            lines.append(f"   • <b>GMP:</b> +{ipo['gmp_percent']:.1f}%")
            lines.append(f"   • <b>Opens:</b> {ipo['start_date']} | <b>Closes:</b> {ipo['last_filing_date']}")
            lines.append("")

        lines.append("────────────────────────")
        lines.append("🎁 <b>Open Free Demat Account:</b>")
        lines.append(
            f'• <a href="{Config.ZERODHA_REFERRAL_URL}">Zerodha Kite</a>  •  '
            f'<a href="{Config.UPSTOX_REFERRAL_URL}">Upstox</a>  •  '
            f'<a href="{Config.GROWW_REFERRAL_URL}">Groww</a>'
        )
        return "\n".join(lines).strip(), False

    return "", False


def _record_dispatch(dispatch_type: str):
    """Record the date of the successful dispatch to prevent duplicate alerts."""
    try:
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {}
        if DISPATCH_STATE_FILE.exists():
            try:
                with open(DISPATCH_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        today_str = datetime.now().strftime("%Y-%m-%d")
        data[dispatch_type] = today_str
        with open(DISPATCH_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.debug(f"Could not record dispatch state: {e}")


def has_dispatched_today(dispatch_type: str) -> bool:
    """Check if an alert of this type has already been dispatched today."""
    try:
        if DISPATCH_STATE_FILE.exists():
            with open(DISPATCH_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            today_str = datetime.now().strftime("%Y-%m-%d")
            return data.get(dispatch_type) == today_str
    except Exception:
        pass
    return False


def run_morning_check(dry_run: bool = False, skip_if_already_dispatched: bool = False) -> Dict:
    """
    Execute the 8:00 AM IST Morning Workflow.
    Syncs Telegram subscribers and checks for newly declared IPO allotments.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    if skip_if_already_dispatched and has_dispatched_today("morning"):
        logger.info(f"Morning alert for today ({today_str}) has already been sent. Suppressing duplicate run.")
        return {"status": "skipped_duplicate", "count": 0, "message": "Already dispatched today"}

    logger.info("Executing 8:00 AM Morning IPO Check...")

    try:
        from subscriber_manager import process_incoming_telegram_updates
        process_incoming_telegram_updates()
    except Exception as e:
        logger.error(f"Error processing Telegram updates in morning check: {e}")

    try:
        from allotment_tracker import check_and_notify_new_allotments
        check_and_notify_new_allotments(dry_run=dry_run)
    except Exception as e:
        logger.error(f"Error checking allotments in morning check: {e}")

    eligible_ipos = get_eligible_ipos(threshold=10.0)

    if not eligible_ipos:
        logger.info("No Mainboard IPOs found with GMP >= 10.0%.")
        if not Config.SILENT_ON_EMPTY:
            msg = "ℹ️ [8:00 AM] IPO Update: No Mainboard IPOs currently meet the 10% GMP criteria today."
            if not dry_run:
                dispatch_alert(msg)
                _record_dispatch("morning")
            return {"status": "silent_empty", "count": 0, "message": msg}
        return {"status": "silent_empty", "count": 0, "message": None}

    message = format_morning_alert(eligible_ipos)

    if dry_run:
        print("\n--- [DRY-RUN] MORNING ALERT PREVIEW ---")
        print(message)
        print("---------------------------------------\n")
        return {"status": "dry_run", "count": len(eligible_ipos), "message": message}

    dispatch_results = dispatch_alert(message)
    _record_dispatch("morning")

    return {
        "status": "dispatched",
        "count": len(eligible_ipos),
        "message": message,
        "results": dispatch_results
    }


def run_reminder_check(dry_run: bool = False, skip_if_already_dispatched: bool = False) -> Dict:
    """
    Execute the 12:30 PM IST Reminder Workflow.
    Syncs Telegram subscribers and checks for newly declared IPO allotments.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    if skip_if_already_dispatched and has_dispatched_today("reminder"):
        logger.info(f"Reminder alert for today ({today_str}) has already been sent. Suppressing duplicate run.")
        return {"status": "skipped_duplicate", "count": 0, "message": "Already dispatched today"}

    logger.info("Executing 12:30 PM Reminder IPO Check...")

    try:
        from subscriber_manager import process_incoming_telegram_updates
        process_incoming_telegram_updates()
    except Exception as e:
        logger.error(f"Error processing Telegram updates in reminder check: {e}")

    try:
        from allotment_tracker import check_and_notify_new_allotments
        check_and_notify_new_allotments(dry_run=dry_run)
    except Exception as e:
        logger.error(f"Error checking allotments in reminder check: {e}")

    eligible_ipos = get_eligible_ipos(threshold=10.0)

    if not eligible_ipos:
        logger.info("No Mainboard IPOs with GMP >= 10.0% for reminder.")
        return {"status": "silent_empty", "count": 0, "message": None}

    message, has_urgent = format_reminder_alert(eligible_ipos)
    if not message:
        return {"status": "no_reminder_needed", "count": 0, "message": None}

    if dry_run:
        print("\n--- [DRY-RUN] 12:30 PM REMINDER PREVIEW ---")
        print(message)
        print("------------------------------------------\n")
        return {"status": "dry_run", "count": len(eligible_ipos), "message": message}

    dispatch_results = dispatch_alert(message)
    _record_dispatch("reminder")

    return {
        "status": "dispatched",
        "count": len(eligible_ipos),
        "message": message,
        "results": dispatch_results
    }


def run_allotment_check(dry_run: bool = False, force: bool = False) -> Dict:
    """
    Dedicated 10:00 PM IST Nightly IPO Allotment Check.
    1. Processes any pending Telegram user commands (/pan, /check).
    2. Scans Link Intime, KFintech, and Bigshare for new allotments.
    3. Auto-checks registered subscriber PANs for captcha-free registrars.
    """
    logger.info("Executing 10:00 PM Nightly IPO Allotment Check...")
    try:
        from subscriber_manager import process_incoming_telegram_updates
        process_incoming_telegram_updates()
    except Exception as e:
        logger.error(f"Error syncing Telegram messages before allotment check: {e}")

    admin_report_res = {}
    try:
        from subscriber_manager import send_daily_admin_subscriber_report
        admin_report_res = send_daily_admin_subscriber_report(dry_run=dry_run, force=force)
    except Exception as e:
        logger.error(f"Error sending daily admin subscriber report: {e}")

    from allotment_tracker import check_and_notify_new_allotments
    allotment_res = check_and_notify_new_allotments(dry_run=dry_run, force_check=force)
    allotment_res["admin_report"] = admin_report_res
    return allotment_res
