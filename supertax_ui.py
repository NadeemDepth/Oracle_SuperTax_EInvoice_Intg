"""
Oracle SuperTax Operations Portal
=================================
Web UI to trigger E-Invoice Cancellations, E-Way Bill Retries/Cancellations, and Manual E-Invoicing.
Displays live API responses and pending invoice data.
"""

import streamlit as st
import subprocess
import sys
import pandas as pd

st.set_page_config(page_title="Oracle SuperTax Operations", layout="wide")

hide_streamlit_style = """
    <style>
        .reportview-container { margin-top: -2em; }
        #MainMenu {visibility: hidden;}
        .stDeployButton {display:none;}
        footer {visibility: hidden;}
        #stDecoration {display:none;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("Oracle SuperTax Integration Portal")
st.markdown("Use this portal to manage E-Invoice exceptions, cancellations, and manual processing.")

python_exe = sys.executable

# --- Tab Layout: Cancel E-Way Bill added before Cancel E-Invoice ---
tab1, tab2, tab3, tab4 = st.tabs([
    "Manual E-Invoice (Push)", 
    "Retry E-Way Bill", 
    "Cancel E-Way Bill", 
    "Cancel E-Invoice"
])

# --------------------------------------------------------------------------
# TAB 1: Manual E-Invoice (Push)
# --------------------------------------------------------------------------
with tab1:
    st.subheader("View Pending & Manually Push E-Invoice")
    
    if st.button("Fetch Pending Invoices from Oracle"):
        with st.spinner("Running BI Publisher Report..."):
            try:
                from ora_supertax_einv_intg import load_config, BIPReportClient, parse_excel_report, group_rows_by_invoice, build_invoice_payload
                import os
                
                fusion_cfg, _ = load_config()
                bip_client = BIPReportClient(fusion_cfg)
                report_bytes = bip_client.run_report(output_format="EXCEL")
                rows = parse_excel_report(report_bytes)
                
                if not rows:
                    st.info("No pending invoices found in Oracle.")
                    st.session_state['pending_docs'] = []
                else:
                    df = pd.DataFrame(rows)
                    st.dataframe(df, use_container_width=True)
                    
                    grouped = group_rows_by_invoice(rows)
                    doc_numbers = []
                    for trx_id, grp_rows in grouped.items():
                        inv = build_invoice_payload(grp_rows)
                        doc_no = inv.get("DocDtls", {}).get("No", "")
                        if doc_no and doc_no not in doc_numbers:
                            doc_numbers.append(doc_no)
                            
                    st.session_state['pending_docs'] = doc_numbers
                    st.success(f"Fetched {len(grouped)} pending invoice(s) across {len(rows)} line(s).")
            except Exception as e:
                st.error(f"Failed to fetch data from Oracle: {e}")
    
    st.divider()
    
    with st.form("push_einvoice_form"):
        known_docs = st.session_state.get('pending_docs', [])
        if known_docs:
            selected_doc = st.selectbox("Select Document Number to Push", options=known_docs)
        else:
            selected_doc = st.text_input("Enter Document Number manually")
            
        submit_push = st.form_submit_button("Generate Selected E-Invoice")
        
        if submit_push:
            if not selected_doc:
                st.warning("Please specify a Document Number.")
            else:
                with st.spinner(f"Pushing Document {selected_doc} to SuperTax..."):
                    result = subprocess.run([python_exe, "ora_supertax_einv_intg.py", "--doc-no", selected_doc], capture_output=True, text=True)
                    combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    
                    if result.returncode == 0:
                        st.success(f"Successfully processed Document {selected_doc}.")
                    else:
                        st.error(f"Failed to process Document {selected_doc}.")
                    
                    st.code(combined_output.strip())

# --------------------------------------------------------------------------
# TAB 2: Retry E-Way Bill
# --------------------------------------------------------------------------
with tab2:
    st.subheader("Generate E-Way Bill for an Existing Document")
    st.markdown("*Note: Ensure the transportation data has been corrected in Oracle before retrying.*")
    with st.form("retry_form"):
        retry_doc_no = st.text_input("Document Number", placeholder="e.g., 27072627104")
        submit_retry = st.form_submit_button("Generate E-Way Bill")
        
        if submit_retry:
            if not retry_doc_no:
                st.warning("Document Number is mandatory.")
            else:
                with st.spinner("Fetching updated data and generating EWB..."):
                    result = subprocess.run([python_exe, "retry_ewaybill.py", "--doc-no", retry_doc_no], capture_output=True, text=True)
                    combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    if result.returncode == 0:
                        st.success("Successfully processed E-Way Bill.")
                    else:
                        st.error("E-Way Bill Generation Failed.")
                    api_lines = [line for line in combined_output.splitlines() if "API Response" in line]
                    if api_lines:
                        st.info(api_lines[-1])
                    else:
                        st.code(combined_output.strip())

# --------------------------------------------------------------------------
# TAB 3: Cancel E-Way Bill (NEW)
# --------------------------------------------------------------------------
with tab3:
    st.subheader("Cancel an Active E-Way Bill (Within 24 Hours)")
    st.markdown("*Note: Only cancels the E-Way Bill. The E-Invoice (IRN) remains active.*")
    with st.form("cancel_ewb_form"):
        cancel_ewb_doc_no = st.text_input("Document Number", placeholder="e.g., 27072627104")
        
        # Standard NIC E-Way Bill Reason Codes
        ewb_reason_options = {
            "1": "1 - Duplicate",
            "2": "2 - Order Cancelled",
            "3": "3 - Data Entry Mistake",
            "4": "4 - Others"
        }
        selected_ewb_reason = st.selectbox(
            "Cancellation Reason", 
            options=list(ewb_reason_options.keys()), 
            format_func=lambda x: ewb_reason_options[x]
        )
        ewb_remarks = st.text_input("Remarks", placeholder="Provide brief reason for E-Way Bill cancellation...")
        submit_cancel_ewb = st.form_submit_button("Cancel E-Way Bill")
        
        if submit_cancel_ewb:
            if not cancel_ewb_doc_no or not ewb_remarks:
                st.warning("Document Number and Remarks are mandatory.")
            else:
                with st.spinner("Processing E-Way Bill cancellation..."):
                    result = subprocess.run(
                        [python_exe, "cancel_ewaybill.py", "--doc-no", cancel_ewb_doc_no, "--reason", selected_ewb_reason, "--remarks", ewb_remarks],
                        capture_output=True, text=True
                    )
                    combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    if result.returncode == 0:
                        st.success("Successfully cancelled E-Way Bill in SuperTax and Oracle.")
                    else:
                        st.error("E-Way Bill Cancellation Failed.")
                    api_lines = [line for line in combined_output.splitlines() if "API Response" in line]
                    if api_lines:
                        st.info(api_lines[-1])
                    else:
                        st.code(combined_output.strip())

# --------------------------------------------------------------------------
# TAB 4: Cancel E-Invoice
# --------------------------------------------------------------------------
with tab4:
    st.subheader("Cancel an Active E-Invoice (Within 24 Hours)")
    st.markdown("*Note: Cancelling the E-Invoice will automatically void any linked E-Way Bill.*")
    with st.form("cancel_form"):
        cancel_doc_no = st.text_input("Document Number", placeholder="e.g., 27072627104")
        
        # Standard NIC E-Invoice Reason Codes
        reason_options = {
            "1": "1 - Duplicate",
            "2": "2 - Data Entry Mistake",
            "3": "3 - Order Cancelled",
            "4": "4 - Other"
        }
        selected_reason = st.selectbox(
            "Cancellation Reason", 
            options=list(reason_options.keys()), 
            format_func=lambda x: reason_options[x]
        )
        remarks = st.text_input("Remarks", placeholder="Provide brief reason for cancellation...")
        submit_cancel = st.form_submit_button("Cancel E-Invoice")
        
        if submit_cancel:
            if not cancel_doc_no or not remarks:
                st.warning("Document Number and Remarks are mandatory.")
            else:
                with st.spinner("Processing cancellation..."):
                    result = subprocess.run(
                        [python_exe, "cancel_einvoice.py", "--doc-no", cancel_doc_no, "--reason", selected_reason, "--remarks", remarks],
                        capture_output=True, text=True
                    )
                    combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    if result.returncode == 0:
                        st.success("Successfully cancelled E-Invoice in SuperTax and Oracle.")
                    else:
                        st.error("Cancellation Failed.")
                    api_lines = [line for line in combined_output.splitlines() if "API Response" in line]
                    if api_lines:
                        st.info(api_lines[-1])
                    else:
                        st.code(combined_output.strip())