"""
Oracle Fusion AR Invoice -> SuperTax E-Way Bill Cancellation
============================================================
Cancels an active E-Way Bill within the strict 24-hour window using Document Number.
Logs payloads into Logs/EWB_Cancel.
"""

import json
import logging
import os
import sys
import argparse
from datetime import datetime
from typing import Any, Dict
from logging.handlers import RotatingFileHandler

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

# --- Configuration Setup ---
FUSION_BASE_URL = os.environ["FUSION_BASE_URL"].rstrip("/")
FUSION_USER = os.environ["FUSION_USERNAME"]
FUSION_PASS = os.environ["FUSION_PASSWORD"]

# Uses the dedicated EWB API Key and fallback to general SuperTax key if not present
SUPERTAX_EWB_API_KEY = os.getenv("SUPERTAX_EWB_API_KEY", os.getenv("SUPERTAX_API_KEY"))

# SuperTax EWB Cancel API Endpoint
SUPERTAX_EWB_CANCEL_URL = os.getenv(
    "SUPERTAX_EWB_CANCEL_API_URL", 
    "https://ewayuat.supertaxgst.in/api/invoices/cancelewaybill"
)

JSON_LOG_DIR = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs\EWB_Cancel"
os.makedirs(JSON_LOG_DIR, exist_ok=True)

def setup_logger():
    master_log_file = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs\einvoice_integration_log.log"
    os.makedirs(os.path.dirname(master_log_file), exist_ok=True)
    logger = logging.getLogger("cancel_ewb")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | [EWB_CANCEL] | %(levelname)-8s | %(message)s")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)
    file_handler = RotatingFileHandler(master_log_file, maxBytes=5_000_000, backupCount=5)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger

logger = setup_logger()

def save_log_file(prefix: str, doc_identifier: str, payload: Dict[str, Any], response: Any = None, error: str = None) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_id = "".join(c for c in str(doc_identifier) if c.isalnum() or c in ("-", "_"))
    filepath = os.path.join(JSON_LOG_DIR, f"{prefix}_{safe_id}_{timestamp}.txt")
    log_content = {
        "timestamp": datetime.now().isoformat(),
        "identifier": doc_identifier,
        "request_payload": payload,
        "response": response,
        "error": error
    }
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_content, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write log file {filepath}: {e}")

def get_fusion_record_by_doc_no(doc_no: str) -> tuple[str, str, str]:
    url = f"{FUSION_BASE_URL}/fscmRestApi/resources/11.13.18.05/Inspira_Einvoice_c?q=DocNumber_c='{doc_no}'"
    resp = requests.get(url, auth=HTTPBasicAuth(FUSION_USER, FUSION_PASS), headers={"Accept": "application/json"})
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise ValueError(f"Document Number {doc_no} not found in Oracle App Composer.")
    
    record = items[0]
    ewb_no = record.get("EwbNo_c")
    if not ewb_no or str(ewb_no).upper() in ("CANCELLED", "NONE", ""):
        raise ValueError(f"Document Number {doc_no} has no active E-Way Bill Number to cancel.")
        
    return str(ewb_no), record.get("Id"), str(record.get("Trx_Id_c", ""))

def update_fusion_record(record_id: str, payload: Dict[str, Any], doc_no: str) -> Dict[str, Any]:
    url = f"{FUSION_BASE_URL}/fscmRestApi/resources/11.13.18.05/Inspira_Einvoice_c/{record_id}"
    auth = HTTPBasicAuth(FUSION_USER, FUSION_PASS)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    
    fusion_resp = requests.patch(url, json=payload, auth=auth, headers=headers)
    try:
        resp_data = fusion_resp.json()
    except Exception:
        resp_data = fusion_resp.text
        
    if fusion_resp.ok:
        save_log_file("AppComp_Cancel_Ewb", doc_no, payload, response=resp_data)
    else:
        save_log_file("AppComp_Cancel_Ewb", doc_no, payload, response=resp_data, error=f"HTTP {fusion_resp.status_code}")
    fusion_resp.raise_for_status()
    return resp_data

def cancel_ewaybill(doc_no: str, reason_code: str, remarks: str) -> None:
    logger.info(f"Initiating E-Way Bill cancellation for Document Number: {doc_no}")
    
    # 1. Fetch EwbNo from Oracle
    try:
        ewb_no, record_id, trx_id = get_fusion_record_by_doc_no(doc_no)
    except Exception as e:
        save_log_file("Cancel_Ewb_Error", doc_no, {"doc_no": doc_no}, error=str(e))
        logger.error(str(e))
        sys.exit(1)
        
    logger.info(f"Found active E-Way Bill: {ewb_no} for Document {doc_no}")

    # 2. Build Specific SuperTax E-Way Bill Cancel Payload Schema
    cancel_payload = {
        "ewaybills": [
            {
                "ewaybill_no": str(ewb_no).strip(),
                "ewaybill_cancel_reason": str(reason_code).strip(),
                "ewaybill_cancel_remark": str(remarks)[:100].strip()
            }
        ]
    }
    
    headers = {
        "key": SUPERTAX_EWB_API_KEY, 
        "Content-Type": "application/json"
    }
    
    try:
        supertax_resp = requests.post(SUPERTAX_EWB_CANCEL_URL, json=cancel_payload, headers=headers)
        try:
            resp_data = supertax_resp.json()
        except Exception:
            resp_data = supertax_resp.text
            
        save_log_file("Cancel_Ewb", doc_no, cancel_payload, response=resp_data)
        
        if not supertax_resp.ok:
            logger.error(f"SuperTax HTTP Error: {resp_data}")
            supertax_resp.raise_for_status()
            
    except Exception as exc:
        save_log_file("Cancel_Ewb", doc_no, cancel_payload, error=str(exc))
        logger.error(f"SuperTax EWB Cancel Call Failed: {exc}")
        sys.exit(1)
        
# 3. Parse Response Handling (Handles both top-level list and dict)
    items = []
    if isinstance(resp_data, list):
        items = resp_data
    elif isinstance(resp_data, dict):
        if "ewaybills" in resp_data and isinstance(resp_data["ewaybills"], list):
            items = resp_data["ewaybills"]
        elif "data" in resp_data and isinstance(resp_data["data"], list):
            items = resp_data["data"]
        else:
            items = [resp_data]
            
    response_item = items[0] if (items and isinstance(items[0], dict)) else {}
    
    # Safely pull status and success from response_item or dict resp_data
    status_val = str(
        response_item.get("status") 
        or response_item.get("Status") 
        or (resp_data.get("status") if isinstance(resp_data, dict) else "")
        or ""
    ).upper()

    success_val = str(
        response_item.get("success") 
        or response_item.get("Success") 
        or (resp_data.get("success") if isinstance(resp_data, dict) else "")
        or ""
    ).lower()

    api_message = (
        response_item.get("message") 
        or response_item.get("Message") 
        or response_item.get("error") 
        or response_item.get("ErrorDetails") 
        or (resp_data.get("message") if isinstance(resp_data, dict) else "")
        or ""
    )

    is_success = (
        success_val == "true" or 
        status_val in ("1", "SUCCESS", "CANCELLED", "ACT") or 
        "CANCEL" in str(api_message).upper()
    )

    if is_success:
        fusion_update = {
            "EwbNo_c": "CANCELLED",
            "InfoCode_c": "CANCELLED",
            "InfoDescCode_c": str(reason_code),
            "InfoMessage_c": f"EWB Cancelled: {remarks} | {api_message}"[:200]
        }
        update_fusion_record(record_id, fusion_update, doc_no)
        console_msg = f"E-Way Bill {ewb_no} successfully cancelled. | Msg: {api_message}"
        logger.info(f"API Response: {console_msg}")
        print(f"API Response: {console_msg}")
    else:
        logger.error(f"E-Way Bill Cancellation Rejected by SuperTax: {api_message}")
        print(f"API Response (Rejected): {api_message}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cancel a SuperTax E-Way Bill.")
    parser.add_argument("--doc-no", required=True, help="Oracle Document Number")
    parser.add_argument("--reason", required=True, choices=["1", "2", "3", "4"], help="1: Duplicate, 2: Order Cancelled, 3: Data Entry Mistake, 4: Others")
    parser.add_argument("--remarks", required=True, help="Reason for cancellation")
    args = parser.parse_args()
    
    cancel_ewaybill(args.doc_no, args.reason, args.remarks)