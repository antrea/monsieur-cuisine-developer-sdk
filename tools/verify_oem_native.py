"""Execute pinned build-292 JNI in an explicit API23 x86 software emulator.

Only /dev/ptmx is opened by the original code. No serial UART, hardware robot,
payload TX/RX, OEM APK install, root request or proprietary distribution. DEX/SO
stay in a NEW private work folder outside source; uploaded inputs are removed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEX_SHA = "daacbce286ea9f4911556d37c66b8559a3f341046cf720fb900bc047b10c2b53"
NATIVE_SHA = "bd3231f08be279700f6ba64b405429082e02159f136b56fe0f26a0c51877d0fa"


def validate_result(result):
    if not isinstance(result, dict):
        raise ValueError("native reference result must be an object")
    required = {"passed": True, "software_pty_only": True, "endpoint": "/dev/ptmx", "android_api": 23,
                "abi": "x86", "character_device": True, "probe_cleanup_verified_ebadf": True,
                "native_open_verified": True, "original_native_close_invoked": False,
                "original_native_close_verified": False, "original_descriptor_field": "a",
                "original_native_close_required_field": "mFd", "original_native_close_field_present": False,
                "invalid_baud_rejected": True, "open_baud_argument": 4800, "physical_baud_measured": False,
                "payload_bytes_sent": 0, "hardware_verified": False,
                "original_dex_sha256": DEX_SHA, "original_native_sha256": NATIVE_SHA}
    if any(result.get(key) != value or type(result.get(key)) is not type(value) for key, value in required.items()):
        raise ValueError("original JNI result does not prove the required software-only checks")


def verify(apk, probe_apk, *, adb, serial, server_port, workdir, exercise_original_close=False):
    if not isinstance(serial, str) or not re.fullmatch(r"emulator-[0-9]+", serial):
        raise ValueError("native execution requires an explicit software emulator target")
    if type(server_port) is not int or not 1 <= server_port <= 65535:
        raise ValueError("invalid ADB server port")
    workdir = Path(workdir).resolve()
    if workdir.exists() or workdir.is_relative_to(ROOT):
        raise ValueError("select a NEW private work directory outside the source checkout")
    source = Path(apk).resolve()
    if not source.is_file() or not 0 < source.stat().st_size <= 512 * 1024**2:
        raise ValueError("original APK is not a bounded regular file")
    components = {}
    with zipfile.ZipFile(source) as archive:
        for entry, expected, bound, output in (("classes.dex", DEX_SHA, 64 * 1024**2, "classes.dex"),
                ("lib/x86/libserial_port.so", NATIVE_SHA, 16 * 1024**2, "libserial_port.so")):
            item = archive.getinfo(entry)
            if not 0 < item.file_size <= bound:
                raise ValueError("reference component exceeds size bound")
            raw = archive.read(item)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("reference component differs from the identified original build")
            components[output] = raw
    workdir.mkdir(mode=0o700)
    for name, raw in components.items():
        (workdir / name).write_bytes(raw)
    prefix = [str(adb), "-P", str(server_port), "-s", serial]
    commands = []
    def run(*arguments, timeout=90):
        commands.append(list(arguments))
        result = subprocess.run(prefix + list(arguments), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout, check=False)
        (workdir / f"command-{len(commands)}.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("emulator reference operation failed; inspect the private command log")
        return result.stdout.replace("\r", "")
    if (run("shell", "getprop", "ro.build.version.sdk").strip() != "23"
            or run("shell", "getprop", "ro.product.cpu.abi").strip() != "x86"
            or run("shell", "getprop", "ro.hardware").strip() not in ("goldfish", "ranchu")):
        raise ValueError("native verification requires actual API23 x86 emulator properties")
    token = uuid.uuid4().hex
    remote_dex = "/data/local/tmp/mc-sdk-native-" + token + ".dex"
    remote_library = "/data/local/tmp/mc-sdk-native-" + token + ".so"
    try:
        if not re.search(r"(?m)^Success$", run("install", "-t", "-r", str(Path(probe_apk).resolve()))):
            raise RuntimeError("native reference probe APK did not install")
        run("push", str(workdir / "classes.dex"), remote_dex)
        run("push", str(workdir / "libserial_port.so"), remote_library)
        output = run("shell", "am", "instrument", "-w", "-r", "-e", "dex", remote_dex,
                     "-e", "native", remote_library, "-e", "exerciseOriginalClose", str(bool(exercise_original_close)).lower(),
                     "org.blackstufflabs.monsieurcuisine.oemprobe/.NativeSerialInstrumentation", timeout=120)
        if "INSTRUMENTATION_RESULT: passed=true" not in output:
            # Preserve failure evidence. A native abort is never a passing JNI
            # close result, even when deliberately reproduced on software PTY.
            run("logcat", "-d", "-t", "1400")
            (workdir / "failure.json").write_text(json.dumps({"passed": False,
                "scope": "original x86 JNI software PTY diagnostic",
                "exercise_original_close": bool(exercise_original_close),
                "hardware_verified": False, "commands": commands}, indent=2) + "\n", encoding="utf-8")
            raise RuntimeError("original native reference did not pass; inspect private instrumentation output")
        raw = subprocess.run(prefix + ["exec-out", "run-as", "org.blackstufflabs.monsieurcuisine.oemprobe",
                             "cat", "files/native-serial.json"], capture_output=True, timeout=30, check=True).stdout
        if len(raw) > 65536:
            raise ValueError("native reference output exceeds size bound")
        result = json.loads(raw)
        validate_result(result)
        result.update(original_apk_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      probe_apk_sha256=hashlib.sha256(Path(probe_apk).read_bytes()).hexdigest(),
                      evidence="OEM DYNAMIC VERIFIED: original x86 JNI open and invalid baud on software PTY; native close NOT verified",
                      original_code_in_distribution=False, commands=commands)
        (workdir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        run("shell", "rm", "-f", remote_dex, remote_library)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("apk", "probe-apk", "adb", "workdir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--exercise-original-close", action="store_true",
                        help="reproduce the original JNI close failure on software PTY; an abort is a failed probe")
    result = verify(**vars(parser.parse_args(argv)))
    print(json.dumps({key: value for key, value in result.items() if key != "commands"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
