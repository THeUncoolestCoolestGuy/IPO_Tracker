"""
Tracker engine for filtering high-GMP IPOs and building alert messages.
Orchestrates the 8:00 AM IST Morning Alert, 12:30 PM IST Reminder Alert,
and 10:00 PM IST Nightly Allotment Check.
Prioritizes GMP > 15% at the top, and displays 10% - 15% at the end.
"""

import sys
import json
import logging
from datetime import datetime, timedelta
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

DISPATCH_STATE_FILE = Config.DATA_DIR / "dispatch_state.json"
LEGACY_DISPATCH_FILE = Config.DATA_DIR / "last_dispatch.json"


def get_classified_ipos(threshold: float = 10.0) -> Tuple[List[Dict], List[Dict]]:
    """
    Classify Mainboard IPOs into:
    1. active_ipos: currently Open or Closing Today (start_date <= today <= last_filing_date)
    2. upcoming_near_ipos: opening in the next 1-2 days (today < start_date <= today + 2 days)
    Both exclude closed issues and require GMP % >= threshold.
    """
    from scraper import get_all_mainboard_ipos, parse_date_str_to_date

    all_ipos = get_all_mainboard_ipos()
    today = datetime.now().date()
    near_future = today + timedelta(days=2)

    active_ipos = []
    upcoming_near_ipos = []

    for ipo in all_ipos:
        status = ipo.get("status", "").lower()
        if status == "closed":
            continue

        gmp_pct = ipo.get("gmp_percent", 0.0)
        if gmp_pct < threshold:
            continue

        last_dt = parse_date_str_to_date(ipo.get("last_filing_date", ""))
        start_dt = parse_date_str_to_date(ipo.get("start_date", ""))

        last_date = last_dt.date() if last_dt else None
        start_date = start_dt.date() if start_dt else None

        # Exclude past/closed IPOs
        if last_date and last_date < today:
            continue

        # Case 1: Closing today or currently open
        if ipo.get("closing_today") or status == "open" or (start_date and last_date and start_date <= today <= last_date):
            active_ipos.append(ipo)
        # Case 2: Opening within the next 1-2 days
        elif start_date and today < start_date <= near_future:
            upcoming_near_ipos.append(ipo)
        # Case 3: Start date TBA/unknown, but last date is valid and >= today
        elif not start_date and last_date and last_date >= today:
            if status == "open":
                active_ipos.append(ipo)
            elif status == "upcoming" and last_date <= near_future:
                upcoming_near_ipos.append(ipo)

    active_ipos.sort(key=lambda x: x.get("gmp_percent", 0.0), reverse=True)
    upcoming_near_ipos.sort(key=lambda x: x.get("gmp_percent", 0.0), reverse=True)
    return active_ipos, upcoming_near_ipos


def get_eligible_ipos(threshold: float = 10.0) -> List[Dict]:
    """
    Fetch Mainboard IPOs that are active or upcoming within 1-2 days.
    Provides backwards compatibility for CLI and external callers.
    """
    active, upcoming = get_classified_ipos(threshold=threshold)
    return active + upcoming


def format_ipo_dates(ipo: Dict) -> str:
    """
    Format IPO dates as 'opening date - closing date' (e.g. '15 Oct – 19 Oct').
    Falls back gracefully if only one date or a pre-formatted range is available.
    """
    start = ipo.get("start_date", "").strip()
    end = ipo.get("last_filing_date", "").strip()
    date_range = ipo.get("date_range", "").strip()

    if start and end and start.upper() != "TBA" and end.upper() != "TBA":
        if start.lower() == end.lower():
            return start
        return f"{start} – {end}"

    if date_range and date_range not in ("-", "TBA", ""):
        return date_range

    if end and end.upper() != "TBA":
        return f"Closes {end}"

    if start and start.upper() != "TBA":
        return f"Opens {start}"

    return "TBA"


def format_morning_alert(active_ipos: List[Dict], upcoming_ipos: Optional[List[Dict]] = None) -> str:
    """
    Format clean, spacious, visually appealing 8:00 AM IST Morning Alert.
    - If active IPOs exist: Shows Strong Conviction (GMP > 15%) first, Moderate (10%-15%) second.
    - If NO active IPOs: Explicitly states 'No Mainboard IPOs currently active or closing today.'
    - Under either case, displays upcoming IPOs opening in the next 1-2 days.
    """
    if upcoming_ipos is None:
        upcoming_ipos = []

    today_str = datetime.now().strftime("%d %b %Y")
    lines = [
        f"🔔 <b>MAINBOARD IPO ALERT</b> • {today_str}",
        ""
    ]

    strong_ipos = [ipo for ipo in active_ipos if ipo.get("gmp_percent", 0.0) >= 15.0]
    moderate_ipos = [ipo for ipo in active_ipos if 10.0 <= ipo.get("gmp_percent", 0.0) < 15.0]

    # Section 1: Active IPOs (or explicit "No active IPO" message)
    if active_ipos:
        if strong_ipos:
            lines.append("🔥 <b>STRONG CONVICTION (GMP &gt; 15%):</b>")
            lines.append("")
            for idx, ipo in enumerate(strong_ipos, 1):
                name = ipo['name']
                price = ipo['price_band']
                gmp_rs = f"₹{ipo['gmp_rs']:.0f}" if ipo['gmp_rs'].is_integer() else f"₹{ipo['gmp_rs']:.1f}"
                gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
                ipo_dates = format_ipo_dates(ipo)
                status = ipo['status'].upper()
                closing_note = "  ⚠️ <b>(CLOSES TODAY!)</b>" if ipo.get("closing_today") else ""

                lines.append(f"<b>{idx}. {name}</b>")
                lines.append(f"   • <b>GMP:</b> {gmp_rs} (<b>{gmp_pct}</b>) 🔥{closing_note}")
                lines.append(f"   • <b>Price:</b> {price}")
                lines.append(f"   • <b>IPO Date:</b> {ipo_dates}")
                lines.append(f"   • <b>Status:</b> {status}")
                lines.append("")

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
                ipo_dates = format_ipo_dates(ipo)
                lines.append(f"• <b>{name}</b>: GMP <b>{gmp_pct}</b> ({gmp_rs}) | Price: {price} | Date: {ipo_dates}{closing_note}")
            lines.append("")
    else:
        lines.append("ℹ️ <b>No Mainboard IPOs are currently active or closing today.</b>")
        lines.append("")

    # Section 2: Upcoming in next 1-2 days
    if upcoming_ipos:
        lines.append("────────────────────────")
        lines.append("📅 <b>UPCOMING (Opening in Next 1–2 Days):</b>")
        lines.append("")
        for idx, ipo in enumerate(upcoming_ipos, 1):
            name = ipo['name']
            price = ipo['price_band']
            gmp_rs = f"₹{ipo['gmp_rs']:.0f}" if ipo['gmp_rs'].is_integer() else f"₹{ipo['gmp_rs']:.1f}"
            gmp_pct = f"+{ipo['gmp_percent']:.1f}%"
            ipo_dates = format_ipo_dates(ipo)
            fire = " 🔥" if ipo.get("gmp_percent", 0.0) >= 15.0 else ""

            lines.append(f"<b>{idx}. {name}</b>")
            lines.append(f"   • <b>GMP:</b> {gmp_rs} (<b>{gmp_pct}</b>){fire}")
            lines.append(f"   • <b>Price Band:</b> {price}")
            lines.append(f"   • <b>IPO Date:</b> {ipo_dates}")
            lines.append("")
    elif not active_ipos:
        lines.append("────────────────────────")
        lines.append("📅 <i>No new Mainboard IPOs scheduled to open in the next 1–2 days.</i>")
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
    Prioritizes IPOs closing TODAY or currently OPEN.
    Returns (message_text, has_urgent_closing_today).
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
            ipo_dates = format_ipo_dates(ipo)
            lines.append(f"<b>• {name}</b>")
            lines.append(f"   • <b>GMP:</b> {gmp_rs} (<b>{gmp_pct}</b>) 🔥")
            lines.append(f"   • <b>Price Band:</b> {ipo['price_band']}")
            lines.append(f"   • <b>IPO Date:</b> {ipo_dates}")
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
                ipo_dates = format_ipo_dates(ipo)
                lines.append(f"<b>• {name}</b>")
                lines.append(f"   • <b>GMP:</b> {gmp_pct}")
                lines.append(f"   • <b>IPO Date:</b> {ipo_dates}")
                lines.append("")

        if moderate_open:
            lines.append("📊 <b>Moderate GMP OPEN (10% – 15%):</b>")
            lines.append("")
            for ipo in moderate_open:
                ipo_dates = format_ipo_dates(ipo)
                lines.append(f"• <b>{ipo['name']}</b>: GMP <b>+{ipo['gmp_percent']:.1f}%</b> | Date: {ipo_dates}")
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

    return "", False


def _record_dispatch(dispatch_type: str):
    """Record the date of the successful dispatch in dispatch_state.json to prevent duplicate alerts."""
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
        today_str = datetime.now().strftime("%Y-%m-%d")
        if DISPATCH_STATE_FILE.exists():
            with open(DISPATCH_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get(dispatch_type) == today_str:
                return True
        if LEGACY_DISPATCH_FILE.exists():
            with open(LEGACY_DISPATCH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get(dispatch_type) == today_str:
                return True
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

    active_ipos, upcoming_ipos = get_classified_ipos(threshold=10.0)
    total_qualifying = len(active_ipos) + len(upcoming_ipos)

    message = format_morning_alert(active_ipos, upcoming_ipos)

    if dry_run:
        print("\n--- [DRY-RUN] MORNING ALERT PREVIEW ---")
        print(message)
        print("---------------------------------------\n")
        return {"status": "dry_run", "count": total_qualifying, "message": message}

    dispatch_results = dispatch_alert(message)
    _record_dispatch("morning")

    return {
        "status": "dispatched",
        "count": total_qualifying,
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

    active_ipos, _ = get_classified_ipos(threshold=10.0)

    if not active_ipos:
        logger.info("No active Mainboard IPOs for 12:30 PM reminder.")
        return {"status": "no_reminder_needed", "count": 0, "message": None}

    message, has_urgent = format_reminder_alert(active_ipos)
    if not message:
        return {"status": "no_reminder_needed", "count": 0, "message": None}

    if dry_run:
        print("\n--- [DRY-RUN] 12:30 PM REMINDER PREVIEW ---")
        print(message)
        print("------------------------------------------\n")
        return {"status": "dry_run", "count": len(active_ipos), "message": message}

    dispatch_results = dispatch_alert(message)
    _record_dispatch("reminder")

    return {
        "status": "dispatched",
        "count": len(active_ipos),
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
