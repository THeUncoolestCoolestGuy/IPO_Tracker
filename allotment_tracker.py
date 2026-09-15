"""
Allotment Tracker Engine for Indian IPOs.
Monitors Link Intime, KFintech, and Bigshare for newly declared allotments.
Maintains state in data/notified_allotments.json to prevent duplicate notifications.
Auto-checks registered subscriber PANs for captcha-free registrars (KFintech).
"""

import sys
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional

from config import Config
from allotment_scraper import get_all_live_allotments
from notifiers import dispatch_alert

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("ipo_tracker.allotment_tracker")

ALLOTMENT_STATE_FILE = Config.DATA_DIR / "notified_allotments.json"

BROKER_APP_LINKS = {
    "Kite": "https://play.google.com/store/apps/details?id=com.zerodha.kite3",
    "Upstox": "https://play.google.com/store/apps/details?id=in.upstox.app",
    "Groww": "https://play.google.com/store/apps/details?id=com.nextbillion.groww",
    "Sharekhan": "https://play.google.com/store/apps/details?id=com.sharekhan.androidsharemobile"
}


def normalize_key(name: str) -> str:
    """Normalize company name to lowercase alphanumeric key for reliable matching."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", name.lower())
    for word in ["limited", "ltd", "ipo", "sme"]:
        cleaned = cleaned.replace(word, "")
    return cleaned.strip()


def load_notified_allotments() -> Dict:
    """Load previously notified allotments registry."""
    if not ALLOTMENT_STATE_FILE.exists():
        return {}
    try:
        with open(ALLOTMENT_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load notified allotments state: {e}")
        return {}


def save_notified_allotments(registry: Dict):
    """Save notified allotments registry to disk."""
    try:
        with open(ALLOTMENT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save notified allotments state: {e}")


def format_allotment_alert(ipo: Dict) -> str:
    """
    Format clean, spacious, visually appealing allotment declared alert.
    """
    name = ipo.get("name", "IPO")
    registrar = ipo.get("registrar", "Registrar")
    portal_url = ipo.get("portal_url", "")
    bse_url = ipo.get("bse_url", "https://www.bseindia.com/investors/appli_check.aspx")
    today_str = datetime.now().strftime("%d %b %Y")

    lines = [
        f"🎉 <b>IPO ALLOTMENT DECLARED!</b> • {today_str}",
        "",
        "Allotment status is now officially LIVE for:",
        f"📌 <b>{name}</b>",
        f"🏛️ <b>Registrar:</b> {registrar}",
        "",
        "────────────────────────",
        "📲 <b>Check Your Status (1-Click):</b>",
        f'👉 <a href="{portal_url}">{registrar} Official Portal</a>',
        f'👉 <a href="{bse_url}">BSE Central Portal</a>',
        ""
    ]

    if registrar == "KFin Technologies":
        lines.append("🤖 <b>Automated PAN Check:</b>")
        lines.append("This IPO has <b>NO CAPTCHA</b>. Registered subscriber PANs are auto-checked now!")
        lines.append("To check your PAN anytime, reply: <code>/check</code> or <code>/pan &lt;PAN&gt;</code>")
    else:
        lines.append(f"⚠️ <i>Note: {registrar} enforces image CAPTCHA verification.")
        lines.append("Automated bot lookup is protected — check directly using the official links above!</i>")

    lines.append("")
    lines.append("────────────────────────")
    lines.append("📲 <b>Direct Broker Launchers:</b>")
    lines.append(
        f'<a href="{BROKER_APP_LINKS["Kite"]}">Kite</a>  •  '
        f'<a href="{BROKER_APP_LINKS["Upstox"]}">Upstox</a>  •  '
        f'<a href="{BROKER_APP_LINKS["Groww"]}">Groww</a>  •  '
        f'<a href="{BROKER_APP_LINKS["Sharekhan"]}">Sharekhan</a>'
    )
    return "\n".join(lines).strip()


def is_debt_or_excluded_issue(name: str) -> bool:
    """
    Exclude corporate debt instruments (NCDs, Bonds, Debentures, Tranches),
    trusts (REIT, InVIT), rights issues, and explicit SME offerings.
    """
    upper = name.upper()
    if re.search(r"\b(NCD|NCDS|BOND|BONDS|DEBENTURE|DEBENTURES|TRANCHE|RIGHTS ISSUE|REIT|INVIT)\b", upper):
        return True
    if re.search(r"\b(SME|SME IPO|SME-IPO)\b", upper):
        return True
    return False


def parse_closing_days_ago(last_date_str: str) -> Optional[int]:
    """Calculate how many days ago an IPO closed."""
    if not last_date_str or last_date_str in ("-", "TBA"):
        return None
    m = re.search(r"(\d+)\s+([A-Za-z]+)", last_date_str)
    if not m:
        return None
    day = int(m.group(1))
    month_str = m.group(2)[:3]
    try:
        today = datetime.now()
        closing_dt = datetime.strptime(f"{day} {month_str} {today.year}", "%d %b %Y")
        return (today - closing_dt).days
    except Exception:
        return None


def check_and_notify_new_allotments(dry_run: bool = False, force_check: bool = False) -> Dict:
    """
    Check all registrars for newly published Mainboard IPO allotments.
    Filters:
    1. Only Mainboard IPOs (excludes NCDs, debt bonds, REITs, SMEs).
    2. Only IPOs in the active allotment window (closed recently within 0 to 5 days).
    3. Auto-checks registered subscriber PANs on KFintech and only sends DMs if
       at least one PAN actually submitted an application (suppresses 0-app spam).
    """
    logger.info("Scanning registrars for newly declared Mainboard IPO allotments...")
    live_ipos = get_all_live_allotments()
    if not live_ipos:
        logger.warning("No live IPOs fetched from registrars.")
        return {"status": "no_data", "count": 0, "new_allotments": []}

    from scraper import get_all_mainboard_ipos
    from pan_checker import find_ipo_by_name

    mainboard_ipos = get_all_mainboard_ipos()
    registry = load_notified_allotments()
    is_first_run = len(registry) == 0 and not force_check

    if is_first_run:
        logger.info(f"First run: Seeding {len(live_ipos)} existing allotments to state registry.")
        for ipo in live_ipos:
            key = normalize_key(ipo["name"])
            registry[key] = {
                "name": ipo["name"],
                "registrar": ipo["registrar"],
                "portal_url": ipo["portal_url"],
                "first_seen": datetime.now().isoformat()
            }
        save_notified_allotments(registry)
        return {
            "status": "seeded_initial",
            "count": len(live_ipos),
            "new_allotments": []
        }

    new_allotments = []
    for ipo in live_ipos:
        key = normalize_key(ipo["name"])
        if key in registry:
            continue

        # 1. Strictly exclude debt / NCD / bonds / trusts
        if is_debt_or_excluded_issue(ipo["name"]):
            logger.debug(f"Skipping non-equity/debt offering: {ipo['name']}")
            continue

        # 2. Match against Mainboard IPO list
        matched_mb = find_ipo_by_name(ipo["name"], all_ipos=mainboard_ipos)
        if not matched_mb:
            logger.debug(f"Skipping non-mainboard or untracked IPO: {ipo['name']}")
            continue

        # 3. Only alert for Mainboard IPOs closing recently (within 0 to 5 days, e.g. today or 1-4 days before)
        days_ago = parse_closing_days_ago(matched_mb.get("last_filing_date", ""))
        status = matched_mb.get("status", "").lower()
        if status in ("upcoming", "open"):
            logger.info(f"Skipping open/upcoming IPO not yet in allotment window: {ipo['name']}")
            continue

        if days_ago is not None and (days_ago < 0 or days_ago > 5):
            logger.info(f"Skipping Mainboard IPO outside recent allotment window ({days_ago} days ago): {ipo['name']}")
            continue

        new_allotments.append(ipo)

    logger.info(f"Detected {len(new_allotments)} qualifying Mainboard allotment(s).")

    if not new_allotments:
        return {"status": "no_new_allotments", "count": 0, "new_allotments": []}

    from notifiers.telegram_notifier import TelegramNotifier
    from subscriber_manager import load_subscribers_registry
    from pan_checker import batch_check_pans, format_allotment_report

    tg_notifier = TelegramNotifier()
    subscribers = load_subscribers_registry()
    results = []

    for ipo in new_allotments:
        alert_msg = format_allotment_alert(ipo)
        if dry_run:
            print("\n--- [DRY-RUN] ALLOTMENT ALERT PREVIEW ---")
            print(alert_msg)
            print("-----------------------------------------\n")
        else:
            dispatch_results = dispatch_alert(alert_msg)
            results.append(dispatch_results)

        if ipo.get("registrar") == "KFin Technologies":
            logger.info(f"Checking registered PANs for KFintech IPO: {ipo['name']}...")
            for chat_id, user_data in subscribers.items():
                if user_data.get("status") in ("blocked", "inactive"):
                    continue
                user_pans = user_data.get("pans", [])
                if not user_pans:
                    continue

                logger.info(f"Checking {len(user_pans)} PAN(s) for user {user_data.get('name')} ({chat_id})...")
                check_res = batch_check_pans(ipo, user_pans)

                # Only send DM if at least 1 PAN actually submitted an application
                has_apps = any(r.get("status") in ("ALLOTTED", "NOT_ALLOTTED") for r in check_res.get("results", []))
                if not has_apps:
                    logger.info(f"No applications found for {user_data.get('name')} in {ipo['name']}, skipping DM notification.")
                    continue

                personal_report = format_allotment_report(check_res)

                if dry_run:
                    print(f"\n--- [DRY-RUN] PERSONALIZED REPORT FOR {user_data.get('name')} ---")
                    print(personal_report)
                    print("----------------------------------------------------------------\n")
                else:
                    tg_notifier.send_direct(chat_id, personal_report)

        key = normalize_key(ipo["name"])
        registry[key] = {
            "name": ipo["name"],
            "registrar": ipo["registrar"],
            "portal_url": ipo["portal_url"],
            "notified_at": datetime.now().isoformat()
        }

    if not dry_run:
        save_notified_allotments(registry)

    return {
        "status": "notified",
        "count": len(new_allotments),
        "new_allotments": [i["name"] for i in new_allotments],
        "dispatch_results": results
    }


def get_active_allotment_pipeline(max_days_ago: int = 6) -> Dict[str, List[Dict[str, Any]]]:
    """
    Intelligent Allotment Window Pipeline:
    Cross-references Mainboard IPOs that closed in the last 1-6 days
    against live registrar lists (KFintech, Link Intime, Bigshare).
    Categorizes them into:
    - kfin_ready: Live on KFintech (eligible for automatic multi-PAN checks)
    - captcha_live: Live on Link Intime / Bigshare (1-click portal links provided)
    - pending: Closed within last 1-5 days, allotment expected any moment
    """
    from scraper import get_all_mainboard_ipos
    from pan_checker import find_ipo_by_name

    ipos = get_all_mainboard_ipos()
    today = datetime.now()

    recent_closed = []
    for ipo in ipos:
        last_date_str = ipo.get("last_filing_date", "")
        m = re.search(r"(\d+)\s+([A-Za-z]+)", last_date_str)
        if m:
            day = int(m.group(1))
            month_str = m.group(2)[:3]
            try:
                closing_dt = datetime.strptime(f"{day} {month_str} {today.year}", "%d %b %Y")
                diff_days = (today - closing_dt).days
                if 0 <= diff_days <= max_days_ago and ipo.get("status", "").lower() == "closed":
                    recent_closed.append({
                        "name": ipo["name"],
                        "last_filing_date": last_date_str,
                        "days_ago": diff_days
                    })
            except Exception:
                pass

    from allotment_scraper import get_all_live_allotments
    all_live = get_all_live_allotments()

    kfin_ready = []
    captcha_live = []
    pending = []

    for ipo in recent_closed:
        matched = find_ipo_by_name(ipo["name"], all_ipos=all_live)
        if matched:
            matched_copy = dict(matched)
            matched_copy["days_ago"] = ipo["days_ago"]
            matched_copy["last_filing_date"] = ipo["last_filing_date"]
            if matched.get("registrar") == "KFin Technologies":
                kfin_ready.append(matched_copy)
            else:
                captcha_live.append(matched_copy)
        else:
            pending.append(ipo)

    return {
        "kfin_ready": kfin_ready,
        "captcha_live": captcha_live,
        "pending": pending
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Allotment Tracker...")
    res = check_and_notify_new_allotments(dry_run=True, force_check=False)
    print("Result:", res)
