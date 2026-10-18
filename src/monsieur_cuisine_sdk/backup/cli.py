"""Read-only local backup CLI, separate from the model-required mc-sdk CLI."""
import argparse
import json
from pathlib import Path
import sys
import struct
import zipfile

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
    compare = sub.add_parser("compare")
    compare.add_argument("session", type=Path)
    compare.add_argument("second", type=Path)
    compare.add_argument("--output", type=Path)
    imported = sub.add_parser("import-backup", help="Import ZIP/session/raw bytes into a NEW private folder")
    imported.add_argument("source", type=Path)
    imported.add_argument("destination", type=Path)
    imported.add_argument("--session-member")
    imported.add_argument("--boot1", type=Path)
    imported.add_argument("--boot2", type=Path)
    imported.add_argument("--sha256")
    stage = sub.add_parser("stage", help="Copy and materialize a verified session for the original file verifier")
    stage.add_argument("session", type=Path)
    stage.add_argument("destination", type=Path)
    provision = sub.add_parser("provision-tool")
    provision.add_argument("archive", type=Path)
    provision.add_argument("destination", type=Path)
    provision.add_argument("--kind", choices=("source", "win64"), default="source")
    external = sub.add_parser("external-verify")
    external.add_argument("archive", type=Path)
    external.add_argument("session", type=Path)
    external.add_argument("--installation", type=Path, required=True)
    external.add_argument("--python", required=True)
    external.add_argument("--reports", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "import-backup":
            from .importer import import_backup
            result = import_backup(args.source, args.destination, session_member=args.session_member,
                                   boot1=args.boot1, boot2=args.boot2, expected_sha256=args.sha256)
        elif args.command == "stage":
            from .importer import copy_session
            result = copy_session(args.session, args.destination, materialize=True)
        elif args.command == "provision-tool":
            from .runtime import MCCBackupRuntime
            result = MCCBackupRuntime(args.archive).provision(args.destination, kind=args.kind)
        elif args.command == "external-verify":
            from .runtime import MCCBackupRuntime
            result = MCCBackupRuntime(args.archive).offline_verify(args.installation, args.session, args.reports, python=args.python)
        elif args.command == "compare":
            from .compare import compare_sessions
            result = compare_sessions(args.session, args.second)
        elif args.command == "inventory":
            result = inventory_session(args.session).to_dict()
        elif args.command == "verify":
            result = verify_session(args.session, reconstruct=not args.no_reconstruct).to_dict()
        else:
            verification = verify_session(args.session, reconstruct=not args.no_reconstruct)
            result = {"verification": verification.to_dict(), "inventory": inventory_session(args.session).to_dict(),
                      "passed": verification.passed, "restorability": "UNVERIFIED: no hardware writes or restoration tested"}
        content = json.dumps(result, indent=2) + "\n"
        if getattr(args, "output", None):
            destination = args.output.resolve()
            session_root = args.session.resolve()
            if destination.is_relative_to(session_root) or (args.command == "compare" and destination.is_relative_to(args.second.resolve())):
                raise ValueError("report output must be outside the read-only session")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        else:
            print(content, end="")
        return 0 if result.get("passed", True) else 1
    except (ValueError, OSError, RecursionError, struct.error, zipfile.BadZipFile):
        # Never echo a user-supplied path, personal filename or image metadata.
        print(json.dumps({"error": "Backup input/output rejected; check the session and choose a new report file"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
