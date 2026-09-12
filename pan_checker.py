"""
PAN Allotment Checker for Indian IPOs.
Supports single and multi-PAN allotment checks for registrars without CAPTCHA (KFintech).
Gracefully detects CAPTCHA-protected registrars and provides direct links.
"""

import sys
import re
import time
import logging
from typing import List, Dict, Any, Optional
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("ipo_tracker.pan_checker")

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

KFINTECH_QUERY_URL = "https://0uz601ms56.execute-api.ap-south-1.amazonaws.com/prod/api/query?type=pan"
PAN_REGEX = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b", re.IGNORECASE)


def extract_pans(text: str) -> List[str]:
    """
    Extract unique valid 10-character Indian PAN numbers from user input text.
    Preserves original order and converts to uppercase.
    """
    if not text:
        return []
    matches = PAN_REGEX.findall(text.upper())
    seen = set()
    unique_pans = []
    for pan in matches:
        if pan not in seen:
            seen.add(pan)
            unique_pans.append(pan)
    return unique_pans


def mask_pan(pan: str) -> str:
    """Mask middle digits of a PAN for privacy: ABCDE1234F -> ABCDE****F."""
    if len(pan) == 10:
        return f"{pan[:5]}****{pan[-1]}"
    return pan


def check_kfintech_pan(company_id: str, pan: str, timeout: int = 25) -> Dict[str, Any]:
    """
    Query KFintech API Gateway for a specific PAN and company ID.
    KFintech requires NO captcha and returns allotment details directly.
    """
    pan = pan.strip().upper()
    headers = {
        **COMMON_HEADERS,
        "reqparam": pan,
        "client_id": str(company_id).strip(),
        "Origin": "https://ipostatus.kfintech.com",
        "Referer": "https://ipostatus.kfintech.com/",
        "Accept": "application/json, text/plain, */*"
    }

    try:
        r = requests.get(KFINTECH_QUERY_URL, headers=headers, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            records = data if isinstance(data, list) else data.get("data", [])
            if records:
                rec = records[0]
                allotted_str = str(rec.get("All_Shares", "0")).strip()
                applied_str = str(rec.get("App_Shares", "0")).strip()
                try:
                    allotted = int(allotted_str)
                except ValueError:
                    allotted = 0
                try:
                    applied = int(applied_str)
                except ValueError:
                    applied = 0

                name = rec.get("Name", "").strip()
                app_no = rec.get("Appln_No", "").strip()
                category = rec.get("category", "RETAIL").strip()

                return {
                    "pan": pan,
                    "masked_pan": mask_pan(pan),
                    "status": "ALLOTTED" if allotted > 0 else "NOT_ALLOTTED",
                    "allotted_shares": allotted,
                    "applied_shares": applied,
                    "name": name,
                    "application_no": app_no,
                    "category": category,
                    "registrar": "KFin Technologies",
                    "raw": rec
                }

        elif r.status_code == 404:
            return {
                "pan": pan,
                "masked_pan": mask_pan(pan),
                "status": "NOT_FOUND",
                "allotted_shares": 0,
                "applied_shares": 0,
                "name": "",
                "application_no": "",
                "category": "",
                "registrar": "KFin Technologies",
                "message": "No application record found"
            }
        else:
            logger.warning(f"KFintech returned status {r.status_code} for PAN {mask_pan(pan)}")
            return {
                "pan": pan,
                "masked_pan": mask_pan(pan),
                "status": "ERROR",
                "allotted_shares": 0,
                "message": f"Server response code {r.status_code}"
            }
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout querying KFintech for PAN {mask_pan(pan)}")
        return {
            "pan": pan,
            "masked_pan": mask_pan(pan),
            "status": "TIMEOUT",
            "allotted_shares": 0,
            "message": "KFintech server timed out. Try again later."
        }
    except Exception as e:
        logger.error(f"Error querying KFintech for PAN {mask_pan(pan)}: {e}")
        return {
            "pan": pan,
            "masked_pan": mask_pan(pan),
            "status": "ERROR",
            "allotted_shares": 0,
            "message": str(e)
        }


def find_ipo_by_name(query: str) -> Optional[Dict[str, Any]]:
    """
    Search active IPOs across registrars matching query string.
    """
    from allotment_scraper import get_all_live_allotments
    ipos = get_all_live_allotments()
    if not ipos:
        return None

    query_clean = re.sub(r"[^a-zA-Z0-9]", "", query.lower())
    for ipo in ipos:
        name_clean = re.sub(r"[^a-zA-Z0-9]", "", ipo["name"].lower())
        if query_clean in name_clean or name_clean in query_clean:
            return ipo
    return None


def batch_check_pans(company_query: Optional[str], pans: List[str]) -> Dict[str, Any]:
    """
    Batch check multiple PAN cards against an IPO.
    If company_query is None, defaults to the newest available KFintech IPO.
    """
    if not pans:
        return {
            "success": False,
            "message": "No PAN numbers provided.",
            "results": []
        }

    from allotment_scraper import get_kfintech_ipos

    target_ipo = None
    if company_query:
        target_ipo = find_ipo_by_name(company_query)
        if not target_ipo:
            kfin_ipos = get_kfintech_ipos()
            for k in kfin_ipos:
                if str(k.get("company_id")) == str(company_query).strip():
                    target_ipo = k
                    break

    if not target_ipo:
        kfin_ipos = get_kfintech_ipos()
        if kfin_ipos:
            target_ipo = kfin_ipos[0]

    if not target_ipo:
        return {
            "success": False,
            "message": "Could not find any active IPO to check against.",
            "results": []
        }

    registrar = target_ipo.get("registrar", "")
    company_name = target_ipo.get("name", "Unknown IPO")
    company_id = target_ipo.get("company_id", "")

    if registrar != "KFin Technologies":
        portal_url = target_ipo.get("portal_url", "https://www.bseindia.com/investors/appli_check.aspx")
        return {
            "success": False,
            "captcha_required": True,
            "company_name": company_name,
            "registrar": registrar,
            "portal_url": portal_url,
            "message": f"⚠️ <b>{company_name}</b> is hosted on <b>{registrar}</b>, which requires image CAPTCHA verification.\nAutomated lookup cannot bypass their captcha.",
            "results": []
        }

    results = []
    for idx, pan in enumerate(pans):
        res = check_kfintech_pan(company_id=company_id, pan=pan)
        results.append(res)
        if idx < len(pans) - 1:
            time.sleep(0.3)

    return {
        "success": True,
        "captcha_required": False,
        "company_name": company_name,
        "registrar": registrar,
        "results": results
    }


def format_allotment_report(batch_response: Dict[str, Any]) -> str:
    """
    Format clean, visually appealing, airy Telegram HTML report for batch PAN results.
    """
    if batch_response.get("captcha_required"):
        company = batch_response.get("company_name", "IPO")
        registrar = batch_response.get("registrar", "Registrar")
        portal_url = batch_response.get("portal_url", "")
        bse_url = "https://www.bseindia.com/investors/appli_check.aspx"

        lines = [
            f"🏛️ <b>ALLOTMENT LOOKUP: {company}</b>\n",
            f"Registrar: <b>{registrar}</b>\n",
            "⚠️ <i>This registrar enforces image CAPTCHA / bot verification. Automated server lookup is protected.</i>\n",
            "📲 <b>Check directly on official portals:</b>",
            f"👉 <a href=\"{portal_url}\">{registrar} Official Portal</a>",
            f"👉 <a href=\"{bse_url}\">BSE Allotment Portal</a>"
        ]
        return "\n".join(lines)

    if not batch_response.get("success"):
        return f"❌ {batch_response.get('message', 'Unable to check allotment.')}"

    company = batch_response.get("company_name", "IPO")
    results = batch_response.get("results", [])

    allotted_count = sum(1 for r in results if r.get("status") == "ALLOTTED")
    not_allotted_count = sum(1 for r in results if r.get("status") == "NOT_ALLOTTED")
    not_found_count = sum(1 for r in results if r.get("status") == "NOT_FOUND")

    lines = [
        f"🎯 <b>ALLOTMENT RESULT: {company}</b>",
        "Registrar: KFin Technologies (Direct API)\n",
        "────────────────────────"
    ]

    for idx, r in enumerate(results, 1):
        status = r.get("status")
        mpan = r.get("masked_pan", "")
        name = r.get("name", "")
        name_str = f" ({name})" if name else ""

        if status == "ALLOTTED":
            shares = r.get("allotted_shares", 0)
            applied = r.get("applied_shares", 0)
            app_no = r.get("application_no", "N/A")
            cat = r.get("category", "RETAIL")
            lines.append(f"<b>{idx}. {mpan}</b>{name_str}")
            lines.append(f"   🟢 <b>ALLOTTED: {shares} Shares!</b> 🎉")
            lines.append(f"   • Applied: {applied} | App No: <code>{app_no}</code> | Cat: {cat}\n")

        elif status == "NOT_ALLOTTED":
            applied = r.get("applied_shares", 0)
            app_no = r.get("application_no", "N/A")
            lines.append(f"<b>{idx}. {mpan}</b>{name_str}")
            lines.append("   🔴 <b>Status: Not Allotted</b>")
            lines.append(f"   • Applied: {applied} | App No: <code>{app_no}</code>\n")

        elif status == "NOT_FOUND":
            lines.append(f"<b>{idx}. {mpan}</b>")
            lines.append("   ⚪ <b>Status: No Application Found</b>")
            lines.append("   • Verify PAN or check if application was submitted\n")

        else:
            lines.append(f"<b>{idx}. {mpan}</b>")
            lines.append(f"   ⚠️ Status: {r.get('message', 'Error')}\n")

    lines.append("────────────────────────")
    lines.append(
        f"📊 <b>Summary:</b> 🟢 {allotted_count} Allotted  •  🔴 {not_allotted_count} Not Allotted  •  ⚪ {not_found_count} Not Found"
    )

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing PAN extraction...")
    test_pans = extract_pans("Test PANs: ABCDE1234F, bcdef2345g and another CDEFG3456H with invalid XYZ123")
    print("Extracted:", test_pans)
    print("Masked:", [mask_pan(p) for p in test_pans])
