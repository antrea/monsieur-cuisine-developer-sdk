"""Run original MCC codec DEX on an explicit emulator and compare SDK outputs.

Original APK/DEX bytes remain in a NEW private work folder outside this checkout.
The probe APK contains no OEM bytecode, SDK codec or network permission. Only
named PowerBoard/CookingUtils/Limits methods run in the isolated Android app.
This verifies host software behavior, not the PowerBoard MCU or physical robot.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from monsieur_cuisine_sdk.conformance import compare_reference


def verify(apk, probe_apk, *, adb, serial, server_port, workdir):
    if not re.fullmatch(r"emulator-[0-9]+", serial):
        raise ValueError("OEM execution is restricted to an explicitly selected emulator")
    workdir = Path(workdir).resolve()
    if workdir.is_relative_to(ROOT) or workdir.exists():
        raise ValueError("select a NEW private work folder outside the source checkout")
    if not 1 <= server_port <= 65535:
        raise ValueError("invalid private ADB server port")
    workdir.mkdir()
    source = Path(apk)
    apk_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(source) as archive:
        item = archive.getinfo("classes.dex")
        if not 0 < item.file_size <= 64 * 1024**2:
            raise ValueError("unsupported original DEX size")
        dex = archive.read(item)
    digest = hashlib.sha256(dex).hexdigest()
    local = workdir / "classes.dex"
    local.write_bytes(dex)
    prefix = [str(adb), "-P", str(server_port), "-s", serial]
    commands = []

    def run(*arguments, timeout=90):
        commands.append(list(arguments))
        result = subprocess.run(prefix + list(arguments), capture_output=True, text=True,
                                encoding="utf-8", timeout=timeout, check=False)
        (workdir / f"command-{len(commands)}.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"emulator command {len(commands)} failed; see private log")
        return result.stdout.replace("\r", "")

    if run("shell", "getprop", "ro.build.version.sdk").strip() != "23":
        raise ValueError("reference validation requires an actual API 23 Android environment")
    remote = "/data/local/tmp/mc-sdk-oem-" + uuid.uuid4().hex + ".dex"
    try:
        installed = run("install", "-t", "-r", str(Path(probe_apk).resolve()))
        if not re.search(r"(?m)^Success$", installed):
            raise RuntimeError("probe APK installation failed")
        run("push", str(local), remote)
        output = run("shell", "am", "instrument", "-w", "-r", "-e", "dex", remote, "-e", "sha256", digest,
                     "org.blackstufflabs.monsieurcuisine.oemprobe/.ReferenceInstrumentation", timeout=300)
        if "passed=true" not in output or "vectors=57998" not in output or digest not in output:
            raise RuntimeError("original DEX probe did not report the complete reference execution")
        dataset = workdir / "art-oem-vectors.jsonl"
        with dataset.open("xb") as destination:
            subprocess.run(prefix + ["exec-out", "run-as", "org.blackstufflabs.monsieurcuisine.oemprobe", "cat", "files/oem-vectors.jsonl"],
                           stdout=destination, stderr=subprocess.PIPE, timeout=60, check=True)
        result = compare_reference(dataset)
        assert result["vectors"] == 57998
        result.update({"original_apk_sha256": apk_sha, "original_dex_sha256": digest,
                       "probe_apk_sha256": hashlib.sha256(Path(probe_apk).read_bytes()).hexdigest(),
                       "reference_origin": "OEM DEX directly executed on Android 6/API 23 ART",
                       "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                       "sdk_codec_inside_probe": False, "original_code_in_distribution": False,
                       "evidence": "OEM DYNAMIC VERIFIED for covered host codec/conversion methods only",
                       "commands": commands})
        (workdir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        run("shell", "rm", "-f", remote)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--probe-apk", type=Path, required=True)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    result = verify(**vars(parser.parse_args()))
    print(json.dumps({k: v for k, v in result.items() if k != "commands"}, indent=2))
    raise SystemExit(0 if result["matched"] else 1)
