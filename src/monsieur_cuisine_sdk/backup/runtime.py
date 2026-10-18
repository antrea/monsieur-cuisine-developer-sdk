"""Operational external MCC Backup integration without vendoring GPL binaries.

An owner-supplied, pinned original distribution supplies the implementation.
Copies are verified against that original before an explicit subprocess launch.
Offline verification never contacts USB. Acquisition is a separate, opt-in
read workflow; it is not executed by tests against an appliance.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import zipfile

from .external import MCCBackupAdapter
from .image import RawImage, sha256_file
from .session import BackupSession, FULL_IMAGE, safe_relative
from ..firmware import gpt

MCC_READ_COMMANDS = (
    "printgpt", "r gpt gpt_primary.bin", "rf emmc_boot1.bin --parttype boot1",
    "rf emmc_boot2.bin --parttype boot2", "rl partitions --skip system,cache,userdata",
    "rf emmc_user_full.bin",
)


def _stop_process_tree(process):
    """Stop the explicitly launched verifier, including Python venv redirects.

    Windows venv python.exe can create a second Python process which inherits
    the log handle. Terminating the redirector alone leaves that worker alive.
    taskkill is an OS adapter, never an installed dependency or shell command.
    POSIX uses the dedicated session created for the verifier.
    """
    if process.poll() is not None:
        return
    if os.name == "nt":
        import shutil
        executable = shutil.which("taskkill.exe")
        if executable is None:
            process.kill(); process.wait(timeout=5)
            raise OSError("Windows taskkill is unavailable; child-tree termination cannot be verified")
        stopped = subprocess.run([executable, "/PID", str(process.pid), "/T", "/F"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10, check=False)
        if stopped.returncode and process.poll() is None:
            process.kill(); process.wait(timeout=5)
            raise OSError("Windows verifier tree termination failed")
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=5)
    finally:
        if os.name != "nt":
            # The direct parent may exit before a descendant that ignored TERM.
            # The dedicated process group must not survive cancellation either.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


class MCCBackupRuntime(MCCBackupAdapter):
    @contextmanager
    def _nested(self, kind):
        if kind not in ("source", "win64"):
            raise ValueError("external tool kind must be source or win64")
        if not self.inspect().get("release_verified"):
            raise ValueError("execution requires the pinned original tool ZIP")
        member = "MCCBackup_1.0_tool/MCCBackup_1.0_" + kind + ".zip"
        with zipfile.ZipFile(self.location) as outer:
            item = outer.getinfo(member)
            if item.file_size > 512 * 1024**2:
                raise ValueError("nested tool archive exceeds size bound")
            payload = outer.read(item)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) > 100000 or sum(e.file_size for e in entries) > 8 * 1024**3:
                raise ValueError("nested tool archive exceeds inventory bound")
            names = set()
            for item in entries:
                name = safe_relative(item.filename.rstrip("/")).as_posix()
                if name.casefold() in names or item.file_size > 512 * 1024**2:
                    raise ValueError("duplicate/oversize external tool member")
                names.add(name.casefold())
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("external tool symlinks are not permitted")
            yield archive

    def provision(self, destination, *, kind="source", cancelled=lambda: False, progress=None):
        """Extract the supplied known tool into a NEW directory; never install drivers."""
        destination = Path(destination).resolve()
        if destination.exists():
            raise ValueError("select a new external installation directory")
        with self._nested(kind) as archive:
            destination.mkdir()
            for item in archive.infolist():
                if cancelled():
                    raise InterruptedError("external tool provisioning cancelled")
                relative = safe_relative(item.filename.rstrip("/"))
                target = destination.joinpath(*relative.parts)
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as output, archive.open(item) as source:
                        while block := source.read(1024 * 1024):
                            if cancelled():
                                raise InterruptedError("external tool provisioning cancelled")
                            output.write(block)
                if progress:
                    progress("Extracting verified external tool files")
        return self.verify_installation(destination, kind=kind, cancelled=cancelled)

    def verify_installation(self, installation, *, kind="source", cancelled=lambda: False):
        installation = Path(installation).resolve()
        seen = 0
        for directory, folders, files in os.walk(installation, followlinks=False):
            seen += len(folders) + len(files)
            if seen > 100000:
                raise ValueError("external installation exceeds inventory bound")
            for name in folders + files:
                item = Path(directory) / name
                if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                    raise ValueError("external installation has a link/junction")
        expected = set()
        count = 0
        with self._nested(kind) as archive:
            for item in archive.infolist():
                if cancelled():
                    raise InterruptedError("external tool installation verification cancelled")
                relative = safe_relative(item.filename.rstrip("/"))
                target = installation.joinpath(*relative.parts)
                if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
                    raise ValueError("external installation has a link/junction")
                if not item.is_dir():
                    if not target.is_file() or target.stat().st_size != item.file_size:
                        raise ValueError("external installation is missing/has changed files")
                    digest = hashlib.sha256()
                    with archive.open(item) as source:
                        while block := source.read(1024 * 1024):
                            digest.update(block)
                    if sha256_file(target, cancelled=cancelled) != digest.hexdigest():
                        raise ValueError("external installation hash mismatch")
                    expected.add(relative.as_posix()); count += 1
        actual = {p.relative_to(installation).as_posix() for p in installation.rglob("*") if p.is_file()}
        if actual != expected:
            raise ValueError("unrecognized files in the external executable installation")
        return {"release_verified": True, "files_verified": count, "kind": kind,
                "drivers_installed": False, "executed": False}

    @staticmethod
    def _find(installation, suffix):
        candidates = [p for p in Path(installation).rglob("*") if p.is_file() and p.as_posix().endswith(suffix)]
        if len(candidates) != 1:
            raise ValueError("external tool entry point is missing or ambiguous")
        return candidates[0]

    def offline_verify(self, installation, session_folder, output_directory, *, python,
                       cancelled=lambda: False, progress=None, timeout=3600):
        """Run the original tool's independent verifier on a complete file image."""
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 86400:
            raise ValueError("external verifier timeout must be within one day")
        self.verify_installation(installation, kind="source", cancelled=cancelled)
        session = BackupSession.open(session_folder)
        if not session.has_full_image:
            raise ValueError("original verifier needs a materialized full image; use ImageRecovery first")
        image = RawImage(session.path(FULL_IMAGE))
        table = gpt.read_table(image.read_at, disk_sectors=image.size // 512)
        backup = gpt.read_table(image.read_at, header_lba=table.header.backup_lba, disk_sectors=image.size // 512)
        if table.problems or backup.problems:
            raise ValueError("bounded GPT preflight failed; external verifier not started")
        output = Path(output_directory).resolve()
        if output.exists() or output.is_relative_to(session.root):
            raise ValueError("choose a new report directory outside the source session")
        script = self._find(installation, "/src/verify_offline.py")
        output.mkdir()
        report = output / "VERIFY_REPORT.txt"
        with (output / "process.log").open("wb") as log:
            if cancelled():
                raise InterruptedError("external verifier cancelled before launch")
            process = subprocess.Popen([str(python), "-I", str(script), str(session.root), "--report", str(report)],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=os.name != "nt",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = time.monotonic() + timeout
            try:
                while process.poll() is None:
                    if cancelled():
                        raise InterruptedError("external file verifier cancelled")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("external file verifier timed out")
                    if progress:
                        progress("Original verifier is reading private image files")
                    try:
                        process.wait(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if process.poll() is None:
                    _stop_process_tree(process)
        text = report.read_text("utf-8") if report.is_file() else ""
        passed = process.returncode == 0 and "RESULT: ALL CHECKS PASSED" in text and not any(line.startswith("FAIL ") for line in text.splitlines())
        return {"passed": passed, "external_verifier_executed": True, "returncode": process.returncode,
                "oem_code_vendored": False, "device_commands_sent": 0,
                "restorability": "UNVERIFIED; file checks only"}

    def start_acquisition(self, installation, destination, *, kind="win64", python=None, device_reads=False):
        """Launch the original read engine only after explicit user opt-in.

        The external tool loads a DA into RAM/disables its watchdog as part of
        the known read workflow. No flash write or protection bypass is added.
        The caller owns the returned subprocess, observes exit and validates the
        resulting session before use. Its raw log is private device metadata.
        """
        if not device_reads:
            raise PermissionError("explicit device_reads=True is required for external acquisition")
        self.verify_installation(installation, kind=kind)
        destination = Path(destination).resolve()
        if destination.exists():
            raise ValueError("acquisition requires a fresh session directory")
        if kind == "win64":
            if os.name != "nt":
                raise OSError("the supplied win64 tool requires Windows; select its source distribution")
            executable = self._find(installation, "/mccbackup-engine.exe")
            command = [str(executable), "--engine"]
        else:
            if not python:
                raise ValueError("select a prepared Python interpreter for the source tool")
            command = [str(python), "-u", str(self._find(installation, "/src/mccbackup.py")), "--engine"]
        destination.mkdir()
        (destination / "commands.txt").write_text("\n".join(MCC_READ_COMMANDS) + "\n", encoding="ascii")
        with (destination / "engine_log.txt").open("xb") as log:
            process = subprocess.Popen(command + ["--noreconnect", "--serialport", "DETECT", "script", "commands.txt"],
                                       cwd=destination, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return process
