"""
Oracle Fusion AR Invoice -> SuperTax E-Way Bill Retry (Method 2)
================================================================
Generates an E-Way Bill for an already registered E-Invoice.
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

try:
    from ora_supertax_einv_intg import (
        load_config, BIPReportClient, parse_excel_report, 
        group_rows_by_invoice, build_invoice_payload
    )
except ImportError:
    print("ERROR: Must be in the same directory as ora_supertax_einv_intg.py")
    sys.exit(1)

load_dotenv()

FUSION_BASE_URL = os.environ["FUSION_BASE_URL"].rstrip("/")
FUSION_USER = os.environ["FUSION_USERNAME"]
FUSION_PASS = os.environ["FUSION_PASSWORD"]
SUPERTAX_API_KEY = os.environ["SUPERTAX_API_KEY"]
SUPERTAX_EWB_URL = os.getenv("SUPERTAX_EWB_API_URL", "https://supertaxuat.in/api/integration/ewaybill/v1.02/save")

JSON_LOG_DIR = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs\EWB_Retry"
os.makedirs(JSON_LOG_DIR, exist_ok=True)

def setup_logger():
    master_log_file = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs\einvoice_integration_log.log"
    os.makedirs(os.path.dirname(master_log_file), exist_ok=True)
    logger = logging.getLogger("retry_ewb")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | [EWB_RETRY] | %(levelname)-8s | %(message)s")
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

def get_fusion_record_by_irn(irn: str) -> tuple[str, str, str]:
    url = f"{FUSION_BASE_URL}/fscmRestApi/resources/11.13.18.05/Inspira_Einvoice_c?q=IRN_Number_c='{irn}'"
    resp = requests.get(url, auth=HTTPBasicAuth(FUSION_USER, FUSION_PASS), headers={"Accept": "application/json"})
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise ValueError(f"IRN {irn} not found in Oracle App Composer.")
    
    record = items[0]
    trx_id = record.get("Trx_Id_c")
    if not trx_id:
        raise ValueError(f"Record for IRN {irn} does not have a Trx_Id_c populated.")
        
    doc_no = record.get("DocNumber_c", str(trx_id))
    return str(trx_id), record.get("Id"), doc_no

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
        save_log_file("AppComp_Ewb_Retry", doc_no, payload, response=resp_data)
    else:
        save_log_file("AppComp_Ewb_Retry", doc_no, payload, response=resp_data, error=f"HTTP {fusion_resp.status_code}")
    fusion_resp.raise_for_status()
    return resp_data

def retry_ewaybill(irn: str) -> None:
    logger.info(f"Initiating E-Way Bill Retry for IRN: {irn}")
    fusion_cfg, supertax_cfg = load_config()
    
    try:
        trx_id, record_id, doc_no = get_fusion_record_by_irn(irn)
    except Exception as e:
        save_log_file("Ewb_Retry_Error", irn, {"irn": irn}, error=str(e))
        logger.error(str(e))
        sys.exit(1)

    bip_client = BIPReportClient(fusion_cfg)
    
    # --- UPDATED: Uses the EWB-specific report path from .env configuration ---
    if not fusion_cfg.ewb_report_abs_path:
        err = "FUSION_EWB_REPORT_ABS_PATH is missing from .env configuration."
        save_log_file("Ewb_Retry_Error", doc_no, {"trx_id": trx_id, "irn": irn}, error=err)
        logger.error(err)
        sys.exit(1)
        
    report_bytes = bip_client.run_report(output_format="EXCEL", report_path_override=fusion_cfg.ewb_report_abs_path)
    
    rows = parse_excel_report(report_bytes)
    grouped = group_rows_by_invoice(rows)
    
    invoice_rows = None
    for key, group in grouped.items():
        if str(key) == str(trx_id):
            invoice_rows = group
            break
            
    if not invoice_rows:
        err = f"Trx ID {trx_id} (Linked to IRN {irn}) was not returned in the Eway Bill Integration Report."
        save_log_file("Ewb_Retry_Error", doc_no, {"trx_id": trx_id, "irn": irn}, error=err)
        logger.error(err)
        sys.exit(1)
        
    mapped_invoice = build_invoice_payload(invoice_rows)
    if "EwbDtls" not in mapped_invoice:
        err = f"No valid E-Way Bill transport details found in report for Trx ID {trx_id}."
        save_log_file("Ewb_Retry_Error", doc_no, {"trx_id": trx_id}, error=err)
        logger.error(err)
        sys.exit(1)

    ewb_payload = {
        "ewaybill": [
            {
                "Irn": irn,
                "DocDtls": mapped_invoice.get("DocDtls", {}),
                "SellerDtls": {"Gstin": mapped_invoice.get("SellerDtls", {}).get("Gstin", "")},
                "EwbDtls": mapped_invoice.get("EwbDtls", {})
            }
        ]
    }
    
    headers = {"key": SUPERTAX_API_KEY, "Content-Type": "application/json"}
    
    try:
        supertax_resp = requests.post(SUPERTAX_EWB_URL, json=ewb_payload, headers=headers)
        try:
            resp_data = supertax_resp.json()
        except Exception:
            resp_data = supertax_resp.text
            
        save_log_file("Ewb_Retry", doc_no, ewb_payload, response=resp_data)
        
        if not supertax_resp.ok:
            logger.error(f"SuperTax HTTP Error: {resp_data}")
            supertax_resp.raise_for_status()
            
    except Exception as exc:
        save_log_file("Ewb_Retry", doc_no, ewb_payload, error=str(exc))
        logger.error(f"SuperTax EWB Call Failed: {exc}")
        sys.exit(1)

    items = resp_data.get("ewayBill", resp_data.get("ewaybill", [resp_data])) if isinstance(resp_data, dict) else [{}]
    response_item = items[0] if items else {}
    
    success_val = str(response_item.get("Success", ""))
    status_val = str(response_item.get("Status", ""))
    message_val = str(response_item.get("Message") or response_item.get("ErrorDetails") or "")
    
    fusion_update = {
        "InfoCode_c": success_val,
        "InfoDescCode_c": status_val,
        "InfoMessage_c": message_val[:200]
    }
    
    if success_val.lower() == "true" or status_val.upper() in ("SUCCESS", "GENERATED"):
        ewb_no = str(response_item.get("EwbNo", ""))
        fusion_update["EwbNo_c"] = ewb_no
        fusion_update["EwbDate_c"] = str(response_item.get("EwbDt", ""))
        fusion_update["EwbValidTill_c"] = str(response_item.get("EwbValidTill", ""))
        
        update_fusion_record(record_id, fusion_update, doc_no)
        console_msg = f"E-Way Bill {ewb_no} generated successfully. | Msg: {message_val}"
        logger.info(f"API Response: {console_msg}")
        print(f"API Response: {console_msg}")
    else:
        update_fusion_record(record_id, fusion_update, doc_no)
        logger.error(f"API Response (Rejected): {message_val}")
        print(f"API Response (Rejected): {message_val}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retry an E-Way Bill generation.")
    parser.add_argument("--irn", required=True, help="Invoice Reference Number (IRN)")
    args = parser.parse_args()
    
    retry_ewaybill(args.irn)