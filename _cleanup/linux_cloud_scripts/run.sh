#!/usr/bin/env bash
# ====================================================================
#  Valve Diagnostics v3 - Runner (Mac/Linux)
#
#  Usage:
#    bash run.sh <input.xlsx>            # AUTO mode (default)
#    bash run.sh <input.xlsx> --manual   # MANUAL mode
# ====================================================================
set -e

cd "$(dirname "$0")"

if [ -z "$1" ]; then
    echo
    echo "============================================================"
    echo "  Valve Diagnostics v3"
    echo "============================================================"
    echo
    echo "Usage: bash run.sh <input.xlsx> [--manual]"
    echo
    echo "Examples:"
    echo "  bash run.sh test_data/synthetic_test_data.xlsx"
    echo "  bash run.sh /path/to/my_plant.xlsx --manual"
    echo
    exit 1
fi

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "ERROR: Python 3 not found. Run install.sh first."
    exit 1
fi

INPUT="$1"
shift

# Build a sensible output directory name
BASENAME=$(basename "$INPUT" .xlsx)
OUTDIR="results_${BASENAME}"

# If --manual was passed, mark it in the output directory name
for arg in "$@"; do
    if [ "$arg" = "--manual" ]; then
        OUTDIR="${OUTDIR}_manual"
    fi
done

echo
echo "============================================================"
echo "  Valve Diagnostics v3"
echo "============================================================"
echo
echo "Input:   $INPUT"
echo "Output:  $OUTDIR"
echo

$PY valve_diagnostics_v3.py --input "$INPUT" --output-dir "$OUTDIR" "$@"
RC=$?

echo
if [ $RC -eq 0 ]; then
    echo "============================================================"
    echo "  Done. Results in: $OUTDIR"
    echo "============================================================"
    echo
    echo "Useful files:"
    echo "  - v3_run_summary.txt"
    echo "  - Loop_diagnostics_v2.xlsx"
    echo "  - Executive_summary.pdf"
    echo "  - health_check_report.txt"
else
    echo "============================================================"
    echo "  Tool finished with code $RC."
    echo "============================================================"
    echo
    echo "If health check found problems, see:"
    echo "  $OUTDIR/health_check_report.txt"
fi
echo

exit $RC
