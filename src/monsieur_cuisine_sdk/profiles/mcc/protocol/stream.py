"""Incremental offline frame parser with explicit corruption diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

from .codec import FrameError, RxFrame, TxFrame, decode_frame


@dataclass(frozen=True, slots=True)
class StreamIssue:
    """A structural problem at an absolute, zero-based byte stream offset.

    ``preview_hex`` is bounded diagnostic context, not a complete input dump.
    ``discarded_count`` counts only bytes discarded by this particular issue.
    Semantic frame warnings remain on decoded frames instead.
    """

    code: str
    message: str
    offset: int
    discarded_count: int
    preview_hex: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code, "message": self.message, "offset": self.offset,
            "discarded_count": self.discarded_count, "preview_hex": self.preview_hex,
        }


class StreamParser:
    """Consume arbitrary splits/concatenations without assuming read boundaries.

    At most 26 incomplete frame bytes are retained between calls. Each input
    byte is processed using a buffer no larger than the maximum frame (27).
    Diagnostics accumulate explicitly in ``issues``; clients processing an
    unbounded stream may periodically archive and clear that public list.
    A recovered frame does not make corrupt input valid: inspect ``issues``.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._received = 0
        self._garbage_start = 0
        self._garbage_count = 0
        self._garbage_preview = bytearray()
        self.issues: list[StreamIssue] = []
        self.discarded_bytes = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    @property
    def remainder(self) -> bytes:
        return bytes(self._buffer)

    def _garbage(self, value: int, offset: int) -> None:
        if not self._garbage_count:
            self._garbage_start = offset
        self._garbage_count += 1
        self.discarded_bytes += 1
        if len(self._garbage_preview) < 16:
            self._garbage_preview.append(value)

    def _flush_garbage(self) -> None:
        if self._garbage_count:
            self.issues.append(StreamIssue(
                "garbage", f"Discarded {self._garbage_count} byte(s) outside a frame.",
                self._garbage_start, self._garbage_count,
                bytes(self._garbage_preview).hex(" ").upper(),
            ))
            self._garbage_count = 0
            self._garbage_preview.clear()

    def _reject(self, code: str, message: str) -> None:
        self._flush_garbage()
        self.issues.append(StreamIssue(
            code, message, self._received - len(self._buffer), 1,
            bytes(self._buffer).hex(" ").upper(),
        ))
        del self._buffer[0]
        self.discarded_bytes += 1

    def _extract(self) -> list[TxFrame | RxFrame]:
        frames: list[TxFrame | RxFrame] = []
        while self._buffer:
            offset = self._received - len(self._buffer)
            if self._buffer[0] != 0x55:
                self._garbage(self._buffer[0], offset)
                del self._buffer[0]
                continue
            self._flush_garbage()
            if len(self._buffer) < 2:
                break
            size = self._buffer[1]
            if size not in (15, 27):
                self._reject("length_byte", f"Unsupported frame length byte 0x{size:02X}.")
                continue
            if len(self._buffer) < 3:
                break
            expected_type = 0xA1 if size == 15 else 0xB1
            if self._buffer[2] != expected_type:
                self._reject("type", f"Expected type byte 0x{expected_type:02X}.")
                continue
            if len(self._buffer) < size:
                break
            try:
                frame = decode_frame(bytes(self._buffer[:size]))
            except FrameError as exc:
                self._reject(exc.code, str(exc))
                continue
            frames.append(frame)
            del self._buffer[:size]
        return frames

    def feed(self, data: bytes) -> list[TxFrame | RxFrame]:
        """Return complete frames found in this chunk; retain a partial suffix."""

        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise FrameError("Stream input must be bytes.", "input_type")
        frames: list[TxFrame | RxFrame] = []
        for value in bytes(data):
            self._received += 1
            if not self._buffer and value != 0x55:
                self._garbage(value, self._received - 1)
                continue
            self._buffer.append(value)
            frames.extend(self._extract())
        self._flush_garbage()
        return frames

    def finish(self) -> None:
        """Raise ``FrameError(code='truncated')`` if a partial frame remains.

        The retained bytes are not discarded: a caller may inspect the error
        or continue feeding the missing bytes after catching it. Garbage is
        reported through ``issues`` and ``discarded_bytes``.
        """

        self._flush_garbage()
        if self._buffer:
            size = self._buffer[1] if len(self._buffer) >= 2 else None
            detail = f"{len(self._buffer)} retained byte(s)"
            if size is not None:
                detail += f"; expected {size}, missing {size - len(self._buffer)}"
            raise FrameError(
                f"Truncated frame at offset {self._received - len(self._buffer)}: {detail}.",
                "truncated", raw=bytes(self._buffer), expected_size=size,
            )
