# Oracle SuperTax E-Invoice Integration

Python-based integration for processing Oracle Fusion AR invoices through the SuperTax APIs.

The integration can:

- Read pending invoice data from an Oracle Fusion BI Publisher (BIP) report through the `ExternalReportWSSService` SOAP API.
- Build the SuperTax e-Invoice payload and submit it through the SuperTax REST API.
- Write the SuperTax response/status back to the Oracle Fusion App Composer object.
- Retry E-Way Bill generation for an already generated E-Invoice.
- Cancel an E-Way Bill.
- Cancel an E-Invoice.
- Provide a Streamlit web UI for the above operations.

## 1. Important Files

| File | Purpose |
|---|---|
| `supertax_ui.py` | Main Streamlit UI. This is the primary file for users/operators. |
| `ora_supertax_einv_intg.py` | Core integration logic: Fusion BIP/SOAP extraction, data mapping, SuperTax E-Invoice API call, and Fusion write-back. |
| `retry_ewaybill.py` | Re-generates an E-Way Bill for an existing E-Invoice. |
| `cancel_ewaybill.py` | Cancels an active E-Way Bill. |
| `cancel_einvoice.py` | Cancels an active E-Invoice. |
| `Run_Oracle_Supertax_Portal.py` | Python launcher for the Streamlit UI. |
| `Launch_Oracle_Supertax_Portal.bat` | Windows launcher; update its hard-coded folder/Python path if required. |
| `Execute_UI_Screen.py` | Older/helper launcher with a hard-coded Python executable path; normally use `Run_Oracle_Supertax_Portal.py` instead. |
| `delete_all_records.py` | Utility to delete records from the Fusion App Composer custom object. **Use with extreme caution.** |
| `requirements.txt` | Python packages required by the application. |
| `.env` | Local configuration and credentials. Do not commit or distribute real credentials. |
| `Logs/` | Integration, cancellation, and E-Way Bill log files. |

`Development_Backup/` contains older development copies and is not required for normal execution.

---

## 2. Prerequisites

The application is intended for Windows because the current logging and launcher configuration uses Windows paths.

Install:

1. Python 3.10+ (a currently supported Python version is recommended).
2. Network access to:
   - Oracle Fusion
   - SuperTax APIs
3. Valid Oracle Fusion credentials with access to:
   - The BI Publisher report used by the integration
   - The Fusion App Composer REST object used for E-Invoice data/status
4. Valid SuperTax API credentials/endpoints.
5. Access to the required Fusion BI Publisher reports:
   - E-Invoice Integration Report
   - E-Way Bill Integration Report

---

## 3. Installation

Open Command Prompt or PowerShell in the project directory.

### Create a virtual environment

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

If PowerShell blocks activation, use Command Prompt or run:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The required packages include:

- `streamlit` - web UI
- `requests` - REST API calls
- `urllib3` - retry/HTTP support
- `zeep` - Oracle Fusion BIP SOAP integration
- `lxml` - XML parsing
- `python-dotenv` - `.env` configuration
- `pandas` - report processing/data transformation
- `openpyxl` - Excel report reading
- `xlrd` - Excel compatibility
- `html5lib` - HTML-table parsing support

---

## 4. Configure `.env`

Create a `.env` file in the project root, next to `ora_supertax_einv_intg.py`.

Do **not** copy production credentials into source control.

Use the following configuration structure:

```env
# Oracle Fusion
FUSION_BASE_URL=https://<your-fusion-instance>
FUSION_USERNAME=<fusion-username>
FUSION_PASSWORD=<fusion-password>

# Main Fusion BIP report
FUSION_REPORT_ABS_PATH=/Custom/<folder>/<E-Invoice-Report>.xdo

# E-Way Bill BIP report
FUSION_EWB_REPORT_ABS_PATH=/Custom/<folder>/<EWB-Report>.xdo

# Report processing
FUSION_REPORT_OUTPUT_FORMAT=EXCEL
FUSION_BYPASS_CACHE=false
FUSION_FLATTEN_XML=false

# Optional report parsing settings
# FUSION_REPORT_HEADER_ROW=0
# FUSION_REPORT_ROW_XPATH=.//SELLER

# SuperTax E-Invoice API
SUPERTAX_API_URL=https://<supertax-endpoint>
SUPERTAX_API_KEY=<supertax-api-key>
SUPERTAX_TIMEOUT_SECONDS=30
SUPERTAX_MAX_RETRIES=3

# Optional / required for cancellation and E-Way Bill operations
SUPERTAX_CANCEL_API_URL=https://<einvoice-cancel-endpoint>
SUPERTAX_EWB_API_URL=https://<ewaybill-generate-endpoint>
SUPERTAX_EWB_CANCEL_API_URL=https://<ewaybill-cancel-endpoint>
SUPERTAX_EWB_API_KEY=<ewaybill-api-key>
```

### Configuration notes

The core script requires:

- `FUSION_BASE_URL`
- `FUSION_USERNAME`
- `FUSION_PASSWORD`
- `FUSION_REPORT_ABS_PATH`
- `SUPERTAX_API_URL`
- `SUPERTAX_API_KEY`

E-Way Bill retry additionally uses:

- `FUSION_EWB_REPORT_ABS_PATH`

The cancellation scripts require the Fusion credentials and the corresponding SuperTax API configuration.

The current source code contains default SuperTax endpoints for some operations. It is preferable to explicitly configure the endpoints in `.env` so that environment changes do not silently use an unintended endpoint.

---

## 5. Start the Application

From the project directory with the virtual environment activated:

```powershell
python -m streamlit run supertax_ui.py
```

Streamlit will display a local URL in the terminal, normally similar to:

```text
http://localhost:8501
```

Open that URL in a browser.

### Alternative launcher

You can also run:

```powershell
python Run_Oracle_Supertax_Portal.py
```

This uses the currently active Python interpreter and launches the Streamlit application.

### Windows `.bat` launcher

`Launch_Oracle_Supertax_Portal.bat` currently contains hard-coded paths. If the project is moved to another machine, update:

```text
C:\Oracle_SuperTax_EInvoice_Intg
```

and the Python executable path.

Using the virtual-environment command from the project directory is safer and more portable:

```powershell
.venv\Scripts\python.exe -m streamlit run supertax_ui.py
```

---

## 6. Main UI Operations

### Tab 1 - Manual E-Invoice Push

1. Click **Fetch Pending Invoices from Oracle**.
2. The application executes the configured Fusion BIP report.
3. The returned Excel/report data is parsed and grouped by invoice.
4. Select the required Document Number.
5. Click **Generate Selected E-Invoice**.
6. `ora_supertax_einv_intg.py` submits the invoice to SuperTax.
7. The response is logged and the Fusion App Composer record is updated.

A document number can also be entered manually if it is not present in the fetched pending list.

### Tab 2 - Retry E-Way Bill

Use this when the E-Invoice/IRN already exists but E-Way Bill generation needs to be retried.

1. Correct the transportation-related data in Fusion first.
2. Enter the Document Number.
3. Click **Generate E-Way Bill**.
4. The script retrieves the existing Fusion record and IRN.
5. It executes the configured E-Way Bill BIP report.
6. It submits the E-Way Bill request to SuperTax.
7. The E-Way Bill result is written back to Fusion.

### Tab 3 - Cancel E-Way Bill

Use this for an active E-Way Bill cancellation.

1. Enter the Document Number.
2. Select the cancellation reason.
3. Enter remarks.
4. Click **Cancel E-Way Bill**.

The script retrieves the E-Way Bill number from Fusion, sends the cancellation request to SuperTax, and updates the Fusion record after a successful response.

### Tab 4 - Cancel E-Invoice

Use this for an active E-Invoice cancellation.

1. Enter the Document Number.
2. Select the cancellation reason.
3. Enter remarks.
4. Click **Cancel E-Invoice**.

The script retrieves the IRN from Fusion, sends the cancellation request to SuperTax, and updates the Fusion record after a successful response.

Cancellation is subject to the applicable SuperTax/GST cancellation rules and time window.

---

## 7. Command-Line Usage

The UI is the recommended operational interface, but the underlying scripts can also be executed directly.

### Process pending invoices

```powershell
python ora_supertax_einv_intg.py
```

### Process one document

```powershell
python ora_supertax_einv_intg.py --doc-no <DOCUMENT_NUMBER>
```

### Retry E-Way Bill

```powershell
python retry_ewaybill.py --doc-no <DOCUMENT_NUMBER>
```

### Cancel E-Way Bill

```powershell
python cancel_ewaybill.py --doc-no <DOCUMENT_NUMBER> --reason <REASON_CODE> --remarks "<REMARKS>"
```

Reason codes:

```text
1 = Duplicate
2 = Order Cancelled
3 = Data Entry Mistake
4 = Others
```

### Cancel E-Invoice

```powershell
python cancel_einvoice.py --doc-no <DOCUMENT_NUMBER> --reason <REASON_CODE> --remarks "<REMARKS>"
```

### Delete all Fusion App Composer records

```powershell
python delete_all_records.py
```

**WARNING:** This is a destructive utility. It loops through the Fusion custom object and deletes its records. Do not run it in production unless the deletion is explicitly intended and authorized.

---

## 8. Logs

The scripts create logs under:

```text
Logs\
```

Typical folders include:

```text
Logs\
├── EInvoice\
├── EWB_Retry\
├── EWB_Cancel\
└── Cancellation\
```

There is also a master integration log:

```text
Logs\einvoice_integration_log.log
```

Logs contain API request/response information and processing errors. Protect the log directory because request payloads and API responses may contain business or invoice information.

---

## 9. Integration Flow

The main E-Invoice flow is:

```text
Oracle Fusion AR
      |
      | BI Publisher Report
      v
ExternalReportWSSService (SOAP)
      |
      v
ora_supertax_einv_intg.py
      |
      | Parse / transform / map
      v
SuperTax E-Invoice REST API
      |
      v
API Response
      |
      v
Oracle Fusion App Composer
      |
      v
Status / IRN / response information updated
```

The Streamlit UI acts as the operator layer:

```text
supertax_ui.py
      |
      +--> ora_supertax_einv_intg.py
      +--> retry_ewaybill.py
      +--> cancel_ewaybill.py
      +--> cancel_einvoice.py
```

---

## 10. Troubleshooting

### `ModuleNotFoundError`

Make sure the virtual environment is activated and run:

```powershell
python -m pip install -r requirements.txt
```

Check the active Python:

```powershell
python --version
python -m pip --version
```

### Missing environment variable

Example:

```text
Missing required environment variable: FUSION_BASE_URL
```

Check that `.env` exists in the project root and contains the required variable.

### Fusion authentication failure

Check:

- Fusion URL
- Username/password
- Network/VPN access
- User permissions
- BI Publisher report access
- App Composer REST object access

### BIP report returns no data

Check:

- `FUSION_REPORT_ABS_PATH`
- Report permissions
- Report parameters/configuration
- Report output format
- Whether the report actually returns pending invoices

### SuperTax API failure

Check:

- SuperTax endpoint
- API key
- Network access
- Request payload in the logs
- HTTP response/status returned by SuperTax

### Streamlit starts but child scripts fail

The UI launches child scripts using the active Python interpreter. Make sure:

```powershell
python -m streamlit run supertax_ui.py
```

is executed from the project directory and that all dependencies are installed in the same environment.

---

## 11. Security Notes

- Never commit `.env` to Git.
- Never share real Fusion passwords or SuperTax API keys in documentation.
- Restrict access to `Logs/`.
- Rotate credentials/API keys if they have been exposed outside the intended environment.
- Review `delete_all_records.py` carefully before executing it.
- Use separate credentials/endpoints for development, UAT, and production where possible.

---

## 12. Recommended First-Time Setup

For a new machine:

```powershell
cd C:\Oracle_SuperTax_EInvoice_Intg

python -m venv .venv
.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Create/configure .env

python -m streamlit run supertax_ui.py
```

Before processing a real invoice, first verify:

1. Fusion login works.
2. The BIP report can be accessed by the configured Fusion user.
3. The BIP report returns the expected columns/data.
4. SuperTax endpoint and API key are correct for the target environment.
5. The Fusion App Composer REST object can be queried/updated.
6. A controlled test invoice is available.

