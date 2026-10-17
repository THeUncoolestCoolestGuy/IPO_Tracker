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
import time
from bs4 import BeautifulSoup
from config import Config

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


# Month name to number mapping for date parsing
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
}


def parse_date_str_to_date(d_str: str) -> Optional[datetime]:
    """
    Parse date string like '21 Oct', '3 Sept', '19 Oct' into a datetime object.
    Year is automatically assigned to match current year (with boundary handling).
    """
    if not d_str or d_str in ("TBA", "-", ""):
        return None
    m = re.search(r"(\d+)\s+([A-Za-z]+)", d_str)
    if not m:
        return None
    day_str, month_str = m.groups()
    month_key = month_str.lower()
    month_num = _MONTH_MAP.get(month_key[:4]) or _MONTH_MAP.get(month_key[:3])
    if not month_num:
        return None
    now = datetime.now()
    year = now.year
    try:
        dt = datetime(year, month_num, int(day_str))
        # Handle cross-year boundary (e.g. November checking January)
        if (dt - now).days > 200:
            dt = dt.replace(year=year - 1)
        elif (now - dt).days > 300:
            dt = dt.replace(year=year + 1)
        return dt
    except ValueError:
        return None


def _clean_company_name_and_status(raw_name: str) -> tuple[str, str]:
    """
    Extract embedded status from IPOWatch company name and clean trailing indicators.
    e.g. 'Jio Platforms  Upcoming' -> ('Jio Platforms', 'Upcoming')
         'Bonfiglioli Transmissions  Open' -> ('Bonfiglioli Transmissions', 'Open')
         'Fusion CX (C)' -> ('Fusion CX', 'Closed')
         'HD Fire Protect (C)' -> ('HD Fire Protect', 'Closed')
         'Paras HealthcareUpcoming' -> ('Paras Healthcare', 'Upcoming')
    """
    cleaned = _clean_text(raw_name)
    extracted_status = ""

    if re.search(r"\((?:C|c)\)|closed", cleaned, re.IGNORECASE):
        extracted_status = "Closed"
    elif re.search(r"\bopen\b|open$", cleaned, re.IGNORECASE):
        extracted_status = "Open"
    elif re.search(r"\bupcoming\b|upcoming$", cleaned, re.IGNORECASE):
        extracted_status = "Upcoming"

    # Strip (C), Upcoming, Open, Closed from the trailing edge of the company name
    cleaned_name = re.sub(
        r"(?:\s*\((?:C|c)\)|\s*Upcoming|Upcoming|\s*Open|Open|\s*Closed|Closed)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    return cleaned_name, extracted_status


def _recompute_ipo_status_and_closing(ipo: Dict) -> Dict:
    """
    Recompute dynamic status and closing_today against TODAY's current date.
    Used both on fresh scrape and when reading cached data to prevent stale flags.
    """
    now = datetime.now()
    today_date = now.date()

    last_filing_str = ipo.get("last_filing_date", "")
    start_date_str = ipo.get("start_date", "")
    last_dt = parse_date_str_to_date(last_filing_str)
    start_dt = parse_date_str_to_date(start_date_str)

    current_status = ipo.get("status", "Upcoming").capitalize()
    closing_today = False

    if last_dt is not None:
        last_date = last_dt.date()
        if last_date < today_date:
            current_status = "Closed"
        elif last_date == today_date:
            closing_today = True
            current_status = "Open"
        elif start_dt is not None:
            start_date = start_dt.date()
            if start_date <= today_date <= last_date:
                current_status = "Open"
            elif today_date < start_date:
                current_status = "Upcoming"
    
    ipo["closing_today"] = closing_today
    ipo["status"] = current_status
    return ipo


def _parse_dates(date_str: str) -> tuple[str, str]:
    """
    Parse date range like '1-3 Sept', '10-15 Sept', '28-1 Sept', '21-23 Oct'.
    Returns (start_date, last_filing_date).
    """
    date_str = _clean_text(date_str)
    if not date_str or date_str in ("-", "TBA"):
        return ("TBA", "TBA")

    # Match format like '10-15 Sept' or '21-23 Oct'
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
    Returns structured list of IPO dictionaries with cleanly separated names,
    verified dates, and accurate status.
    """
    url = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }

    html = None
    timeout_sec = getattr(Config, "SCRAPER_TIMEOUT", 60)
    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers=headers, timeout=timeout_sec)
            response.raise_for_status()
            html = response.text
            break
        except Exception as e:
            logger.warning(f"IPOWatch fetch attempt {attempt}/3 failed: {e}. Retrying...")
            if attempt < 3:
                time.sleep(2)

    if not html:
        logger.error("Failed to fetch IPOWatch GMP after 3 attempts.")
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
    has_status_col = False
    for idx, h in enumerate(header_cells):
        h_lower = h.lower().strip()
        if "name" in h_lower or "company" in h_lower:
            col_map["name"] = idx
        elif "gmp" in h_lower:
            col_map["gmp"] = idx
        elif "price" in h_lower:
            col_map["price"] = idx
        elif "listing" in h_lower or "gain" in h_lower:
            col_map["est_listing"] = idx
        elif "date" in h_lower:
            col_map["date"] = idx
        elif "status" in h_lower:
            col_map["status"] = idx
            has_status_col = True

    results = []
    for r in rows[1:]:
        cells = [_clean_text(c.get_text()) for c in r.find_all(["td", "th"])]
        if len(cells) < 4:
            continue

        raw_company_cell = cells[col_map["name"]] if col_map["name"] < len(cells) else ""
        if not raw_company_cell or raw_company_cell.lower() in ("ipo name", "company"):
            continue

        # Clean name and extract embedded status (e.g. '(C)', 'Open', 'Upcoming')
        clean_name, extracted_status = _clean_company_name_and_status(raw_company_cell)
        if not clean_name:
            continue

        raw_gmp = cells[col_map["gmp"]] if col_map["gmp"] < len(cells) else "0"
        raw_price = cells[col_map["price"]] if col_map["price"] < len(cells) else "0"
        raw_listing = cells[col_map["est_listing"]] if col_map["est_listing"] < len(cells) else ""
        raw_date = cells[col_map["date"]] if col_map["date"] < len(cells) else ""
        
        explicit_status = cells[col_map["status"]].strip().capitalize() if (has_status_col and col_map["status"] < len(cells)) else ""
        initial_status = explicit_status or extracted_status or "Upcoming"

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

        ipo_dict = {
            "name": clean_name,
            "type": "Mainboard",
            "price_band": raw_price,
            "price_upper": price_val,
            "gmp_rs": gmp_val,
            "gmp_percent": gmp_pct,
            "date_range": raw_date,
            "start_date": start_date,
            "last_filing_date": last_filing_date,
            "closing_today": False,
            "status": initial_status,
            "est_listing": raw_listing
        }

        # Dynamically determine real status and closing_today from dates
        ipo_dict = _recompute_ipo_status_and_closing(ipo_dict)
        results.append(ipo_dict)

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
    Automatically caches to data/cached_mainboard_ipos.json and uses cache as
    short-term fallback (max 6 hours). Stale cache older than 6 hours is
    discarded to prevent serving September data in October.
    """
    import json
    from datetime import timezone, timedelta

    CACHE_MAX_AGE_HOURS = 6
    cache_file = Config.DATA_DIR / "cached_mainboard_ipos.json"

    ipos = fetch_mainboard_ipos_ipowatch()
    if ipos:
        try:
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            cache_payload = {
                "_cached_at": datetime.now(timezone.utc).isoformat(),
                "data": ipos
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save mainboard IPO cache: {e}")
        return ipos

    # --- Fallback: read cache only if it is fresh enough ---
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)

            # Support both new format {"_cached_at": ..., "data": [...]}
            # and legacy format (plain list written by previous code)
            if isinstance(cached, dict) and "_cached_at" in cached:
                cached_at_str = cached["_cached_at"]
                cached_ipos = cached.get("data", [])
                try:
                    cached_at = datetime.fromisoformat(cached_at_str)
                    if cached_at.tzinfo is None:
                        cached_at = cached_at.replace(tzinfo=timezone.utc)
                    age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
                    if age_hours > CACHE_MAX_AGE_HOURS:
                        logger.warning(
                            f"IPO cache is {age_hours:.1f}h old (max {CACHE_MAX_AGE_HOURS}h). "
                            "Discarding stale cache — returning empty list."
                        )
                        return []
                except Exception:
                    pass  # If timestamp is malformed, proceed to return cached data

                if isinstance(cached_ipos, list) and cached_ipos:
                    logger.info(f"Using fresh cache ({len(cached_ipos)} items, age < {CACHE_MAX_AGE_HOURS}h) as fallback.")
                    # Recompute dynamic status and closing_today against TODAY's date
                    return [_recompute_ipo_status_and_closing(dict(item)) for item in cached_ipos]

            elif isinstance(cached, list) and cached:
                # Legacy plain-list format: no timestamp → treat as stale, discard
                logger.warning(
                    "IPO cache has no timestamp (legacy format). "
                    "Discarding to prevent serving stale data."
                )
                return []

        except Exception as e:
            logger.error(f"Error loading cached mainboard IPOs: {e}")

    return []


if __name__ == "__main__":
    print("\n🔍 Fetching Live Mainboard IPOs & GMP Data...\n")
    ipos = get_all_mainboard_ipos()
    print(f"Found {len(ipos)} Mainboard IPOs:\n")
    print(f"{'IPO Name':<28} | {'Price':<10} | {'GMP (₹)':<8} | {'GMP %':<8} | {'Dates':<12} | {'Last Filing':<12} | {'Status'}")
    print("-" * 105)
    for ipo in ipos:
        print(f"{ipo['name'][:26]:<28} | {ipo['price_band']:<10} | ₹{ipo['gmp_rs']:<7.1f} | {ipo['gmp_percent']:>5.2f}% | {ipo['date_range']:<12} | {ipo['last_filing_date']:<12} | {ipo['status']}")
