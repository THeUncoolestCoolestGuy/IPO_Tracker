"""
Automatic Telegram Chat ID Setup and Verification Helper.
Checks for users who clicked 'START' on @PaunwalaIpoAlert_bot and updates .env.
"""

import sys
import time
import requests
from config import Config

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BOT_TOKEN = Config.TELEGRAM_BOT_TOKEN
BOT_USERNAME = "PaunwalaIpoAlert_bot"


def get_updates():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Error checking Telegram API: {e}")
        return {}


def send_welcome(chat_id, user_name):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    text = (
        f"🎉 Hello {user_name}!\n\n"
        "✅ Your phone is now successfully linked to Paunwala IPO Tracker!\n"
        "You will receive:\n"
        "• Daily 8:00 AM IST alerts when Mainboard IPO GMP > 10%\n"
        "• Daily 12:30 PM IST reminders for IPOs closing that day."
    )
    requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)


def update_env_file(chat_ids):
    env_path = Config.BASE_DIR / ".env"
    ids_str = ",".join(str(cid) for cid in chat_ids)
    
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re
        if re.search(r"^TELEGRAM_CHAT_IDS=.*$", content, flags=re.MULTILINE):
            new_content = re.sub(
                r"^TELEGRAM_CHAT_IDS=.*$",
                f"TELEGRAM_CHAT_IDS={ids_str}",
                content,
                flags=re.MULTILINE
            )
        else:
            new_content = content + f"\nTELEGRAM_CHAT_IDS={ids_str}\n"

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        print(f"✅ Successfully updated .env with Chat IDs: {ids_str}")
    except Exception as e:
        print(f"❌ Error updating .env: {e}")


def main():
    print("=" * 65)
    print("🤖 TELEGRAM BOT AUTO-LINK HELPER")
    print(f"Bot Username: @{BOT_USERNAME}")
    print(f"Link:         https://t.me/{BOT_USERNAME}")
    print("=" * 65)

    print("\n👉 STEP 1: Open Telegram on the phone(s) that should receive alerts.")
    print(f"👉 STEP 2: Search for '@{BOT_USERNAME}' (or click https://t.me/{BOT_USERNAME}).")
    print("👉 STEP 3: Click 'START' or send any message (e.g. 'hi').\n")

    print("Listening for messages... (will auto-detect your chat ID)")

    detected_chats = {}
    
    # Check current updates first
    data = get_updates()
    for item in data.get("result", []):
        msg = item.get("message") or item.get("my_chat_member", {}).get("chat")
        if msg:
            chat = msg.get("chat", msg)
            cid = chat.get("id")
            name = chat.get("first_name", "") or chat.get("title", "User")
            if cid:
                detected_chats[cid] = name

    if detected_chats:
        print(f"\n🎉 Found {len(detected_chats)} user(s) already connected:")
        for cid, name in detected_chats.items():
            print(f"  • {name} (Chat ID: {cid})")
            send_welcome(cid, name)
        update_env_file(list(detected_chats.keys()))
        return

    print("Waiting for you to click START in Telegram (checking every 3s)...")
    for _ in range(20):
        time.sleep(3)
        data = get_updates()
        for item in data.get("result", []):
            msg = item.get("message")
            if msg:
                chat = msg.get("chat", {})
                cid = chat.get("id")
                name = chat.get("first_name", "User")
                if cid and cid not in detected_chats:
                    detected_chats[cid] = name
                    print(f"\n🎉 Detected: {name} (Chat ID: {cid})!")
                    send_welcome(cid, name)

        if detected_chats:
            break

    if detected_chats:
        update_env_file(list(detected_chats.keys()))
        print("\nAll set! Run 'python main.py --run-now' to send a test alert!")
    else:
        print("\n⏳ No message received yet. Whenever you click START on Telegram, run:")
        print("   python setup_telegram.py")


if __name__ == "__main__":
    main()

