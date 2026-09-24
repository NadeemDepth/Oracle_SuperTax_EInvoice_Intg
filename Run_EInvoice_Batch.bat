@echo off
cd /d "C:\Oracle_SuperTax_EInvoice_Intg"

:: Execute using your designated Python 3.14 executable
"C:\Users\NadeemShaikh\AppData\Local\Python\pythoncore-3.14-64\python.exe" ora_supertax_einv_intg.py

exit /b %ERRORLEVEL%