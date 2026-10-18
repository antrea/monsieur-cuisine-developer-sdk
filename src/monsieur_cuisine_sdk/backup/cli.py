"""Read-only local backup CLI, separate from the model-required mc-sdk CLI."""
import argparse
import json
from pathlib import Path
import sys
import struct

from .inventory import inventory_session
from .verify import verify_session


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "inventory", "report"):
        command = sub.add_parser(name)
        command.add_argument("session", type=Path)
        command.add_argument("--output", type=Path)
        if name != "inventory":
            command.add_argument("--no-reconstruct", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "inventory":
            result = inventory_session(args.session).to_dict()
        elif args.command == "verify":
            result = verify_session(args.session, reconstruct=not args.no_reconstruct).to_dict()
        else:
            verification = verify_session(args.session, reconstruct=not args.no_reconstruct)
            result = {"verification": verification.to_dict(), "inventory": inventory_session(args.session).to_dict(),
                      "passed": verification.passed, "restorability": "UNVERIFIED: no hardware writes or restoration tested"}
        content = json.dumps(result, indent=2) + "\n"
        if args.output:
            destination = args.output.resolve()
            session_root = args.session.resolve()
            if destination.is_relative_to(session_root):
                raise ValueError("report output must be outside the read-only session")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        else:
            print(content, end="")
        return 0 if result.get("passed", True) else 1
    except (ValueError, OSError, RecursionError, struct.error):
        # Never echo a user-supplied path, personal filename or image metadata.
        print(json.dumps({"error": "Backup input/output rejected; check the session and choose a new report file"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
