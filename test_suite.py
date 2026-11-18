"""
Comprehensive, Enterprise-Grade Automated Test Suite for Indian Mainboard IPO Tracker.
Covers critical edge cases, boundaries, and failure modes across:
  1. Scraper Parsing & Text Normalization
  2. Date Parsing & Calendar Boundaries
  3. Dynamic Lifecycle & Status Evaluation
  4. Alert Formatting & Telegram HTML Compliance
  5. PAN Security & AES-256 Cryptography
  6. Allotment Pipeline & Registrar Mapping
  7. Dispatch State Idempotency & Concurrency
  8. Scraper Failovers, Resilient Cache & Low-GMP Gating
  9. Subscriber Management & Bot Commands
  10. Notifier Resilience & Network Error Handling

Can be executed anytime via CLI:
  python test_suite.py [--notify-admin]
"""

import sys
import os
import re
import time
import json
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Any
import requests
from unittest.mock import patch, MagicMock, mock_open

# Ensure UTF-8 console encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import Config
from scraper import (
    _clean_text,
    _parse_currency,
    _parse_price_band,
    _clean_company_name_and_status,
    _parse_dates,
    parse_date_str_to_date,
    _recompute_ipo_status_and_closing,
    fetch_mainboard_ipos_ipowatch,
    fetch_mainboard_ipos_investorgain,
    fetch_mainboard_ipos_ipoguru,
    get_all_mainboard_ipos,
)
from tracker import (
    format_ipo_dates,
    format_morning_alert,
    format_reminder_alert,
    get_classified_ipos,
    has_dispatched_today,
    _record_dispatch,
    BROKER_APP_LINKS,
)
from pan_checker import (
    extract_pans,
    mask_pan,
    check_kfintech_pan,
    format_allotment_report,
)
from crypto_utils import encrypt_pan, decrypt_pan
from notifiers.telegram_notifier import TelegramNotifier
from notifiers.console import ConsoleNotifier
from subscriber_manager import (
    _telegram_post_with_retry,
    load_subscribers_registry,
    save_subscribers_registry,
    deactivate_subscriber,
    process_incoming_telegram_updates,
)
from allotment_tracker import normalize_key


class TestResultTracker:
    def __init__(self):
        self.groups: Dict[str, List[Tuple[str, bool, str]]] = {}
        self.group_times: Dict[str, float] = {}
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
    """Execute all 10 unit test suites with full isolation and sub-second speed."""
    # Quiet expected error and warning logs during intentional negative testing
    prev_log_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)

    tracker = TestResultTracker()

    try:
        # ---------------------------------------------------------
        # SUITE 1: Scraper Parsing & Text Normalization
        # ---------------------------------------------------------
        g1 = "1. Scraper Parsing & Text Normalization"
        t_start = time.time()

        # Price Band
        tracker.record(g1, "Price Band: Range ('168 to 177')", _parse_price_band("168 to 177") == 177.0)
        tracker.record(g1, "Price Band: Single ('₹586')", _parse_price_band("₹586") == 586.0)
        tracker.record(g1, "Price Band: Comma ('₹1,119')", _parse_price_band("₹1,119") == 1119.0)
        tracker.record(g1, "Price Band: Dual Symbol Range ('₹1,200 to ₹1,250')", _parse_price_band("₹1,200 to ₹1,250") == 1250.0)
        tracker.record(g1, "Price Band: Hyphen Range ('100 - 120')", _parse_price_band("100 - 120") == 120.0)
        tracker.record(g1, "Price Band: Invalid Placeholder ('TBA')", _parse_price_band("TBA") == 0.0)
        tracker.record(g1, "Price Band: Dash Only ('-')", _parse_price_band("-") == 0.0)
        tracker.record(g1, "Price Band: Empty String ('')", _parse_price_band("") == 0.0)

        # Currency
        tracker.record(g1, "Currency: Standard ('₹225')", _parse_currency("₹225") == 225.0)
        tracker.record(g1, "Currency: Decimal ('₹130.50')", _parse_currency("₹130.50") == 130.5)
        tracker.record(g1, "Currency: 'Rs.' Prefix ('Rs. 450')", _parse_currency("Rs. 450") == 450.0)
        tracker.record(g1, "Currency: Comma with Decimal ('₹1,250.75')", _parse_currency("₹1,250.75") == 1250.75)
        tracker.record(g1, "Currency: Zero ('0')", _parse_currency("0") == 0.0)
        tracker.record(g1, "Currency: Dash ('-')", _parse_currency("-") == 0.0)

        # Clean Company Name & Embedded Status
        n1, s1 = _clean_company_name_and_status("Bonfiglioli Transmissions  Open")
        tracker.record(g1, "Clean Name: Embedded 'Open'", n1 == "Bonfiglioli Transmissions" and s1 == "Open")

        n2, s2 = _clean_company_name_and_status("Fusion CX (C)")
        tracker.record(g1, "Clean Name: Embedded '(C)' -> Closed", n2 == "Fusion CX" and s2 == "Closed")

        n3, s3 = _clean_company_name_and_status("HD Fire Protect (c)")
        tracker.record(g1, "Clean Name: Embedded '(c)' lower -> Closed", n3 == "HD Fire Protect" and s3 == "Closed")

        n4, s4 = _clean_company_name_and_status("Paras HealthcareUpcoming")
        tracker.record(g1, "Clean Name: Embedded 'Upcoming'", n4 == "Paras Healthcare" and s4 == "Upcoming")

        n5, s5 = _clean_company_name_and_status("Acme Industries Closed")
        tracker.record(g1, "Clean Name: Embedded 'Closed'", n5 == "Acme Industries" and s5 == "Closed")

        tracker.record(g1, "Clean Text: HTML Entities & Space Normalization", _clean_text("Acme&nbsp;Corp  ") == "Acme Corp")

        n6, s6 = _clean_company_name_and_status("Tata Motors Ltd")
        tracker.record(g1, "Clean Name: Plain Name Unchanged", n6 == "Tata Motors Ltd" and s6 == "")
        tracker.group_times[g1] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 2: Date Parsing & Calendar Boundaries
        # ---------------------------------------------------------
        g2 = "2. Date Parsing & Calendar Boundaries"
        t_start = time.time()

        tracker.record(g2, "Range: Hyphenated ('15-19 Oct')", _parse_dates("15-19 Oct") == ("15 Oct", "19 Oct"))
        tracker.record(g2, "Range: Space Padded ('21 - 23 Oct')", _parse_dates("21 - 23 Oct") == ("21 Oct", "23 Oct"))
        tracker.record(g2, "Range: Cross-Month ('28 Aug - 1 Sept')", _parse_dates("28 Aug - 1 Sept") == ("28 Aug", "1 Sept"))
        tracker.record(g2, "Range: Word 'to' ('10 to 15 Sept')", _parse_dates("10 to 15 Sept") == ("10 Sept", "15 Sept"))
        tracker.record(g2, "Range: Month First ('Oct 15 - 19')", _parse_dates("Oct 15 - 19") == ("15 Oct", "19 Oct"))
        tracker.record(g2, "Range: Month First Dual ('Oct 15 - Oct 19')", _parse_dates("Oct 15 - Oct 19") == ("15 Oct", "19 Oct"))
        tracker.record(g2, "Single Day: Day First ('16 Oct')", _parse_dates("16 Oct") == ("16 Oct", "16 Oct"))
        tracker.record(g2, "Single Day: Month First ('Oct 16')", _parse_dates("Oct 16") == ("16 Oct", "16 Oct"))
        tracker.record(g2, "Placeholder: 'TBA'", _parse_dates("TBA") == ("TBA", "TBA"))
        tracker.record(g2, "Placeholder: Dash ('-')", _parse_dates("-") == ("TBA", "TBA"))

        # parse_date_str_to_date
        dt1 = parse_date_str_to_date("19 Oct")
        dt2 = parse_date_str_to_date("Oct 19")
        tracker.record(g2, "parse_date_str: Day vs Month First Equivalence", dt1 is not None and dt2 is not None and dt1.day == 19 and dt1.month == 10 and dt2.day == 19)

        dt3 = parse_date_str_to_date("15 Sept")
        dt4 = parse_date_str_to_date("15 Sep")
        tracker.record(g2, "parse_date_str: 4-letter ('Sept') vs 3-letter ('Sep')", dt3 is not None and dt4 is not None and dt3.month == 9 and dt4.month == 9)

        tracker.record(g2, "parse_date_str: Invalid Format ('InvalidDate')", parse_date_str_to_date("InvalidDate") is None)
        tracker.record(g2, "parse_date_str: Empty / TBA Inputs", parse_date_str_to_date("TBA") is None and parse_date_str_to_date("") is None)
        tracker.group_times[g2] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 3: Dynamic Lifecycle & Status Evaluation
        # ---------------------------------------------------------
        g3 = "3. Dynamic Lifecycle & Status Evaluation"
        t_start = time.time()

        now = datetime.now()
        today_str = now.strftime("%d %b")
        yesterday_str = (now - timedelta(days=2)).strftime("%d %b")
        tomorrow_str = (now + timedelta(days=1)).strftime("%d %b")
        future_str = (now + timedelta(days=5)).strftime("%d %b")

        # 1. Past IPO -> Closed
        past_ipo = {"name": "Past Corp", "start_date": "10 Aug", "last_filing_date": yesterday_str, "status": "Open", "price_band": "₹100"}
        _recompute_ipo_status_and_closing(past_ipo)
        tracker.record(g3, "Past IPO Auto-Closed", past_ipo["status"] == "Closed" and not past_ipo["closing_today"])

        # 2. Closing Today
        closing_ipo = {"name": "Closing Corp", "start_date": yesterday_str, "last_filing_date": today_str, "status": "Upcoming"}
        _recompute_ipo_status_and_closing(closing_ipo)
        tracker.record(g3, "Closing Today Detection", closing_ipo["closing_today"] is True and closing_ipo["status"] == "Open")

        # 3. Currently Open
        open_ipo = {"name": "Open Corp", "start_date": yesterday_str, "last_filing_date": tomorrow_str, "status": "Upcoming"}
        _recompute_ipo_status_and_closing(open_ipo)
        tracker.record(g3, "Currently Open Detection", open_ipo["status"] == "Open" and not open_ipo["closing_today"])

        # 4. Future Upcoming
        up_ipo = {"name": "Upcoming Corp", "start_date": tomorrow_str, "last_filing_date": future_str, "status": "Upcoming"}
        _recompute_ipo_status_and_closing(up_ipo)
        tracker.record(g3, "Future Upcoming Detection", up_ipo["status"] == "Upcoming" and not up_ipo["closing_today"])

        # 5. Single-day IPO (opens & closes today)
        single_day_ipo = {"name": "SingleDay Corp", "start_date": today_str, "last_filing_date": today_str, "status": "Upcoming"}
        _recompute_ipo_status_and_closing(single_day_ipo)
        tracker.record(g3, "Single-day IPO Opens & Closes Today", single_day_ipo["closing_today"] is True and single_day_ipo["status"] == "Open")

        # 6. Missing start date with future closing
        tba_start_ipo = {"name": "TBA Start Corp", "start_date": "TBA", "last_filing_date": tomorrow_str, "status": "Open"}
        _recompute_ipo_status_and_closing(tba_start_ipo)
        tracker.record(g3, "TBA Start Date with Future Closing", tba_start_ipo["status"] == "Open" and not tba_start_ipo["closing_today"])

        # 7. Both dates TBA
        all_tba_ipo = {"name": "All TBA Corp", "start_date": "TBA", "last_filing_date": "TBA", "status": "Upcoming"}
        _recompute_ipo_status_and_closing(all_tba_ipo)
        tracker.record(g3, "Both Dates TBA Retains Original Status", all_tba_ipo["status"] == "Upcoming" and not all_tba_ipo["closing_today"])

        # 8. Preservation of other metadata fields
        meta_ipo = {"name": "Meta Corp", "price_band": "₹500", "gmp_percent": 45.0, "start_date": yesterday_str, "last_filing_date": today_str}
        _recompute_ipo_status_and_closing(meta_ipo)
        tracker.record(g3, "Non-lifecycle Fields Preserved Intact", meta_ipo.get("price_band") == "₹500" and meta_ipo.get("gmp_percent") == 45.0)
        tracker.group_times[g3] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 4: Alert Formatting & Telegram HTML Compliance
        # ---------------------------------------------------------
        g4 = "4. Alert Formatting & Telegram HTML Compliance"
        t_start = time.time()

        # format_ipo_dates
        tracker.record(g4, "Format Range ('15 Oct – 19 Oct')", format_ipo_dates({"start_date": "15 Oct", "last_filing_date": "19 Oct"}) == "15 Oct – 19 Oct")
        tracker.record(g4, "Format Single Day ('21 Oct')", format_ipo_dates({"start_date": "21 Oct", "last_filing_date": "21 Oct"}) == "21 Oct")
        tracker.record(g4, "Format Missing Start ('Closes 23 Oct')", format_ipo_dates({"start_date": "TBA", "last_filing_date": "23 Oct"}) == "Closes 23 Oct")
        tracker.record(g4, "Format Missing End ('Opens 15 Oct')", format_ipo_dates({"start_date": "15 Oct", "last_filing_date": "TBA"}) == "Opens 15 Oct")
        tracker.record(g4, "Format All TBA ('TBA')", format_ipo_dates({"start_date": "TBA", "last_filing_date": "TBA"}) == "TBA")

        # Morning Alert HTML and Content
        mock_active = [
            {"name": "Tonbo Imaging", "price_band": "₹700", "gmp_rs": 516.0, "gmp_percent": 73.7, "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "OPEN", "closing_today": False},
            {"name": "Sahajanand Medical", "price_band": "₹344", "gmp_rs": 35.0, "gmp_percent": 10.2, "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "OPEN", "closing_today": False},
            {"name": "Subdued Closing", "price_band": "₹150", "gmp_rs": 5.0, "gmp_percent": 3.3, "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "OPEN", "closing_today": True}
        ]
        mock_upcoming = [
            {"name": "Jio Platforms", "price_band": "₹1,119", "gmp_rs": 225.0, "gmp_percent": 20.1, "start_date": "21 Oct", "last_filing_date": "23 Oct", "status": "UPCOMING", "closing_today": False}
        ]
        morning_text = format_morning_alert(mock_active, mock_upcoming)
        tracker.record(g4, "Morning Alert: HTML Tag Balance", validate_html_tags(morning_text))
        tracker.record(g4, "Morning Alert: Modern Header ('IPO Date:') Present", "IPO Date:" in morning_text)
        tracker.record(g4, "Morning Alert: Legacy Header ('Last Filing:') Absent", "Last Filing:" not in morning_text)
        tracker.record(g4, "Morning Alert: Strong Conviction Section (>15%)", "STRONG CONVICTION (GMP &gt; 15%)" in morning_text and "Tonbo Imaging" in morning_text)
        tracker.record(g4, "Morning Alert: Moderate Section (10%-15%)", "MODERATE GMP (10% – 15%)" in morning_text and "Sahajanand Medical" in morning_text)
        tracker.record(g4, "Morning Alert: Subdued Closing Today Section", "ALSO CLOSING TODAY (Subdued GMP &lt; 10%)" in morning_text and "Subdued Closing" in morning_text)

        # Empty Active Morning Alert
        empty_morning_text = format_morning_alert([], mock_upcoming)
        tracker.record(g4, "Morning Alert: Empty Active Notice", "No Mainboard IPOs are currently active" in empty_morning_text)
        tracker.record(g4, "Morning Alert: Character Limit Safe (< 4096 chars)", len(morning_text) < 4096 and len(empty_morning_text) < 4096)

        # Reminder Alert HTML and Content
        closing_only = [{"name": "Urgent Corp", "price_band": "₹200", "gmp_rs": 40.0, "gmp_percent": 20.0, "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "Open", "closing_today": True}]
        reminder_text, is_closing = format_reminder_alert(closing_only)
        tracker.record(g4, "Reminder Alert: Tag Balance", validate_html_tags(reminder_text))
        tracker.record(g4, "Reminder Alert: Urgent Closing Returns True", is_closing is True)
        tracker.record(g4, "Reminder Alert: Cut-off Notice Included", "5:00 PM IST" in reminder_text)

        open_only = [{"name": "Open Corp", "price_band": "₹200", "gmp_rs": 40.0, "gmp_percent": 20.0, "start_date": "15 Oct", "last_filing_date": "25 Oct", "status": "open", "closing_today": False}]
        open_rem_text, is_closing_open = format_reminder_alert(open_only)
        tracker.record(g4, "Reminder Alert: Open Only Returns False", is_closing_open is False and "Active Mainboard IPOs OPEN" in open_rem_text)

        empty_rem_text, is_empty = format_reminder_alert([])
        tracker.record(g4, "Reminder Alert: Empty Returns Empty & False", empty_rem_text == "" and is_empty is False)

        # Broker links
        broker_urls_valid = all(url.startswith("https://") for url in BROKER_APP_LINKS.values())
        tracker.record(g4, "Broker Referral Links Valid HTTPS URLs", broker_urls_valid)
        tracker.group_times[g4] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 5: PAN Security & AES-256 Cryptography
        # ---------------------------------------------------------
        g5 = "5. PAN Security & AES-256 Cryptography"
        t_start = time.time()

        # Extraction
        sample_text = "Here are PANs: ABCDE1234F, abcde1234f, BCDEF2345G and bad ones 12345ABCDE, XYZ123."
        extracted = extract_pans(sample_text)
        tracker.record(g5, "PAN Extraction: Regex & Deduplication", extracted == ["ABCDE1234F", "BCDEF2345G"])

        prose_sample = "Check PAN (ABCDE1234F) and [BCDEF2345G] please."
        tracker.record(g5, "PAN Extraction: Embedded within Prose & Brackets", extract_pans(prose_sample) == ["ABCDE1234F", "BCDEF2345G"])

        invalid_sample = "12345ABCDE, ABCDE12345, ABC1234F, ABCDEF1234G"
        tracker.record(g5, "PAN Extraction: Rejection of Invalid Structures", extract_pans(invalid_sample) == [])

        # Masking
        tracker.record(g5, "PAN Masking: Standard ('ABCDE****F')", mask_pan("ABCDE1234F") == "ABCDE****F")
        tracker.record(g5, "PAN Masking: Short/Invalid Inputs Safe", mask_pan("ABC") == "ABC" and mask_pan("") == "")

        # AES-256 Fernet Cryptography
        original_pan = "AAAPA1234M"
        encrypted = encrypt_pan(original_pan)
        decrypted = decrypt_pan(encrypted)
        tracker.record(g5, "AES-256: Ciphertext Prefix ('enc:')", encrypted.startswith("enc:"))
        tracker.record(g5, "AES-256: Roundtrip Encryption/Decryption", decrypted == original_pan)
        tracker.record(g5, "AES-256: Encryption Idempotency", encrypt_pan(encrypted) == encrypted)
        tracker.record(g5, "AES-256: Legacy Plaintext Pass-Through", decrypt_pan("XYZPA9999Z") == "XYZPA9999Z")
        tracker.record(g5, "AES-256: Corrupted Ciphertext Graceful Handling", decrypt_pan("enc:corrupted_token_123") == "enc:corrupted_token_123")
        tracker.record(g5, "AES-256: Empty / None Inputs", encrypt_pan("") == "" and decrypt_pan("") == "")
        tracker.group_times[g5] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 6: Allotment Pipeline & Registrar Mapping
        # ---------------------------------------------------------
        g6 = "6. Allotment Pipeline & Registrar Mapping"
        t_start = time.time()

        n1 = normalize_key("Manipal Payment And Identity Solutions Limited - IPO")
        n2 = normalize_key("Manipal Payment and Identity Solutions Ltd")
        tracker.record(g6, "Registrar Company Name Normalization", n1 == n2)
        tracker.record(g6, "Normalization Suffix Stripping ('Limited/Ltd/IPO/SME')", normalize_key("Acme Tech SME Limited IPO") == "acmetech")

        # Allotment Report Formatter (Captcha Required)
        captcha_report = format_allotment_report({
            "captcha_required": True,
            "company_name": "Test Captcha IPO",
            "registrar": "Link Intime",
            "portal_url": "https://linkintime.co.in"
        })
        tracker.record(g6, "Captcha Allotment Report HTML & Links", validate_html_tags(captcha_report) and "Link Intime" in captcha_report and "bseindia.com" in captcha_report)

        # Allotment Report Formatter (Direct API Success - Multi-PAN)
        direct_report = format_allotment_report({
            "success": True,
            "company_name": "Steamhouse India",
            "registrar": "KFin Technologies",
            "results": [
                {"masked_pan": "ABCDE****F", "status": "ALLOTTED", "allotted_shares": 185, "applied_shares": 185, "application_no": "APP123", "category": "RETAIL"},
                {"masked_pan": "BCDEF****G", "status": "NOT_ALLOTTED", "allotted_shares": 0, "applied_shares": 185, "application_no": "APP124"},
                {"masked_pan": "CDEFG****H", "status": "NOT_FOUND", "allotted_shares": 0, "applied_shares": 0}
            ]
        })
        tracker.record(g6, "Direct API Allotment Report HTML Balance", validate_html_tags(direct_report))
        tracker.record(g6, "Direct API Allotted Status Formatting", "ALLOTTED: 185 Shares!" in direct_report)
        tracker.record(g6, "Direct API Not Allotted Formatting", "Status: Not Allotted" in direct_report)
        tracker.record(g6, "Direct API Summary Counts Line", "1 Allotted" in direct_report and "1 Not Allotted" in direct_report and "1 Not Found" in direct_report)

        # KFintech Query Simulation
        mock_kfin_resp = MagicMock()
        mock_kfin_resp.status_code = 200
        mock_kfin_resp.json.return_value = [{"All_Shares": "150", "App_Shares": "150", "Name": "Investor", "Appln_No": "1001", "category": "RETAIL"}]
        with patch("requests.get", return_value=mock_kfin_resp):
            res = check_kfintech_pan("123", "ABCDE1234F")
            tracker.record(g6, "KFintech API Query: Success (Allotted)", res.get("status") == "ALLOTTED" and res.get("allotted_shares") == 150)

        mock_kfin_404 = MagicMock()
        mock_kfin_404.status_code = 404
        with patch("requests.get", return_value=mock_kfin_404):
            res_404 = check_kfintech_pan("123", "ABCDE1234F")
            tracker.record(g6, "KFintech API Query: 404 Not Found", res_404.get("status") == "NOT_FOUND")

        with patch("requests.get", side_effect=requests.exceptions.Timeout("Timed out")):
            res_timeout = check_kfintech_pan("123", "ABCDE1234F")
            tracker.record(g6, "KFintech API Query: Timeout Recovery", res_timeout.get("status") == "TIMEOUT")
        tracker.group_times[g6] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 7: Dispatch State Idempotency & Concurrency
        # ---------------------------------------------------------
        g7 = "7. Dispatch State Idempotency & Concurrency"
        t_start = time.time()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dispatch = Path(tmp_dir) / "dispatch_state.json"
            with patch("tracker.DISPATCH_STATE_FILE", tmp_dispatch), \
                 patch("tracker.LEGACY_DISPATCH_FILE", Path(tmp_dir) / "last_dispatch.json"):

                # Fresh state
                tracker.record(g7, "Fresh State: Not Dispatched", has_dispatched_today("morning") is False)

                # Record morning dispatch
                _record_dispatch("morning")
                tracker.record(g7, "Recorded Key: Dispatched Today", has_dispatched_today("morning") is True)
                tracker.record(g7, "Unrecorded Key: Isolation Preserved", has_dispatched_today("reminder") is False)

                # Date rollover test (yesterday's date)
                yesterday_iso = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                with open(tmp_dispatch, "w", encoding="utf-8") as f:
                    json.dump({"morning": yesterday_iso}, f)
                tracker.record(g7, "Date Rollover: Yesterday's Dispatch Returns False", has_dispatched_today("morning") is False)

                # Corrupted JSON recovery
                with open(tmp_dispatch, "w", encoding="utf-8") as f:
                    f.write("corrupted { invalid json")
                tracker.record(g7, "Corrupted JSON Recovery", has_dispatched_today("morning") is False)
        tracker.group_times[g7] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 8: Scraper Failovers, Resilient Cache & Low-GMP Gating
        # ---------------------------------------------------------
        g8 = "8. Scraper Failovers, Resilient Cache & Gating"
        t_start = time.time()

        # 1. IPOWatch HTML parsing
        mock_ipowatch_html = """
        <table>
          <tr><th>IPO Name</th><th>GMP</th><th>Trend</th><th>Price</th><th>Est Listing</th><th>IPO Date</th><th>Status</th></tr>
          <tr><td>Acme Technologies Open</td><td>₹120</td><td>Up</td><td>₹500</td><td>₹620 (24.0%)</td><td>15-19 Oct</td><td>Open</td></tr>
        </table>
        """
        mock_resp_ipowatch = MagicMock()
        mock_resp_ipowatch.status_code = 200
        mock_resp_ipowatch.text = mock_ipowatch_html
        with patch("requests.get", return_value=mock_resp_ipowatch):
            ipowatch_res = fetch_mainboard_ipos_ipowatch()
            tracker.record(g8, "IPOWatch HTML Parsing & GMP Extraction", len(ipowatch_res) == 1 and ipowatch_res[0]["name"] == "Acme Technologies" and ipowatch_res[0]["gmp_percent"] == 24.0)

        # 2. InvestorGain Parsing & SME Exclusion
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
        mock_resp_ig = MagicMock()
        mock_resp_ig.status_code = 200
        mock_resp_ig.text = mock_ig_html
        with patch("requests.get", return_value=mock_resp_ig):
            ig_results = fetch_mainboard_ipos_investorgain()
            ig_pass = len(ig_results) == 1 and ig_results[0]["name"] == "Tonbo Imaging India" and ig_results[0]["gmp_percent"] == 74.29
            tracker.record(g8, "InvestorGain Mainboard Parsing & SME Exclusion", ig_pass)

        # 3. IPOGuru HTML Scraping & SME Exclusion
        mock_guru_html = """
        <table>
          <tr><th>Company</th><th>Issue Price</th><th>IPO GMP</th><th>GMP %</th></tr>
          <tr><td>Tonbo Imaging India Mainboard 15 Oct - 19 Oct</td><td>Rs 700</td><td>Rs 520</td><td>74.29%</td></tr>
          <tr><td>Shellz India SME 15 Oct - 19 Oct</td><td>Rs 179</td><td>Rs 41</td><td>22.91%</td></tr>
        </table>
        """
        mock_guru_resp = MagicMock()
        mock_guru_resp.status_code = 200
        mock_guru_resp.text = mock_guru_html
        with patch("requests.get", return_value=mock_guru_resp), patch("scraper.Config.IPOGURU_API_KEY", ""):
            guru_results = fetch_mainboard_ipos_ipoguru()
            guru_pass = len(guru_results) == 1 and guru_results[0]["name"] == "Tonbo Imaging India" and guru_results[0]["gmp_percent"] == 74.29
            tracker.record(g8, "IPOGuru Live HTML Parsing & SME Exclusion", guru_pass)

        # 4. IPOGuru Developer REST API Parsing
        mock_api_payload = {
            "success": True,
            "data": [
                {"name": "API Test IPO", "type": "Mainboard", "status": "Open", "gmp": {"price": "50", "percentage": "25%", "estimated_listing_price": 250}},
                {"name": "API SME IPO", "type": "SME", "status": "Open", "gmp": {"price": "10", "percentage": "10%", "estimated_listing_price": 110}}
            ]
        }
        mock_api_resp = MagicMock()
        mock_api_resp.status_code = 200
        mock_api_resp.json.return_value = mock_api_payload
        with patch("requests.get", return_value=mock_api_resp), patch("scraper.Config.IPOGURU_API_KEY", "mock_key"):
            api_results = fetch_mainboard_ipos_ipoguru()
            api_pass = len(api_results) == 1 and api_results[0]["name"] == "API Test IPO" and api_results[0]["gmp_percent"] == 25.0
            tracker.record(g8, "IPOGuru Developer API Parsing & Validation", api_pass)

        # 5. Multi-tier Failovers
        mock_guru_failover = [{"name": "Guru Failover", "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "Open", "gmp_percent": 18.0, "price_band": "₹300"}]
        with patch("scraper.fetch_mainboard_ipos_ipowatch", return_value=[]), \
             patch("scraper.fetch_mainboard_ipos_ipoguru", return_value=mock_guru_failover), \
             patch("builtins.open", create=True):
            res_tier2 = get_all_mainboard_ipos()
            tracker.record(g8, "Tier-2 Failover to IPOGuru", len(res_tier2) == 1 and res_tier2[0]["name"] == "Guru Failover")

        mock_secondary_data = [{"name": "InvestorGain Failover", "start_date": "15 Oct", "last_filing_date": "19 Oct", "status": "Open", "gmp_percent": 20.0, "price_band": "₹500"}]
        with patch("scraper.fetch_mainboard_ipos_ipowatch", return_value=[]), \
             patch("scraper.fetch_mainboard_ipos_ipoguru", return_value=[]), \
             patch("scraper.fetch_mainboard_ipos_investorgain", return_value=mock_secondary_data), \
             patch("builtins.open", create=True):
            res_tier3 = get_all_mainboard_ipos()
            tracker.record(g8, "Tier-3 Failover to InvestorGain", len(res_tier3) == 1 and res_tier3[0]["name"] == "InvestorGain Failover")

        # 6. Resilient Cache Retention (>6h old cache not discarded) & Dynamic Date Recomputation
        old_iso = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        mock_cache_data = {
            "_cached_at": old_iso,
            "data": [
                {"name": "Bonfiglioli Transmissions", "start_date": "15 Oct", "last_filing_date": today_str, "status": "Upcoming", "gmp_percent": 22.2, "price_band": "₹586"}
            ]
        }
        with patch("scraper.fetch_mainboard_ipos_ipowatch", return_value=[]), \
             patch("scraper.fetch_mainboard_ipos_ipoguru", return_value=[]), \
             patch("scraper.fetch_mainboard_ipos_investorgain", return_value=[]), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(mock_cache_data))):
            cached_res = get_all_mainboard_ipos()
            cache_survives = len(cached_res) == 1 and cached_res[0]["name"] == "Bonfiglioli Transmissions"
            date_recomputed = cached_res[0].get("closing_today") is True and cached_res[0].get("status") == "Open"
            tracker.record(g8, "Resilient Cache Retained (>6h old)", cache_survives)
            tracker.record(g8, "Cache Dynamic Date Recomputation", date_recomputed)

        # 7. Low-GMP Closing-Today Retention (Zetwerk 3.3%)
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
            tracker.record(g8, "Active IPOs Sorted Descending by GMP %", c_active[0]["gmp_percent"] >= c_active[1]["gmp_percent"])
        tracker.group_times[g8] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 9: Subscriber Management & Bot Commands
        # ---------------------------------------------------------
        g9 = "9. Subscriber Management & Bot Commands"
        t_start = time.time()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_sub_file = Path(tmp_dir) / "subscribers.json"
            with patch("subscriber_manager.SUBSCRIBERS_FILE", tmp_sub_file):
                # Baseline test
                reg = load_subscribers_registry()
                tracker.record(g9, "Registry Baseline Auto-Initialization", "2056597708" in reg and reg["2056597708"]["role"] == "admin")

                # Save with PAN cards
                reg["2056597708"]["pans"] = ["ABCDE1234F", "BCDEF2345G"]
                save_subscribers_registry(reg)

                # Check that on-disk representation is encrypted
                with open(tmp_sub_file, "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
                p1_disk = disk_data["2056597708"]["pans"][0]
                tracker.record(g9, "On-Disk Registry: PAN Encrypted with 'enc:'", p1_disk.startswith("enc:"))

                # Reload and verify in-memory decryption
                reloaded = load_subscribers_registry()
                p1_mem = reloaded["2056597708"]["pans"][0]
                tracker.record(g9, "In-Memory Registry: PAN Decrypted to Plaintext", p1_mem == "ABCDE1234F")

                # Deactivation
                deactivate_subscriber("2056597708", "blocked")
                reg_deactivated = load_subscribers_registry()
                tracker.record(g9, "User Deactivation Status Update", reg_deactivated["2056597708"].get("status") == "blocked")

                # Corrupted file recovery
                with open(tmp_sub_file, "w", encoding="utf-8") as f:
                    f.write("corrupted json {")
                recovered = load_subscribers_registry()
                tracker.record(g9, "Corrupted subscribers.json Recovery", "2056597708" in recovered)

                # Bot Command: /pan with valid PANs
                updates_pan = [{
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 999999, "first_name": "Test", "username": "testuser"},
                        "text": "/pan ABCDE1234F, BCDEF2345G"
                    }
                }]
                mock_up_resp = MagicMock()
                mock_up_resp.json.return_value = {"ok": True, "result": updates_pan}
                with patch("requests.get", return_value=mock_up_resp), \
                     patch("subscriber_manager._telegram_post_with_retry", return_value=True), \
                     patch("subscriber_manager.Config.TELEGRAM_BOT_TOKEN", "mock_token"):
                    process_incoming_telegram_updates(notify_admin=False)
                    updated_reg = load_subscribers_registry()
                    user_pans = updated_reg.get("999999", {}).get("pans", [])
                    tracker.record(g9, "Command /pan: Saves Multiple PANs", "ABCDE1234F" in user_pans and "BCDEF2345G" in user_pans)

                # Bot Command: /removepan
                updates_clear = [{
                    "update_id": 2,
                    "message": {
                        "chat": {"id": 999999, "first_name": "Test", "username": "testuser"},
                        "text": "/removepan"
                    }
                }]
                mock_clear_resp = MagicMock()
                mock_clear_resp.json.return_value = {"ok": True, "result": updates_clear}
                with patch("requests.get", return_value=mock_clear_resp), \
                     patch("subscriber_manager._telegram_post_with_retry", return_value=True), \
                     patch("subscriber_manager.Config.TELEGRAM_BOT_TOKEN", "mock_token"):
                    process_incoming_telegram_updates(notify_admin=False)
                    cleared_reg = load_subscribers_registry()
                    tracker.record(g9, "Command /removepan: Clears Saved PANs", cleared_reg.get("999999", {}).get("pans") == [])
        tracker.group_times[g9] = time.time() - t_start

        # ---------------------------------------------------------
        # SUITE 10: Notifier Resilience & Network Error Handling
        # ---------------------------------------------------------
        g10 = "10. Notifier Resilience & Network Error Handling"
        t_start = time.time()

        # 1. Post with Retry: Success HTTP 200
        mock_post_ok = MagicMock()
        mock_post_ok.json.return_value = {"ok": True}
        with patch("requests.post", return_value=mock_post_ok):
            ok = _telegram_post_with_retry("token", {"chat_id": "123", "text": "hello"})
            tracker.record(g10, "Telegram Post: Success HTTP 200", ok is True)

        # 2. Post with Retry: Parse Error Recovery (strips parse_mode and succeeds)
        mock_post_parse_err = MagicMock()
        mock_post_parse_err.json.side_effect = [
            {"ok": False, "error_code": 400, "description": "Bad Request: can't parse entities"},
            {"ok": True}
        ]
        with patch("requests.post", return_value=mock_post_parse_err):
            payload = {"chat_id": "123", "text": "<b>unclosed tag", "parse_mode": "HTML"}
            ok_recovery = _telegram_post_with_retry("token", payload)
            tracker.record(g10, "Telegram Post: Parse Error Fallback to Plain Text", ok_recovery is True and "parse_mode" not in payload)

        # 3. Post with Retry: Permanent Client Error HTTP 403 (User blocked bot)
        mock_post_403 = MagicMock()
        mock_post_403.json.return_value = {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}
        with patch("requests.post", return_value=mock_post_403):
            ok_403 = _telegram_post_with_retry("token", {"chat_id": "123", "text": "hello"}, max_retries=2)
            tracker.record(g10, "Telegram Post: Permanent Error HTTP 403 No Loop", ok_403 is False)

        # 4. TelegramNotifier: Missing Token Handled Safely
        notifier_no_token = TelegramNotifier(bot_token="")
        tracker.record(g10, "TelegramNotifier: Missing Token Returns False Gracefully", notifier_no_token.send_direct("123", "msg") is False)

        # 5. ConsoleNotifier: Dispatch without Error
        console_notifier = ConsoleNotifier()
        with patch("builtins.print"):
            console_res = console_notifier.send(["admin"], "Test message")
        tracker.record(g10, "ConsoleNotifier: Dispatches without Error", console_res.get("success") is True)

        # 6. Admin Test Report Generator HTML Balance & Summary
        report_text = build_concise_admin_report(tracker)
        tracker.record(g10, "Admin Report: HTML Tag Balance", validate_html_tags(report_text))
        tracker.record(g10, "Admin Report: Contains Status & Counts", "Overall:" in report_text and "Tests Passed" in report_text)
        tracker.group_times[g10] = time.time() - t_start

    finally:
        logging.disable(prev_log_level)

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
        g_time = tracker.group_times.get(group, 0.0)
        lines.append(f"{g_icon} <b>{group}:</b> {group_passed}/{group_total} <i>({g_time*1000:.1f}ms)</i>")

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
    print("\n" + "=" * 80)
    print("🚀 COMPREHENSIVE IPO TRACKER & GMP ALERT ENGINE TEST SUITE")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%d %b %Y, %I:%M %p IST')} | Platform: {sys.platform}\n")

    tracker = run_all_tests()

    for group, tests in tracker.groups.items():
        g_time = tracker.group_times.get(group, 0.0)
        passed_count = sum(1 for _, p, _ in tests if p)
        print(f"\n📁 {group} ({passed_count}/{len(tests)} passed in {g_time*1000:.1f}ms):")
        for name, passed, detail in tests:
            status = "✅ PASS" if passed else "❌ FAIL"
            detail_str = f" - {detail}" if detail else ""
            print(f"  {status:<8} {name}{detail_str}")

    print("\n" + "=" * 80)
    status_label = "✅ ALL 10 TEST SUITES PASSED" if tracker.all_passed else "❌ SUITE FAILURES DETECTED"
    print(f"Summary: {tracker.passed_tests}/{tracker.total_tests} Tests Passed in {tracker.duration_sec:.2f}s  [{status_label}]")
    print("=" * 80 + "\n")

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
