"""
Main entry point and CLI for Indian Mainboard IPO Tracker & GMP Alert System.
"""

import sys
import argparse
import logging
from config import Config
from scraper import get_all_mainboard_ipos
from tracker import run_morning_check, run_reminder_check
from scheduler import start_scheduler_daemon
from notifiers import dispatch_alert

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
    print(f" GMP Threshold:    > {Config.GMP_THRESHOLD_PERCENT}%")
    print(f" Schedules:        08:00 AM & 12:30 PM IST")
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

    print("\nLegend: 🔥 = GMP exceeds threshold (>10%) | ⚠️ = Closes today\n")


def test_notification():
    """Send a test message to verify notification configuration."""
    print("📲 Sending Test Notification across configured channels...")
    test_msg = (
        "✅ IPO Tracker Test Alert:\n"
        "Your IPO alert service is connected successfully!\n"
        "You will receive daily updates at 8:00 AM and 12:30 PM IST when Mainboard IPO GMP > 10%."
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

    args = parser.parse_args()

    print_banner()

    if args.run_now:
        print("▶ Executing Morning 8:00 AM IPO Check...")
        res = run_morning_check(dry_run=args.dry_run)
        print(f"Completed with status: {res['status']} (Found {res['count']} qualifying IPOs)")

    elif args.run_reminder:
        print("▶ Executing Reminder 12:30 PM IPO Check...")
        res = run_reminder_check(dry_run=args.dry_run)
        print(f"Completed with status: {res['status']} (Found {res['count']} qualifying IPOs)")

    elif args.daemon:
        print("▶ Starting background scheduler daemon...")
        start_scheduler_daemon()

    elif args.test_notification:
        test_notification()

    elif args.list:
        list_current_ipos()

    else:
        # Default: list current IPOs and show helpful usage instructions
        list_current_ipos()
        print("Quick Commands:")
        print("  python main.py --run-now --dry-run      : Test morning alert without sending SMS")
        print("  python main.py --run-reminder --dry-run : Test 12:30 PM reminder without sending SMS")
        print("  python main.py --run-now                : Run live morning alert (sends SMS/messages)")
        print("  python main.py --daemon                 : Keep running in background on this PC")
        print("  python main.py --test-notification      : Test your SMS / WhatsApp / Telegram setup\n")


if __name__ == "__main__":
    main()
