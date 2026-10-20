"""Compatibility entry to the unified CLI; use its documented command syntax."""
import sys
from monsieur_cuisine_sdk.cli import main as _main

def main(argv=None):
    return _main(["--model", "mcc", *(sys.argv[1:] if argv is None else argv)])

if __name__ == "__main__":
    raise SystemExit(main())
