"""
Robust Automated Test Suite for Indian Mainboard IPO Tracker.
Covers all edge cases across:
  1. Scraper Parsing & Text Normalization
  2. Date Parsing & Calendar Boundaries
  3. Dynamic Lifecycle & Status Evaluation
  4. Alert Formatting & Telegram HTML Compliance
  5. PAN Extraction, Masking & AES-256 Cryptography
  6. Allotment Pipeline & Registrar Mapping
  7. Dispatch State Concurrency & Idempotency

Can be executed anytime via CLI:
  python test_suite.py [--notify-admin]
"""

import sys
import os
import re
import time
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Any
import unittest.mock
from unittest.mock import patch, MagicMock, mock_open

# Ensure UTF-8 console encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import Config
from scraper import (
    _parse_currency,
    _parse_price_band,
    _clean_company_name_and_status,
    _parse_dates,
    parse_date_str_to_date,
    _recompute_ipo_status_and_closing,
)
from tracker import (
    format_ipo_dates,
    format_morning_alert,
    format_reminder_alert,
    get_classified_ipos,
    has_dispatched_today,
    _record_dispatch,
)
from pan_checker import (
    extract_pans,
    mask_pan,
    format_allotment_report,
)
from crypto_utils import encrypt_pan, decrypt_pan
from notifiers.telegram_notifier import TelegramNotifier


class TestResultTracker:
    def __init__(self):
        self.groups: Dict[str, List[Tuple[str, bool, str]]] = {}
        self.start_time = time.time()

    def record(self, group: str, test_name: str, passed: bool, detail: str = ""):
        if group not in self.groups:
            self.groups[group] = []
        self.groups[group].append((test_name, passed, detail))

    @property
    def total_tests(self) -> int:
        return sum(len(tests) for tests in self.groups.values())

    @property
    def passed_tests(self) -> int:
        return sum(sum(1 for _, p, _ in tests if p) for tests in self.groups.values())

    @property
    def failed_tests(self) -> int:
        return self.total_tests - self.passed_tests

    @property
    def all_passed(self) -> bool:
        return self.failed_tests == 0

    @property
    def duration_sec(self) -> float:
        return time.time() - self.start_time


def validate_html_tags(html_str: str) -> bool:
    """Validate that standard Telegram HTML tags are properly opened and closed."""
    tags = ["b", "i", "code", "a", "s", "u"]
    for t in tags:
        open_count = len(re.findall(rf"<{t}(?:\s+[^>]*)?>", html_str, re.IGNORECASE))
        close_count = len(re.findall(rf"</{t}>", html_str, re.IGNORECASE))
        if open_count != close_count:
            return False
    return True


def run_all_tests() -> TestResultTracker:
    tracker = TestResultTracker()

    # ---------------------------------------------------------
    # SUITE 1: Scraper Parsing & Text Normalization
    # ---------------------------------------------------------
    g1 = "1. Scraper & Regex Cleaners"

    # Price Band
    tracker.record(g1, "Price Band Range ('168 to 177')", _parse_price_band("168 to 177") == 177.0)
    tracker.record(g1, "Price Band Single ('₹586')", _parse_price_band("₹586") == 586.0)
    tracker.record(g1, "Price Band Comma ('₹1,119')", _parse_price_band("₹1,119") == 1119.0)
    tracker.record(g1, "Price Band Invalid ('TBA')", _parse_price_band("TBA") == 0.0)

    # Currency
    tracker.record(g1, "Currency Standard ('₹225')", _parse_currency("₹225") == 225.0)
    tracker.record(g1, "Currency Decimal ('₹130.50')", _parse_currency("₹130.50") == 130.5)
    tracker.record(g1, "Currency Zero ('0')", _parse_currency("0") == 0.0)

    # Name and Embedded Status Cleaning
    name1, st1 = _clean_company_name_and_status("Bonfiglioli Transmissions  Open")
    tracker.record(g1, "Clean Name 'Open'", name1 == "Bonfiglioli Transmissions" and st1 == "Open")

    name2, st2 = _clean_company_name_and_status("Fusion CX (C)")
    tracker.record(g1, "Clean Name '(C)' -> Closed", name2 == "Fusion CX" and st2 == "Closed")

    name3, st3 = _clean_company_name_and_status("Paras HealthcareUpcoming")
    tracker.record(g1, "Clean Name 'Upcoming'", name3 == "Paras Healthcare" and st3 == "Upcoming")

    name4, st4 = _clean_company_name_and_status("HD Fire Protect (c)")
    tracker.record(g1, "Clean Name '(c)' lower -> Closed", name4 == "HD Fire Protect" and st4 == "Closed")

    # ---------------------------------------------------------
    # SUITE 2: Date Parsing & Boundaries
    # ---------------------------------------------------------
    g2 = "2. Date Parsing & Boundaries"

    # _parse_dates
    d1 = _parse_dates("15-19 Oct")
    tracker.record(g2, "Range '15-19 Oct'", d1 == ("15 Oct", "19 Oct"))

    d2 = _parse_dates("21 - 23 Oct")
    tracker.record(g2, "Range spaces '21 - 23 Oct'", d2 == ("21 Oct", "23 Oct"))

    d3 = _parse_dates("28 Aug - 1 Sept")
    tracker.record(g2, "Cross-Month '28 Aug - 1 Sept'", d3 == ("28 Aug", "1 Sept"))

    d4 = _parse_dates("10 to 15 Sept")
    tracker.record(g2, "Word 'to' '10 to 15 Sept'", d4 == ("10 Sept", "15 Sept"))

    d5 = _parse_dates("Oct 15 - 19")
    tracker.record(g2, "Month First 'Oct 15 - 19'", d5 == ("15 Oct", "19 Oct"))

    d6 = _parse_dates("Oct 15 - Oct 19")
    tracker.record(g2, "Month First Dual 'Oct 15 - Oct 19'", d6 == ("15 Oct", "19 Oct"))

    d7 = _parse_dates("16 Oct")
    tracker.record(g2, "Single Day '16 Oct'", d7 == ("16 Oct", "16 Oct"))

    d8 = _parse_dates("Oct 16")
    tracker.record(g2, "Single Day 'Oct 16'", d8 == ("16 Oct", "16 Oct"))

    d9 = _parse_dates("TBA")
    tracker.record(g2, "Placeholder 'TBA'", d9 == ("TBA", "TBA"))

    # parse_date_str_to_date
    dt1 = parse_date_str_to_date("19 Oct")
    dt2 = parse_date_str_to_date("Oct 19")
    tracker.record(g2, "parse_date_str Day vs Month first", dt1 is not None and dt2 is not None and dt1.day == 19 and dt1.month == 10 and dt2.day == 19)

    dt_invalid = parse_date_str_to_date("InvalidDate")
    tracker.record(g2, "parse_date_str Invalid", dt_invalid is None)

    # ---------------------------------------------------------
    # SUITE 3: Dynamic Lifecycle & Status Evaluation
    # ---------------------------------------------------------
    g3 = "3. Lifecycle & Status Evaluation"

    now = datetime.now()
    today_str = now.strftime("%d %b")
    yesterday_str = (now - timedelta(days=2)).strftime("%d %b")
    tomorrow_str = (now + timedelta(days=1)).strftime("%d %b")
    future_str = (now + timedelta(days=5)).strftime("%d %b")

    # Past IPO -> Must be Closed
    past_ipo = {"name": "Past Inc", "start_date": "10 Aug", "last_filing_date": yesterday_str, "status": "Open"}
    _recompute_ipo_status_and_closing(past_ipo)
    tracker.record(g3, "Past IPO Auto-Closed", past_ipo["status"] == "Closed" and not past_ipo["closing_today"])

    # Closing Today
    closing_ipo = {"name": "Closing Inc", "start_date": yesterday_str, "last_filing_date": today_str, "status": "Upcoming"}
    _recompute_ipo_status_and_closing(closing_ipo)
    tracker.record(g3, "Closing Today Detection", closing_ipo["closing_today"] and closing_ipo["status"] == "Open")

    # Currently Open
    open_ipo = {"name": "Open Inc", "start_date": yesterday_str, "last_filing_date": tomorrow_str, "status": "Upcoming"}
    _recompute_ipo_status_and_closing(open_ipo)
    tracker.record(g3, "Currently Open Detection", open_ipo["status"] == "Open" and not open_ipo["closing_today"])

    # Upcoming
    up_ipo = {"name": "Upcoming Inc", "start_date": tomorrow_str, "last_filing_date": future_str, "status": "Upcoming"}
    _recompute_ipo_status_and_closing(up_ipo)
    tracker.record(g3, "Future Upcoming Detection", up_ipo["status"] == "Upcoming" and not up_ipo["closing_today"])

    # ---------------------------------------------------------
    # SUITE 4: Alert Formatting & Telegram HTML Compliance
    # ---------------------------------------------------------
    g4 = "4. Alert Formatting & HTML"

    # format_ipo_dates
    f1 = format_ipo_dates({"start_date": "15 Oct", "last_filing_date": "19 Oct"})
    tracker.record(g4, "Format Range ('15 Oct – 19 Oct')", f1 == "15 Oct – 19 Oct")

    f2 = format_ipo_dates({"start_date": "21 Oct", "last_filing_date": "21 Oct"})
    tracker.record(g4, "Format Single Day ('21 Oct')", f2 == "21 Oct")

    f3 = format_ipo_dates({"start_date": "TBA", "last_filing_date": "23 Oct"})
    tracker.record(g4, "Format Missing Start ('Closes 23 Oct')", f3 == "Closes 23 Oct")

    f4 = format_ipo_dates({"start_date": "TBA", "last_filing_date": "TBA"})
    tracker.record(g4, "Format All TBA ('TBA')", f4 == "TBA")

    # Morning Alert HTML and Content
    mock_active = [
        {
            "name": "Tonbo Imaging",
            "price_band": "₹700",
            "gmp_rs": 516.0,
            "gmp_percent": 73.7,
            "start_date": "15 Oct",
            "last_filing_date": "19 Oct",
            "status": "OPEN",
            "closing_today": False
        },
        {
            "name": "Sahajanand Medical",
            "price_band": "₹344",
            "gmp_rs": 35.0,
            "gmp_percent": 10.2,
            "start_date": "15 Oct",
            "last_filing_date": "19 Oct",
            "status": "OPEN",
            "closing_today": False
        }
    ]
    mock_upcoming = [
        {
            "name": "Jio Platforms",
            "price_band": "₹1,119",
            "gmp_rs": 225.0,
            "gmp_percent": 20.1,
            "start_date": "21 Oct",
            "last_filing_date": "23 Oct",
            "status": "UPCOMING",
            "closing_today": False
        }
    ]
    morning_text = format_morning_alert(mock_active, mock_upcoming)
    tracker.record(g4, "Morning Alert Tag Balance", validate_html_tags(morning_text))
    tracker.record(g4, "Morning Alert Has 'IPO Date:'", "IPO Date:" in morning_text)
    tracker.record(g4, "Morning Alert No Legacy 'Last Filing:'", "Last Filing:" not in morning_text)

    # Empty Active Morning Alert
    empty_morning_text = format_morning_alert([], mock_upcoming)
    tracker.record(g4, "Empty Active Displays Explicit Notice", "No Mainboard IPOs are currently active" in empty_morning_text)

    # Reminder Alert HTML and Content
    reminder_text, _ = format_reminder_alert(mock_active)
    tracker.record(g4, "Reminder Alert Tag Balance", validate_html_tags(reminder_text))
    tracker.record(g4, "Reminder Alert No Legacy 'Last Filing Date:'", "Last Filing Date:" not in reminder_text)

    # ---------------------------------------------------------
    # SUITE 5: PAN Security & AES-256 Cryptography
    # ---------------------------------------------------------
    g5 = "5. PAN Crypto & Validation"

    # PAN extraction
    sample_text = "Here are PANs: ABCDE1234F, abcde1234f, BCDEF2345G and bad ones 12345ABCDE, XYZ123."
    pans = extract_pans(sample_text)
    tracker.record(g5, "PAN Regex Extraction & Deduplication", pans == ["ABCDE1234F", "BCDEF2345G"])

    # PAN Masking
    masked = mask_pan("ABCDE1234F")
    tracker.record(g5, "PAN Masking ('ABCDE****F')", masked == "ABCDE****F")

    # Cryptography Roundtrip
    original_pan = "AAAPA1234M"
    encrypted = encrypt_pan(original_pan)
    decrypted = decrypt_pan(encrypted)
    tracker.record(g5, "AES-256 Encryption Prefix ('enc:')", encrypted.startswith("enc:"))
    tracker.record(g5, "AES-256 Decryption Roundtrip", decrypted == original_pan)

    # Legacy Compatibility
    legacy_plain = "XYZPA9999Z"
    tracker.record(g5, "Legacy Plaintext Decrypt Fallback", decrypt_pan(legacy_plain) == legacy_plain)

    # ---------------------------------------------------------
    # SUITE 6: Allotment Pipeline & Registrar Mapping
    # ---------------------------------------------------------
    g6 = "6. Allotment & Pipeline Mapping"

    from allotment_tracker import normalize_key
    n1 = normalize_key("Manipal Payment And Identity Solutions Limited - IPO")
    n2 = normalize_key("Manipal Payment and Identity Solutions Ltd")
    tracker.record(g6, "Registrar Company Name Normalization", n1 == n2)

    # Allotment Report Formatter (Captcha Required)
    captcha_report = format_allotment_report({
        "captcha_required": True,
        "company_name": "Test Captcha IPO",
        "registrar": "Link Intime",
        "portal_url": "https://linkintime.co.in"
    })
    tracker.record(g6, "Captcha Allotment Report HTML", validate_html_tags(captcha_report) and "Link Intime" in captcha_report)

    # Allotment Report Formatter (Direct API Success)
    direct_report = format_allotment_report({
        "success": True,
        "company_name": "Steamhouse India",
        "registrar": "KFin Technologies",
        "results": [
            {"masked_pan": "ABCDE****F", "status": "NOT_ALLOTTED", "applied_shares": 185, "application_no": "12345"}
        ]
    })
    tracker.record(g6, "Direct API Allotment Report HTML", validate_html_tags(direct_report) and "Steamhouse India" in direct_report)

    # ---------------------------------------------------------
    # SUITE 7: Dispatch State Concurrency & Idempotency
    # ---------------------------------------------------------
    g7 = "7. Dispatch State & Concurrency"

    test_dispatch_key = "_unit_test_dispatch"
    _record_dispatch(test_dispatch_key)
    tracker.record(g7, "Dispatch Recording", has_dispatched_today(test_dispatch_key) is True)

    fake_key = "_non_existent_dispatch_key_999"
    tracker.record(g7, "Non-existent Dispatch Check", has_dispatched_today(fake_key) is False)

    # Clean up test key from state file
    try:
        from tracker import DISPATCH_STATE_FILE
        if DISPATCH_STATE_FILE.exists():
            with open(DISPATCH_STATE_FILE, "r", encoding="utf-8") as f:
                d_data = json.load(f)
            d_data.pop(test_dispatch_key, None)
            with open(DISPATCH_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(d_data, f, indent=2)
    except Exception:
        pass

    # ---------------------------------------------------------
    # SUITE 8: Scraper Failover, Resilient Cache & Low-GMP Gating
    # ---------------------------------------------------------
    g8 = "8. Scraper Failover & Low-GMP Gating"

    # 1. InvestorGain Parsing & SME Exclusion
    mock_ig_html = """
    <table>
      <tr><th>H1</th></tr>
      <tr><th>H2</th></tr>
      <tr>
        <td>Tonbo Imaging India Ltd</td>
        <td>₹520 (74.29%)</td>
        <td>₹665 - ₹700</td>
        <td>₹700</td>
        <td>₹700</td>
        <td>₹1,220</td>
        <td>74.29%</td>
        <td>15-Oct</td>
        <td>19-Oct</td>
      </tr>
      <tr>
        <td>Shellz India Ltd SME IPO</td>
        <td>₹30 (16.76%)</td>
        <td>₹170 - ₹179</td>
        <td>₹179</td>
        <td>₹179</td>
        <td>₹209</td>
        <td>16.76%</td>
        <td>15-Oct</td>
        <td>19-Oct</td>
      </tr>
    </table>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = mock_ig_html
    with patch("requests.get", return_value=mock_resp):
        from scraper import fetch_mainboard_ipos_investorgain
        ig_results = fetch_mainboard_ipos_investorgain()
        ig_pass = (
            len(ig_results) == 1
            and ig_results[0]["name"] == "Tonbo Imaging India"
            and ig_results[0]["gmp_rs"] == 520.0
            and ig_results[0]["gmp_percent"] == 74.29
            and ig_results[0]["start_date"] == "15 Oct"
            and ig_results[0]["last_filing_date"] == "19 Oct"
        )
        tracker.record(g8, "InvestorGain Mainboard Parsing & SME Exclusion", ig_pass)

    # 2. Scraper Failover (IPOWatch -> InvestorGain)
    mock_secondary_data = [{"name": "Failover IPO", "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "Open", "gmp_percent": 20.0, "price_band": "₹500"}]
    with patch("scraper.fetch_mainboard_ipos_ipowatch", return_value=[]), \
         patch("scraper.fetch_mainboard_ipos_investorgain", return_value=mock_secondary_data), \
         patch("builtins.open", create=True):
        from scraper import get_all_mainboard_ipos
        failover_res = get_all_mainboard_ipos()
        tracker.record(g8, "Failover from IPOWatch to InvestorGain", len(failover_res) == 1 and failover_res[0]["name"] == "Failover IPO")

    # 3. Resilient Cache Retention (>6h old cache not discarded)
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    mock_cache_data = {
        "_cached_at": old_iso,
        "data": [
            {"name": "Bonfiglioli Transmissions", "start_date": "15 Oct", "last_filing_date": today_str, "status": "Upcoming", "gmp_percent": 22.2, "price_band": "₹586"}
        ]
    }
    with patch("scraper.fetch_mainboard_ipos_ipowatch", return_value=[]), \
         patch("scraper.fetch_mainboard_ipos_investorgain", return_value=[]), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(mock_cache_data))):
        cached_res = get_all_mainboard_ipos()
        cache_survives = len(cached_res) == 1 and cached_res[0]["name"] == "Bonfiglioli Transmissions"
        date_recomputed = cached_res[0].get("closing_today") is True and cached_res[0].get("status") == "Open"
        tracker.record(g8, "Resilient Cache Retained (>6h old)", cache_survives)
        tracker.record(g8, "Cache Dynamic Date Recomputation", date_recomputed)

    # 4. Low-GMP Closing-Today Retention (Zetwerk 3.3%)
    mock_classified_input = [
        {"name": "Tonbo Imaging", "gmp_percent": 74.3, "start_date": "15 Oct", "last_filing_date": today_str, "closing_today": True, "status": "Open"},
        {"name": "Zetwerk", "gmp_percent": 3.3, "start_date": "15 Oct", "last_filing_date": today_str, "closing_today": True, "status": "Open"},
        {"name": "Subdued Non-Closing", "gmp_percent": 4.0, "start_date": "15 Oct", "last_filing_date": future_str, "closing_today": False, "status": "Open"},
    ]
    with patch("scraper.get_all_mainboard_ipos", return_value=mock_classified_input):
        c_active, c_upcoming = get_classified_ipos(threshold=10.0)
        c_names = [x["name"] for x in c_active]
        tracker.record(g8, "Low-GMP Closing-Today Retained (<10%)", "Zetwerk" in c_names and "Tonbo Imaging" in c_names)
        tracker.record(g8, "Low-GMP Non-Closing Excluded", "Subdued Non-Closing" not in c_names and "Subdued Non-Closing" not in [x["name"] for x in c_upcoming])

    # 5. Subdued GMP Alert Section Formatting & Tag Balance
    mock_morning_input = [
        {"name": "Tonbo Imaging", "price_band": "₹700", "gmp_rs": 520.0, "gmp_percent": 74.3, "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "Open", "closing_today": True},
        {"name": "Zetwerk", "price_band": "₹151", "gmp_rs": 5.0, "gmp_percent": 3.3, "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "Open", "closing_today": True},
    ]
    morning_formatted = format_morning_alert(mock_morning_input, [])
    has_subdued_hdr = "ALSO CLOSING TODAY (Subdued GMP &lt; 10%)" in morning_formatted
    has_both = "Tonbo Imaging" in morning_formatted and "Zetwerk" in morning_formatted
    tags_valid = validate_html_tags(morning_formatted)
    tracker.record(g8, "Subdued GMP Alert Section & HTML Balance", has_subdued_hdr and has_both and tags_valid)

    return tracker


def build_concise_admin_report(tracker: TestResultTracker) -> str:
    """Format an executive, concise report suitable for Telegram delivery to Admin."""
    today_str = datetime.now().strftime("%d %b %Y • %I:%M %p IST")
    status_icon = "✅" if tracker.all_passed else "❌"
    overall_status = "ALL PASSED" if tracker.all_passed else "FAILED"

    lines = [
        f"🧪 <b>[ADMIN] IPO Tracker Engine Test Report</b>",
        f"📅 <i>{today_str}</i>",
        "────────────────────────",
        f"<b>Overall: {status_icon} {overall_status} ({tracker.passed_tests}/{tracker.total_tests} Tests Passed)</b>",
        f"⏱️ <i>Execution Time: {tracker.duration_sec:.2f}s</i>",
        "────────────────────────"
    ]

    for group, tests in tracker.groups.items():
        group_passed = sum(1 for _, p, _ in tests if p)
        group_total = len(tests)
        g_icon = "🟢" if group_passed == group_total else "🔴"
        lines.append(f"{g_icon} <b>{group}:</b> {group_passed}/{group_total}")

    lines.append("────────────────────────")
    if tracker.all_passed:
        lines.append("🚀 <b>System Status:</b> Fully healthy, robust & production ready!")
    else:
        lines.append("⚠️ <b>Failures Detected:</b>")
        for group, tests in tracker.groups.items():
            for name, passed, detail in tests:
                if not passed:
                    lines.append(f"• [{group}] {name}: {detail}")

    return "\n".join(lines).strip()


def send_test_report_to_admin(tracker: TestResultTracker) -> bool:
    """Send the concise test report directly to the Admin Telegram chat ID."""
    report_msg = build_concise_admin_report(tracker)
    admin_id = getattr(Config, "ADMIN_CHAT_ID", "2056597708")
    notifier = TelegramNotifier()
    return notifier.send_direct(admin_id, report_msg)


if __name__ == "__main__":
    notify_admin = "--notify-admin" in sys.argv or "-n" in sys.argv
    print("\n🔍 Running Comprehensive IPO Tracker Test Suite...\n")
    tracker = run_all_tests()

    for group, tests in tracker.groups.items():
        print(f"\n📁 {group}:")
        for name, passed, detail in tests:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status:<8} {name}")

    print("\n" + "=" * 60)
    print(f"Summary: {tracker.passed_tests}/{tracker.total_tests} passed in {tracker.duration_sec:.2f}s")
    print("=" * 60 + "\n")

    if notify_admin:
        print(f"📲 Sending Concise Test Report to Admin ({Config.ADMIN_CHAT_ID})...")
        ok = send_test_report_to_admin(tracker)
        if ok:
            print("✅ Report successfully delivered to Admin on Telegram!")
        else:
            print("❌ Failed to deliver report to Admin.")
    else:
        print("💡 To also notify admin on Telegram, run: python test_suite.py --notify-admin")

    sys.exit(0 if tracker.all_passed else 1)
