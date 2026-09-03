"""
Interactive Setup Assistant for WhatsApp Notifications.
Supports:
  1. CallMeBot API (Free, 24/7 Cloud & Local)
  2. Local WhatsApp Web Automation (pywhatkit)
"""

import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)


def update_env_file(updates: dict):
    lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    keys_updated = set()
    new_lines = []

    for line in lines:
        matched = False
        for k, v in updates.items():
            if re.match(rf"^\s*{re.escape(k)}\s*=", line):
                new_lines.append(f"{k}={v}\n")
                keys_updated.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for k, v in updates.items():
        if k not in keys_updated:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def setup_callmebot():
    print("\n=======================================================")
    print("  Option 1: CallMeBot WhatsApp (Free 24/7 Cloud)")
    print("=======================================================")
    print("Each recipient needs to do this 1-time 15-second setup:\n")
    print("1. Save the CallMeBot phone number in your contacts:")
    print("   👉 Phone: +34 644 71 82 39  (or +34 644 20 82 39)")
    print("2. Open WhatsApp and send this exact message to that number:")
    print("   👉 I allow callmebot to send me messages")
    print("3. CallMeBot will instantly reply with your personal API Key!\n")

    recipients = []
    while True:
        phone = input("Enter recipient phone number with country code (e.g. +919876543210) [Enter to finish]: ").strip()
        if not phone:
            break
        apikey = input(f"Enter the CallMeBot API key for {phone}: ").strip()
        if apikey:
            recipients.append(f"{phone}:{apikey}")
            print(f"✅ Added {phone}!")

    if recipients:
        current_channels = os.getenv("NOTIFICATION_CHANNELS", "console,telegram").split(",")
        if "callmebot" not in current_channels:
            current_channels.append("callmebot")
        channels_str = ",".join([c.strip() for c in current_channels if c.strip()])

        recipients_str = ",".join(recipients)
        update_env_file({
            "CALLMEBOT_RECIPIENTS": recipients_str,
            "NOTIFICATION_CHANNELS": channels_str
        })
        print(f"\n🎉 Saved! NOTIFICATION_CHANNELS set to: {channels_str}")
        print(f"CALLMEBOT_RECIPIENTS set to: {recipients_str}")


def setup_whatsapp_web():
    print("\n=======================================================")
    print("  Option 2: WhatsApp Web Automation (Local PC)")
    print("=======================================================")
    print("This opens your personal WhatsApp Web in Chrome to send alerts.\n")

    current_phones = os.getenv("WHATSAPP_PHONE_NUMBERS", "")
    if current_phones:
        print(f"Current phone numbers: {current_phones}")
    new_phones = input(f"Enter comma-separated phone numbers with +91 (Press Enter to keep current): ").strip()
    if not new_phones:
        new_phones = current_phones

    current_channels = os.getenv("NOTIFICATION_CHANNELS", "console,telegram").split(",")
    if "whatsapp_web" not in current_channels:
        current_channels.append("whatsapp_web")
    channels_str = ",".join([c.strip() for c in current_channels if c.strip()])

    update_env_file({
        "WHATSAPP_PHONE_NUMBERS": new_phones,
        "NOTIFICATION_CHANNELS": channels_str
    })
    print(f"\n🎉 Saved! NOTIFICATION_CHANNELS set to: {channels_str}")
    print(f"WHATSAPP_PHONE_NUMBERS set to: {new_phones}")


def main():
    print("\n=======================================================")
    print(" 🚀 WhatsApp Notification Setup Assistant")
    print("=======================================================")
    print("Choose your preferred WhatsApp notification method:")
    print(" 1. CallMeBot API (100% Free, runs 24/7 in Cloud & Local)")
    print(" 2. WhatsApp Web Automation (Uses your local WhatsApp Web)")
    print(" 3. Enable Both (Local Web + Cloud Gateway)")
    print(" 4. Exit")

    choice = input("\nEnter choice [1-4]: ").strip()
    if choice == "1":
        setup_callmebot()
    elif choice == "2":
        setup_whatsapp_web()
    elif choice == "3":
        setup_callmebot()
        setup_whatsapp_web()
    else:
        print("Exiting setup.")


if __name__ == "__main__":
    main()
