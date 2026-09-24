"""
Oracle SuperTax Operations Portal
=================================
Web UI to trigger E-Invoice Cancellations and E-Way Bill Retries.
Displays live API responses.
"""

import streamlit as st
import subprocess
import sys

st.set_page_config(page_title="Oracle SuperTax Operations", layout="centered")

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
st.markdown("Use this portal to manage E-Invoice exceptions and cancellations.")

python_exe = sys.executable

tab1, tab2 = st.tabs(["Cancel E-Invoice", "Retry E-Way Bill"])

with tab1:
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
        selected_reason = st.selectbox(
            "Cancellation Reason", 
            options=list(reason_options.keys()), 
            format_func=lambda x: reason_options[x]
        )
        remarks = st.text_input("Remarks", placeholder="Provide brief reason for cancellation...")
        submit_cancel = st.form_submit_button("Cancel E-Invoice")
        
        if submit_cancel:
            if not cancel_irn or not remarks:
                st.warning("IRN and Remarks are mandatory.")
            else:
                with st.spinner("Processing cancellation..."):
                    result = subprocess.run(
                        [python_exe, "cancel_einvoice.py", "--irn", cancel_irn, "--reason", selected_reason, "--remarks", remarks],
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

with tab2:
    st.subheader("Generate E-Way Bill for an Existing IRN")
    st.markdown("*Note: Ensure the transportation data has been corrected in Oracle before retrying.*")
    
    with st.form("retry_form"):
        # CHANGED: Now asks for IRN instead of Transaction ID
        retry_irn = st.text_input(
            "Invoice Reference Number (IRN)", 
            placeholder="e.g., 23994d282f418adf1bee60aeefd4379c65e40e8d1caf5c84a9c23b352460dab4"
        )
        submit_retry = st.form_submit_button("Generate E-Way Bill")
        
        if submit_retry:
            if not retry_irn:
                st.warning("IRN is mandatory.")
            else:
                with st.spinner("Fetching updated data and generating EWB..."):
                    result = subprocess.run(
                        [python_exe, "retry_ewaybill.py", "--irn", retry_irn],
                        capture_output=True, text=True
                    )
                    
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