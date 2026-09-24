"""
Oracle SuperTax Operations Portal
=================================
Web UI to trigger E-Invoice Cancellations, E-Way Bill Retries, and Manual E-Invoicing.
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

tab1, tab2, tab3 = st.tabs(["Manual E-Invoice (Push)", "Retry E-Way Bill", "Cancel E-Invoice"])

with tab1:
    st.subheader("View Pending & Manually Push E-Invoice")
    
    if st.button("Fetch Pending Invoices from Oracle"):
        with st.spinner("Running BI Publisher Report..."):
            try:
                from ora_supertax_einv_intg import load_config, BIPReportClient, parse_excel_report, group_rows_by_invoice
                import os
                
                fusion_cfg, _ = load_config()
                bip_client = BIPReportClient(fusion_cfg)
                report_bytes = bip_client.run_report(output_format="EXCEL")
                rows = parse_excel_report(report_bytes)
                
                if not rows:
                    st.info("No pending invoices found in Oracle.")
                    st.session_state['pending_trx'] = []
                else:
                    # Display all data directly from the report
                    df = pd.DataFrame(rows)
                    st.dataframe(df, use_container_width=True)
                    
                    grouped = group_rows_by_invoice(rows)
                    st.session_state['pending_trx'] = list(grouped.keys())
                    st.success(f"Fetched {len(grouped)} pending invoice(s) across {len(rows)} line(s).")
            except Exception as e:
                st.error(f"Failed to fetch data from Oracle: {e}")
    
    st.divider()
    
    with st.form("push_einvoice_form"):
        known_trx = st.session_state.get('pending_trx', [])
        if known_trx:
            selected_trx = st.selectbox("Select Transaction to Push", options=known_trx)
        else:
            selected_trx = st.text_input("Enter Transaction ID manually")
            
        submit_push = st.form_submit_button("Generate Selected E-Invoice")
        
        if submit_push:
            if not selected_trx:
                st.warning("Please specify a Transaction ID.")
            else:
                with st.spinner(f"Pushing Transaction {selected_trx} to SuperTax..."):
                    result = subprocess.run([python_exe, "ora_supertax_einv_intg.py", "--trx-id", selected_trx], capture_output=True, text=True)
                    combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    
                    if result.returncode == 0:
                        st.success(f"Successfully processed Transaction {selected_trx}.")
                    else:
                        st.error(f"Failed to process Transaction {selected_trx}.")
                    
                    st.code(combined_output.strip())

with tab2:
    st.subheader("Generate E-Way Bill for an Existing IRN")
    st.markdown("*Note: Ensure the transportation data has been corrected in Oracle before retrying.*")
    with st.form("retry_form"):
        retry_irn = st.text_input("Invoice Reference Number (IRN)", placeholder="e.g., 23994d282f418adf1bee60aeefd4379c65e40e8d1caf5c84a9c23b352460dab4")
        submit_retry = st.form_submit_button("Generate E-Way Bill")
        
        if submit_retry:
            if not retry_irn:
                st.warning("IRN is mandatory.")
            else:
                with st.spinner("Fetching updated data and generating EWB..."):
                    result = subprocess.run([python_exe, "retry_ewaybill.py", "--irn", retry_irn], capture_output=True, text=True)
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

with tab3:
    st.subheader("Cancel an Active E-Invoice (Within 24 Hours)")
    with st.form("cancel_form"):
        cancel_irn = st.text_input(
            "Invoice Reference Number (IRN)", 
            placeholder="e.g., 23994d282f418adf1bee60aeefd4379c65e40e8d1caf5c84a9c23b352460dab4"
        )
        reason_options = {
            "1": "1 - Duplicate",
            "2": "2 - Data Entry Mistake",
            "3": "3 - Order Cancelled",
            "4": "4 - Other"
        }
        selected_reason = st.selectbox("Cancellation Reason", options=list(reason_options.keys()), format_func=lambda x: reason_options[x])
        remarks = st.text_input("Remarks", placeholder="Provide brief reason for cancellation...")
        submit_cancel = st.form_submit_button("Cancel E-Invoice")
        
        if submit_cancel:
            if not cancel_irn or not remarks:
                st.warning("IRN and Remarks are mandatory.")
            else:
                with st.spinner("Processing cancellation..."):
                    result = subprocess.run([python_exe, "cancel_einvoice.py", "--irn", cancel_irn, "--reason", selected_reason, "--remarks", remarks], capture_output=True, text=True)
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