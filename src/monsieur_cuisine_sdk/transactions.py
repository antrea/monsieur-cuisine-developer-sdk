"""Durable ADB app/configuration transactions and restartable compensation.

The journal is private device metadata. Keep it outside published source and
back it up. Only newly added user apps and explicitly supported settings are
changed; arbitrary package updates/data restoration are not implied. Every
intent is persisted before the external command, including rollback intents.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import tempfile
import sqlite3
import re

from .adb import AdbClient, AdbError, ApkMetadata, CapabilityError, SETTING_KEYS, MANAGER_PACKAGE, metadata_dict, package_name, component_name, normalized_component


def _seal(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _exclusive_target(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        # One mutating transaction per target, across journal directories and
        # processes. An OS-managed SQLite lock is automatically released after
        # a host crash. It is transient coordination, not global configuration.
        identity = self.client.target_digest
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identity):
            raise ValueError("invalid transaction target identity")
        directory = Path(tempfile.gettempdir()) / "mc-sdk-operation-locks"
        if directory.is_symlink():
            raise ValueError("linked operation lock directory is not permitted")
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / (identity + ".sqlite3")
        if path.is_symlink():
            raise ValueError("linked operation lock is not permitted")
        try:
            with closing(sqlite3.connect(path, timeout=0)) as database:
                database.execute("BEGIN IMMEDIATE")
                return method(self, *args, **kwargs)
        except sqlite3.OperationalError as exc:
            raise AdbError("target has another active transaction or coordination is unavailable") from exc
    return run


class AppTransaction:
    """Write-ahead journal for app additions, settings and supported HOME changes.

    Rolling back a new app removes its data created during this transaction.
    Existing apps cannot be silently upgraded/removed. Conflicting external
    changes stop compensation instead of overwriting somebody else's changes.
    A crash after an ADB command but before recording its success is recoverable
    by inspecting Package Manager/settings and verifying the installed APK hash.
    """
    def __init__(self, client: AdbClient, directory):
        self.client = client
        self.directory = Path(directory).resolve()
        self.path = self.directory / "transaction.json"
        self.data = None

    def _save(self):
        data = deepcopy(self.data)
        data["integrity_sha256"] = _seal({key: value for key, value in data.items() if key != "integrity_sha256"})
        raw = json.dumps(data, indent=2).encode("utf-8") + b"\n"
        if len(raw) > 4 * 1024**2:
            raise ValueError("transaction journal exceeds size limit")
        lock = self.directory / ".journal-lock.sqlite3"
        if lock.is_symlink():
            raise ValueError("linked journal lock is not permitted")
        try:
            # SQLite provides a portable OS-managed writer lock released on
            # process death. The JSON remains the inspectable canonical journal.
            with closing(sqlite3.connect(lock, timeout=0)) as database:
                database.execute("BEGIN IMMEDIATE")
                if self.path.exists():
                    if self.path.stat().st_size > 4 * 1024**2:
                        raise ValueError("journal exceeds size limit")
                    current = json.loads(self.path.read_text("utf-8"))
                    if current.get("integrity_sha256") != self.data.get("integrity_sha256"):
                        raise AdbError("journal changed in another session; reload before any new operation")
                descriptor, temporary = tempfile.mkstemp(prefix=".transaction-", dir=self.directory)
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                    os.replace(temporary, self.path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
        except sqlite3.OperationalError as exc:
            raise AdbError("journal is busy or unavailable; no external operation started") from exc
        self.data = data

    def begin(self):
        if self.data is not None or self.directory.exists():
            raise ValueError("choose a new transaction directory")
        info = self.client.diagnose()
        baseline = {"packages": self.client.packages(), "homes": self.client.home_preferences(),
                    "settings": {namespace + "/" + key: self.client.read_setting(namespace, key)
                                 for namespace, key in sorted(SETTING_KEYS)}, "sdk": info["sdk"]}
        self.directory.mkdir(parents=False)
        self.data = {"schema": "mcc-adb-transaction-v1", "target_digest": self.client.target_digest,
                     "baseline": baseline, "status": "open", "actions": []}
        self._save()
        return deepcopy(baseline)

    def load(self):
        if self.path.is_symlink() or not self.path.is_file() or self.path.stat().st_size > 4 * 1024**2:
            raise ValueError("invalid transaction file")
        data = json.loads(self.path.read_text("utf-8"))
        if not isinstance(data, dict) or data.get("schema") != "mcc-adb-transaction-v1":
            raise ValueError("unsupported transaction schema")
        if data.get("target_digest") != self.client.target_digest:
            raise ValueError("transaction belongs to another ADB target")
        if data.get("integrity_sha256") != _seal({k: v for k, v in data.items() if k != "integrity_sha256"}):
            raise ValueError("transaction integrity mismatch")
        if not isinstance(data.get("actions"), list) or len(data["actions"]) > 1000:
            raise ValueError("invalid action journal")
        for action in data["actions"]:
            if action.get("kind") not in ("install", "setting", "home") or action.get("phase") not in ("intent", "applied", "undo-intent", "undone"):
                raise ValueError("unsupported transaction action")
            if action["kind"] == "install":
                name = package_name(action["metadata"]["package"])
                if name in data["baseline"]["packages"]:
                    raise ValueError("journal attempts to remove a pre-existing package")
            elif action["kind"] == "setting":
                if tuple(action["key"].split("/")) not in SETTING_KEYS:
                    raise ValueError("unsupported journal setting")
            else:
                component_name(action["after"])
        self.data = data
        return self

    def _intent(self, kind, **values):
        if self.data is None or self.data["status"] != "open":
            raise ValueError("begin or load an open transaction first")
        if any(action["phase"] in ("intent", "undo-intent") for action in self.data["actions"]):
            raise AdbError("transaction has an unresolved operation; recover/roll back it before making new changes")
        action = {"kind": kind, "phase": "intent", **values}
        self.data["actions"].append(action)
        self._save()
        return action

    def _applied(self):
        self.data["actions"][-1]["phase"] = "applied"
        self._save()

    @_exclusive_target
    def install(self, apk, metadata: ApkMetadata):
        if self.data is None:
            raise ValueError("begin a transaction first")
        if metadata.package in self.data["baseline"]["packages"] or metadata.package in self.client.packages():
            raise CapabilityError("transaction install requires a previously absent user package")
        if any(a["kind"] == "install" and a["metadata"]["package"] == metadata.package for a in self.data["actions"]):
            raise ValueError("package already tracked by this transaction")
        self._intent("install", metadata=metadata_dict(metadata))
        result = self.client.install(apk, metadata)
        self._applied()
        return result

    @_exclusive_target
    def setting(self, namespace, key, value):
        if (namespace, key) not in SETTING_KEYS:
            raise ValueError("unsupported configuration key")
        before = self.client.read_setting(namespace, key)
        self._intent("setting", key=namespace + "/" + key, before=before, after=str(value))
        self.client.write_setting(namespace, key, value)
        self._applied()

    @_exclusive_target
    def home(self, component):
        before = self.client.home_preferences()
        if len(before) > 1:
            raise CapabilityError("persistent HOME change requires an unambiguous prior HOME for rollback")
        component = normalized_component(component)
        effective = None
        if not before:
            if component.split("/")[0] != MANAGER_PACKAGE:
                raise CapabilityError("without a prior HOME preference only the SDK companion can guarantee preference cleanup")
            query = self.client.query_homes()
            effective = query.get("effective_home")
            if not effective or "ResolverActivity" in effective:
                original_homes = [home["component"] for home in query.get("homes", [])
                                  if home["component"].split("/")[0] != MANAGER_PACKAGE
                                  and home["component"].split("/")[0] in self.data["baseline"]["packages"]]
                if len(original_homes) != 1:
                    raise CapabilityError("no unambiguous prior HOME to return to")
                effective = original_homes[0]
            component_name(effective)
        self._intent("home", before=before[0] if before else None, before_effective=effective, after=component)
        self.client.select_home(component)
        self._applied()

    @_exclusive_target
    def rollback(self):
        if self.data is None:
            raise ValueError("load a transaction first")
        if self.data["status"] == "rolled-back":
            return self.verify_rollback()
        self.data["status"] = "rolling-back"
        self._save()
        for index in reversed(range(len(self.data["actions"]))):
            action = self.data["actions"][index]
            if action["phase"] == "undone":
                continue
            self.data["actions"][index]["phase"] = "undo-intent"
            self._save()
            if action["kind"] == "install":
                metadata = action["metadata"]
                if metadata["package"] in self.client.packages():
                    if self.client.installed_apk_hashes(metadata["package"], workdir=self.directory) != [metadata["sha256"]]:
                        raise AdbError("installed app differs from transaction APK; rollback stopped")
                    self.client.uninstall(metadata["package"])
            elif action["kind"] == "setting":
                namespace, key = action["key"].split("/")
                value = self.client.read_setting(namespace, key)
                if value not in (action["before"], action["after"]):
                    raise AdbError("setting changed outside this transaction; rollback stopped")
                if value != action["before"]:
                    self.client.write_setting(namespace, key, action["before"])
            else:
                homes = self.client.home_preferences()
                if action["before"] is None:
                    if homes == [action["after"]]:
                        self.client.clear_own_home(action["after"])
                    elif homes:
                        raise AdbError("HOME changed outside this transaction; rollback stopped")
                    if action.get("before_effective"):
                        self.client.start_activity(action["before_effective"])
                elif homes != [action["before"]]:
                    if homes != [action["after"]]:
                        raise AdbError("HOME changed outside this transaction; rollback stopped")
                    self.client.select_home(action["before"])
            self.data["actions"][index]["phase"] = "undone"
            self._save()
        result = self.verify_rollback()
        self.data["status"] = "rolled-back"
        self._save()
        return result

    def verify_rollback(self):
        baseline = self.data["baseline"]
        current = set(self.client.packages())
        removed = all(a["metadata"]["package"] not in current for a in self.data["actions"] if a["kind"] == "install")
        initial_settings = {}
        for action in self.data["actions"]:
            if action["kind"] == "setting":
                initial_settings.setdefault(action["key"], action["before"])
        restored = all(self.client.read_setting(*key.split("/")) == value
                       for key, value in initial_settings.items())
        homes = self.client.home_preferences()
        home_ok = homes == baseline["homes"]
        # A one-time return to the original UI is distinct from restoring HOME.
        if home_ok and len(homes) == 1:
            self.client.start_activity(homes[0])
        if not (removed and restored and home_ok and set(baseline["packages"]).issubset(current)):
            raise AdbError("rollback postconditions failed")
        return {"rollback_verified": True, "added_apps_removed": removed, "settings_restored": restored,
                "home_restored": home_ok, "baseline_packages_preserved": True,
                "environment": "emulator" if self.client.serial.startswith("emulator-") else "explicit device",
                "hardware_verified": False}
