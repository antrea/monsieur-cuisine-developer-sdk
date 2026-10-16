"""Opt-in virtual byte adapters; no real serial port is ever accepted or opened.

``SerialLike`` is a driver-free in-process endpoint. ``POSIXPTYBridge`` can
explicitly create a fresh POSIX pseudo-terminal for another local application.
Neither adapter advances model time implicitly, starts on import, or installs
drivers. Windows COM emulation is not implemented; the memory and loopback TCP
adapters are available on Windows without a serial driver.
"""

from __future__ import annotations

import math
import os
import threading
import time
from types import TracebackType

from .model import PowerBoardModel


def _buffer_limit(value: int) -> int:
    if type(value) is not int or value < 27:
        raise ValueError("max_buffer_bytes must be an integer of at least 27")
    return value


class SerialLike:
    """A small read/write serial-style interface backed only by memory.

    ``timeout=0`` reads immediately; ``None`` waits until the requested count or
    close; a finite nonnegative timeout may return a partial read. These waits
    use wall time but never advance the model's virtual physics. ``write``
    returns the number of input bytes, including partial/invalid protocol data;
    that byte count is not command acceptance or a hardware acknowledgement.
    Call ``advance``/``sample`` to enqueue further synthetic responses.

    All wrappers use ``model_lock``. If another component shares ``model``,
    share that same lock or serialize access externally. Buffer overflow raises
    ``BufferError`` and increments ``buffer_overruns``; the model operation has
    already occurred, and no RX from that operation is added to the buffer.
    """

    port = "memory://mcc-powerboard"
    baudrate = 4800  # Descriptive only; memory bytes are not baud-rate paced.

    def __init__(
        self, model: PowerBoardModel | None = None, *, timeout: float | None = 0.0,
        max_buffer_bytes: int = 1_048_576,
    ) -> None:
        self.model = model if model is not None else PowerBoardModel()
        self.model_lock = threading.RLock()
        self._condition = threading.Condition(self.model_lock)
        self.max_buffer_bytes = _buffer_limit(max_buffer_bytes)
        self._buffer = bytearray()
        self._open = True
        self.buffer_overruns = 0
        self.timeout = timeout

    @property
    def timeout(self) -> float | None:
        return self._timeout

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        if value is not None:
            try:
                valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                         and math.isfinite(value) and value >= 0)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("timeout must be None or a finite nonnegative number")
        self._timeout = None if value is None else float(value)

    @property
    def is_open(self) -> bool:
        with self.model_lock:
            return self._open

    def _ensure_open(self) -> None:
        if not self._open:
            raise ValueError("I/O operation on closed memory endpoint")

    @property
    def in_waiting(self) -> int:
        with self.model_lock:
            self._ensure_open()
            return len(self._buffer)

    def _enqueue(self, frames: list[bytes]) -> None:
        payload = b"".join(frames)
        if len(self._buffer) + len(payload) > self.max_buffer_bytes:
            self.buffer_overruns += 1
            raise BufferError("synthetic RX buffer is full; read or reset it before continuing")
        self._buffer.extend(payload)
        self._condition.notify_all()

    def write(self, data: bytes) -> int:
        """Feed raw bytes and buffer resulting RX; return input byte count."""

        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValueError("write requires bytes")
        raw = bytes(data)
        with self._condition:
            self._ensure_open()
            self._enqueue(self.model.feed(raw))
            return len(raw)

    def read(self, size: int = 1) -> bytes:
        if type(size) is not int or size < 0:
            raise ValueError("read size must be a nonnegative integer")
        with self._condition:
            self._ensure_open()
            timeout = self.timeout
            deadline = None if timeout is None else time.monotonic() + timeout
            while len(self._buffer) < size:
                if timeout == 0:
                    break
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    break
                self._condition.wait(remaining)
                self._ensure_open()
            result = bytes(self._buffer[:size])
            del self._buffer[:size]
            return result

    def flush(self) -> None:
        """Writes already reach the memory model synchronously; verify open."""

        with self.model_lock:
            self._ensure_open()

    def reset_input_buffer(self) -> None:
        """Clear delivered RX bytes; delayed model responses remain queued."""

        with self.model_lock:
            self._ensure_open()
            self._buffer.clear()

    def reset_output_buffer(self) -> None:
        """Discard incomplete TX parsing, preserving already applied commands."""

        with self.model_lock:
            self._ensure_open()
            self.model.reset_input()

    def advance(self, delta_ms: int) -> list[bytes]:
        with self._condition:
            self._ensure_open()
            frames = self.model.advance(delta_ms)
            self._enqueue(frames)
            return frames

    def sample(self) -> list[bytes]:
        with self._condition:
            self._ensure_open()
            frames = self.model.sample()
            self._enqueue(frames)
            return frames

    def snapshot(self) -> dict[str, object]:
        with self.model_lock:
            return self.model.snapshot()

    def set_sensors(self, **changes: object) -> None:
        with self.model_lock:
            self._ensure_open()
            self.model.set_sensors(**changes)

    def set_faults(self, **changes: object) -> None:
        with self.model_lock:
            self._ensure_open()
            self.model.set_faults(**changes)

    def configure(self, **changes: object) -> None:
        with self.model_lock:
            self._ensure_open()
            self.model.configure(**changes)

    def close(self) -> None:
        """Wake blocked readers without changing the model's motor target."""

        with self._condition:
            if not self._open:
                return
            self._open = False
            self._buffer.clear()
            self.model.reset_input()
            self._condition.notify_all()

    def __enter__(self) -> SerialLike:
        with self.model_lock:
            self._ensure_open()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        self.close()


class POSIXPTYBridge:
    """Explicit fresh pseudo-terminal for a local external serial application.

    ``start`` accepts no device path: it creates a new ``pty.openpty`` pair,
    places its slave in raw mode and exposes ``slave_name``. Only the created
    master/slave descriptors are touched. No real UART or existing COM port is
    opened. Model time still advances through ``advance``; applications need a
    host loop that calls it and optionally ``sample``. On Windows, ``start``
    raises ``NotImplementedError``. Construction/import remain portable.
    """

    def __init__(
        self, model: PowerBoardModel | None = None, *, max_buffer_bytes: int = 1_048_576,
    ) -> None:
        self.model = model if model is not None else PowerBoardModel()
        self.model_lock = threading.RLock()
        self.max_buffer_bytes = _buffer_limit(max_buffer_bytes)
        self.slave_name: str | None = None
        self.last_error: str | None = None
        self._master: int | None = None
        self._slave: int | None = None
        self._pending = bytearray()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._closed = False

    @property
    def running(self) -> bool:
        with self.model_lock:
            return self._master is not None and not self._stop.is_set()

    def _ensure_running(self) -> None:
        if self._master is None or self._closed or self._stop.is_set():
            raise RuntimeError("pseudo-terminal bridge is not running")

    def start(self) -> POSIXPTYBridge:
        if os.name != "posix":
            raise NotImplementedError(
                "POSIX pseudo-terminals are unavailable here; use SerialLike or loopback TCP. "
                "A Windows virtual COM bridge is not implemented."
            )
        import pty
        import tty

        with self.model_lock:
            if self._closed:
                raise RuntimeError("bridge is closed; create a new instance")
            if self._master is not None:
                return self
            master, slave = pty.openpty()
            try:
                tty.setraw(slave)
                os.set_blocking(master, False)
                self.slave_name = os.ttyname(slave)
            except BaseException:
                os.close(master)
                os.close(slave)
                raise
            self._master, self._slave = master, slave
            self.model.reset_input()
            self._thread = threading.Thread(target=self._run, name="powerboard-virtual-pty", daemon=True)
            self._thread.start()
        return self

    def _flush_locked(self) -> None:
        if self._master is None:
            return
        while self._pending:
            try:
                sent = os.write(self._master, self._pending)
            except BlockingIOError:
                return
            if not sent:
                return
            del self._pending[:sent]

    def _enqueue_locked(self, frames: list[bytes]) -> None:
        payload = b"".join(frames)
        if len(self._pending) + len(payload) > self.max_buffer_bytes:
            raise BufferError("pseudo-terminal response buffer is full")
        self._pending.extend(payload)
        self._flush_locked()

    def _run(self) -> None:
        import select

        try:
            while not self._stop.is_set():
                with self.model_lock:
                    master = self._master
                    pending = bool(self._pending)
                if master is None:
                    return
                readable, writable, _ = select.select([master], [master] if pending else [], [], 0.05)
                with self.model_lock:
                    if self._master != master or self._stop.is_set():
                        return
                    if readable:
                        try:
                            data = os.read(master, 4096)
                        except BlockingIOError:
                            data = b""
                        if data:
                            self._enqueue_locked(self.model.feed(data))
                    if writable:
                        self._flush_locked()
        except (OSError, ValueError, BufferError) as exc:
            if not self._stop.is_set():
                self.last_error = type(exc).__name__
                self.close()

    def advance(self, delta_ms: int) -> list[bytes]:
        with self.model_lock:
            self._ensure_running()
            frames = self.model.advance(delta_ms)
            self._enqueue_locked(frames)
            return frames

    def sample(self) -> list[bytes]:
        with self.model_lock:
            self._ensure_running()
            frames = self.model.sample()
            self._enqueue_locked(frames)
            return frames

    def snapshot(self) -> dict[str, object]:
        with self.model_lock:
            return self.model.snapshot()

    def close(self) -> None:
        with self.model_lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            descriptors = (self._master, self._slave)
            self._master = self._slave = None
            self._pending.clear()
            self.model.reset_input()
            worker = self._thread
        for descriptor in descriptors:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2.0)

    def __enter__(self) -> POSIXPTYBridge:
        return self.start()

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        self.close()
