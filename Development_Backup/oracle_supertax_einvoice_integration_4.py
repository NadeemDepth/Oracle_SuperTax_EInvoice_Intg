"""
Oracle Fusion AR Invoice -> SuperTax e-Invoice Integration
============================================================

Extracts AR invoice data from Oracle Fusion Receivables via a BI Publisher
(BIP) report exposed through the ExternalReportWSSService SOAP API, maps it
to the SuperTax e-Invoice JSON schema, and posts it to the SuperTax REST API.

Supports two run modes:
    1. Batch mode   -> python oracle_supertax_einvoice_integration.py
       Pulls every invoice the BIP report returns (i.e. whatever filter the
       report/data model itself applies, e.g. "not yet e-invoiced").
    2. On-demand    -> python oracle_supertax_einvoice_integration.py --invoice-number MH-INV22060051
       Passes a bind parameter to the BIP report so it returns just one
       invoice. Requires the report's data model to expose that parameter
       (see "Oracle configuration prerequisites" in the accompanying notes).

Configuration is read from environment variables (see .env.example). Never
hardcode credentials or the SuperTax API key directly in this file.
"""

from __future__ import annotations

import json
from datetime import datetime
import argparse
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
from typing import Any, Dict, Iterable, List, Optional

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads a .env file in the current working directory, if present
except ImportError:
    # python-dotenv not installed — fine as long as the env vars are set some
    # other way (real OS environment variables, CI/CD secrets, etc.)
    pass

try:
    from urllib3.util.retry import Retry
except ImportError:  # very old urllib3
    from urllib3.util import Retry  # type: ignore

from zeep import Client, Settings
from zeep.transports import Transport

# --------------------------------------------------------------------------
# 1. Configuration (env-driven — do not hardcode secrets)
# --------------------------------------------------------------------------

@dataclass
class FusionConfig:
    base_url: str
    username: str
    password: str
    report_abs_path: str  # e.g. /Custom/Inspira/E-Invoicing/E-Invoice Integration Report(.xdo)
    invoice_number_param: str = "p_customer_trx_id"  # bind param name on the report, if any
    bypass_cache: bool = False  # forces BIP to re-run against live data instead of a cached result
    flatten_xml: bool = False   # asks BIP to flatten nested XML groups — most useful with XML output

    def __post_init__(self) -> None:
        # BIP requires the .xdo extension on reportAbsolutePath; add it if missing
        # so the value can be configured either way in .env.
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
            raise RuntimeError(
                f"Missing required environment variable: {name}. "
                f"See .env.example for the full list."
            )
        return val

    fusion = FusionConfig(
        base_url=require("FUSION_BASE_URL"),
        username=require("FUSION_USERNAME"),
        password=require("FUSION_PASSWORD"),
        report_abs_path=require("FUSION_REPORT_ABS_PATH"),
        invoice_number_param=os.getenv("FUSION_INVOICE_PARAM", "p_customer_trx_id"),
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
# 2. Logging
# --------------------------------------------------------------------------

def setup_logging(log_file: str = "einvoice_integration.log") -> logging.Logger:
    logger = logging.getLogger("einvoice")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()


# --------------------------------------------------------------------------
# 3. Oracle Fusion BIP (SOAP) extraction
# --------------------------------------------------------------------------

class BIPReportClient:
    """
    Thin wrapper around Oracle's ExternalReportWSSService SOAP API for
    running a BI Publisher report and retrieving its output.
    """

    def __init__(self, config: FusionConfig):
        self.config = config
        self.wsdl_url = f"{config.base_url.rstrip('/')}/xmlpserver/services/ExternalReportWSSService?wsdl"

        session = requests.Session()
        session.auth = HTTPBasicAuth(config.username, config.password)

        transport = Transport(session=session, timeout=60, operation_timeout=120)
        settings = Settings(strict=False, xml_huge_tree=True)

        logger.info("Connecting to Fusion BIP WSDL: %s", self.wsdl_url)
        self.client = Client(wsdl=self.wsdl_url, transport=transport, settings=settings)

    def run_report(self, parameters: Optional[Dict[str, str]] = None, output_format: str = "XML") -> bytes:
        """
        Calls runReport and returns the decoded report bytes.

        Note on auth: Fusion's ExternalReportWSSService normally accepts the
        same HTTP Basic credentials used for Fusion REST APIs. If your
        environment enforces WS-Security UsernameToken instead, add the
        zeep wsse.UsernameToken plugin when constructing Client().

        Note on output_format: "XML" (the raw BIP data-engine output) is used
        by default because it does not depend on a CSV template being
        registered against the report — every BIP report can return XML.
        "CSV" only works if a CSV output type has been explicitly enabled on
        the report definition; if it hasn't, BIP may silently return a
        different format (e.g. PDF/Excel bytes), which then fails to decode
        as text downstream.
        """
        param_items = []
        if parameters:
            for name, value in parameters.items():
                param_items.append({"item": name, "values": {"item": [str(value)]}})

        report_request = {
            "attributeFormat": output_format,
            "attributeTemplate": None,
                                 
                                
            "reportAbsolutePath": self.config.report_abs_path,
            "parameterNameValues": {"item": param_items} if param_items else None,
            "sizeOfDataChunkDownload": -1,
            "byPassCache": self.config.bypass_cache,
            "flattenXML": self.config.flatten_xml,
        }

        logger.info(
            "Running BIP report %s (format=%s, params=%s)",
            self.config.report_abs_path, output_format, parameters,
        )

        try:
            # appParams is a required (if unused) argument on this WSDL —
            # pass an empty string rather than None, which zeep treats as
            # "field not provided" and rejects for required elements.
            response = self.client.service.runReport(
                reportRequest=report_request, appParams=""
            )
        except Exception:
            logger.exception("BIP runReport call failed")
            raise

        content_type = getattr(response, "reportContentType", None)
        logger.info("BIP report response content type: %s", content_type)

        if not getattr(response, "reportBytes", None):
            logger.warning("BIP report returned no data.")
            return b""

        raw_response_bytes = response.reportBytes
        if isinstance(raw_response_bytes, str):
            # Some environments return reportBytes as a base64 string.
            raw_bytes = base64.b64decode(raw_response_bytes)
        else:
            # zeep decodes xsd:base64Binary fields to raw bytes automatically —
            # in that case reportBytes is already the decoded content, so
            # decoding it again as base64 would fail (or silently corrupt it).
            raw_bytes = raw_response_bytes

        if os.getenv("FUSION_DUMP_RAW_REPORT", "").lower() in ("1", "true", "yes"):
            dump_path = f"report_output_debug.{('xml' if output_format.upper() == 'XML' else output_format.lower())}"
            with open(dump_path, "wb") as fh:
                fh.write(raw_bytes)
            logger.info("Raw report output dumped to %s for inspection.", dump_path)

        return raw_bytes


def parse_csv_report(report_bytes: bytes) -> List[Dict[str, str]]:
    """Parses the CSV bytes returned by the BIP report into a list of dict rows."""
    if not report_bytes:
        return []
    try:
        text = report_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        dump_path = _dump_debug_bytes(report_bytes, suffix="unknown")
        raise ValueError(
            "Report output is not valid UTF-8 text — this report/environment "
            "is likely not honoring the requested CSV format and returning "
            f"something else (e.g. its native Excel bytes). Dumped to {dump_path} "
            "— open it in a hex/text editor to confirm what it actually is."
        )
    reader = csv.DictReader(io.StringIO(text))
    # Normalize header whitespace/case so column lookups are forgiving.
    rows = []
    for raw_row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in raw_row.items()})
    return rows


def _dump_debug_bytes(report_bytes: bytes, suffix: str = "bin") -> str:
    """Always-available fallback dump used when parsing fails, regardless of
    the FUSION_DUMP_RAW_REPORT flag, so there's something to inspect."""
    dump_path = f"report_output_debug_onfail.{suffix}"
    try:
        with open(dump_path, "wb") as fh:
            fh.write(report_bytes or b"")
        logger.error("Raw report bytes dumped to %s for inspection.", dump_path)
    except OSError:
        logger.exception("Could not write debug dump to %s", dump_path)
    return dump_path


def parse_xml_report(report_bytes: bytes) -> List[Dict[str, str]]:
    """
    Parses the raw BIP data-engine XML into a list of flat dict rows.

    BIP's raw XML output nests each repeating row under a group element
    (commonly like <G_1>...</G_1>, repeated under a <LIST_G_1> parent) whose
    exact tag names come from the Data Model, not a fixed standard. Rather
    than hardcode those names, this walks the tree, finds whichever element
    tag repeats most often as siblings (i.e. the row/detail level), and
    flattens each occurrence's leaf elements into a dict of {column: value}.

    If your data model's structure doesn't flatten cleanly this way (e.g. it
    nests header and line items as separate levels), adjust ROW_XPATH below
    to point at the exact repeating element once you've inspected the raw
    XML (set FUSION_DUMP_RAW_REPORT=1 to save it to report_output_debug.xml).
    """
    if not report_bytes:
        return []

    from lxml import etree
    from collections import Counter

    # Strip a UTF-8 BOM and any leading/trailing whitespace — both are
    # common causes of "Start tag expected, '<' not found" even when the
    # content is otherwise valid XML.
    cleaned = report_bytes
    if cleaned.startswith(b"\xef\xbb\xbf"):
        cleaned = cleaned[3:]
    cleaned = cleaned.strip()

    if not cleaned.startswith(b"<"):
        dump_path = _dump_debug_bytes(report_bytes, suffix="unknown")
        preview = report_bytes[:200]
        raise ValueError(
            "Report output does not look like XML (doesn't start with '<' "
            "after stripping BOM/whitespace) — this report/environment may "
            "be ignoring the requested output format, same as it did for "
            f"CSV. First bytes: {preview!r}. Full bytes dumped to {dump_path} "
            "— open it in a hex/text editor and share what it actually is."
        )

    try:
        root = etree.fromstring(cleaned)
    except etree.XMLSyntaxError:
        dump_path = _dump_debug_bytes(report_bytes, suffix="xml")
        logger.exception("Failed to parse report output as XML; dumped to %s", dump_path)
        raise

    # Strip namespaces so tag lookups are simple.
    for elem in root.iter():
        if isinstance(elem.tag, str) and "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    row_xpath_override = os.getenv("FUSION_REPORT_ROW_XPATH")  # e.g. ".//G_1"
    if row_xpath_override:
        row_elements = root.findall(row_xpath_override)
    else:
        tag_counts: Counter = Counter()
        for parent in root.iter():
            child_tags = [c.tag for c in parent]
            for tag, cnt in Counter(child_tags).items():
                if cnt > 1:
                    tag_counts[tag] += cnt
        if not tag_counts:
            logger.warning(
                "Could not detect a repeating row element in the report XML; "
                "treating the root's direct children as rows. Set "
                "FUSION_REPORT_ROW_XPATH to override."
            )
            row_elements = list(root)
        else:
            row_tag = tag_counts.most_common(1)[0][0]
            row_elements = root.findall(f".//{row_tag}")

    rows: List[Dict[str, str]] = []
    for row_el in row_elements:
        row: Dict[str, str] = {}
        for child in row_el.iter():
            if len(child) == 0 and child is not row_el:
                row[child.tag] = (child.text or "").strip()
        rows.append(row)

    return rows


def parse_excel_report(report_bytes: bytes) -> List[Dict[str, str]]:
    """
    Parses XLS/XLSX bytes returned by the BIP report into a list of dict rows.

    Oracle BIP's "Excel" output is sometimes a genuine binary .xls/.xlsx
    workbook, and sometimes an HTML table saved with an .xls extension (a
    long-standing BIP quirk). This tries a real Excel parse first and falls
    back to HTML-table parsing so either case works without configuration.

    If your report has title/subtitle rows above the actual column headers,
    set FUSION_REPORT_HEADER_ROW (0-based) to the row your real headers are
    on — default assumes the header row is the very first row.
    """
    if not report_bytes:
        return []

    import pandas as pd

    header_row = int(os.getenv("FUSION_REPORT_HEADER_ROW", "0"))

    df = None
    last_error: Optional[Exception] = None

    for attempt, reader in (
        ("excel", lambda: pd.read_excel(io.BytesIO(report_bytes), header=header_row)),
        ("html-table", lambda: pd.read_html(io.BytesIO(report_bytes), header=header_row)[0]),
    ):
        try:
            df = reader()
            logger.info("Parsed report output as %s.", attempt)
            break
        except Exception as exc:  # noqa: BLE001 - trying multiple strategies deliberately
            last_error = exc
            logger.debug("Excel parse attempt '%s' failed: %s", attempt, exc)

    if df is None:
        dump_path = _dump_debug_bytes(report_bytes, suffix="xls")
        raise ValueError(
            "Could not parse the report output as Excel or an HTML table. "
            f"Raw bytes dumped to {dump_path} — open it in Excel (or a hex "
            f"editor if Excel refuses it) to see its actual structure. "
            f"Last error: {last_error}"
        )

    df = df.fillna("")
    # Normalize header whitespace and stringify every value for downstream mapping.
    df.columns = [str(c).strip() for c in df.columns]
    rows = df.astype(str).to_dict(orient="records")

    if os.getenv("FUSION_DUMP_RAW_REPORT", "").lower() in ("1", "true", "yes"):
        _dump_debug_bytes(report_bytes, suffix="xls")

    return rows


# --------------------------------------------------------------------------
# 4. Data mapping: BIP report columns -> SuperTax JSON schema
# --------------------------------------------------------------------------
#
# IMPORTANT: The column names below (left side, upper case) mirror the
# staging-table field names used in the existing .NET job (EWM_GST_E_INV_RES_STG)
# on the assumption the new EINV_INTG_DM data model was built to expose the
# same fields. Once you run the report and can see its actual output header
# row, confirm/adjust the keys in REPORT_COLUMN_* below — everything else in
# this script is column-name agnostic and will keep working.

REPORT_COLUMN_INVOICE_ID = "CUSTOMER_TRX_ID"   # groups rows into one invoice

REPORT_TO_TRANDTLS = {
    "TaxSch": lambda r: r.get("TAX_SCHEME", "GST"),
    "SupTyp": lambda r: r.get("SUPPLY_TYPE"),
    "RegRev": lambda r: r.get("REVERSE_CHARGE") or "N",
}

REPORT_TO_DOCDTLS = {
    "Typ": lambda r: r.get("DOCUMENT_TYPE"),
    "No": lambda r: r.get("DOCUMENT_NUMBER"),
    "Dt": lambda r: r.get("DOCUMENT_DATE"),  # must already be DD/MM/YYYY
}

REPORT_TO_SELLERDTLS = {
    "Gstin": lambda r: r.get("SELLER_GSTIN"),
    "LglNm": lambda r: r.get("SELLER_LEGALNAME"),
    "TrdNm": lambda r: r.get("SELLER_TRADENAME"),
    "Addr1": lambda r: r.get("SELLER_ADDRESS1"),
    "Addr2": lambda r: r.get("SELLER_ADDRESS2") or None,
    "Loc": lambda r: r.get("SELLER_CITY"),
    "Pin": lambda r: clean_numeric_str(r.get("SELLER_PINCODE")),
    "Stcd": lambda r: clean_numeric_str(r.get("SELLER_STATECODE"), zero_pad=2),
}

REPORT_TO_BUYERDTLS = {
    "Gstin": lambda r: r.get("BUYER_GSTIN"),
    "LglNm": lambda r: r.get("BUYER_LEGALNAME"),
    "TrdNm": lambda r: r.get("BUYER_TRADENAME"),
    "Pos": lambda r: clean_numeric_str(r.get("BUYER_POS"), zero_pad=2),
    "Addr1": lambda r: r.get("BUYER_ADDRESS1"),
    "Addr2": lambda r: r.get("BUYER_ADDRESS2") or None,
    "Loc": lambda r: r.get("BUYER_CITY"),
    "Pin": lambda r: clean_numeric_str(r.get("BUYER_PINCODE")),
    "Stcd": lambda r: clean_numeric_str(r.get("BUYER_STATECODE"), zero_pad=2),
}

# Item (line)-level mapping — one entry per invoice line row.
REPORT_TO_ITEM = {
    "SlNo": lambda r: r.get("SERIAL_NUMBER"),
    "IsServc": lambda r: resolve_is_service(r),
    "PrdDesc": lambda r: r.get("PRODUCT_DESCRIPTION"),
    "HsnCd": lambda r: clean_hsn(r.get("HSN_CODE")) or "8314",
    "Qty": lambda r: to_number(r.get("QUANTITY")),
    "Unit": lambda r: r.get("UNIT"),
    "UnitPrice": lambda r: to_number(r.get("UNIT_PRICE")),
    "TotAmt": lambda r: to_number(r.get("TOTAL_AMOUNT")),
    "Discount": lambda r: to_number(r.get("DISCOUNT")) or 0,
    "AssAmt": lambda r: to_number(r.get("ASSESSABLE_AMOUNT")) or 0,
    "GstRt": lambda r: to_number(r.get("GST_RATE")) or 0,
    "SgstAmt": lambda r: to_number(r.get("SGST_AMT")) or 0,
    "IgstAmt": lambda r: to_number(r.get("IGST_AMT")) or 0,
    "CgstAmt": lambda r: to_number(r.get("CGST_AMT")) or 0,
    "CesRt": lambda r: to_number(r.get("CESS_RATE")) or 0,
    "CesAmt": lambda r: to_number(r.get("CESS_AMOUNT")) or 0,
    "CesNonAdvlAmt": lambda r: to_number(r.get("CESS_NON_ADVOL_AMOUNT")) or 0,
    "StateCesRt": lambda r: to_number(r.get("STATE_CESS_RATE")) or 0,
    "StateCesAmt": lambda r: to_number(r.get("STATE_CESS_AMOUNT")) or 0,
    "StateCesNonAdvlAmt": lambda r: to_number(r.get("STATE_CESS_NON_ADVOL_AMOUNT")) or 0,
    "OthChrg": lambda r: to_number(r.get("OTHER_CHARGES")) or 0,
    "TotItemVal": lambda r: to_number(r.get("TOTAL_ITEM_VALUE")),
}

REPORT_TO_VALDTLS = {
    "AssVal": lambda r: to_number(r.get("TOTAL_ASSESSABLE_VALUE")),
    "CgstVal": lambda r: to_number(r.get("TOTAL_CGST_VALUE")) or 0,
    "SgstVal": lambda r: to_number(r.get("TOTAL_SGST_VALUE")) or 0,
    "IgstVal": lambda r: to_number(r.get("TOTAL_IGST_VALUE")) or 0,
    "CesVal": lambda r: to_number(r.get("TOTAL_CESS_VALUE")) or 0,
    "StCesVal": lambda r: to_number(r.get("TOTAL_STATE_CESS_VALUE")) or 0,
    "RndOffAmt": lambda r: to_number(r.get("ROUNDED_OFF_AMOUNT")) or 0,
    "TotInvVal": lambda r: to_number(r.get("FINAL_INVOICE_VALUE")),
}


def to_number(value: Optional[str]):
    """Converts a report string value to int/float for JSON; returns None if blank/invalid."""
    if value is None or str(value).strip() == "":
        return None
    try:
        dec = Decimal(str(value).strip())
        return int(dec) if dec == dec.to_integral_value() else float(dec)
    except InvalidOperation:
        logger.warning("Could not parse numeric value: %r", value)
        return None

def clean_hsn(value: Optional[str]) -> str:
    """Removes decimals if Excel parsed the HSN as a float (e.g., '998314.0' -> '998314')"""
    if not value:
        return ""
    return str(value).split('.')[0].strip()


def clean_numeric_str(value: Optional[str], zero_pad: Optional[int] = None) -> str:
    """
    Cleans a code/identifier field (pincode, state code, POS) that Excel may
    have parsed as a float, e.g. "400059.0" -> "400059", "9.0" -> "09" when
    zero_pad=2. GST state codes and place-of-supply values are always
    2-digit strings, so zero_pad=2 restores the leading zero Excel drops.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    if zero_pad:
        s = s.zfill(zero_pad)
    return s


def resolve_hsn(row: Dict[str, str]) -> str:
    """
    Resolves the line's HSN/SAC code without guessing a fixed default.

    Priority:
    1. The report's own HSN_CODE column, if present (cleaned of any Excel
       float artifact).
    2. A code embedded in the product description after "||" — a pattern
       seen in real data here, e.g. "Computers || 8471".
    3. Blank — deliberately NOT defaulted to a fixed code like "998314",
       since that was a services SAC code being sent for goods lines and
       was the main cause of every invoice failing HSN validation. A blank
       HsnCd will surface as a clear "missing" error instead of a silent,
       wrong "invalid" one — the real fix is getting the correct source
       column name or populating HSN on the AR line/item master.
    """
    hsn = clean_hsn(row.get("HSN_CODE"))
    if hsn:
        return hsn

    desc = row.get("PRODUCT_DESCRIPTION") or ""
    if "||" in desc:
        candidate = desc.rsplit("||", 1)[-1].strip()
        if candidate.isdigit():
            return candidate

    return ""


def resolve_is_service(row: Dict[str, str]) -> str:
    """
    Derives Y/N from the resolved HSN code's own convention rather than
    trusting a possibly-unreliable IS_SERVICE column in isolation: GST SAC
    (service) codes are always 6 digits starting with "99"; HSN (goods)
    codes never are. This guarantees IsServc and HsnCd can't contradict
    each other, which was independently causing "HSN Code field value is
    invalid" even when a real code was present.
    """
    hsn = resolve_hsn(row)
    if hsn:
        return "Y" if (len(hsn) == 6 and hsn.startswith("99")) else "N"
    val = (row.get("IS_SERVICE") or "").strip().upper()
    return val or "N"

def _apply_mapping(row: Dict[str, str], mapping: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for target_field, getter in mapping.items():
        value = getter(row)
        if value is not None and value != "":
            out[target_field] = value
    return out


def build_invoice_payload(invoice_rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """Builds one SuperTax invoice object from all report rows belonging to one AR invoice."""
    header_row = invoice_rows[0]

    invoice: Dict[str, Any] = {
        "CustDocNo": header_row.get("DOCUMENT_NUMBER"),
        "Version": "1.2",
        "TranDtls": _apply_mapping(header_row, REPORT_TO_TRANDTLS),
        "DocDtls": _apply_mapping(header_row, REPORT_TO_DOCDTLS),
        "SellerDtls": _apply_mapping(header_row, REPORT_TO_SELLERDTLS),
        "BuyerDtls": _apply_mapping(header_row, REPORT_TO_BUYERDTLS),
        "ItemList": [_apply_mapping(line_row, REPORT_TO_ITEM) for line_row in invoice_rows],
        "ValDtls": _apply_mapping(header_row, REPORT_TO_VALDTLS),
    }
    return invoice


def group_rows_by_invoice(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """Groups flat report rows into {invoice_key: [line_rows...]} preserving row order."""
    rows_sorted = sorted(rows, key=lambda r: r.get(REPORT_COLUMN_INVOICE_ID, ""))
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for key, group in groupby(rows_sorted, key=lambda r: r.get(REPORT_COLUMN_INVOICE_ID, "")):
        grouped[key] = list(group)
    return grouped


# --------------------------------------------------------------------------
# 5. SuperTax REST client
# --------------------------------------------------------------------------

class SuperTaxClient:
    def __init__(self, config: SuperTaxConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "key": config.api_key,  # SuperTax expects the API key in a header literally named "key"
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

        retry = Retry(
            total=config.max_retries,
            backoff_factor=2,          # 2s, 4s, 8s ...
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["POST"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def send_invoices(self, invoices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """POSTs a batch of invoices (SuperTax accepts an array under "invoices")."""
        payload = {"invoices": invoices}
        try:
            resp = self.session.post(
                self.config.api_url, json=payload, timeout=self.config.timeout_seconds
            )
        except requests.exceptions.RequestException:
            logger.exception("Network error calling SuperTax API")
            raise

        if resp.status_code == 429:
            logger.error("SuperTax API rate limit exceeded even after retries.")
            resp.raise_for_status()

        if 400 <= resp.status_code < 600:
            logger.error(
                "SuperTax API returned HTTP %s: %s", resp.status_code, resp.text[:2000]
            )
            resp.raise_for_status()

        try:
            return resp.json()
        except ValueError:
            logger.error("SuperTax API response was not valid JSON: %s", resp.text[:2000])
            raise

# --------------------------------------------------------------------------
# Save the request/response payloads to a local log file for troubleshooting.
# --------------------------------------------------------------------------
def save_payload_log(trx_id: str, payload: Dict[str, Any], response: Any = None, error: str = None) -> None:
    """Saves the JSON request payload and API response to the local Logs directory."""
    log_dir = r"C:\Oracle_SuperTax_EInvoice_Intg\Logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Create a timestamped filename, sanitizing the trx_id to ensure it's a valid Windows filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_trx_id = "".join(c for c in str(trx_id) if c.isalnum() or c in ("-", "_"))
    filepath = os.path.join(log_dir, f"{safe_trx_id}_{timestamp}.json")
    
    log_content = {
        "timestamp": datetime.now().isoformat(),
        "transaction_id": trx_id,
        "request_payload": payload,
        "response": response,
        "error": error
    }
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_content, f, indent=4)
    except Exception as e:
        logger.error("Failed to write JSON payload log to %s: %s", filepath, e)


def write_back_to_fusion(request_payload: Dict[str, Any], supertax_response: Dict[str, Any], fusion_cfg: FusionConfig, trx_id: str) -> None:
    """Pushes the integration results back to the Inspira_Einvoice custom object via CRM REST API."""
    
    custom_object_url = f"{fusion_cfg.base_url.rstrip('/')}/fscmRestApi/resources/11.13.18.05/Inspira_Einvoice_c"
    inv_data = request_payload["invoices"][0]
    
    # 1. Extract nested response data FIRST (because SuperTax hides errors inside arrays)
    response_data = supertax_response
    if "data" in supertax_response and isinstance(supertax_response["data"], list) and len(supertax_response["data"]) > 0:
        response_data = supertax_response["data"][0]
    elif "results" in supertax_response and isinstance(supertax_response["results"], list) and len(supertax_response["results"]) > 0:
        response_data = supertax_response["results"][0]
    elif "invoices" in supertax_response and isinstance(supertax_response["invoices"], list) and len(supertax_response["invoices"]) > 0:
        response_data = supertax_response["invoices"][0]

    # 2. Safely extract status and messages from the newly nested response_data
    status = response_data.get("Status") or response_data.get("status") or "FAILED"
    
    # Grab the message, checking both the nested data and top-level response as a fallback
    raw_message = str(response_data.get("Messages") or response_data.get("ErrorDetails") or supertax_response.get("ErrorDetails") or "No message")
    safe_message = raw_message[:200] # Truncate to prevent Fusion 400 Bad Request error
    
    success_flag = response_data.get("Success") or ("false" if status.upper() == "FAILED" else "true")
    
    # Map the payload to Fusion Custom Object fields
    fusion_payload = {
        "Supply_Type_c": inv_data.get("TranDtls", {}).get("SupTyp", ""),
        "SellerGSTIN_c": inv_data.get("SellerDtls", {}).get("Gstin", ""),
        "DocType_c": inv_data.get("DocDtls", {}).get("Typ", ""),
        "DocDate_c": inv_data.get("DocDtls", {}).get("Dt", ""),
        "DocNumber_c": inv_data.get("DocDtls", {}).get("No", ""),
        
        "Ack_Number_c": str(response_data.get("AckNo", "")),
        "Ack_Date_c": response_data.get("AckDt", ""),
        "Record_c": str(response_data.get("Record", "")),
        "FinYear_c": str(response_data.get("Fy", "")),
        "QR_Code_c": response_data.get("SignedQRCode", ""),
        "IRN_Number_c": response_data.get("Irn", ""),
        "RawQRCode_c": response_data.get("SignedQRCode", ""),
        
        # Use the securely extracted variables here
        "Success_c": str(success_flag),
        "Messages_c": safe_message,
        "Status_c": str(status),
        
        "Trx_Id_c": str(trx_id),
        "Trx_Number_c": inv_data.get("DocDtls", {}).get("No", "")
    }
    
    auth = HTTPBasicAuth(fusion_cfg.username, fusion_cfg.password)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    
    try:
        # --- NEW LOGIC: Query Oracle to check if the record exists ---
        query_url = f"{custom_object_url}?q=Trx_Id_c={trx_id}"
        get_resp = requests.get(query_url, auth=auth, headers=headers)
        get_resp.raise_for_status()
        
        items = get_resp.json().get("items", [])
        
        if items:
            # Record exists -> UPDATE (PATCH request)
            record_id = items[0].get("Id")  # Internal Fusion Record ID
            patch_url = f"{custom_object_url}/{record_id}"
            
            logger.info(f"Record exists for Trx_Id {trx_id}. Updating existing row (Id: {record_id})...")
            patch_resp = requests.patch(patch_url, json=fusion_payload, auth=auth, headers=headers)
            patch_resp.raise_for_status()
            logger.info(f"Successfully updated Inspira_Einvoice record for Trx_Id {trx_id}.")
            
        else:
            # Record does not exist -> CREATE (POST request)
            logger.info(f"No existing record for Trx_Id {trx_id}. Creating new row...")
            post_resp = requests.post(custom_object_url, json=fusion_payload, auth=auth, headers=headers)
            post_resp.raise_for_status()
            logger.info(f"Successfully created Inspira_Einvoice record for Trx_Id {trx_id}.")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to write to Fusion Custom Object: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Fusion API Error Details: {e.response.text}")

# --------------------------------------------------------------------------
# 6. Orchestration
# --------------------------------------------------------------------------

def run_integration(invoice_number: Optional[str] = None) -> List[Dict[str, Any]]:
    fusion_cfg, supertax_cfg = load_config()

    bip_client = BIPReportClient(fusion_cfg)
    params = {fusion_cfg.invoice_number_param: invoice_number} if invoice_number else None

    output_format = os.getenv("FUSION_REPORT_OUTPUT_FORMAT", "XML").upper()
    report_bytes = bip_client.run_report(parameters=params, output_format=output_format)

    if output_format == "CSV":
        rows = parse_csv_report(report_bytes)
    elif output_format == "XML":
        rows = parse_xml_report(report_bytes)
    elif output_format in ("XLS", "XLSX", "EXCEL", "EXCEL2000"):
        rows = parse_excel_report(report_bytes)
    else:
        raise ValueError(
            f"Unsupported FUSION_REPORT_OUTPUT_FORMAT '{output_format}'. "
            "Use CSV, XML, or XLS/XLSX/EXCEL."
        )

    if not rows:
        logger.info("No invoices returned by the report. Nothing to send.")
        return []

    grouped = group_rows_by_invoice(rows)
    logger.info("Report returned %d invoice(s) across %d row(s).", len(grouped), len(rows))

    tax_client = SuperTaxClient(supertax_cfg)
    results: List[Dict[str, Any]] = []

    for trx_id, invoice_rows in grouped.items():
        try:
            invoice_payload = build_invoice_payload(invoice_rows)
            full_request_payload = {"invoices": [invoice_payload]}

            # Print the exact request payload to the log ---
            logger.info("Invoice %s Request Payload: %s", trx_id, json.dumps(full_request_payload))

            response = tax_client.send_invoices([invoice_payload])
            logger.info("Invoice %s submitted. Response: %s", trx_id, response)
            results.append({"invoice": trx_id, "success": True, "response": response})
            
            # 1. Write the success log to the local folder
            save_payload_log(trx_id, full_request_payload, response=response)
            
            # 2. Write the success response back to Oracle Fusion App Composer
            write_back_to_fusion(full_request_payload, response, fusion_cfg, trx_id)
            
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to submit invoice %s", trx_id)
            results.append({"invoice": trx_id, "success": False, "error": str(exc)})
            
            # 1. Write the failure log to the local folder
            save_payload_log(
                trx_id, 
                full_request_payload if 'full_request_payload' in locals() else None, 
                error=str(exc)
            )
            
            # 2. Write the failure response back to Oracle Fusion App Composer
            error_response_mock = {"ErrorDetails": str(exc), "status": "FAILED"}
            write_back_to_fusion(
                full_request_payload if 'full_request_payload' in locals() else {"invoices": [{}]}, 
                error_response_mock, 
                fusion_cfg, 
                trx_id
            )
        time.sleep(1)    
    return results

# --------------------------------------------------------------------------
# 7. CLI entry point
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Oracle Fusion -> SuperTax e-Invoice integration")
    parser.add_argument(
        "--invoice-number",
        help=(
            "Customer Trx ID (or your chosen key) of a single invoice to push on-demand. "
            "Omit to run in batch mode against whatever the BIP report/data model filters for."
        ),
    )
    args = parser.parse_args()

    results = run_integration(args.invoice_number)

    failures = [r for r in results if not r["success"]]
    if failures:
        logger.error("%d invoice(s) failed to submit.", len(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()