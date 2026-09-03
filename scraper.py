"""
Scraper module for Indian Mainboard IPOs and Grey Market Premium (GMP).
Primary Source: IPOWatch (live Mainboard GMP table)
Secondary / Cross-check: NSE India Upcoming IPOs API
"""

import sys
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("ipo_tracker.scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
]


def _clean_text(text: str) -> str:
    """Clean HTML entities and extra whitespace."""
    if not text:
        return ""
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_currency(val: str) -> float:
    """Extract numeric value from currency string like '₹140', 'Rs. 239', '₹-'."""
    if not val:
        return 0.0
    val = val.replace("₹", "").replace("Rs.", "").replace(",", "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)", val)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    return 0.0


def _parse_price_band(price_str: str) -> float:
    """Extract the upper band price from strings like '₹140', '₹168 to ₹177', '₹632'."""
    if not price_str:
        return 0.0
    numbers = re.findall(r"(\d+(?:\.\d+)?)", price_str.replace(",", ""))
    if not numbers:
        return 0.0
    try:
        # If a range is given (e.g. 168 to 177), take the upper cut-off price
        return float(numbers[-1])
    except ValueError:
        return 0.0


def _parse_dates(date_str: str) -> tuple[str, str]:
    """
    Parse date range like '1-3 Sept', '10-15 Sept', '28-1 Sept', '21-23 Sept'.
    Returns (start_date, last_filing_date).
    """
    date_str = _clean_text(date_str)
    if not date_str or date_str in ("-", "TBA"):
        return ("TBA", "TBA")

    # Match format like '10-15 Sept' or '1-3 Sept'
    m1 = re.match(r"^(\d+)\s*-\s*(\d+)\s+([A-Za-z]+)$", date_str)
    if m1:
        start_day, end_day, month = m1.groups()
        return (f"{start_day} {month}", f"{end_day} {month}")

    # Match format like '28 Aug - 1 Sept'
    m2 = re.match(r"^(\d+\s+[A-Za-z]+)\s*-\s*(\d+\s+[A-Za-z]+)$", date_str)
    if m2:
        return (m2.group(1), m2.group(2))

    return (date_str, date_str)


def fetch_mainboard_ipos_ipowatch() -> List[Dict]:
    """
    Fetch Mainboard IPOs and GMP from IPOWatch.
    Returns structured list of IPO dictionaries.
    """
    url = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        logger.error(f"Failed to fetch IPOWatch GMP: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    if not tables:
        logger.warning("No tables found on IPOWatch page")
        return []

    # Table 0 is always Mainboard IPOs on IPOWatch
    mainboard_table = tables[0]
    rows = mainboard_table.find_all("tr")
    if not rows:
        return []

    # Parse headers to identify column indices
    header_row = rows[0]
    header_cells = [_clean_text(c.get_text()) for c in header_row.find_all(["th", "td"])]
    
    col_map = {
        "name": 0,
        "gmp": 1,
        "trend": 2,
        "price": 3,
        "est_listing": 4,
        "date": 5,
        "status": 6
    }
    for idx, h in enumerate(header_cells):
        h_lower = h.lower().strip()
        if "name" in h_lower:
            col_map["name"] = idx
        elif "gmp" in h_lower:
            col_map["gmp"] = idx
        elif "price" in h_lower:
            col_map["price"] = idx
        elif "listing" in h_lower:
            col_map["est_listing"] = idx
        elif h_lower == "date":
            col_map["date"] = idx
        elif "status" in h_lower:
            col_map["status"] = idx

    results = []
    for r in rows[1:]:
        cells = [_clean_text(c.get_text()) for c in r.find_all(["td", "th"])]
        if len(cells) < 4:
            continue

        raw_name = cells[col_map["name"]] if col_map["name"] < len(cells) else ""
        if not raw_name or raw_name == "IPO Name":
            continue

        raw_gmp = cells[col_map["gmp"]] if col_map["gmp"] < len(cells) else "0"
        raw_price = cells[col_map["price"]] if col_map["price"] < len(cells) else "0"
        raw_listing = cells[col_map["est_listing"]] if col_map["est_listing"] < len(cells) else ""
        raw_date = cells[col_map["date"]] if col_map["date"] < len(cells) else ""
        raw_status = cells[col_map["status"]] if col_map["status"] < len(cells) else "Upcoming"

        gmp_val = _parse_currency(raw_gmp)
        price_val = _parse_price_band(raw_price)

        # Extract GMP % from est_listing like '₹158 (12.86%)' or calculate
        gmp_pct = 0.0
        pct_match = re.search(r"\(([\d\.]+)%\)", raw_listing)
        if pct_match:
            try:
                gmp_pct = float(pct_match.group(1))
            except ValueError:
                gmp_pct = 0.0
        elif price_val > 0 and gmp_val > 0:
            gmp_pct = round((gmp_val / price_val) * 100, 2)

        start_date, last_filing_date = _parse_dates(raw_date)

        # Determine if closing today (match exact day and month, e.g. '3 Sept' != '23 Sept')
        now = datetime.now()
        current_day = str(now.day)
        current_month = now.strftime("%b").lower()
        closing_today = False
        if last_filing_date != "TBA":
            # Extract day and month from last_filing_date
            date_match = re.search(r"(\d+)\s+([A-Za-z]+)", last_filing_date)
            if date_match:
                f_day, f_month = date_match.groups()
                if f_day == current_day and f_month.lower()[:3] == current_month[:3]:
                    closing_today = True

        status_clean = raw_status.strip().capitalize()
        if not status_clean:
            status_clean = "Upcoming"

        results.append({
            "name": raw_name,
            "type": "Mainboard",
            "price_band": raw_price,
            "price_upper": price_val,
            "gmp_rs": gmp_val,
            "gmp_percent": gmp_pct,
            "date_range": raw_date,
            "start_date": start_date,
            "last_filing_date": last_filing_date,
            "closing_today": closing_today,
            "status": status_clean,
            "est_listing": raw_listing
        })

    return results


def fetch_nse_upcoming_ipos() -> List[Dict]:
    """
    Fetch upcoming official IPO issues directly from NSE India API.
    Used for official cross-referencing of dates and issue prices.
    """
    url = "https://www.nseindia.com/api/all-upcoming-issues?category=ipo"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"
    }

    try:
        session = requests.Session()
        # Prime session cookies with NSE homepage
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        res = session.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                return data
    except Exception as e:
        logger.debug(f"NSE API fetch notice (optional): {e}")
    return []


def get_all_mainboard_ipos() -> List[Dict]:
    """
    Master function: Scrapes IPOWatch Mainboard IPOs and returns clean list.
    """
    ipos = fetch_mainboard_ipos_ipowatch()
    return ipos


if __name__ == "__main__":
    print("\n🔍 Fetching Live Mainboard IPOs & GMP Data...\n")
    ipos = get_all_mainboard_ipos()
    print(f"Found {len(ipos)} Mainboard IPOs:\n")
    print(f"{'IPO Name':<28} | {'Price':<10} | {'GMP (₹)':<8} | {'GMP %':<8} | {'Dates':<12} | {'Last Filing':<12} | {'Status'}")
    print("-" * 105)
    for ipo in ipos:
        print(f"{ipo['name'][:26]:<28} | {ipo['price_band']:<10} | ₹{ipo['gmp_rs']:<7.1f} | {ipo['gmp_percent']:>5.2f}% | {ipo['date_range']:<12} | {ipo['last_filing_date']:<12} | {ipo['status']}")
