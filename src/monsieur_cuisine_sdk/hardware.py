"""Explicit MCC serial sessions, independent of the synthetic controller.

Nothing opens on import/construction. Serial access is optional (pyserial), at
the caller's selected port, 4800 baud / 8N1 without flow control. Receive-only
is the default. Active sessions require explicit opt-in and fresh telemetry.
These host checks are not certified appliance interlocks or an execution ACK.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Callable, Protocol

from .profiles.mcc.protocol.codec import (
    Direction, Operation, RxFrame, TxFrame, decode_frame, encode_tx,
)
from .profiles.mcc.protocol.stream import StreamParser


class ByteTransport(Protocol):
    def open(self) -> None: ...
    def read(self, size: int) -> bytes: ...
    def write(self, data: bytes) -> int: ...
    def close(self) -> None: ...


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    FAILED = "failed"


class TelemetryTimeout(TimeoutError):
    pass


class SerialTransport:
    """Optional real serial transport. No discovery or implicit reconnect.

    The factory parameter is for integration tests/custom serial backends.
    pyserial is imported only by open(); the normal desktop needs neither it
    nor an OS serial driver. DTR/RTS are requested low before opening; some OS
    drivers may still pulse lines, so opening a port is always a deliberate act.
    """
    def __init__(self, port: str, *, read_only: bool = True, factory=None):
        if not isinstance(port, str) or not port or "\0" in port:
            raise ValueError("an explicit serial port is required")
        self.port, self.read_only, self.factory = port, read_only, factory
        self._serial = None

    def open(self):
        if self._serial is not None:
            raise ConnectionError("serial transport already open")
        factory = self.factory
        if factory is None:
            try:
                from serial import Serial
            except ImportError as exc:
                raise RuntimeError("install the optional serial extra to open serial ports") from exc
            factory = Serial
        serial = factory(port=None, baudrate=4800, bytesize=8, parity="N", stopbits=1,
                         timeout=0.05, write_timeout=0.5, xonxoff=False, rtscts=False, dsrdtr=False)
        try:
            serial.dtr = serial.rts = False
            serial.port = self.port
            serial.open()
        except BaseException:
            serial.close()
            raise
        self._serial = serial

    def _current(self):
        if self._serial is None:
            raise ConnectionError("serial transport is closed")
        return self._serial

    def read(self, size):
        if type(size) is not int or not 1 <= size <= 65536:
            raise ValueError("read size must be 1..65536")
        return bytes(self._current().read(size))

    def write(self, data):
        if self.read_only:
            raise PermissionError("serial transport is receive-only")
        return self._current().write(bytes(data))

    def close(self):
        serial, self._serial = self._serial, None
        if serial is not None:
            serial.close()


@dataclass(frozen=True)
class WireEvent:
    time: float
    kind: str
    hex: str = ""
    detail: str = ""


class MCCSerialSession:
    """Owner-thread MCC session with incremental RX, latched TX and deadlines.

    Call poll() frequently (normally every 10–50 ms). Active mode repeats the
    last validated command at the observed 100 ms host cadence; it never fills
    a delayed schedule with a burst or replays commands on reconnect. Unknown
    opcodes/calibration are available in the codec, not this active controller.
    No PowerBoard watchdog or physical STOP acknowledgement is assumed.
    """
    def __init__(self, transport: ByteTransport, *, active: bool = False,
                 telemetry_timeout: float = 1.0, partial_timeout: float = 0.5,
                 clock: Callable[[], float] = time.monotonic, max_events: int = 4096):
        for value in (telemetry_timeout, partial_timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("timeouts must be positive finite seconds")
        if type(max_events) is not int or not 16 <= max_events <= 100000:
            raise ValueError("max_events must be 16..100000")
        self.transport, self.active, self.clock = transport, active, clock
        self.telemetry_timeout, self.partial_timeout = telemetry_timeout, partial_timeout
        self.events = deque(maxlen=max_events)
        self.state = ConnectionState.DISCONNECTED
        self.telemetry: RxFrame | None = None
        self.last_error: str | None = None
        self._parser = StreamParser()
        self._last_rx = self._partial_since = self._next_tx = None
        self._command = encode_tx(Operation.STOP)
        self.armed = False

    def _log(self, kind, raw=b"", detail=""):
        self.events.append(WireEvent(self.clock(), kind, raw.hex(), detail))

    def connect(self):
        if self.state == ConnectionState.CONNECTED:
            raise ConnectionError("disconnect before connecting")
        self.telemetry = None
        self._last_rx = self._partial_since = self._next_tx = None
        self._parser = StreamParser()
        self.armed = False
        self._command = encode_tx(Operation.STOP)
        try:
            self.transport.open()
        except Exception as exc:
            self.state, self.last_error = ConnectionState.FAILED, type(exc).__name__
            raise
        self.state, self.last_error = ConnectionState.CONNECTED, None
        self._log("connected")
        return self

    def _fresh(self):
        if self.telemetry is None or self._last_rx is None or self.clock() - self._last_rx > self.telemetry_timeout:
            raise TelemetryTimeout("fresh valid telemetry is required")
        return self.telemetry

    def arm(self):
        if not self.active:
            raise PermissionError("session is receive-only; active mode must be explicitly selected")
        if self.state != ConnectionState.CONNECTED:
            raise ConnectionError("session is disconnected")
        state = self._fresh()
        if state.lid_open or state.error_code or state.error_detected or not state.bowl_ntc_detected or state.actual_rpm:
            raise PermissionError("arming requires closed lid, NTC, no error and observed zero RPM")
        self.armed = True
        self._next_tx = self.clock()
        self._log("armed", detail="host gate only; no physical safety certification")

    def command(self, raw: bytes):
        frame = decode_frame(raw)
        if not isinstance(frame, TxFrame):
            raise ValueError("expected an MCC TX frame")
        if frame.operation == Operation.STOP:
            return self.stop()
        if not self.armed:
            raise PermissionError("explicit arm required")
        state = self._fresh()
        if state.lid_open or state.error_code or state.error_detected or not state.bowl_ntc_detected:
            self.stop()
            raise PermissionError("controller telemetry blocks actuation")
        from .profiles.mcc.oem_policy import HostPolicy
        if frame.calibration or frame.tare or frame.warnings or frame.operation not in (
                Operation.STANDARD, Operation.STEAM, Operation.TOAST, Operation.KNEAD, Operation.TURBO):
            raise ValueError("unsupported active operation; use offline protocol tools for experiments")
        decision = HostPolicy("strict").start(frame.operation, frame.speed_level, frame.direction,
                    frame.temperature_level, measured_temperature=state.actual_temperature,
                    lid_open=state.lid_open, error_code=state.error_code)
        if decision.refusals or decision.confirmations:
            raise PermissionError("host policy rejected active command")
        self._command = bytes(raw)
        self._next_tx = self.clock()

    def _write(self, raw):
        written = 0
        while written < len(raw):
            count = self.transport.write(raw[written:])
            if type(count) is not int or not 0 < count <= len(raw) - written:
                raise ConnectionError("serial write made no valid progress")
            written += count
        self._log("tx", raw)

    def stop(self):
        if not self.active:
            raise PermissionError("receive-only sessions never send STOP or any other command")
        previous = decode_frame(self._command)
        self._command = encode_tx(Operation.STOP, direction=previous.direction)
        self.armed = False
        self._next_tx = None
        if self.state == ConnectionState.CONNECTED:
            try:
                self._write(self._command)
            except Exception as exc:
                self._fail(exc)
                raise

    def _fail(self, exc):
        self.armed = False
        self._next_tx = None
        self.state, self.last_error = ConnectionState.FAILED, type(exc).__name__
        self._log("failure", detail=self.last_error)
        self.transport.close()

    def poll(self):
        if self.state != ConnectionState.CONNECTED:
            raise ConnectionError("session is disconnected")
        now = self.clock()
        try:
            if self._partial_since is not None and now - self._partial_since >= self.partial_timeout:
                self._log("discarded", self._parser.remainder, "partial frame expired")
                self._parser = StreamParser()
                self._partial_since = None
            raw = self.transport.read(256)
            if len(raw) > 256:
                raise ConnectionError("transport exceeded requested read bound")
            previous = self._parser.buffered_bytes
            received = []
            for frame in self._parser.feed(raw):
                if isinstance(frame, RxFrame):
                    self.telemetry, self._last_rx = frame, now
                    received.append(frame)
                    self._log("rx", frame.raw)
                else:
                    self._log("discarded", frame.raw, "TX echo is not telemetry")
            for issue in self._parser.issues:
                self._log("parser", detail=issue.code)
            self._parser.issues.clear()
            if self._parser.buffered_bytes:
                if not previous or received or self._partial_since is None:
                    self._partial_since = now
            else:
                self._partial_since = None
            if self.armed:
                if self._last_rx is None or now - self._last_rx > self.telemetry_timeout:
                    self.stop()
                    raise TelemetryTimeout("telemetry expired; host sent STOP; physical stop is unconfirmed")
                if self.telemetry.lid_open or self.telemetry.error_code or self.telemetry.error_detected or not self.telemetry.bowl_ntc_detected:
                    self.stop()
                    self._log("disarmed", detail="unsafe telemetry")
                elif self._next_tx is not None and now >= self._next_tx:
                    self._write(self._command)
                    self._next_tx = now + 0.1
            return received
        except TelemetryTimeout:
            raise
        except Exception as exc:
            self._fail(exc)
            raise

    def close(self):
        try:
            if self.active and self.armed and self.state == ConnectionState.CONNECTED:
                self.stop()
        finally:
            self.transport.close()
            self.armed = False
            self.telemetry = None
            self.state = ConnectionState.DISCONNECTED
            self._parser = StreamParser()
            self._log("disconnected", detail="no physical STOP acknowledgement implied")

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        self.close()


class ReplayTransport:
    """Receive-only recorded RX bytes delivered by an injected monotonic clock.

    Entries are (seconds_since_open, bytes). This replays observations, not OEM
    execution. It never constructs synthetic telemetry or opens a device.
    """
    def __init__(self, entries, *, clock=time.monotonic):
        self.entries = tuple((float(t), bytes(data)) for t, data in entries)
        if any(not math.isfinite(t) or t < 0 or len(data) > 65536 for t, data in self.entries):
            raise ValueError("invalid replay entry")
        if any(a[0] > b[0] for a, b in zip(self.entries, self.entries[1:])):
            raise ValueError("replay entries must be ordered")
        self.clock, self._start = clock, None

    def open(self):
        if self._start is not None:
            raise ConnectionError("replay already open")
        self._start, self._index, self._pending = self.clock(), 0, bytearray()

    def read(self, size):
        if self._start is None:
            raise ConnectionError("replay is closed")
        while self._index < len(self.entries) and self.entries[self._index][0] <= self.clock() - self._start:
            self._pending.extend(self.entries[self._index][1])
            self._index += 1
            if len(self._pending) >= size:
                break
        data = bytes(self._pending[:size])
        del self._pending[:size]
        return data

    def write(self, data):
        raise PermissionError("trace replay is receive-only")

    def close(self):
        self._start = None


def main(argv=None):
    """Receive-only diagnostics and offline recorded-RX inspection."""
    import argparse
    from dataclasses import asdict
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=main.__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    monitor = commands.add_parser("monitor")
    monitor.add_argument("--port", required=True)
    monitor.add_argument("--seconds", type=float, default=5)
    monitor.add_argument("--output", type=Path, required=True, help="new private JSONL trace")
    replay = commands.add_parser("replay")
    replay.add_argument("trace", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "replay":
            if args.trace.stat().st_size > 16 * 1024**2:
                raise ValueError("trace too large")
            decoded = []
            for line in args.trace.read_text("utf-8").splitlines():
                event = json.loads(line)
                if event.get("kind") == "rx":
                    frame = decode_frame(bytes.fromhex(event["hex"]))
                    if not isinstance(frame, RxFrame):
                        raise ValueError("trace RX contains a TX frame")
                    decoded.append(frame.to_dict())
            print(json.dumps({"mode": "recorded observations", "frames": decoded,
                              "hardware_validation_implied": False}, indent=2))
            return 0
        if not math.isfinite(args.seconds) or not 0 < args.seconds <= 3600:
            raise ValueError("duration must be positive and at most one hour")
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            with MCCSerialSession(SerialTransport(args.port), max_events=16) as session:
                deadline = time.monotonic() + args.seconds
                while time.monotonic() < deadline:
                    session.poll()
                    while session.events:
                        output.write(json.dumps(asdict(session.events.popleft())) + "\n")
                    output.flush()
        print(json.dumps({"receive_only": True, "commands_sent": 0, "hardware_verified": False}))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError):
        print(json.dumps({"error": "serial diagnostic failed; no automatic reconnect", "completed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
