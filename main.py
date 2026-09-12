"""
Main entry point and CLI for Indian Mainboard IPO Tracker & GMP Alert System.
"""

import sys
import argparse
import logging
from config import Config
from scraper import get_all_mainboard_ipos
from tracker import run_morning_check, run_reminder_check, run_allotment_check
from scheduler import start_scheduler_daemon
from notifiers import dispatch_alert
from notifiers.base import strip_html

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ipo_tracker.main")


def print_banner():
    banner = r"""
  ___ ____   ___    _____              _             
 |_ _|  _ \ / _ \  |_   _| __ __ _  ___| | _____ _ __ 
  | || |_) | | | |   | || '__/ _` |/ __| |/ / _ \ '__|
  | ||  __/| |_| |   | || | | (_| | (__|   <  __/ |   
 |___|_|    \___/    |_||_|  \__,_|\___|_|\_\___|_|   
    """
    print(banner)
    print(" Indian Mainboard IPO & GMP Alert System (NSE / BSE)")
    print(f" Target Numbers:   {', '.join(Config.PHONE_NUMBERS)}")
    if Config.WHATSAPP_PHONE_NUMBERS:
        print(f" WhatsApp Targets: {', '.join(Config.WHATSAPP_PHONE_NUMBERS)} (Chirag & Mita Paunwala only)")
    print(f" GMP Threshold:    > {Config.GMP_THRESHOLD_PERCENT}%")
    print(f" Schedules:        08:00 AM, 12:30 PM & 10:00 PM IST")
    print(f" Channels:         {', '.join(Config.NOTIFICATION_CHANNELS)}")
    print("=" * 65 + "\n")


def list_current_ipos():
    """Display all current Mainboard IPOs in a formatted table."""
    print("🔍 Fetching live Mainboard IPOs from NSE/BSE sources...\n")
    ipos = get_all_mainboard_ipos()
    if not ipos:
        print("❌ No IPOs found or network error.")
        return

    print(f"Found {len(ipos)} Mainboard IPO(s):\n")
    header = f"{'#':<3} | {'IPO Name':<26} | {'Price Band':<10} | {'GMP (₹)':<8} | {'GMP %':<8} | {'Filing Date':<12} | {'Status'}"
    print(header)
    print("-" * len(header))

    for idx, ipo in enumerate(ipos, 1):
        gmp_highlight = "🔥" if ipo['gmp_percent'] >= Config.GMP_THRESHOLD_PERCENT else "  "
        closing_mark = "⚠️" if ipo.get("closing_today") else "  "
        print(f"{idx:<3} | {ipo['name'][:25]:<26} | {ipo['price_band']:<10} | ₹{ipo['gmp_rs']:<7.1f} | {ipo['gmp_percent']:>5.2f}% {gmp_highlight} | {ipo['last_filing_date']:<10} {closing_mark} | {ipo['status']}")

    print("\nLegend: 🔥 = GMP exceeds threshold (>15%) | ⚠️ = Closes today\n")


def test_notification():
    """Send a test message to verify notification configuration."""
    print("📲 Sending Test Notification across configured channels...")
    test_msg = (
        "✅ <b>IPO Tracker Test Alert:</b>\n\n"
        "Your IPO alert service is connected successfully!\n"
        "You will receive daily updates:\n"
        "• <b>08:00 AM:</b> Morning Alert (GMP > 15%)\n"
        "• <b>12:30 PM:</b> Reminder Alert (IPOs closing today)\n"
        "• <b>10:00 PM:</b> Nightly Allotment Declaration Alert"
    )
    results = dispatch_alert(test_msg)
    print("\nDispatch Results:")
    for res in results:
        status_symbol = "✅" if res.get("success") else "❌"
        print(f"  {status_symbol} Channel [{res['channel']}]: {res}")


def main():
    parser = argparse.ArgumentParser(description="Indian Mainboard IPO & GMP Alert System")
    parser.add_argument("--run-now", action="store_true", help="Run the 8:00 AM Morning Check immediately")
    parser.add_argument("--run-reminder", action="store_true", help="Run the 12:30 PM Reminder Check immediately")
    parser.add_argument("--dry-run", action="store_true", help="Preview alert message without sending paid SMS")
    parser.add_argument("--daemon", action="store_true", help="Start the continuous background scheduler daemon (IST)")
    parser.add_argument("--list", action="store_true", help="List all current Mainboard IPOs and their GMP")
    parser.add_argument("--test-notification", action="store_true", help="Send a test message to configured channels")
    parser.add_argument("--subscribers", action="store_true", help="Check for newly joined Telegram users and list active subscribers")
    parser.add_argument("--check-allotment", action="store_true", help="Scan registrars for newly declared IPO allotments (10:00 PM Nightly)")
    parser.add_argument("--check-pan", action="store_true", help="Check allotment status for specific PAN(s)")
    parser.add_argument("--pans", type=str, default="", help="Comma-separated PAN numbers for --check-pan (e.g. ABCDE1234F,BCDEF2345G)")
    parser.add_argument("--company", type=str, default=None, help="Company name or ID for --check-pan")
    parser.add_argument("--sync-messages", action="store_true", help="Process pending Telegram commands and user messages")
    parser.add_argument("--skip-if-already-dispatched", action="store_true", help="Skip if today's alert was already dispatched")

    args = parser.parse_args()

    print_banner()

    if args.subscribers:
        print("▶ Checking for new Telegram subscribers and user updates...")
        from subscriber_manager import process_incoming_telegram_updates, load_subscribers_registry
        new_users = process_incoming_telegram_updates(notify_admin=True)
        if new_users:
            print(f"🎉 Detected {len(new_users)} new user(s) and notified Admin!")
            for u in new_users:
                print(f"  + Added: {u['name']} (Chat ID: {u['id']})")
        else:
            print("No new subscribers detected.")

        registry = load_subscribers_registry()
        print(f"\n📋 Currently Enrolled Subscribers ({len(registry)}):")
        for cid, info in registry.items():
            role_tag = f"[{info.get('role', 'member').upper()}]"
            pan_count = len(info.get("pans", []))
            pan_str = f"({pan_count} saved PANs)" if pan_count > 0 else "(no PANs saved)"
            status_tag = f" [{info.get('status').upper()}]" if info.get('status') else ""
            print(f"  • {info.get('name', 'Unknown')} (ID: {cid}) {role_tag} {pan_str}{status_tag}")
        print()

    elif args.sync_messages:
        print("▶ Processing incoming Telegram commands and messages...")
        from subscriber_manager import process_incoming_telegram_updates
        new_users = process_incoming_telegram_updates(notify_admin=True)
        print("✅ Telegram sync completed.")

    elif args.check_pan:
        from pan_checker import extract_pans, batch_check_pans, format_allotment_report
        pan_list = extract_pans(args.pans) if args.pans else []
        if not pan_list:
            print("❌ No valid PAN numbers specified. Use --pans ABCDE1234F,BCDEF2345G")
            return

        print(f"▶ Checking {len(pan_list)} PAN(s) for company: {args.company or 'Latest KFintech IPO'}...")
        res = batch_check_pans(args.company, pan_list)
        report = format_allotment_report(res)
        print("\n" + strip_html(report) + "\n")

    elif args.check_allotment:
        print("▶ Executing 10:00 PM Nightly IPO Allotment Check across registrars...")
        res = run_allotment_check(dry_run=args.dry_run)
        print(f"Completed with status: {res['status']} (New allotments: {res.get('new_allotments', [])})")

    elif args.run_now:
        print("▶ Executing Morning 8:00 AM IPO Check...")
        res = run_morning_check(dry_run=args.dry_run, skip_if_already_dispatched=args.skip_if_already_dispatched)
        print(f"Completed with status: {res['status']} (Found {res['count']} qualifying IPOs)")

    elif args.run_reminder:
        print("▶ Executing Reminder 12:30 PM IPO Check...")
        res = run_reminder_check(dry_run=args.dry_run, skip_if_already_dispatched=args.skip_if_already_dispatched)
        print(f"Completed with status: {res['status']} (Found {res['count']} qualifying IPOs)")

    elif args.daemon:
        print("▶ Starting background scheduler daemon...")
        start_scheduler_daemon()

    elif args.test_notification:
        test_notification()

    elif args.list:
        list_current_ipos()

    else:
        list_current_ipos()
        print("Quick Commands:")
        print("  python main.py --run-now --dry-run      : Test morning alert without sending SMS")
        print("  python main.py --run-reminder --dry-run : Test 12:30 PM reminder without sending SMS")
        print("  python main.py --check-allotment        : Scan registrars for newly declared IPO allotments (10:00 PM)")
        print("  python main.py --check-pan --pans <PANS>: Check allotment status for single/multiple PANs")
        print("  python main.py --sync-messages          : Process pending Telegram user commands (/pan, /check)")
        print("  python main.py --run-now                : Run live morning alert (sends messages)")
        print("  python main.py --daemon                 : Keep running in background on this PC")
        print("  python main.py --test-notification      : Test your notification channels\n")


if __name__ == "__main__":
    main()
