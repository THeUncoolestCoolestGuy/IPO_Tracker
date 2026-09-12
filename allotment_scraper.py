"""
Allotment Scraper for Indian IPOs.
Queries the live allotment company dropdowns across the top 3 registrars:
  1. Link Intime (MUFG)
  2. KFin Technologies
  3. Bigshare Services
"""

import sys
import re
import json
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("ipo_tracker.allotment_scraper")

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

BSE_ALLOTMENT_URL = "https://www.bseindia.com/investors/appli_check.aspx"


def clean_company_name(name: str) -> str:
    """Clean extra spaces and trailing IPO indicators."""
    if not name:
        return ""
    cleaned = re.sub(r"\s+", " ", name).strip()
    return cleaned


def get_linkintime_ipos(timeout: int = 15) -> List[Dict]:
    """
    Fetch active IPOs listed on Link Intime (MUFG) portal.
    Endpoint: https://in.mpms.mufg.com/Initial_Offer/IPO.aspx/GetDetails
    """
    portal_url = "https://in.mpms.mufg.com/Initial_Offer/public-issues.html"
    api_url = "https://in.mpms.mufg.com/Initial_Offer/IPO.aspx/GetDetails"
    headers = {
        **COMMON_HEADERS,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": portal_url
    }

    ipos = []
    try:
        r = requests.post(api_url, headers=headers, json={}, timeout=timeout, verify=False)
        if r.status_code == 200:
            data = r.json().get("d", "")
            if data:
                root = ET.fromstring(data)
                for table in root.findall("Table"):
                    cid_el = table.find("company_id")
                    name_el = table.find("companyname")
                    if cid_el is not None and name_el is not None and name_el.text:
                        name = clean_company_name(name_el.text)
                        ipos.append({
                            "name": name,
                            "registrar": "Link Intime",
                            "portal_url": portal_url,
                            "bse_url": BSE_ALLOTMENT_URL,
                            "company_id": cid_el.text.strip()
                        })
    except Exception as e:
        logger.error(f"Error fetching Link Intime IPOs: {e}")

    return ipos


def get_kfintech_ipos(timeout: int = 15) -> List[Dict]:
    """
    Fetch active IPOs listed on KFin Technologies portal.
    Parses live company registry from ipostatus.kfintech.com React bundle.
    """
    portal_url = "https://ipostatus.kfintech.com"
    ipos = []
    try:
        r = requests.get(portal_url, headers=COMMON_HEADERS, timeout=timeout, verify=False)
        if r.status_code == 200:
            # Find the main React bundle
            js_files = re.findall(r'src=["\']([^"\']+\.js)["\']', r.text)
            for js in js_files:
                js_url = portal_url + "/" + js.lstrip("./")
                jr = requests.get(js_url, headers=COMMON_HEADERS, timeout=timeout, verify=False)
                if jr.status_code == 200:
                    # Match JSON string inside rf=JSON.parse('...')
                    m = re.search(r"rf=JSON\.parse\('([^']+)'\)", jr.text)
                    if m:
                        data_str = m.group(1).encode("utf-8").decode("unicode_escape")
                        raw_list = json.loads(data_str)
                        for item in raw_list:
                            name = clean_company_name(item.get("name", ""))
                            if name:
                                ipos.append({
                                    "name": name,
                                    "registrar": "KFin Technologies",
                                    "portal_url": portal_url,
                                    "bse_url": BSE_ALLOTMENT_URL,
                                    "company_id": str(item.get("clientId", ""))
                                })
                        break
    except Exception as e:
        logger.error(f"Error fetching KFintech IPOs: {e}")

    return ipos


def get_bigshare_ipos(timeout: int = 15) -> List[Dict]:
    """
    Fetch active IPOs listed on Bigshare Services portal.
    Endpoint: https://ipo.bigshareonline.com/IPO_Status.html
    """
    portal_url = "https://ipo.bigshareonline.com/IPO_Status.html"
    ipos = []
    try:
        from bs4 import BeautifulSoup
        r = requests.get(portal_url, headers=COMMON_HEADERS, timeout=timeout, verify=False)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            select = soup.find("select", id="ddlCompany")
            if select:
                for opt in select.find_all("option"):
                    txt = clean_company_name(opt.get_text(strip=True))
                    val = opt.get("value", "").strip()
                    if txt and not txt.startswith("--"):
                        ipos.append({
                            "name": txt,
                            "registrar": "Bigshare Services",
                            "portal_url": portal_url,
                            "bse_url": BSE_ALLOTMENT_URL,
                            "company_id": val
                        })
    except Exception as e:
        logger.error(f"Error fetching Bigshare IPOs: {e}")

    return ipos


def get_all_live_allotments(timeout: int = 15) -> List[Dict]:
    """
    Query all 3 registrars and return combined list of live IPO allotments.
    """
    all_ipos = []

    # 1. Link Intime
    li = get_linkintime_ipos(timeout=timeout)
    logger.info(f"Link Intime: found {len(li)} active IPO(s)")
    all_ipos.extend(li)

    # 2. KFintech
    kf = get_kfintech_ipos(timeout=timeout)
    logger.info(f"KFintech: found {len(kf)} active IPO(s)")
    all_ipos.extend(kf)

    # 3. Bigshare
    bs = get_bigshare_ipos(timeout=timeout)
    logger.info(f"Bigshare: found {len(bs)} active IPO(s)")
    all_ipos.extend(bs)

    return all_ipos


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Allotment Scraper...")
    results = get_all_live_allotments()
    print(f"\nTotal active IPOs across all registrars: {len(results)}")
    print("\nSample IPOs declared:")
    for item in results[:10]:
        print(f"  [{item['registrar']}] {item['name']} -> {item['portal_url']}")

