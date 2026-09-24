"""
Oracle Fusion AR Invoice -> SuperTax e-Invoice Integration
============================================================
Extracts AR invoice data from Oracle Fusion Receivables via a BI Publisher
(BIP) report exposed through the ExternalReportWSSService SOAP API, maps it
to the SuperTax e-Invoice JSON schema, and posts it to the SuperTax REST API.
"""

from __future__ import annotations

import json
from datetime import datetime
import base64
import csv
import io
import logging
import os
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import groupby
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

try:
    from dotenv import load_dotenv
    load_dotenv() 
except ImportError:
    pass

try:
    from urllib3.util.retry import Retry
except ImportError: 
    from urllib3.util import Retry  # type: ignore

from zeep import Client, Settings
from zeep.transports import Transport

# --------------------------------------------------------------------------
# 1. Configuration (No Parameters)
# --------------------------------------------------------------------------

@dataclass
class FusionConfig:
    base_url: str
    username: str
    password: str
    report_abs_path: str 
    bypass_cache: bool = False  
    flatten_xml: bool = False   

    def __post_init__(self) -> None:
        if not self.report_abs_path.lower().endswith(".xdo"):
            self.report_abs_path = f"{self.report_abs_path}.xdo"

@dataclass
class SuperTaxConfig:
    api_url: str
    api_key: str
    timeout_seconds: int = 30
    max_retries: int = 3

def load_config() -> tuple[FusionConfig, SuperTaxConfig]:
    def require(name: str) -> str:
        val = os.getenv(name)
        if not val:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return val

    fusion = FusionConfig(
        base_url=require("FUSION_BASE_URL"),
        username=require("FUSION_USERNAME"),
        password=require("FUSION_PASSWORD"),
        report_abs_path=require("FUSION_REPORT_ABS_PATH"),
        bypass_cache=os.getenv("FUSION_BYPASS_CACHE", "false").lower() in ("1", "true", "yes"),
        flatten_xml=os.getenv("FUSION_FLATTEN_XML", "false").lower() in ("1", "true", "yes"),
    )
    supertax = SuperTaxConfig(
        api_url=require("SUPERTAX_API_URL"),
        api_key=require("SUPERTAX_API_KEY"),
        timeout_seconds=int(os.getenv("SUPERTAX_TIMEOUT_SECONDS", "30")),
        max_retries=int(os.getenv("SUPERTAX_MAX_RETRIES", "3")),
    )
    return fusion, supertax

# --------------------------------------------------------------------------
# 2. Logging Setup
# --------------------------------------------------------------------------

def setup_logging() -> logging.Logger:
    master_log_file = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs\einvoice_integration_log.log"
    os.makedirs(os.path.dirname(master_log_file), exist_ok=True)
    
    logger = logging.getLogger("einvoice")
    logger.setLevel(logging.INFO)
    
    fmt = logging.Formatter("%(asctime)s | [EINVOICE] | %(levelname)-8s | %(message)s")
    
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)
    
    file_handler = RotatingFileHandler(master_log_file, maxBytes=5_000_000, backupCount=5)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

# --------------------------------------------------------------------------
# 3. Oracle Fusion BIP (SOAP) extraction
# --------------------------------------------------------------------------

class BIPReportClient:
    def __init__(self, config: FusionConfig):
        self.config = config
        self.wsdl_url = f"{config.base_url.rstrip('/')}/xmlpserver/services/ExternalReportWSSService?wsdl"
        session = requests.Session()
        session.auth = HTTPBasicAuth(config.username, config.password)
        transport = Transport(session=session, timeout=60, operation_timeout=120)
        settings = Settings(strict=False, xml_huge_tree=True)
        logger.info("Connecting to Fusion BIP WSDL: %s", self.wsdl_url)
        self.client = Client(wsdl=self.wsdl_url, transport=transport, settings=settings)

    def run_report(self, output_format: str = "XML") -> bytes:
        report_request = {
            "attributeFormat": output_format,
            "attributeTemplate": None,
            "reportAbsolutePath": self.config.report_abs_path,
            "parameterNameValues": None, 
            "sizeOfDataChunkDownload": -1,
            "byPassCache": self.config.bypass_cache,
            "flattenXML": self.config.flatten_xml,
        }

        logger.info("Running BIP report %s (format=%s)", self.config.report_abs_path, output_format)

        try:
            response = self.client.service.runReport(reportRequest=report_request, appParams="")
        except Exception:
            logger.exception("BIP runReport call failed")
            raise

        if not getattr(response, "reportBytes", None):
            logger.warning("BIP report returned no data.")
            return b""

        raw_bytes = response.reportBytes
        if isinstance(raw_bytes, str):
            raw_bytes = base64.b64decode(raw_bytes)
                
        return raw_bytes

def parse_xml_report(report_bytes: bytes) -> List[Dict[str, str]]:
    if not report_bytes: return []
    from lxml import etree
    cleaned = report_bytes
    if cleaned.startswith(b"\xef\xbb\xbf"): cleaned = cleaned[3:]
    cleaned = cleaned.strip()

    try:
        root = etree.fromstring(cleaned)
    except etree.XMLSyntaxError:
        logger.exception("Failed to parse report output as XML")
        raise

    for elem in root.iter():
        if isinstance(elem.tag, str) and "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    row_xpath_override = os.getenv("FUSION_REPORT_ROW_XPATH", ".//SELLER")
    row_elements = root.findall(row_xpath_override)
    
    rows: List[Dict[str, str]] = []
    for row_el in row_elements:
        row: Dict[str, str] = {}
        for child in row_el.iter():
            if len(child) == 0 and child is not row_el:
                row[child.tag.upper()] = (child.text or "").strip()
        rows.append(row)
    return rows

def parse_excel_report(report_bytes: bytes) -> List[Dict[str, str]]:
    if not report_bytes: return []
    import pandas as pd
    header_row = int(os.getenv("FUSION_REPORT_HEADER_ROW", "0"))
    df = None
    
    for attempt, reader in (
        ("excel", lambda: pd.read_excel(io.BytesIO(report_bytes), header=header_row)),
        ("html-table", lambda: pd.read_html(io.BytesIO(report_bytes), header=header_row)[0]),
    ):
        try:
            df = reader()
            break
        except Exception:
            pass

    if df is None: raise ValueError("Could not parse as Excel/HTML")

    df = df.ffill().fillna("")
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df.astype(str).to_dict(orient="records")

# --------------------------------------------------------------------------
# 4. Data Cleaners & Mapping 
# --------------------------------------------------------------------------

def to_number(value: Optional[str]):
    if not value or str(value).strip() == "": return 0.0
    try:
        dec = Decimal(str(value).strip())
        val = int(dec) if dec == dec.to_integral_value() else float(dec)
        return abs(val)
    except InvalidOperation:
        return 0.0

def clean_hsn(value: Optional[str]) -> str:
    if not value: return ""
    return str(value).split('.')[0].strip()

def clean_gst_rate(value: Optional[str]) -> float:
    if not value: return 0.0
    v = str(value).replace('%', '').strip()
    try:
        rate = abs(float(v))
        if 0 < rate < 1: rate = rate * 100
        return int(rate) if rate.is_integer() else round(rate, 2)
    except ValueError:
        return 0.0

def format_date(value: Optional[str]) -> str:
    if not value or str(value).strip() == "": return ""
    v = str(value).strip()
    if len(v) >= 10 and v[4] == '-' and v[7] == '-':
        return f"{v[8:10]}/{v[5:7]}/{v[0:4]}"
    return v.replace("-", "/")

def clean_veh_type(value: Optional[str]) -> str:
    if not value: return ""
    v = str(value).strip().upper()
    if "ODC" in v or v == "O": return "O"
    if "REGULAR" in v or v == "R": return "R"
    return str(value)

def clean_distance(value: Optional[str]) -> Optional[int]:
    if not value or str(value).strip() == "": return None
    try:
        return abs(int(float(str(value).strip())))
    except ValueError:
        return None

REPORT_COLUMN_INVOICE_ID = "CUSTOMER TRX ID"   

REPORT_TO_TRANDTLS = {
    "TaxSch": lambda r: "GST",
    "SupTyp": lambda r: r.get("SUPPLY TYPE") or "B2B",
    "RegRev": lambda r: "Y" if str(r.get("REVERSE CHARGE", "")).upper() in ("Y", "YES") else "N",
}

REPORT_TO_DOCDTLS = {
    "Typ": lambda r: r.get("DOCUMENT TYPE", "INV"),
    "No": lambda r: r.get("DOCUMENT NUMBER"),
    "Dt": lambda r: format_date(r.get("DOCUMENT DATE")), 
}

REPORT_TO_SELLERDTLS = {
    "Gstin": lambda r: r.get("SELLER GSTIN"),
    "LglNm": lambda r: r.get("SELLER LEGALNAME"),
    "TrdNm": lambda r: r.get("SELLER LEGALNAME"),
    "Addr1": lambda r: r.get("SELLER ADDRESS 1"),
    "Addr2": lambda r: r.get("SELLER ADDRESS 2") or None,
    "Loc": lambda r: r.get("SELLER CITY"),
    "Pin": lambda r: str(r.get("SELLER PINCODE", "")).replace(".0", ""),
    "Stcd": lambda r: r.get("SELLER GSTIN")[:2] if r.get("SELLER GSTIN") else "",
}

REPORT_TO_BUYERDTLS = {
    "Gstin": lambda r: r.get("BUYER GSTIN"),
    "LglNm": lambda r: r.get("BUYER LEGALNAME"),
    "TrdNm": lambda r: r.get("BUYER LEGALNAME"),
    "Pos": lambda r: r.get("BUYER GSTIN")[:2] if r.get("BUYER GSTIN") else "",
    "Addr1": lambda r: r.get("BUYER ADDRESS 1"),
    "Addr2": lambda r: r.get("BUYER ADDRESS 2") or None,
    "Loc": lambda r: r.get("BUYER CITY"),
    "Pin": lambda r: str(r.get("BUYER PINCODE", "")).replace(".0", ""),
    "Stcd": lambda r: r.get("BUYER GSTIN")[:2] if r.get("BUYER GSTIN") else "",
}

REPORT_TO_ITEM = {
    "IsServc": lambda r: r.get("IS SERVICE") or "N", 
    "PrdDesc": lambda r: r.get("PRODUCT DESCRIPTION"),
    "HsnCd": lambda r: clean_hsn(r.get("HSN CODE")) or "998314",
    "Qty": lambda r: to_number(r.get("QUANTITY")),
    "Unit": lambda r: r.get("UNIT", "NOS"),
    "UnitPrice": lambda r: to_number(r.get("UNIT PRICE")),
    "Discount": lambda r: to_number(r.get("TOTAL DISCOUNT")) or 0,
    "GstRt": lambda r: clean_gst_rate(r.get("GSTRATE")),
    "SgstAmt": lambda r: to_number(r.get("SGST AMOUNT")) or 0,
    "IgstAmt": lambda r: to_number(r.get("IGST AMOUNT")) or 0,
    "CgstAmt": lambda r: to_number(r.get("CGST AMOUNT")) or 0,
    "CesRt": lambda r: to_number(r.get("CESSRATE")) or 0,
    "CesAmt": lambda r: to_number(r.get("CESS AMOUNT")) or 0,
    "CesNonAdvlAmt": lambda r: to_number(r.get("CESS NON-ADVOL AMOUNT")) or 0,
    "StateCesRt": lambda r: to_number(r.get("STATE CESS RATE")) or 0,
    "StateCesAmt": lambda r: to_number(r.get("STATE CESS AMOUNT")) or 0,
    "StateCesNonAdvlAmt": lambda r: to_number(r.get("STATE CESS NON-ADVOL AMOUNT")) or 0,
    "OthChrg": lambda r: 0,
}

REPORT_TO_EWB = {
    "TransId": lambda r: r.get("TRANSPORTER GSTIN"),
    "TransName": lambda r: r.get("TRANSPORTER NAME.1") or r.get("TRANSPORTER NAME"),
    "TransMode": lambda r: r.get("TRANSPORTER MODE"),
    "Distance": lambda r: clean_distance(r.get("TRANSPORT DISTANCE")),
    "TransDocNo": lambda r: r.get("TRANSPORTER DOCUMENT NUMBER"),
    "TransDocDt": lambda r: format_date(r.get("TRASNPORTER DOCUMENT DATE") or r.get("TRANSPORTER DOCUMENT DATE")),
    "VehNo": lambda r: r.get("VEHICLE NUMBER.1") or r.get("VEHICLE NUMBER"),
    "VehType": lambda r: clean_veh_type(r.get("VEHICLE TYPE"))
}

def _apply_mapping(row: Dict[str, str], mapping: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for target_field, getter in mapping.items():
        value = getter(row)
        if value is not None and value != "" and value != "None" and value != "nan":
            out[target_field] = value
    return out

def build_invoice_payload(invoice_rows: List[Dict[str, str]]) -> Dict[str, Any]:
    header_row = invoice_rows[0]
    items = []
    
    for idx, line_row in enumerate(invoice_rows, start=1):
        mapped_item = _apply_mapping(line_row, REPORT_TO_ITEM)
        mapped_item["SlNo"] = str(idx)
        
        qty = round(mapped_item.get("Qty", 1.0) or 1.0, 3)
        price = round(mapped_item.get("UnitPrice", 0.0) or 0.0, 3)
        discount = round(mapped_item.get("Discount", 0.0) or 0.0, 2)
        
        ass_amt = abs(round((qty * price) - discount, 2))
        mapped_item["TotAmt"] = abs(round(qty * price, 2))
        mapped_item["AssAmt"] = ass_amt
        
        cgst = round(mapped_item.get("CgstAmt", 0.0) or 0.0, 2)
        sgst = round(mapped_item.get("SgstAmt", 0.0) or 0.0, 2)
        igst = round(mapped_item.get("IgstAmt", 0.0) or 0.0, 2)
        cess = round(mapped_item.get("CesAmt", 0.0) or 0.0, 2)
        cess_non = round(mapped_item.get("CesNonAdvlAmt", 0.0) or 0.0, 2)
        st_cess = round(mapped_item.get("StateCesAmt", 0.0) or 0.0, 2)
        st_cess_non = round(mapped_item.get("StateCesNonAdvlAmt", 0.0) or 0.0, 2)
        oth_chrg = round(mapped_item.get("OthChrg", 0.0) or 0.0, 2)
        
        mapped_item["TotItemVal"] = round(ass_amt + cgst + sgst + igst + cess + cess_non + st_cess + st_cess_non + oth_chrg, 2)
        items.append(mapped_item)

    invoice: Dict[str, Any] = {
        "CustDocNo": header_row.get("DOCUMENT NUMBER"),
        "Version": "1.01",
        "TranDtls": _apply_mapping(header_row, REPORT_TO_TRANDTLS),
        "DocDtls": _apply_mapping(header_row, REPORT_TO_DOCDTLS),
        "SellerDtls": _apply_mapping(header_row, REPORT_TO_SELLERDTLS),
        "BuyerDtls": _apply_mapping(header_row, REPORT_TO_BUYERDTLS),
        "ItemList": items,
        "ValDtls": {},
    }
    
    prec_inv_no = header_row.get("PRECEEDING INVOICE NUMBER") or header_row.get("PRECEDING INVOICE NUMBER")
    prec_inv_dt = format_date(header_row.get("PRECEDING INVOICE DATE"))
    
    if prec_inv_no and prec_inv_no.strip():
        prec_doc = {"InvNo": str(prec_inv_no).strip()}
        if prec_inv_dt and prec_inv_dt.strip():
            prec_doc["InvDt"] = str(prec_inv_dt).strip()
        invoice["PrecDocDtls"] = [prec_doc]
        
    ewb_dtls = _apply_mapping(header_row, REPORT_TO_EWB)
    if ewb_dtls:
        ewb_dtls["IsEWayBillIntegrated"] = "true" 
        invoice["EwbDtls"] = ewb_dtls
    
    total_ass_val = sum(item["AssAmt"] for item in items)
    total_cgst = sum(item.get("CgstAmt", 0.0) or 0.0 for item in items)
    total_sgst = sum(item.get("SgstAmt", 0.0) or 0.0 for item in items)
    total_igst = sum(item.get("IgstAmt", 0.0) or 0.0 for item in items)
    total_cess = sum((item.get("CesAmt", 0.0) or 0.0) + (item.get("CesNonAdvlAmt", 0.0) or 0.0) for item in items)
    total_st_cess = sum((item.get("StateCesAmt", 0.0) or 0.0) + (item.get("StateCesNonAdvlAmt", 0.0) or 0.0) for item in items)
    
    val_dtls = invoice["ValDtls"]
    val_dtls["AssVal"] = round(total_ass_val, 2)
    val_dtls["CgstVal"] = round(total_cgst, 2)
    val_dtls["SgstVal"] = round(total_sgst, 2)
    val_dtls["IgstVal"] = round(total_igst, 2)
    val_dtls["CesVal"] = round(total_cess, 2)
    val_dtls["StCesVal"] = round(total_st_cess, 2)
    
    round_off = round(to_number(header_row.get("ROUNDING OFF")), 2)
    val_dtls["RndOffAmt"] = round_off
    val_dtls["TotInvVal"] = round(total_ass_val + total_cgst + total_sgst + total_igst + total_cess + total_st_cess + round_off, 2)
    
    return invoice

def group_rows_by_invoice(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    id_col = REPORT_COLUMN_INVOICE_ID
    if rows and id_col not in rows[0]:
        for alt in ["CUSTOMER TRX ID", "TRX_ID", "ID", "CUSTOMER_TRX_ID_C", "CUSTOMER_TRX_ID"]:
            if alt in rows[0]:
                id_col = alt
                break
                
    logger.info(f"Grouping invoices using column identifier: '{id_col}'")
    
    rows_sorted = sorted(rows, key=lambda r: str(r.get(id_col, "")))
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for key, group in groupby(rows_sorted, key=lambda r: str(r.get(id_col, ""))):
        grouped[key] = list(group)
    return grouped

# --------------------------------------------------------------------------
# 5. SuperTax Client & Writeback Logic
# --------------------------------------------------------------------------

class SuperTaxClient:
    def __init__(self, config: SuperTaxConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"key": config.api_key, "Content-Type": "application/json", "Accept": "application/json"})
        retry = Retry(total=config.max_retries, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=frozenset(["POST"]), raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def send_invoices(self, invoices: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {"invoices": invoices}
        try:
            resp = self.session.post(self.config.api_url, json=payload, timeout=self.config.timeout_seconds)
            if resp.status_code == 429: resp.raise_for_status()
            if 400 <= resp.status_code < 600:
                logger.error("SuperTax EINV API returned HTTP %s: %s", resp.status_code, resp.text[:2000])
                resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException:
            logger.exception("Network error calling SuperTax API")
            raise
        except ValueError:
            logger.error("SuperTax API response was not valid JSON")
            raise

# --- UPDATED: Centralized EInvoice .txt Logging Functions ---
LOG_DIR_EINV = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs\EInvoice"
os.makedirs(LOG_DIR_EINV, exist_ok=True)

def save_einv_log(doc_no: str, payload: Dict[str, Any], response: Any = None, error: str = None) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_doc_no = "".join(c for c in str(doc_no) if c.isalnum() or c in ("-", "_"))
    filepath = os.path.join(LOG_DIR_EINV, f"EInvoice_{safe_doc_no}_{timestamp}.txt")
    log_content = {
        "timestamp": datetime.now().isoformat(),
        "document_no": doc_no,
        "request_payload": payload,
        "response": response,
        "error": error
    }
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_content, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write EINV txt payload log to {filepath}: {e}")

def save_fusion_log(doc_no: str, payload: Dict[str, Any], response: Any = None, error: str = None) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_doc_no = "".join(c for c in str(doc_no) if c.isalnum() or c in ("-", "_"))
    filepath = os.path.join(LOG_DIR_EINV, f"AppComp_EInvoice_{safe_doc_no}_{timestamp}.txt")
    log_content = {
        "timestamp": datetime.now().isoformat(), 
        "document_no": doc_no, 
        "fusion_request_payload": payload, 
        "fusion_response": response, 
        "error": error
    }
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_content, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write Fusion txt payload log to {filepath}: {e}")

def write_back_to_fusion(request_payload: Dict[str, Any], supertax_response: Dict[str, Any], fusion_cfg: FusionConfig, trx_id: str, doc_no: str) -> None:
    custom_object_url = f"{fusion_cfg.base_url.rstrip('/')}/fscmRestApi/resources/11.13.18.05/Inspira_Einvoice_c"
    inv_data = request_payload["invoices"][0]
    
    response_items = []
    if "data" in supertax_response and isinstance(supertax_response["data"], list):
        response_items = supertax_response["data"]
    elif "results" in supertax_response and isinstance(supertax_response["results"], list):
        response_items = supertax_response["results"]
    elif "invoices" in supertax_response and isinstance(supertax_response["invoices"], list):
        response_items = supertax_response["invoices"]
    else:
        response_items = [supertax_response] 
        
    combined_messages = []
    all_success = True
    overall_status = "SUCCESS"
    response_data = response_items[0] if response_items else {}

    for item in response_items:
        msg = str(item.get("Messages") or item.get("ErrorDetails") or "")
        if msg and msg not in combined_messages:
            combined_messages.append(msg)
            
        item_status = str(item.get("Status") or item.get("status") or "").upper()
        if item_status in ("ERROR", "FAILED"):
            overall_status = item_status
            
        item_success = item.get("Success")
        if item_success is False or str(item_success).lower() == "false":
            all_success = False

    status = overall_status if not all_success else (response_data.get("Status") or "SUCCESS")
    success_flag = "true" if all_success else "false"
    
    raw_message = " | ".join(combined_messages) if combined_messages else "No message"
    safe_message = raw_message[:200] 
    
    fusion_payload = {
        "Supply_Type_c": inv_data.get("TranDtls", {}).get("SupTyp", ""),
        "SellerGSTIN_c": inv_data.get("SellerDtls", {}).get("Gstin", ""),
        "DocType_c": inv_data.get("DocDtls", {}).get("Typ", ""),
        "DocNumber_c": inv_data.get("DocDtls", {}).get("No", ""),
        "Success_c": success_flag,
        "Messages_c": safe_message,
        "Status_c": status,
        "Trx_Id_c": str(trx_id), 
        "Trx_Number_c": inv_data.get("DocDtls", {}).get("No", "")
    }
    
    def add_if_exists(target_key, value):
        val_str = str(value).strip()
        if val_str and val_str not in ("None", "nan", ""):
            fusion_payload[target_key] = val_str

    add_if_exists("DocDate_c", inv_data.get("DocDtls", {}).get("Dt"))
    
    ack_date = response_data.get("AckDate") or response_data.get("AckDt")
    add_if_exists("Ack_Date_c", ack_date)
    add_if_exists("Ack_Number_c", response_data.get("AckNo"))
    
    add_if_exists("Record_c", response_data.get("Record"))
    add_if_exists("FinYear_c", response_data.get("Fy"))
    add_if_exists("IRN_Number_c", response_data.get("Irn"))
    add_if_exists("SignedQRCode_c", response_data.get("SignedQRCode"))
    
    qr_code = response_data.get("QrCode")
    if qr_code:
        add_if_exists("RawQRCode_c", str(qr_code)[:500])
        
    add_if_exists("EwbNo_c", response_data.get("EwbNo"))
    
    ewb_dt = response_data.get("EwbDate") or response_data.get("EwbDt")
    add_if_exists("EwbDate_c", ewb_dt)
    add_if_exists("EwbValidTill_c", response_data.get("EwbValidTill"))
    
    info_code = response_data.get("InfoCode") or response_data.get("InfCode") or response_data.get("InfoDtls", {}).get("InfCode")
    add_if_exists("InfoCode_c", info_code)

    info_desc = response_data.get("InfoDescCode") or response_data.get("InfDesc") or response_data.get("InfoDtls", {}).get("Desc")
    add_if_exists("InfoDescCode_c", info_desc)

    info_msg = response_data.get("InfoMessage") or response_data.get("InfMsg") or response_data.get("InfoDtls", {}).get("Msg")
    if info_msg:
        add_if_exists("InfoMessage_c", str(info_msg)[:200])
    
    auth = HTTPBasicAuth(fusion_cfg.username, fusion_cfg.password)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    
    try:
        query_url = f"{custom_object_url}?q=Trx_Id_c={trx_id}"
        get_resp = requests.get(query_url, auth=auth, headers=headers)
        get_resp.raise_for_status()
        items = get_resp.json().get("items", [])
        
        fusion_resp = None
        if items:
            record_id = items[0].get("Id")  
            patch_url = f"{custom_object_url}/{record_id}"
            logger.info(f"Record exists. Updating row (Id: {record_id})...")
            fusion_resp = requests.patch(patch_url, json=fusion_payload, auth=auth, headers=headers)
            action = "updated"
        else:
            logger.info(f"No existing record. Creating new row...")
            fusion_resp = requests.post(custom_object_url, json=fusion_payload, auth=auth, headers=headers)
            action = "created"
            
        try:
            resp_data = fusion_resp.json()
        except ValueError:
            resp_data = fusion_resp.text

        if fusion_resp.ok:
            save_fusion_log(doc_no, fusion_payload, response=resp_data)
            logger.info(f"Successfully {action} record for Doc {doc_no} (Trx ID {trx_id}).")
        else:
            error_msg = f"HTTP {fusion_resp.status_code}"
            save_fusion_log(doc_no, fusion_payload, response=resp_data, error=error_msg)
            logger.error(f"Fusion API Error Body: {resp_data}")
            
        fusion_resp.raise_for_status()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to write to Fusion Custom Object: {e}")
        if 'fusion_resp' not in locals() or fusion_resp is None:
            save_fusion_log(doc_no, fusion_payload, error=str(e))

# --------------------------------------------------------------------------
# 6. Orchestration
# --------------------------------------------------------------------------

def run_integration() -> List[Dict[str, Any]]:
    fusion_cfg, supertax_cfg = load_config()
    bip_client = BIPReportClient(fusion_cfg)
    output_format = os.getenv("FUSION_REPORT_OUTPUT_FORMAT", "XML").upper()
    
    report_bytes = bip_client.run_report(output_format=output_format)
    
    if output_format == "CSV": rows = parse_csv_report(report_bytes)
    elif output_format == "XML": rows = parse_xml_report(report_bytes)
    elif output_format in ("XLS", "XLSX", "EXCEL", "EXCEL2000"): rows = parse_excel_report(report_bytes)
    else: raise ValueError(f"Unsupported format '{output_format}'")

    if not rows:
        logger.info("No invoices returned by the report. Nothing to send.")
        return []

    grouped = group_rows_by_invoice(rows)
    logger.info("Report returned %d invoice(s) across %d row(s).", len(grouped), len(rows))
    tax_client = SuperTaxClient(supertax_cfg)
    results: List[Dict[str, Any]] = []

    for customer_trx_id, invoice_rows in grouped.items():
        if not customer_trx_id: 
            available_cols = list(invoice_rows[0].keys())
            logger.warning(f"SKIPPING ROW: Could not find the Customer Trx ID. Available columns are: {available_cols}")
            continue 
            
        try:
            invoice_payload = build_invoice_payload(invoice_rows)
            doc_no = invoice_payload.get("CustDocNo", str(customer_trx_id))
            full_request_payload = {"invoices": [invoice_payload]}
            logger.info("Invoice %s (Doc %s) Request Payload: %s", customer_trx_id, doc_no, json.dumps(full_request_payload))

            response = tax_client.send_invoices([invoice_payload])
            logger.info("Invoice %s (Doc %s) submitted. Response: %s", customer_trx_id, doc_no, response)
            results.append({"invoice": customer_trx_id, "doc_no": doc_no, "success": True, "response": response})
            
            # Save request/response into Logs/EInvoice/EInvoice_<DocNo>_<Date>_<Time>.txt
            save_einv_log(doc_no, full_request_payload, response=response)
            
            # Save App Composer writeback into Logs/EInvoice/AppComp_EInvoice_<DocNo>_<Date>_<Time>.txt
            write_back_to_fusion(full_request_payload, response, fusion_cfg, customer_trx_id, doc_no)
            
        except Exception as exc:  # noqa: BLE001
            doc_no = locals().get("doc_no", str(customer_trx_id))
            logger.exception("Failed to submit invoice %s (Doc %s)", customer_trx_id, doc_no)
            results.append({"invoice": customer_trx_id, "doc_no": doc_no, "success": False, "error": str(exc)})
            
            payload_to_log = locals().get("full_request_payload", {"invoices": [{}]})
            save_einv_log(doc_no, payload_to_log, error=str(exc))
            
            error_response_mock = {"ErrorDetails": str(exc), "status": "FAILED"}
            write_back_to_fusion(
                payload_to_log, error_response_mock, fusion_cfg, customer_trx_id, doc_no
            )
        time.sleep(1)    
    return results

def main() -> None:
    logger.info("Starting batch execution for Oracle to SuperTax integration...")
    results = run_integration()
    
    failures = [r for r in results if not r.get("success")]
    if failures:
        logger.error("%d invoice(s) failed to submit.", len(failures))
        sys.exit(1)

if __name__ == "__main__":
    main()