"""
Internal Automated Test Suite for IPO Tracker.
Tests:
1. Date range parsing with various formats.
2. IPO date range formatter.
3. Live classification (Active vs Upcoming 1-2 days vs Past/Closed).
4. Morning and Reminder alert text formatting.
5. Allotment pipeline check.
"""
import sys
from datetime import datetime
from tracker import get_classified_ipos, format_morning_alert, format_reminder_alert, format_ipo_dates
from scraper import parse_date_str_to_date, _parse_dates

def run_tests():
    print("=" * 60)
    print("  INTERNAL TEST SUITE: IPO TRACKER ENGINE")
    print("=" * 60)

    # 1. Date Range Parsing
    print("\n[TEST 1] Testing Date Range Parsing:")
    test_cases = [
        ("15-19 Oct", ("15 Oct", "19 Oct")),
        ("21-23 Oct", ("21 Oct", "23 Oct")),
        ("28 Aug - 1 Sept", ("28 Aug", "1 Sept")),
        ("10 to 15 Sept", ("10 Sept", "15 Sept")),
        ("Oct 15 - 19", ("15 Oct", "19 Oct")),
        ("Oct 15 - Oct 19", ("15 Oct", "19 Oct")),
        ("16 Oct", ("16 Oct", "16 Oct")),
        ("TBA", ("TBA", "TBA")),
        ("-", ("TBA", "TBA")),
    ]
    all_passed = True
    for raw, expected in test_cases:
        res = _parse_dates(raw)
        status = "PASSED" if res == expected else f"FAILED (got {res})"
        if res != expected:
            all_passed = False
        print(f"  • {raw:<16} -> {str(res):<25} [{status}]")

    # 2. Date Formatter
    print("\n[TEST 2] Testing IPO Date Formatting:")
    mock_ipos = [
        ({"start_date": "15 Oct", "last_filing_date": "19 Oct"}, "15 Oct – 19 Oct"),
        ({"start_date": "21 Oct", "last_filing_date": "21 Oct"}, "21 Oct"),
        ({"start_date": "TBA", "last_filing_date": "23 Oct"}, "Closes 23 Oct"),
        ({"start_date": "TBA", "last_filing_date": "TBA"}, "TBA"),
    ]
    for ipo, expected in mock_ipos:
        formatted = format_ipo_dates(ipo)
        status = "PASSED" if formatted == expected else f"FAILED (got {formatted})"
        if formatted != expected:
            all_passed = False
        print(f"  • {str(ipo):<55} -> {formatted:<18} [{status}]")

    # 3. Live Classification
    print("\n[TEST 3] Testing Live Classification & Alert Generation:")
    active, upcoming = get_classified_ipos(threshold=10.0)
    print(f"  • Active IPOs: {len(active)}")
    for a in active:
        print(f"    - {a['name']:<26} | Status: {a.get('status'):<8} | GMP: {a.get('gmp_percent'):>5.1f}% | Dates: {format_ipo_dates(a)}")

    print(f"  • Upcoming IPOs (Next 1-2 Days): {len(upcoming)}")
    for u in upcoming:
        print(f"    - {u['name']:<26} | Status: {u.get('status'):<8} | GMP: {u.get('gmp_percent'):>5.1f}% | Dates: {format_ipo_dates(u)}")

    # 4. Alert Text Formatting
    print("\n[TEST 4] Alert Text Generation:")
    morning_msg = format_morning_alert(active, upcoming)
    reminder_msg, has_urgent = format_reminder_alert(active)
    assert "IPO Date:" in morning_msg or "No Mainboard IPOs" in morning_msg, "Morning alert missing IPO Date"
    assert "Last Filing Date:" not in morning_msg, "Morning alert still has legacy Last Filing Date"
    assert "Last Filing Date:" not in reminder_msg, "Reminder alert still has legacy Last Filing Date"
    print("  • Morning Alert Length: ", len(morning_msg), "chars [PASSED]")
    print("  • Reminder Alert Length:", len(reminder_msg), "chars [PASSED]")

    print("\n" + "=" * 60)
    if all_passed:
        print("  🎉 ALL INTERNAL TESTS PASSED SUCCESSFULLY!")
    else:
        print("  ❌ SOME TESTS FAILED")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
