"""Launcher script for SuperTax Streamlit Web UI."""

import subprocess
import sys

if __name__ == "__main__":
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "supertax_ui.py"
    ]
    subprocess.run(cmd)