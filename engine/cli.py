"""
CLI — command-line entry point for the v2 engine (standalone use).
====================================================================

Allows the engine to be invoked directly without the v3 wrapper, e.g.
for backwards compatibility or quick re-runs on already-cleaned data.
"""

import argparse

from .engine import run_diagnostics


def _parse_args():
    p = argparse.ArgumentParser(
        description="Commercial-grade control loop diagnostics tool (v2)"
    )
    p.add_argument("--input", required=True, help="Path to Excel input file")
    p.add_argument("--output-dir", default="./diagnostics_output",
                   help="Directory for outputs")
    p.add_argument("--quiet", action="store_true", help="Suppress console logging")
    return p.parse_args()


def main():
    args = _parse_args()
    run_diagnostics(args.input, args.output_dir, verbose=not args.quiet)


if __name__ == "__main__":
    main()
