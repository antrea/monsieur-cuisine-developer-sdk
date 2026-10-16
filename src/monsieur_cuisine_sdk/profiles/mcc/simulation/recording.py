"""Portable JSON input recordings and deterministic binary/state replay.

Recording is local and explicit. Replay opens no sockets and evaluates no code.
The format records model inputs, not a captured physical appliance session.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .model import PhysicsConfig, PowerBoardModel

FORMAT = "mcc-powerboard-recording-v1"
OPS = frozenset(("feed", "advance", "sample", "set_sensors", "set_faults", "configure", "reset_input", "reset_transport"))


def _config(data: dict[str, Any]) -> PhysicsConfig:
    values = dict(data)
    try:
        if "speed_rpm" in values:
            values["speed_rpm"] = tuple(values["speed_rpm"])
        return PhysicsConfig(**values)
    except TypeError as exc:
        raise ValueError("invalid initial physics configuration") from exc


class RecordingSession:
    """A model-compatible facade recording every supported input in order.

    Start with a fresh model; inject initial sensor values through this facade.
    Direct writes through ``controller`` bypass recording and must be avoided.
    External orchestration must serialize calls, as with PowerBoardModel.
    The default 100000-event budget matches replay. A full recorder rejects an
    operation before model mutation; save and start another recording. Callers
    choosing a different ``max_events`` must use that same budget for replay.
    """

    def __init__(self, config: PhysicsConfig | None = None, *, max_events: int | None = 100000) -> None:
        if max_events is not None and (type(max_events) is not int or max_events <= 0):
            raise ValueError("max_events must be a positive integer or None")
        self.max_events = max_events
        self.model = PowerBoardModel(config)
        self.initial_config = asdict(self.model.config)
        self.events: list[dict[str, Any]] = []

    @property
    def now_ms(self) -> int:
        return self.model.now_ms

    @property
    def controller(self):
        return self.model.controller

    @property
    def config(self):
        return self.model.config

    @property
    def connected(self) -> bool:
        return self.model.connected

    @property
    def log(self):
        return self.model.log

    def _invoke(self, operation: str, data: dict[str, Any]) -> Any:
        # Reject before invoking the model: every successful recorded operation
        # must remain replayable under the matching configured event budget.
        if self.max_events is not None and len(self.events) >= self.max_events:
            raise ValueError("recording event limit reached; save and start a new recording")
        if operation == "feed":
            result = self.model.feed(bytes.fromhex(data["hex"]))
        elif operation == "advance":
            result = self.model.advance(data["milliseconds"])
        else:
            result = getattr(self.model, operation)(**data)
        snapshot = self.model.snapshot()
        checkpoint = {name: snapshot[name] for name in ("now_ms", "velocity_rpm", "controller", "physics", "connected")}
        # JSON round-trip makes tuples/lists identical on save and replay.
        event = {"operation": operation, "input": data,
                 "rx_hex": [raw.hex() for raw in result] if isinstance(result, list) else [],
                 "checkpoint": checkpoint}
        self.events.append(json.loads(json.dumps(event, allow_nan=False)))
        return result

    def feed(self, data: bytes) -> list[bytes]:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValueError("feed requires bytes")
        return self._invoke("feed", {"hex": bytes(data).hex()})

    def advance(self, delta_ms: int) -> list[bytes]:
        return self._invoke("advance", {"milliseconds": delta_ms})

    def sample(self) -> list[bytes]:
        return self._invoke("sample", {})

    def set_sensors(self, **changes: Any) -> None:
        self._invoke("set_sensors", changes)

    def set_faults(self, **changes: Any) -> None:
        self._invoke("set_faults", changes)

    def configure(self, **changes: Any) -> None:
        self._invoke("configure", changes)

    def reset_input(self) -> None:
        self._invoke("reset_input", {})

    def reset_transport(self) -> None:
        self._invoke("reset_transport", {})

    def snapshot(self) -> dict[str, Any]:
        return self.model.snapshot()

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps({"format": FORMAT, "synthetic": True,
                                      "initial_config": self.initial_config, "events": self.events}, allow_nan=False))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False)+"\n", encoding="utf-8")


def replay_recording(data: dict[str, Any], *, max_events: int | None = 100000) -> dict[str, Any]:
    """Recreate a synthetic session and compare every RX byte and checkpoint.

    Only fixed model operations are allowed. Malformed schemas raise ValueError;
    a well-formed recording with changed expectations returns FAIL diagnostics.
    No timestamps are interpreted as wall-clock delays.
    """
    if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("synthetic") is not True:
        raise ValueError("unsupported synthetic recording format")
    if not isinstance(data.get("initial_config"), dict) or not isinstance(data.get("events"), list):
        raise ValueError("recording requires initial_config and events")
    if max_events is not None and (type(max_events) is not int or max_events <= 0):
        raise ValueError("max_events must be a positive integer or None")
    if max_events is not None and len(data["events"]) > max_events:
        raise ValueError(f"recording exceeds {max_events} events")
    session = RecordingSession(_config(data["initial_config"]), max_events=max_events)
    mismatches = []
    for number, event in enumerate(data["events"]):
        if not isinstance(event, dict) or not isinstance(event.get("operation"), str) or event["operation"] not in OPS or not isinstance(event.get("input"), dict):
            raise ValueError(f"invalid recording event {number}")
        if not isinstance(event.get("rx_hex"), list) or not isinstance(event.get("checkpoint"), dict):
            raise ValueError(f"event {number} requires rx_hex and checkpoint")
        try:
            session._invoke(event["operation"], event["input"])
        except (TypeError, KeyError) as exc:
            raise ValueError(f"invalid input for event {number}") from exc
        actual = session.events[-1]
        for field in ("rx_hex", "checkpoint"):
            if event[field] != actual[field]:
                mismatches.append({"event": number, "field": field})
    return {"synthetic": True, "PASS": not mismatches, "status": "PASS" if not mismatches else "FAIL",
            "events": len(session.events), "matched": len(session.events)-len({item["event"] for item in mismatches}),
            "mismatches": mismatches, "final_state": session.snapshot()}


def demo_recording() -> RecordingSession:
    from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Direction, Operation, encode_tx

    session = RecordingSession()
    session.set_sensors(weight=250, firmware_version=4924)
    session.sample()
    session.feed(encode_tx(Operation.STANDARD, speed=3, direction=Direction.CLOCKWISE))
    for _ in range(10):
        session.advance(100)
        session.sample()
    session.feed(encode_tx(Operation.STOP))
    for _ in range(5):
        session.advance(100)
        session.sample()
    session.set_sensors(error_code=5)
    session.sample()
    return session
