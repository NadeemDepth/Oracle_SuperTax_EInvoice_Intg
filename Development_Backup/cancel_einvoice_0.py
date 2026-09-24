"""
Oracle Fusion AR Invoice -> SuperTax E-Invoice Cancellation
============================================================
Cancels an active E-Invoice (IRN) within the strict 24-hour window.
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

FUSION_BASE_URL = os.environ["FUSION_BASE_URL"].rstrip("/")
FUSION_USER = os.environ["FUSION_USERNAME"]
FUSION_PASS = os.environ["FUSION_PASSWORD"]
SUPERTAX_API_KEY = os.environ["SUPERTAX_API_KEY"]
SUPERTAX_CANCEL_URL = os.getenv("SUPERTAX_CANCEL_API_URL", "https://inspira.supertaxuat.in/api/integration/einvoices/v1.01/sales/cancel")

# --- FIXED: Cancellation logs go to Cancellation folder ---
JSON_LOG_DIR = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs\Cancellation"
os.makedirs(JSON_LOG_DIR, exist_ok=True)

def setup_logger():
    master_log_file = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs\einvoice_integration_log.log"
    os.makedirs(os.path.dirname(master_log_file), exist_ok=True)
    logger = logging.getLogger("cancel_einv")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | [CANCEL] | %(levelname)-8s | %(message)s")
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

def get_fusion_record_by_irn(irn: str) -> Dict[str, Any]:
    url = f"{FUSION_BASE_URL}/fscmRestApi/resources/11.13.18.05/Inspira_Einvoice_c?q=IRN_Number_c='{irn}'"
    resp = requests.get(url, auth=HTTPBasicAuth(FUSION_USER, FUSION_PASS), headers={"Accept": "application/json"})
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise ValueError(f"IRN {irn} not found in Oracle App Composer.")
    return items[0]

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
        save_log_file("AppComp_Cancel_EInvoice", doc_no, payload, response=resp_data)
    else:
        save_log_file("AppComp_Cancel_EInvoice", doc_no, payload, response=resp_data, error=f"HTTP {fusion_resp.status_code}")
    fusion_resp.raise_for_status()
    return resp_data

def cancel_invoice(irn: str, reason_code: str, remarks: str) -> None:
    logger.info(f"Initiating cancellation for IRN: {irn}")
    
    try:
        record = get_fusion_record_by_irn(irn)
    except Exception as e:
        save_log_file("Cancel_EInvoice_Error", irn, {"irn": irn}, error=str(e))
        logger.error(f"Error fetching record: {e}")
        sys.exit(1)
        
    trx_id = record.get("Trx_Id_c", "Unknown")
    doc_no = record.get("DocNumber_c", trx_id)

    cancel_payload = {
        "invoices": [
            {
                "Irn": irn,
                "CnlRsn": str(reason_code),
                "CnlRem": str(remarks)[:100]
            }
        ]
    }
    
    headers = {"key": SUPERTAX_API_KEY, "Content-Type": "application/json"}
    
    try:
        supertax_resp = requests.post(SUPERTAX_CANCEL_URL, json=cancel_payload, headers=headers)
        try:
            resp_data = supertax_resp.json()
        except Exception:
            resp_data = supertax_resp.text
            
        save_log_file("Cancel_EInvoice", doc_no, cancel_payload, response=resp_data)
        
        if not supertax_resp.ok:
            logger.error(f"SuperTax HTTP Error: {resp_data}")
            supertax_resp.raise_for_status()
            
    except Exception as exc:
        save_log_file("Cancel_EInvoice", doc_no, cancel_payload, error=str(exc))
        logger.error(f"SuperTax Call Failed: {exc}")
        sys.exit(1)
        
    items = resp_data.get("invoices", resp_data.get("data", [resp_data])) if isinstance(resp_data, dict) else [{}]
    response_item = items[0] if items else {}
    
    status = str(response_item.get("Status", "")).upper()
    success = str(response_item.get("Success", "false")).lower()
    
    api_message = response_item.get("Messages") or response_item.get("ErrorDetails") or f"Status: {status}"
    
    if success == "true" or status in ("CANCELLED", "SUCCESS"):
        fusion_update = {
            "Status_c": "CANCELLED",
            "Success_c": "true",
            "Messages_c": f"Cancelled successfully. Reason: {remarks} | {api_message}"[:200],
            "EwbNo_c": "CANCELLED"
        }
        update_fusion_record(record.get("Id"), fusion_update, doc_no)
        logger.info(f"API Response: {api_message}")
        print(f"API Response: {api_message}")
    else:
        logger.error(f"Cancellation Rejected by SuperTax: {api_message}")
        print(f"API Response (Rejected): {api_message}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cancel a SuperTax E-Invoice.")
    parser.add_argument("--irn", required=True, help="Invoice Reference Number (IRN)")
    parser.add_argument("--reason", required=True, choices=["1", "2", "3", "4"], help="1: Duplicate, 2: Data Entry Mistake")
    parser.add_argument("--remarks", required=True, help="Reason for cancellation")
    args = parser.parse_args()
    
    cancel_invoice(args.irn, args.reason, args.remarks)