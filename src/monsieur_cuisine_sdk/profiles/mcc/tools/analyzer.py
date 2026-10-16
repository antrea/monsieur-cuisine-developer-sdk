"""Offline mixed TX/RX analysis with explicit corruption and unknown values."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Iterable

from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import FrameError, RxFrame, TxFrame, decode_frame, parse_hex
from monsieur_cuisine_sdk.profiles.mcc.protocol.stream import StreamParser


@dataclass
class LogAnalysis:
    frames: list[dict[str, object]] = field(default_factory=list)
    issues: list[dict[str, object]] = field(default_factory=list)

    def telemetry(self) -> list[dict[str, object]]:
        """RX rows; observed_ms is local recording metadata, never a wire field."""
        keys = ("actual_rpm", "target_rpm", "actual_temperature", "target_temperature", "weight",
                "direction_name", "motor_on", "heater_on", "lid_open", "error_code", "android_error_code", "firmware_version")
        return [{"frame_index": index, "observed_ms": item.get("observed_ms"),
                 **{key: item[key] for key in keys}} for index, item in enumerate(self.frames) if item["kind"] == "RX"]

    def to_dict(self) -> dict[str, object]:
        tx = [item for item in self.frames if item["kind"] == "TX"]
        rx = [item for item in self.frames if item["kind"] == "RX"]
        ranges = {}
        for key in ("actual_rpm", "actual_temperature", "weight"):
            values = [int(item[key]) for item in rx]
            ranges[key] = {"minimum": min(values), "maximum": max(values)} if values else None
        return {"structurally_valid": bool(self.frames) and not self.issues,
                "scope": "Offline framing and recorded observations; no physical safety or wire timestamps",
                "frame_count": len(self.frames), "tx_count": len(tx), "rx_count": len(rx),
                "operations": dict(Counter(str(item["operation_name"]) for item in tx)),
                "board_errors_with_flag": dict(Counter(str(item["error_code"]) for item in rx if item["error_detected"])),
                "ranges": ranges, "semantic_warning_count": sum(len(item["warnings"]) for item in self.frames),
                "frames": self.frames, "issues": self.issues, "telemetry": self.telemetry()}


def _finish(parser: StreamParser, result: LogAnalysis, *, source: str = "stream") -> None:
    result.issues.extend({"source": source, **issue.to_dict()} for issue in parser.issues)
    try:
        parser.finish()
    except FrameError as exc:
        result.issues.append({"source": source, "code": exc.code, "message": str(exc),
                              "bytes_remaining": exc.bytes_remaining, "missing_bytes": exc.missing_bytes})


def analyze_chunks(chunks: Iterable[bytes]) -> LogAnalysis:
    """Analyze arbitrarily fragmented raw bytes, retaining recoverable frames."""
    parser, result = StreamParser(), LogAnalysis()
    for chunk in chunks:
        result.frames.extend(frame.to_dict() for frame in parser.feed(chunk))
    _finish(parser, result)
    return result


def analyze_recording(data: dict[str, object]) -> LogAnalysis:
    """Inspect model inputs/expected RX without executing the recording.

    TX fragments persist separately across feed events. RX bytes are retained
    individually, including a diagnostic for every corrupted expected response.
    This is an analyzer, not the deterministic replay verification tool.
    """
    if not isinstance(data, dict) or data.get("format") != "mcc-powerboard-recording-v1" or not isinstance(data.get("events"), list):
        raise ValueError("unsupported Digital Twin recording")
    result, tx_parser = LogAnalysis(), StreamParser()
    connected = True
    for number, event in enumerate(data["events"]):
        if not isinstance(event, dict):
            raise ValueError(f"event {number} is not an object")
        checkpoint = event.get("checkpoint", {})
        if not isinstance(checkpoint, dict):
            raise ValueError(f"event {number} checkpoint must be an object")
        at = checkpoint.get("now_ms")
        next_connected = checkpoint.get("connected", connected)
        if type(next_connected) is not bool:
            raise ValueError(f"event {number} connected must be boolean")
        if event.get("operation") in ("reset_input", "reset_transport") or next_connected != connected:
            _finish(tx_parser, result, source=f"TX session ending at event {number}")
            tx_parser = StreamParser()
        connected = next_connected
        if event.get("operation") == "feed":
            try:
                raw_text = event["input"]["hex"]
                raw = parse_hex(raw_text) if raw_text else b""
                if connected:
                    for frame in tx_parser.feed(raw):
                        if isinstance(frame, TxFrame):
                            result.frames.append({**frame.to_dict(), "observed_ms": at})
                        else:
                            result.issues.append({"event":number,"code":"rx_in_tx_input","message":"A response frame was supplied as a command; it is not observed RX telemetry"})
                elif raw:
                    result.issues.append({"event":number,"code":"ignored_tx_disconnected","message":"TX bytes were ignored while virtual link was disconnected"})
            except (KeyError, TypeError, FrameError) as exc:
                result.issues.append({"event": number, "code": "recorded_tx", "message": str(exc)})
        responses = event.get("rx_hex", [])
        if not isinstance(responses, list):
            raise ValueError(f"event {number} rx_hex must be a list")
        for raw in responses:
            try:
                frame = decode_frame(raw)
                if not isinstance(frame, RxFrame):
                    raise ValueError("recorded response must be RX")
                result.frames.append({**frame.to_dict(), "observed_ms": at})
            except (ValueError, TypeError) as exc:
                result.issues.append({"event": number, "code": "recorded_rx", "message": str(exc)})
    _finish(tx_parser, result, source="recorded TX")
    return result


def analyze_file(path: str | Path, *, input_format: str = "hex") -> LogAnalysis:
    path = Path(path)
    if input_format == "recording":
        return analyze_recording(json.loads(path.read_text(encoding="utf-8")))
    if input_format not in ("hex", "binary"):
        raise ValueError("input_format must be hex, binary or recording")

    def chunks():
        if input_format == "binary":
            with path.open("rb") as handle:
                while block := handle.read(4096):
                    yield block
        else:
            with path.open(encoding="utf-8-sig") as handle:
                for number, line in enumerate(handle, 1):
                    content = line.split("#", 1)[0].strip()
                    if content:
                        try:
                            yield parse_hex(content)
                        except FrameError as exc:
                            raise ValueError(f"invalid HEX at line {number}: {exc}") from exc
    return analyze_chunks(chunks())
