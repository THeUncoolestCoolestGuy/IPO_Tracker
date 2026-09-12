"""
Subscriber Manager for Telegram Bot.
Auto-detects when new users start the bot, enrolls them,
manages user PAN cards (/pan, /mypan, /removepan),
and handles interactive allotment checks (/check).
"""

import time
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
from config import Config
from pan_checker import extract_pans, mask_pan, batch_check_pans, format_allotment_report

logger = logging.getLogger("ipo_tracker.subscribers")
SUBSCRIBERS_FILE = Config.DATA_DIR / "subscribers.json"
DISPATCH_STATE_FILE = Config.DATA_DIR / "dispatch_state.json"


def _telegram_post_with_retry(
    token: str,
    payload: Dict[str, Any],
    max_retries: int = 3,
    timeout: int = 60
) -> bool:
    """Send a POST request to Telegram sendMessage with retry, backoff, and HTML fallback."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.post(url, json=payload, timeout=timeout)
            data = res.json()
            if data.get("ok"):
                return True

            code = data.get("error_code")
            desc = data.get("description", "")

            # Fallback to plain text if HTML parse error
            if code == 400 and "can't parse" in desc.lower() and "parse_mode" in payload:
                logger.warning(f"Telegram parse error for {payload.get('chat_id')}: {desc}. Retrying plain text.")
                payload.pop("parse_mode", None)
                continue

            if code in (400, 403):
                logger.warning(f"Telegram permanent failure for {payload.get('chat_id')}: {desc}")
                return False
            if code == 429:
                retry_after = data.get("parameters", {}).get("retry_after", 3)
                time.sleep(retry_after)
                continue
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.warning(f"Telegram network issue sending to {payload.get('chat_id')} (attempt {attempt}/{max_retries}): {e}")
        except Exception as e:
            logger.error(f"Telegram unexpected error: {e}")
            return False

        if attempt < max_retries:
            time.sleep(attempt * 2)
    return False


def load_subscribers_registry() -> Dict[str, Dict[str, Any]]:
    """Load the subscriber registry from data/subscribers.json."""
    if SUBSCRIBERS_FILE.exists():
        try:
            with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
        except Exception as e:
            logger.error(f"Error loading subscribers.json: {e}")

    baseline = {
        "2056597708": {"name": "The uncoolest coolest guy", "role": "admin", "pans": ["DREPP6871C"], "joined_at": "2026-09-08T10:00:00+05:30"},
        "443423364": {"name": "Dr. Chirag Paunwala (@cpaunwala)", "role": "member", "pans": [], "joined_at": "2026-09-08T10:00:00+05:30"},
        "810585239": {"name": "Mita Paunwala (@Mpaunwala)", "role": "member", "pans": [], "joined_at": "2026-09-08T10:00:00+05:30"},
        "424851606": {"name": "K", "role": "member", "status": "blocked", "pans": [], "joined_at": "2026-09-08T10:00:00+05:30"},
        "516357277": {"name": "Paresh Bardolia", "role": "member", "pans": [], "joined_at": "2026-09-08T10:00:00+05:30"},
        "1293713981": {"name": "Sarthak", "role": "member", "pans": [], "joined_at": "2026-09-08T10:00:00+05:30"},
        "1400902994": {"name": "Dobby", "role": "member", "pans": [], "joined_at": "2026-09-08T10:00:00+05:30"},
        "1763761508": {"name": "Sahil Sharma (@shlsharma)", "role": "member", "pans": [], "joined_at": "2026-09-12T12:00:00+05:30"},
        "1557596640": {"name": "M Sharan", "role": "member", "pans": [], "joined_at": "2026-09-12T14:30:00+05:30"}
    }
    save_subscribers_registry(baseline)
    return baseline


def save_subscribers_registry(registry: Dict[str, Dict[str, Any]]):
    """Save the subscriber registry to data/subscribers.json."""
    try:
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving subscribers.json: {e}")


def deactivate_subscriber(chat_id: str, reason: str = "blocked"):
    """Mark a subscriber as inactive / blocked so we don't attempt sending to them."""
    cid = str(chat_id).strip()
    registry = load_subscribers_registry()
    if cid in registry:
        registry[cid]["status"] = reason
        save_subscribers_registry(registry)
        logger.info(f"Subscriber {cid} marked as {reason}.")


def process_incoming_telegram_updates(notify_admin: bool = True) -> List[Dict[str, Any]]:
    """
    Poll Telegram getUpdates to process all incoming user commands and messages:
    - /start: Enroll new subscriber, show welcome menu
    - /pan <PANS>: Save single or multiple PAN cards for automated allotment checks
    - /mypan: Show saved PAN cards
    - /removepan: Clear saved PAN cards
    - /check [IPO] [PANS]: On-demand allotment check
    - /help: Show command help
    """
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        return []

    registry = load_subscribers_registry()
    admin_id = getattr(Config, "ADMIN_CHAT_ID", "2056597708")
    new_subscribers = []
    max_update_id = 0

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    updates = []
    for attempt in range(1, 4):
        try:
            res = requests.get(url, timeout=60)
            data = res.json()
            if data.get("ok"):
                updates = data.get("result", [])
                break
            else:
                logger.warning(f"getUpdates returned error: {data.get('description')}")
        except Exception as e:
            logger.warning(f"Error checking Telegram getUpdates (attempt {attempt}/3): {e}")
            time.sleep(attempt * 2)

    has_registry_changes = False

    for update in updates:
        uid = update.get("update_id", 0)
        if uid > max_update_id:
            max_update_id = uid

        msg = update.get("message") or update.get("my_chat_member") or {}
        chat = msg.get("chat") or {}
        cid = str(chat.get("id", "")).strip()

        if not cid:
            continue

        first = chat.get("first_name", "")
        last = chat.get("last_name", "")
        uname = chat.get("username", "")
        full_name = f"{first} {last}".strip()
        display_name = f"{full_name} (@{uname})" if uname else full_name

        text = msg.get("text", "").strip()

        # 1. Enrol new subscriber if not in registry
        if cid not in registry:
            logger.info(f"New Telegram subscriber detected: {display_name} (ID: {cid})")
            IST = timezone(timedelta(hours=5, minutes=30))
            now_iso = datetime.now(IST).isoformat()
            user_info = {
                "name": display_name,
                "role": "member",
                "pans": [],
                "joined_at": now_iso
            }
            registry[cid] = user_info
            new_subscribers.append({"id": cid, "name": display_name})
            has_registry_changes = True

            welcome_lines = [
                f"🎉 <b>Welcome to Paunwala IPO Alerts, {first or 'Investor'}!</b>",
                "",
                "You are now subscribed to receive daily Indian Mainboard IPO alerts:",
                "• <b>08:00 AM IST:</b> Morning Alert (Strong GMP &gt; 15% first, 10%–15% at end)",
                "• <b>12:30 PM IST:</b> Reminder Alert (IPOs closing today at 5:00 PM)",
                "• <b>10:00 PM IST:</b> Nightly Allotment Declaration Alert",
                "",
                "────────────────────────",
                "🎯 <b>NEW FEATURE: Automated IPO Allotment Checker!</b>",
                "",
                "Save your PAN cards now and let the bot automatically check your allotment status:",
                "",
                "1️⃣ <b>Save your PAN Card(s):</b>",
                "Reply to this bot with your PAN:",
                "👉 <code>/pan &lt;YOUR_PAN&gt;</code>",
                "",
                "<i>Tip: You can save multiple PAN cards at once for your whole family:</i>",
                "👉 <code>/pan ABCDE1234F, BCDEF2345G, CDEFG3456H</code>",
                "",
                "2️⃣ <b>Check Allotment Anytime:</b>",
                "👉 <code>/check</code> — Instantly check saved PANs against the latest declared IPO!",
                "👉 <code>/check &lt;COMPANY&gt; &lt;PAN&gt;</code> — Check a specific company.",
                "",
                "3️⃣ <b>Manage Your Cards:</b>",
                "👉 <code>/mypan</code> — View your saved cards (masked for privacy).",
                "👉 <code>/removepan</code> — Remove your saved cards.",
                "",
                "────────────────────────",
                "🔒 <i>Privacy Guarantee: Your PAN cards are masked (e.g. ABCDE****F) and strictly used only for official registrar allotment lookups.</i>",
                "",
                "────────────────────────",
                "🎁 <b>Open Free Demat Account:</b>",
                f'• <a href="{Config.ZERODHA_REFERRAL_URL}">Zerodha Kite</a>',
                f'• <a href="{Config.UPSTOX_REFERRAL_URL}">Upstox</a> (Zero AMC)',
                f'• <a href="{Config.GROWW_REFERRAL_URL}">Groww</a> (Code: <code>{Config.GROWW_REFERRAL_CODE}</code>)'
            ]
            welcome_msg = "\n".join(welcome_lines)

            _telegram_post_with_retry(
                token,
                {"chat_id": cid, "text": welcome_msg, "parse_mode": "HTML", "disable_web_page_preview": True}
            )

            if notify_admin and admin_id and cid != admin_id:
                admin_lines = [
                    "🔔 <b>[ADMIN] New Subscriber Joined!</b>",
                    "",
                    f"👤 Name: <b>{display_name}</b>",
                    f"🆔 Chat ID: <code>{cid}</code>",
                    "✅ Automatically enrolled for all daily alerts."
                ]
                _telegram_post_with_retry(
                    token,
                    {"chat_id": admin_id, "text": "\n".join(admin_lines), "parse_mode": "HTML"}
                )

        # 2. Process Interactive Commands
        if not text:
            continue

        cmd_lower = text.lower()

        # Command: /pan <PANS> or pan <PANS>
        if cmd_lower.startswith("/pan") or cmd_lower.startswith("pan "):
            pans = extract_pans(text)
            if pans:
                existing = registry[cid].get("pans", [])
                merged = []
                seen = set()
                for p in existing + pans:
                    if p not in seen:
                        seen.add(p)
                        merged.append(p)

                registry[cid]["pans"] = merged
                has_registry_changes = True

                masked_list = [f"• <code>{mask_pan(p)}</code>" for p in merged]
                reply_lines = [
                    f"✅ <b>Saved {len(merged)} PAN Card(s) for your account:</b>",
                    ""
                ]
                reply_lines.extend(masked_list)
                reply_lines.extend([
                    "",
                    "💡 <i>Whenever an IPO allotment without captcha is declared at 10:00 PM, all your PANs will be auto-checked!</i>",
                    "",
                    "To check allotment status right now, reply: <code>/check</code>"
                ])
                reply = "\n".join(reply_lines)
            else:
                reply_lines = [
                    "❌ <b>No valid PAN cards found.</b>",
                    "",
                    "Please enter 10-character Indian PAN cards:",
                    "👉 <code>/pan ABCDE1234F</code>",
                    "👉 <code>/pan ABCDE1234F, BCDEF2345G</code>"
                ]
                reply = "\n".join(reply_lines)
            _telegram_post_with_retry(token, {"chat_id": cid, "text": reply, "parse_mode": "HTML"})

        # Command: /mypan or /pans
        elif cmd_lower in ("/mypan", "/pans", "mypan", "pans"):
            saved = registry[cid].get("pans", [])
            if saved:
                masked_list = [f"• <code>{mask_pan(p)}</code>" for p in saved]
                reply_lines = [
                    f"📋 <b>Your Registered PAN Cards ({len(saved)}):</b>",
                    ""
                ]
                reply_lines.extend(masked_list)
                reply_lines.extend([
                    "",
                    "👉 To add more: <code>/pan &lt;PAN&gt;</code>",
                    "👉 To clear all: <code>/removepan</code>",
                    "👉 To check allotment: <code>/check</code>"
                ])
                reply = "\n".join(reply_lines)
            else:
                reply_lines = [
                    "ℹ️ <b>You have no saved PAN cards yet.</b>",
                    "",
                    "Save your PANs now for automatic allotment alerts:",
                    "👉 <code>/pan ABCDE1234F, BCDEF2345G</code>"
                ]
                reply = "\n".join(reply_lines)
            _telegram_post_with_retry(token, {"chat_id": cid, "text": reply, "parse_mode": "HTML"})

        # Command: /removepan or /clearpan
        elif cmd_lower in ("/removepan", "/clearpan", "removepan", "clearpan"):
            registry[cid]["pans"] = []
            has_registry_changes = True
            reply = "🗑️ <b>All saved PAN cards have been removed from your account.</b>"
            _telegram_post_with_retry(token, {"chat_id": cid, "text": reply, "parse_mode": "HTML"})

        # Command: /check [IPO] [PANS]
        elif cmd_lower.startswith("/check") or cmd_lower.startswith("check"):
            import re
            extracted_pans = extract_pans(text)
            company_query = None

            cleaned_text = re.sub(r"^/check\s*|^check\s*", "", text, flags=re.IGNORECASE)
            for p in extracted_pans:
                cleaned_text = re.sub(re.escape(p), "", cleaned_text, flags=re.IGNORECASE)
            cleaned_text = cleaned_text.replace(",", " ").strip()
            if cleaned_text:
                company_query = cleaned_text

            query_pans = extracted_pans or registry[cid].get("pans", [])

            if not query_pans:
                reply_lines = [
                    "ℹ️ <b>Please provide a PAN number to check.</b>",
                    "",
                    "Examples:",
                    "• Check on-the-fly: <code>/check ABCDE1234F</code>",
                    "• Save PANs once for auto-checking: <code>/pan ABCDE1234F, BCDEF2345G</code>"
                ]
                reply = "\n".join(reply_lines)
                _telegram_post_with_retry(token, {"chat_id": cid, "text": reply, "parse_mode": "HTML"})
            else:
                _telegram_post_with_retry(
                    token,
                    {"chat_id": cid, "text": "🔍 <i>Checking allotment status across registrars...</i>", "parse_mode": "HTML"}
                )
                res = batch_check_pans(company_query, query_pans)
                report = format_allotment_report(res)
                _telegram_post_with_retry(
                    token,
                    {"chat_id": cid, "text": report, "parse_mode": "HTML", "disable_web_page_preview": True}
                )

        # Command: /help
        elif cmd_lower in ("/help", "help", "/commands"):
            help_lines = [
                "🤖 <b>Paunwala IPO Bot Commands:</b>",
                "",
                "• <code>/pan &lt;PAN1&gt;, &lt;PAN2&gt;</code> — Save single or multiple PAN cards",
                "• <code>/mypan</code> — View your saved PAN cards",
                "• <code>/removepan</code> — Clear your saved PAN cards",
                "• <code>/check</code> — Check allotment for your saved PANs",
                "• <code>/check &lt;COMPANY&gt; &lt;PAN&gt;</code> — Check specific company &amp; PAN",
                "• <code>/help</code> — Show this help message",
                "",
                "⏰ <b>Scheduled Alerts:</b>",
                "• 8:00 AM IST: High-GMP Morning Alert",
                "• 12:30 PM IST: Closing Today Reminder",
                "• 10:00 PM IST: Nightly Allotment Declaration Alert"
            ]
            help_msg = "\n".join(help_lines)
            _telegram_post_with_retry(token, {"chat_id": cid, "text": help_msg, "parse_mode": "HTML"})

    if max_update_id > 0:
        try:
            requests.get(f"{url}?offset={max_update_id + 1}&limit=1", timeout=60)
            logger.debug(f"Acknowledged Telegram updates up to {max_update_id}")
        except Exception as e:
            logger.debug(f"Could not acknowledge getUpdates offset {max_update_id + 1}: {e}")

    if has_registry_changes or new_subscribers:
        save_subscribers_registry(registry)
        logger.info(f"Subscribers registry updated successfully.")

    return new_subscribers


def sync_new_subscribers(notify_admin: bool = True) -> List[Dict[str, Any]]:
    """Backward-compatible wrapper calling process_incoming_telegram_updates."""
    return process_incoming_telegram_updates(notify_admin=notify_admin)


def get_all_active_chat_ids() -> List[str]:
    """
    Get all active Telegram Chat IDs combining .env and subscribers.json.
    Also processes updates to catch any newly joined users or commands.
    Excludes any blocked/inactive users.
    """
    process_incoming_telegram_updates(notify_admin=True)
    registry = load_subscribers_registry()

    all_ids = set()
    for cid, info in registry.items():
        if info.get("status") not in ("blocked", "inactive"):
            all_ids.add(str(cid).strip())

    for cid in Config.TELEGRAM_CHAT_IDS:
        cid_str = str(cid).strip()
        if cid_str and registry.get(cid_str, {}).get("status") not in ("blocked", "inactive"):
            all_ids.add(cid_str)

    return list(all_ids)


def has_admin_report_dispatched_today() -> bool:
    """Check if the admin daily subscriber report has already been dispatched today."""
    try:
        if DISPATCH_STATE_FILE.exists():
            with open(DISPATCH_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            IST = timezone(timedelta(hours=5, minutes=30))
            today_str = datetime.now(IST).strftime("%Y-%m-%d")
            return data.get("admin_subscriber_report") == today_str
    except Exception:
        pass
    return False


def record_admin_report_dispatch():
    """Record dispatch of admin daily subscriber report to prevent duplicate sends."""
    try:
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {}
        if DISPATCH_STATE_FILE.exists():
            try:
                with open(DISPATCH_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        IST = timezone(timedelta(hours=5, minutes=30))
        today_str = datetime.now(IST).strftime("%Y-%m-%d")
        data["admin_subscriber_report"] = today_str
        with open(DISPATCH_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.debug(f"Could not record admin report dispatch state: {e}")


def send_daily_admin_subscriber_report(dry_run: bool = False, force: bool = False) -> Dict[str, Any]:
    """
    Send daily executive subscriber digest privately to Admin (Config.ADMIN_CHAT_ID)
    at the 10:00 PM cron job.
    Reports any new subscribers who joined today, along with overall community counts.
    """
    token = Config.TELEGRAM_BOT_TOKEN
    admin_id = getattr(Config, "ADMIN_CHAT_ID", "2056597708")

    if not token or not admin_id:
        logger.warning("Cannot send admin subscriber report: missing token or admin_id")
        return {"status": "error", "message": "Missing credentials"}

    if not force and not dry_run and has_admin_report_dispatched_today():
        logger.info("Admin daily subscriber report already dispatched today. Skipping duplicate.")
        return {"status": "skipped_duplicate", "count": 0}

    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    display_date = now_ist.strftime("%d %b %Y")

    registry = load_subscribers_registry()

    new_today = []
    active_members = []
    blocked_members = []
    total_pans = 0
    members_with_pans = 0

    for cid, info in registry.items():
        is_blocked = info.get("status") in ("blocked", "inactive")
        if is_blocked:
            blocked_members.append((cid, info))
        else:
            active_members.append((cid, info))
            pans = info.get("pans", [])
            if pans:
                members_with_pans += 1
                total_pans += len(pans)

        joined_at = info.get("joined_at", "")
        if joined_at.startswith(today_str):
            new_today.append((cid, info))

    lines = [
        "👑 <b>[ADMIN] Daily Subscriber Digest</b>",
        f"📅 <i>{display_date} • 10:00 PM IST Sync</i>",
        "",
        "────────────────────────"
    ]

    if new_today:
        lines.append(f"🆕 <b>New Subscribers Joined Today ({len(new_today)}):</b>")
        for cid, u in new_today:
            uname = u.get("name", "Unknown")
            pans = len(u.get("pans", []))
            pan_tag = f"💳 {pans} PAN(s)" if pans > 0 else "💳 0 PANs"
            lines.append(f"• <b>{uname}</b>\n  🆔 <code>{cid}</code> | {pan_tag}")
    else:
        lines.append("🆕 <b>New Subscribers Joined Today:</b>")
        lines.append("ℹ️ <i>None (No new users joined today)</i>")

    lines.extend([
        "",
        "────────────────────────",
        "📊 <b>Community Overview:</b>",
        f"• 👥 Total Active Members: <b>{len(active_members)}</b>",
        f"• 💳 Members with Saved PANs: <b>{members_with_pans}</b> ({total_pans} total PANs registered)",
        f"• 🚫 Blocked / Inactive: <b>{len(blocked_members)}</b>",
        "",
        "────────────────────────",
        f"📋 <b>All Active Members ({len(active_members)}):</b>"
    ])

    for idx, (cid, u) in enumerate(active_members, 1):
        name = u.get("name", "Unknown")
        is_admin = u.get("role") == "admin" or cid == admin_id
        role_tag = " [ADMIN]" if is_admin else ""
        pans = len(u.get("pans", []))
        pan_info = f" • {pans} PAN" if pans > 0 else ""
        lines.append(f"{idx}. {name}{role_tag}{pan_info}")

    report_msg = "\n".join(lines).strip()

    if dry_run:
        print("\n--- [DRY-RUN] ADMIN DAILY SUBSCRIBER REPORT ---")
        print(report_msg)
        print("------------------------------------------------\n")
        return {"status": "dry_run", "message": report_msg, "new_today": len(new_today)}

    success = _telegram_post_with_retry(
        token,
        {"chat_id": admin_id, "text": report_msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    )

    if success:
        record_admin_report_dispatch()
        logger.info(f"Admin daily subscriber report dispatched successfully to Admin ({admin_id}).")
        return {"status": "dispatched", "new_today": len(new_today), "message": report_msg}
    else:
        logger.error(f"Failed to dispatch admin daily subscriber report to Admin ({admin_id}).")
        return {"status": "failed", "new_today": len(new_today)}

