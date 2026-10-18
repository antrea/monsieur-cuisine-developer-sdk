"""Explicit-target Android package and launcher operations; never used on startup.

ADB and aapt are external Android SDK tools supplied by the developer. This
module neither enables debugging, obtains root nor changes protected OEM apps.
Mutations need explicit application_changes=True; use AppTransaction to journal
and roll back an install rather than issuing an untracked package operation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from .backup.image import sha256_file

PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+")
COMPONENT = re.compile(r"[A-Za-z][A-Za-z0-9_.]*/\.?[A-Za-z][A-Za-z0-9_.$]*")
SETTING_KEYS = frozenset({("system", "screen_brightness"), ("system", "screen_off_timeout")})
PROTECTED = frozenset({"de.silpion.mc2", "android", "com.android.settings", "com.android.systemui"})


class AdbError(RuntimeError):
    pass


class CapabilityError(AdbError):
    pass


def package_name(value):
    if not isinstance(value, str) or (value != "android" and not PACKAGE.fullmatch(value)):
        raise ValueError("invalid package name")
    return value


def component_name(value):
    if not isinstance(value, str) or not COMPONENT.fullmatch(value):
        raise ValueError("invalid activity component")
    return value


@dataclass(frozen=True)
class ApkMetadata:
    package: str
    minimum_sdk: int
    version_code: str
    sha256: str
    size: int
    launch_activity: str | None


def inspect_apk(apk, *, aapt, runner=subprocess.run):
    """Read actual manifest metadata using Android's aapt, with a bounded APK."""
    path = Path(apk).resolve()
    if path.is_symlink() or path.suffix.lower() != ".apk" or not 0 < path.stat().st_size <= 512 * 1024**2:
        raise ValueError("select a regular APK of at most 512 MiB")
    checksum = sha256_file(path)
    result = runner([str(aapt), "dump", "badging", str(path)], capture_output=True, text=True, timeout=30, check=False)
    if result.returncode or len(result.stdout) > 4 * 1024**2:
        raise AdbError("aapt could not inspect the APK")
    package = re.search(r"^package: name='([^']+)' versionCode='([^']+)'", result.stdout, re.M)
    minimum = re.search(r"^sdkVersion:'(\d+)'", result.stdout, re.M)
    activity = re.search(r"^launchable-activity: name='([^']+)'", result.stdout, re.M)
    if not package or not minimum:
        raise AdbError("APK lacks supported package/minimum SDK metadata")
    package_name(package[1])
    if not 1 <= int(minimum[1]) <= 100:
        raise AdbError("unsupported APK minimum SDK")
    launch = component_name(package[1] + "/" + activity[1]) if activity else None
    if sha256_file(path) != checksum:
        raise AdbError("APK changed during inspection")
    return ApkMetadata(package[1], int(minimum[1]), package[2], checksum, path.stat().st_size, launch)


class AdbClient:
    """ADB subprocess backend with a required exact target for device operations.

    Device enumeration is read-only. Physical application changes are never
    inferred from an attached device or from a prior emulator test. Select the
    target and opt into changes explicitly. Firmware/partition writes, root,
    remount, reboot, shell scripts and OEM package removal are not exposed.
    """
    def __init__(self, executable, *, serial: str, server_port: int = 5037,
                 application_changes: bool = False, runner=subprocess.run):
        if not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", serial):
            raise ValueError("select one explicit ADB target")
        if type(server_port) is not int or not 1 <= server_port <= 65535:
            raise ValueError("invalid ADB server port")
        self.executable, self.serial, self.server_port = str(executable), serial, server_port
        self.application_changes, self.runner = application_changes, runner
        self.target_digest = hashlib.sha256(serial.encode("utf-8")).hexdigest()

    def _run(self, arguments, *, target=True, timeout=20):
        prefix = [self.executable, "-P", str(self.server_port)]
        if target:
            prefix += ["-s", self.serial]
        result = self.runner(prefix + list(arguments), capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode or len(result.stdout) > 8 * 1024**2:
            raise AdbError("ADB operation failed; check target authorization and privileges")
        if result.stdout.startswith(("Error:", "Failure [", "Exception occurred")):
            raise AdbError("Android rejected the requested operation")
        return result.stdout.replace("\r", "").strip()

    def _shell(self, *arguments):
        # adb shell reparses arguments on older Android versions. All dynamic
        # tokens must be shell-safe even though the local subprocess uses argv.
        if any(not re.fullmatch(r"[-A-Za-z0-9_./:$=+]+", str(value)) for value in arguments):
            raise ValueError("unsafe Android shell argument")
        return self._run(["shell", *(shlex.quote(str(arg)) for arg in arguments)])

    def _mutating(self):
        if not self.application_changes:
            raise PermissionError("application changes require explicit opt-in")
        self.require_authorized()

    def devices(self):
        rows = []
        for line in self._run(["devices"], target=False).splitlines()[1:]:
            columns = line.split()
            if len(columns) == 2:
                rows.append({"serial": columns[0], "state": columns[1]})
        return rows

    @classmethod
    def enumerate_devices(cls, executable, *, server_port=5037, runner=subprocess.run):
        """Discovery is read-only and does not require selecting a device first."""
        return cls(executable, serial="enumeration-only", server_port=server_port, runner=runner).devices()

    def require_authorized(self):
        if self._run(["get-state"]) != "device":
            raise AdbError("selected ADB target is not authorized/online")

    def diagnose(self):
        self.require_authorized()
        properties = {key: self._shell("getprop", key) for key in (
            "ro.build.version.sdk", "ro.build.version.release", "ro.product.model", "ro.product.manufacturer")}
        try:
            sdk = int(properties["ro.build.version.sdk"])
        except ValueError as exc:
            raise AdbError("invalid Android API level") from exc
        uid = self._shell("id", "-u")
        return {"target_digest": self.target_digest, "sdk": sdk, "properties": properties,
                "shell_uid": uid, "root_available": uid == "0", "hardware_validated": False,
                "environment": "emulator" if self.serial.startswith("emulator-") else "explicit device",
                "application_changes_enabled": self.application_changes}

    def packages(self, *, kind="all"):
        if kind not in ("all", "user", "system"):
            raise ValueError("package kind must be all/user/system")
        args = ["pm", "list", "packages"] + ({"user": ["-3"], "system": ["-s"]}.get(kind, []))
        names = []
        for line in self._shell(*args).splitlines():
            if line.startswith("package:"):
                names.append(package_name(line[8:]))
        return sorted(set(names))

    def _user_package(self, package):
        package_name(package)
        if package in PROTECTED or package.startswith("android.") or package in self.packages(kind="system"):
            raise PermissionError("protected/system package changes are not supported")

    def installed_apk_hashes(self, package, *, workdir):
        """Hash copies pulled from Package Manager's paths, never guess locations."""
        package_name(package)
        paths = []
        for line in self._shell("pm", "path", package).splitlines():
            if not line.startswith("package:"):
                raise AdbError("unexpected Package Manager path response")
            remote = line[8:]
            if not re.fullmatch(r"/(?:data/app|system/app|system/priv-app)/[A-Za-z0-9_./=+-]+\.apk", remote) or ".." in remote.split("/"):
                raise AdbError("unsafe installed APK path")
            paths.append(remote)
        if len(paths) > 32:
            raise AdbError("too many split APKs")
        hashes = []
        with tempfile.TemporaryDirectory(dir=workdir, prefix="verify-apk-") as temporary:
            for index, remote in enumerate(paths):
                local = Path(temporary) / f"{index}.apk"
                self._run(["pull", remote, str(local)], timeout=120)
                if not local.is_file() or local.stat().st_size > 512 * 1024**2:
                    raise AdbError("installed APK exceeds verification bound")
                hashes.append(sha256_file(local))
        return hashes

    def install(self, apk, metadata: ApkMetadata):
        self._mutating()
        self._user_package(metadata.package)
        if metadata.package in self.packages():
            raise CapabilityError("use a transaction with an explicit update/data preservation policy; new installs only")
        if metadata.minimum_sdk > self.diagnose()["sdk"]:
            raise CapabilityError("APK requires a newer Android API")
        path = Path(apk).resolve()
        if path.stat().st_size != metadata.size or sha256_file(path) != metadata.sha256:
            raise AdbError("APK no longer matches inspected metadata")
        # Android Package Manager validates signatures; never use downgrade,
        # permission auto-grant or verification-disabling flags.
        output = self._run(["install", str(path)], timeout=120)
        if not re.search(r"(?m)^Success$", output) or metadata.package not in self.packages():
            raise AdbError("installation was not confirmed by Package Manager")
        return {"package": metadata.package, "installed": True, "signature_verifier": "Android Package Manager"}

    def uninstall(self, package):
        self._mutating()
        self._user_package(package)
        if package not in self.packages():
            return {"package": package, "removed": True, "already_absent": True}
        output = self._run(["uninstall", package], timeout=60)
        if output != "Success" or package in self.packages():
            raise AdbError("uninstall was not confirmed")
        return {"package": package, "removed": True}

    def start_activity(self, component):
        self.require_authorized()
        output = self._shell("am", "start", "-W", "-n", component_name(component))
        if "Status: ok" not in output:
            raise AdbError("activity did not start successfully")
        return {"component": component, "started": True}

    def home_preferences(self):
        raw = self._shell("dumpsys", "package", "preferred-xml", "--full")
        try:
            tree = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise AdbError("cannot read Android preferred activities") from exc
        homes = []
        for item in tree.findall(".//item"):
            if item.find("filter/cat[@name='android.intent.category.HOME']") is not None:
                homes.append(component_name(item.attrib["name"]))
        return sorted(set(homes))

    def select_home(self, component):
        self._mutating()
        component_name(component)
        # pm set-home-activity is absent on the original API 23 command line.
        # Detect capabilities instead of assuming root or silently claiming a
        # one-time launch changed the persistent HOME preference.
        help_text = self._shell("pm", "help")
        if "set-home-activity" not in help_text:
            raise CapabilityError("persistent HOME selection unavailable via this Android pm; use the system HOME chooser")
        self._shell("pm", "set-home-activity", component)
        if component not in self.home_preferences():
            raise AdbError("HOME preference change was not confirmed")
        return {"component": component, "persistent": True}

    def home_chooser(self):
        self.require_authorized()
        output = self._shell("am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")
        if "Error:" in output or "unable to resolve" in output:
            raise AdbError("system HOME chooser was not available")
        return {"system_chooser_requested": True, "persistent_selection_verified": False}

    def read_setting(self, namespace, key):
        if (namespace, key) not in SETTING_KEYS:
            raise ValueError("setting is not part of the supported configuration set")
        return self._shell("settings", "get", namespace, key)

    def write_setting(self, namespace, key, value):
        self._mutating()
        if (namespace, key) not in SETTING_KEYS or not re.fullmatch(r"[0-9]{1,10}|null", str(value)):
            raise ValueError("unsupported setting/value")
        if str(value) == "null":
            self._shell("settings", "delete", namespace, key)
        else:
            self._shell("settings", "put", namespace, key, str(value))
        if self.read_setting(namespace, key) != str(value):
            raise AdbError("configuration change was not confirmed")


def metadata_dict(metadata):
    return asdict(metadata)
