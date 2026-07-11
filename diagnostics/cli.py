"""
CLI — command-line entry point for the v3 wrapper.
====================================================

Parses command-line flags and hands off to the pipeline.
"""

import argparse
import sys

from .constants import V3_VERSION
from .pipeline import run_v3


def _parse_args():
    p = argparse.ArgumentParser(
        description=f"Valve Diagnostics v{V3_VERSION} — self-calibrating, "
                    "self-validating wrapper around the v2 engine."
    )
    p.add_argument("--input", required=True, help="Path to input Excel file")
    p.add_argument("--output-dir", default="./diagnostics_output",
                   help="Directory for outputs")
    p.add_argument("--manual", action="store_true",
                   help="Use manual DIAGNOSTIC_CONFIG values; disable "
                        "auto-calibration")
    p.add_argument("--skip-incomplete-loops", action="store_true",
                   help="Automatically skip loops with > 30%% missing data "
                        "instead of blocking on them")
    p.add_argument("--force", action="store_true",
                   help="Run even if health check found problems "
                        "(NOT recommended)")
    p.add_argument("--quiet", action="store_true", help="Suppress console output")
    p.add_argument("--config-json", default=None,
                   help="Path to a JSON file with a flat {parameter: value} "
                        "config dict, bypassing the Excel DIAGNOSTIC_CONFIG "
                        "read entirely. Used by the dashboard for per-user "
                        "config; not needed for plain CLI runs.")
    return p.parse_args()


def main():
    args = _parse_args()
    mode = "MANUAL" if args.manual else "AUTO"
    config = None
    if args.config_json:
        import json
        with open(args.config_json, encoding="utf-8") as f:
            config = json.load(f)
    code = run_v3(args.input, args.output_dir, mode=mode,
                  verbose=not args.quiet,
                  skip_incomplete=args.skip_incomplete_loops,
                  force_run_with_problems=args.force,
                  config=config)
    sys.exit(code)


if __name__ == "__main__":
    main()
