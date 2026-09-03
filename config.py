"""
Configuration loader for IPO Tracker & GMP Alert System.
Reads settings from .env file with validation and smart defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

class Config:
    BASE_DIR = BASE_DIR
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"

    # Recipients
    _raw_phones = os.getenv("PHONE_NUMBERS", "")
    PHONE_NUMBERS = [p.strip() for p in _raw_phones.split(",") if p.strip()]

    # Threshold
    try:
        GMP_THRESHOLD_PERCENT = float(os.getenv("GMP_THRESHOLD_PERCENT", "10.0"))
    except ValueError:
        GMP_THRESHOLD_PERCENT = 10.0

    # Notification channels: comma-separated e.g. "console,fast2sms"
    _raw_channels = os.getenv("NOTIFICATION_CHANNELS", "console")
    NOTIFICATION_CHANNELS = [c.strip().lower() for c in _raw_channels.split(",") if c.strip()]

    # Fast2SMS
    FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY", "").strip()

    # Twilio
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
    TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886").strip()

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _raw_chat_ids = os.getenv("TELEGRAM_CHAT_IDS", "").strip()
    TELEGRAM_CHAT_IDS = [cid.strip() for cid in _raw_chat_ids.split(",") if cid.strip()]
    ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "2056597708").strip()

    # WhatsApp (CallMeBot & WhatsApp Web)
    CALLMEBOT_RECIPIENTS = os.getenv("CALLMEBOT_RECIPIENTS", "").strip()
    _raw_wa_phones = os.getenv("WHATSAPP_PHONE_NUMBERS", "").strip()
    WHATSAPP_PHONE_NUMBERS = [p.strip() for p in _raw_wa_phones.split(",") if p.strip()]

    # Schedule times (IST)
    MORNING_SCHEDULE_TIME = os.getenv("MORNING_SCHEDULE_TIME", "08:00").strip()
    REMINDER_SCHEDULE_TIME = os.getenv("REMINDER_SCHEDULE_TIME", "14:30").strip()
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata").strip()

    # Behavior
    SILENT_ON_EMPTY = os.getenv("SILENT_ON_EMPTY", "true").lower() in ("true", "1", "yes")

    # Referral / Demat account opening link
    ZERODHA_REFERRAL_URL = os.getenv("ZERODHA_REFERRAL_URL", "https://zerodha.com/open-account?c=LJ0070").strip()

# Ensure required directories exist
Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
Config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
