 @echo off
title Oracle SuperTax Integration Portal
cd /d "C:\Oracle_SuperTax_EInvoice_Intg"

echo Starting Oracle SuperTax Integration Portal...
echo Please wait, opening in your default web browser...

"C:\Users\NadeemShaikh\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m streamlit run supertax_ui.py

pause