"""
Scheduler daemon for IPO Tracker & GMP Alert System.
Runs continuously in background and triggers:
  - 8:00 AM IST: Morning Check
  - 12:30 PM IST: Reminder Check
"""

import sys
import time
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from tzlocal import get_localzone as ZoneInfo

from config import Config
from tracker import run_morning_check, run_reminder_check

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Config.LOGS_DIR / "scheduler.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("ipo_tracker.scheduler")


def parse_time_hh_mm(time_str: str) -> tuple[int, int]:
    """Parse '08:00' or '12:30' into (hour, minute)."""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


def start_scheduler_daemon():
    """Start blocking APScheduler loop in IST timezone."""
    tz_str = Config.TIMEZONE or "Asia/Kolkata"
    try:
        ist_tz = ZoneInfo(tz_str)
    except Exception:
        ist_tz = "Asia/Kolkata"

    m_hour, m_minute = parse_time_hh_mm(Config.MORNING_SCHEDULE_TIME)
    r_hour, r_minute = parse_time_hh_mm(Config.REMINDER_SCHEDULE_TIME)

    scheduler = BlockingScheduler(timezone=ist_tz)

    # 8:00 AM IST Job
    scheduler.add_job(
        run_morning_check,
        CronTrigger(hour=m_hour, minute=m_minute, timezone=ist_tz),
        id="morning_check",
        name=f"Morning Check at {Config.MORNING_SCHEDULE_TIME} IST",
        misfire_grace_time=3600
    )

    # 12:30 PM IST Job
    scheduler.add_job(
        run_reminder_check,
        CronTrigger(hour=r_hour, minute=r_minute, timezone=ist_tz),
        id="reminder_check",
        name=f"Reminder Check at {Config.REMINDER_SCHEDULE_TIME} IST",
        misfire_grace_time=3600
    )

    print("=" * 65)
    print("🚀 IPO TRACKER SCHEDULER DAEMON STARTED")
    print(f"Timezone:           {tz_str}")
    print(f"Morning Check:      Daily at {Config.MORNING_SCHEDULE_TIME} IST")
    print(f"Reminder Check:     Daily at {Config.REMINDER_SCHEDULE_TIME} IST")
    print(f"GMP Threshold:      > {Config.GMP_THRESHOLD_PERCENT}%")
    print(f"Active Channels:    {', '.join(Config.NOTIFICATION_CHANNELS)}")
    print(f"Recipients:         {', '.join(Config.PHONE_NUMBERS)}")
    print("=" * 65)
    print("Press Ctrl+C to exit.\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler daemon stopped by user.")


if __name__ == "__main__":
    start_scheduler_daemon()
