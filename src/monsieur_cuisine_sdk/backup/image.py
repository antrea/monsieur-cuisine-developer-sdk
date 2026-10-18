"""Random-access views of disk images: a raw file, or a composite assembled from pieces.

A composite image lets a backup that ships only partition files (not the full
user-area image) be checked against the full image's recorded SHA-256: if the
assembled bytes hash the same, the pieces are a lossless representation.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

CHUNK = 8 * 1024 * 1024


class RawImage:
    """Read-only view of one file (optionally a window inside it)."""

    def __init__(self, path, offset: int = 0, length: int | None = None):
        self.path = Path(path)
        total = self.path.stat().st_size
        if offset < 0 or offset > total:
            raise ValueError("window offset outside the file")
        self.base = offset
        self.size = total - offset if length is None else length
        if self.base + self.size > total:
            raise ValueError("window extends past the end of the file")

    def read_at(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0:
            raise ValueError("negative read")
        length = max(0, min(length, self.size - offset))
        if not length:
            return b""
        with open(self.path, "rb") as handle:
            handle.seek(self.base + offset)
            return handle.read(length)


@dataclass(frozen=True)
class Segment:
    """``length`` bytes at image ``offset``: from ``source`` at ``source_offset``, or zeros, or literal data."""
    offset: int
    length: int
    source: Path | None = None
    source_offset: int = 0
    data: bytes | None = None
    label: str = ""


class CompositeImage:
    """Image of ``size`` bytes made of non-overlapping segments; uncovered bytes read as zero."""

    def __init__(self, size: int, segments: list[Segment]):
        ordered = sorted(segments, key=lambda s: s.offset)
        for seg in ordered:
            if seg.length < 0 or seg.offset < 0 or seg.offset + seg.length > size:
                raise ValueError(f"segment {seg.label or seg.offset} outside the image")
            if seg.data is not None and len(seg.data) != seg.length:
                raise ValueError(f"segment {seg.label} data length mismatch")
            if seg.source is not None and os.path.getsize(seg.source) < seg.source_offset + seg.length:
                raise ValueError(f"segment {seg.label}: source file too short")
        for before, after in zip(ordered, ordered[1:]):
            if after.offset < before.offset + before.length:
                raise ValueError(f"segments {before.label} and {after.label} overlap")
        self.size, self.segments = size, ordered

    def read_at(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0:
            raise ValueError("negative read")
        end = min(self.size, offset + length)
        out = bytearray()
        cursor = offset
        for seg in self.segments:
            seg_end = seg.offset + seg.length
            if seg_end <= cursor or seg.offset >= end:
                continue
            if seg.offset > cursor:
                out += bytes(seg.offset - cursor)
                cursor = seg.offset
            take = min(end, seg_end) - cursor
            inner = cursor - seg.offset
            if seg.data is not None:
                out += seg.data[inner:inner + take]
            elif seg.source is not None:
                with open(seg.source, "rb") as handle:
                    handle.seek(seg.source_offset + inner)
                    out += handle.read(take)
            else:
                out += bytes(take)
            cursor += take
        if cursor < end:
            out += bytes(end - cursor)
        return bytes(out)

    def coverage(self) -> dict[str, int]:
        covered = {"file": 0, "literal": 0, "zero": 0}
        for seg in self.segments:
            covered["file" if seg.source else "literal" if seg.data is not None else "zero"] += seg.length
        covered["implicit_zero"] = self.size - sum(s.length for s in self.segments)
        return covered


def sha256_image(image, *, progress=None, chunk: int = CHUNK) -> str:
    """SHA-256 of a whole RawImage/CompositeImage, streamed in ``chunk`` reads."""
    digest, offset = hashlib.sha256(), 0
    while offset < image.size:
        block = image.read_at(offset, min(chunk, image.size - offset))
        if not block:
            raise ValueError(f"image ended early at {offset}")
        digest.update(block)
        offset += len(block)
        if progress:
            progress(offset, image.size)
    return digest.hexdigest()


def sha256_file(path, *, chunk: int = CHUNK) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def is_all_zero(image, offset: int, length: int, *, chunk: int = CHUNK) -> bool:
    end = offset + length
    while offset < end:
        block = image.read_at(offset, min(chunk, end - offset))
        if not block or block.count(0) != len(block):
            return False
        offset += len(block)
    return True
