#!/usr/bin/env bash
# ====================================================================
#  Valve Diagnostics v3 - Installer (Mac/Linux)
# ====================================================================
set -e

cd "$(dirname "$0")"

echo
echo "============================================================"
echo "  Valve Diagnostics v3 - Installer"
echo "============================================================"
echo

# Find Python
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "ERROR: Python 3 not found."
    echo "Install from https://www.python.org/downloads/"
    exit 1
fi

echo "Using Python: $PY"
$PY --version
echo

echo "Installing required libraries..."
echo "(takes about a minute the first time)"
echo

$PY -m pip install --upgrade pip || echo "(pip upgrade failed, continuing)"

# Try with user flag first (works in most cases without admin)
if ! $PY -m pip install -r requirements.txt 2>&1; then
    echo
    echo "Standard install failed. Retrying with --user flag..."
    $PY -m pip install --user -r requirements.txt
fi

echo
echo "============================================================"
echo "  Installation complete."
echo "============================================================"
echo
echo "Next: try running"
echo "    bash run.sh test_data/synthetic_test_data.xlsx"
echo "to confirm everything works."
echo
