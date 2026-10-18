"""Explicit-target ADB tools, durable application rollback and offline rehearsal.

Legacy plan/rehearse commands remain explicitly synthetic. Operational commands
use Android Package Manager; application changes require a separate opt-in.
No command enables ADB, obtains root or writes appliance firmware/partitions.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess

from .backup.image import sha256_file
from .adb import AdbError

PROPERTIES = ("ro.build.version.release", "ro.build.version.sdk", "ro.product.model", "ro.product.manufacturer")


class ReadOnlyADB:
    def __init__(self, executable, *, runner=subprocess.run):
        self.executable, self.runner = str(Path(executable)), runner

    def _read(self, arguments):
        allowed = arguments == ["get-state"] or (len(arguments) == 3 and arguments[:2] == ["shell", "getprop"]
                                                  and arguments[2] in PROPERTIES)
        if not allowed:
            raise ValueError("ADB command outside the read-only diagnostic allowlist")
        done = self.runner([self.executable, *arguments], capture_output=True, text=True, timeout=10, check=False)
        if done.returncode or len(done.stdout) > 4096:
            raise ValueError("ADB unavailable, unauthorized or diagnostic response too large")
        return done.stdout.strip()

    def diagnose(self):
        state = self._read(["get-state"])
        if state != "device":
            raise ValueError("no authorized ADB device; ADB is disabled by default on MCC")
        return {"state": state, "read_only": True, "hardware_validated": False,
                "build": {key: self._read(["shell", "getprop", key]) for key in PROPERTIES},
                "identifiers_included": False}


def application_plan(apk, package, *, minimum_sdk):
    """Hash a supplied APK as opaque bytes and prepare a non-executing plan."""
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+", package):
        raise ValueError("invalid application package")
    if package == "de.silpion.mc2" or package.startswith("android."):
        raise ValueError("replacement of manufacturer/system applications is not supported")
    if type(minimum_sdk) is not int or not 1 <= minimum_sdk <= 100:
        raise ValueError("minimum_sdk must be explicitly declared")
    apk = Path(apk)
    if apk.suffix.lower() != ".apk" or not 0 < apk.stat().st_size <= 512 * 1024**2:
        raise ValueError("select an APK within the size bound")
    return {"schema": "mcc-app-plan-v1", "package": package, "sha256": sha256_file(apk),
            "bytes": apk.stat().st_size, "declared_minimum_sdk": minimum_sdk,
            "metadata_source": "caller; APK internals not inspected", "execution": "offline-only",
            "signatures_checked": False, "hardware_compatibility": "UNVERIFIED"}


class ApplicationSandbox:
    """A local transaction model to rehearse install/launcher/rollback semantics.

    State contains only package names and supplied hashes. It neither launches
    ADB nor creates an appliance installer; an authorized physical transport and
    independent compatibility evidence would be required for device changes.
    """
    def __init__(self, *, android_sdk=23):
        if type(android_sdk) is not int or not 1 <= android_sdk <= 100:
            raise ValueError("invalid Android SDK")
        self.android_sdk = android_sdk
        self.apps = {}
        self.launcher = "de.silpion.mc2"
        self._baseline = None

    def snapshot(self):
        self._baseline = (deepcopy(self.apps), self.launcher)
        return {"apps": deepcopy(self.apps), "launcher": self.launcher, "simulation": True}

    def apply(self, plan):
        if self._baseline is None:
            raise ValueError("take a local rollback snapshot first")
        if not isinstance(plan, dict) or type(plan.get("declared_minimum_sdk")) is not int:
            raise ValueError("plan must contain an explicit integer Android level")
        if (plan.get("schema") != "mcc-app-plan-v1" or plan.get("execution") != "offline-only"
                or plan.get("declared_minimum_sdk", 101) > self.android_sdk):
            raise ValueError("plan incompatible with this simulated Android level")
        if not re.fullmatch(r"[0-9a-f]{64}", plan.get("sha256", "")):
            raise ValueError("plan lacks an integrity hash")
        package = plan.get("package", "")
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+", package) or package == "de.silpion.mc2" or package.startswith("android."):
            raise ValueError("unsupported package")
        self.apps[package] = plan["sha256"]

    def select_launcher(self, package):
        if package not in self.apps and package != "de.silpion.mc2":
            raise ValueError("launcher must exist in the local sandbox")
        self.launcher = package

    def rollback(self):
        if self._baseline is None:
            raise ValueError("no rollback snapshot")
        self.apps, self.launcher = deepcopy(self._baseline)
        return {"apps": deepcopy(self.apps), "launcher": self.launcher, "simulation": True}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    diagnostic = sub.add_parser("diagnostics"); diagnostic.add_argument("--adb", required=True)
    plan = sub.add_parser("plan"); plan.add_argument("apk", type=Path)
    plan.add_argument("--package", required=True); plan.add_argument("--minimum-sdk", type=int, required=True)
    plan.add_argument("--output", type=Path)
    rehearsal = sub.add_parser("rehearse"); rehearsal.add_argument("plan", type=Path)
    for operation in ("devices", "info", "apps", "install", "remove", "start", "home", "home-chooser", "config", "rollback"):
        command = sub.add_parser(operation)
        command.add_argument("--adb", required=True)
        command.add_argument("--serial", required=operation != "devices", help="exact authorized ADB target; never selected automatically")
        command.add_argument("--server-port", type=int, default=5037)
        command.add_argument("--allow-app-changes", action="store_true")
        if operation in ("install", "config", "home", "rollback"):
            command.add_argument("--journal", type=Path, required=True)
        if operation == "install":
            command.add_argument("apk", type=Path)
            command.add_argument("--aapt", required=True)
        elif operation == "remove":
            command.add_argument("package")
            command.add_argument("--allow-data-removal", action="store_true")
        elif operation in ("start", "home"):
            command.add_argument("component")
        elif operation == "config":
            command.add_argument("key", choices=("screen_brightness", "screen_off_timeout"))
            command.add_argument("value")
    args = parser.parse_args(argv)
    try:
        if args.command == "diagnostics":
            result = ReadOnlyADB(args.adb).diagnose()
        elif args.command == "plan":
            result = application_plan(args.apk, args.package, minimum_sdk=args.minimum_sdk)
        elif args.command == "rehearse":
            if args.plan.stat().st_size > 65536:
                raise ValueError("plan too large")
            data = json.loads(args.plan.read_text('utf-8'))
            sandbox = ApplicationSandbox(); before = sandbox.snapshot()
            sandbox.apply(data); sandbox.select_launcher(data['package'])
            after = sandbox.rollback()
            result = {"simulation": True, "rollback_matches_snapshot": before == after,
                      "hardware_commands_sent": 0, "restoration_tested_on_hardware": False}
        else:
            from .adb import AdbClient, AdbError, inspect_apk
            from .transactions import AppTransaction
            client = AdbClient(args.adb, serial=args.serial or "enumeration-only", server_port=args.server_port,
                               application_changes=args.allow_app_changes)
            if args.command in ("install", "config", "home", "rollback"):
                if not args.allow_app_changes:
                    raise PermissionError("explicit --allow-app-changes required")
                transaction = AppTransaction(client, args.journal)
                if args.command == "rollback" or args.journal.exists():
                    transaction.load()
                else:
                    transaction.begin()
            try:
                if args.command == "devices":
                    result = {"devices": client.devices()}
                elif args.command == "info":
                    result = client.diagnose()
                elif args.command == "apps":
                    result = {"user_packages": client.packages(kind="user"), "homes": client.home_preferences()}
                elif args.command == "install":
                    result = transaction.install(args.apk, inspect_apk(args.apk, aapt=args.aapt))
                elif args.command == "remove":
                    if not args.allow_data_removal:
                        raise PermissionError("--allow-data-removal is required to remove an app and its data")
                    result = client.uninstall(args.package)
                elif args.command == "start":
                    result = client.start_activity(args.component)
                elif args.command == "home":
                    transaction.home(args.component)
                    result = {"home": args.component, "persistent": True}
                elif args.command == "home-chooser":
                    result = client.home_chooser()
                elif args.command == "config":
                    transaction.setting("system", args.key, args.value)
                    result = {"setting": args.key, "updated": True}
                else:
                    result = transaction.rollback()
            except AdbError as exc:
                print(json.dumps({"error": str(exc), "completed": False})); return 2
        if getattr(args, 'output', None):
            with args.output.open('x', encoding='utf-8', newline='\n') as handle:
                handle.write(json.dumps(result, indent=2) + '\n')
        else:
            print(json.dumps(result, indent=2))
        return 0
    except AdbError as exc:
        print(json.dumps({"error": str(exc), "completed": False})); return 2
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired):
        print(json.dumps({"error": "USB operation rejected; check arguments, opt-in and private journal", "completed": False})); return 2


if __name__ == "__main__":
    raise SystemExit(main())
