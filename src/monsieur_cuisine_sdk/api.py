"""Shared lifecycle, deterministic recording and bounded response faults.

The codecs and physical hypotheses remain independent profile implementations.
This module uses no sockets, Tk, wall clock, threads or real-device transport.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass, asdict
from enum import Enum
import heapq
import json
import math
from pathlib import Path
import threading

from .framing import SelectedStream


class DeviceModel(str, Enum):
    MCC = "mcc"
    MCS = "mcs"


class OwnershipError(ValueError):
    pass


class RecordingLimitError(ValueError):
    pass


@dataclass(frozen=True)
class TwinState:
    model: str
    generation: int
    time: float
    requested_speed: float
    actual_speed: float
    target_speed: float
    speed_unit: str
    actual_rpm: int | None
    requested_direction: str
    actual_direction: str
    target_temperature: float
    temperature: float
    weight: float
    lid_open: bool
    ntc_present: bool
    error_code: int
    firmware: int
    motor_on: bool
    heater_on: bool
    owner: str
    synthetic: bool
    raw: dict

    def to_dict(self):
        return asdict(self)


def _seconds_ns(seconds, *, maximum=3600):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= maximum:
        raise ValueError(f"seconds must be finite, nonnegative and <= {maximum}")
    return round(seconds * 1_000_000_000)


def _profile(model, seed, parameters):
    if model == DeviceModel.MCC:
        from .profiles.mcc.profile import MCCProfile
        return MCCProfile(seed=seed, parameters=parameters)
    from .profiles.mcs.profile import MCSProfile
    return MCSProfile(seed=seed, parameters=parameters)


class DigitalTwin:
    """One owner-thread session with an explicit device profile.

    High-level speed is a model-specific UI level, never a cross-model physical
    equivalence. Temperature is an exact supported Celsius target. Network and
    GUI adapters are opt-in and share this instance.
    """
    def __init__(self, model: DeviceModel | str, *, seed: int = 292,
                 parameters: dict | None = None, record: bool = True,
                 max_actions: int = 100000, max_pending_bytes: int = 65536,
                 on_recording_full: str = "stop"):
        self.model = DeviceModel(model)
        if type(seed) is not int:
            raise ValueError("seed must be integer")
        if type(record) is not bool or type(max_actions) is not int or not 2 <= max_actions <= 100000:
            raise ValueError("record bool and max_actions 2..100000 required")
        if type(max_pending_bytes) is not int or not 269 <= max_pending_bytes <= 1048576:
            raise ValueError("max_pending_bytes must be 269..1048576")
        if on_recording_full not in ("stop", "continue"):
            raise ValueError("on_recording_full must be 'stop' or 'continue'")
        self.seed, self.max_actions, self.max_pending_bytes = seed, max_actions, max_pending_bytes
        # "stop": a full recording requests a synthetic STOP and ends the session
        # (scripted/CLI default). "continue": the recording is marked truncated
        # and the simulation keeps running unrecorded (interactive desktop).
        self.on_recording_full = on_recording_full
        self._thread = threading.get_ident()
        self.profile = _profile(self.model, seed, parameters)
        self.generation = 0
        self.now_ns = 0
        self._total_ns = self._total_ticks = 0
        self._owner = None
        self._delivering = False
        self._observers, self._switch_observers = [], []
        self.stream = SelectedStream(self.model.value)
        self._pending = []
        self._response_serial = 0
        self._pending_bytes = 0
        self._faults = {"delay_seconds": 0.0, "drop_next": 0, "corrupt_next": 0, "disconnected": False}
        self.overflow = False
        self.recording_full = False
        self._recorded_bytes = 0
        self.command_count = 0
        self.record_enabled = record
        self.timeline = deque(maxlen=1000)
        self.frames = deque(maxlen=400)
        self.history = deque(maxlen=600)
        self.recording = {"schema": "monsieur-cuisine-recording-v1", "model": self.model.value,
                          "seed": seed, "parameters": deepcopy(self.profile.parameters),
                          "max_actions": max_actions, "max_pending_bytes": max_pending_bytes,
                          "synthetic": True, "actions": []}
        self._point()

    def _check_thread(self, *, mutating=True):
        if threading.get_ident() != self._thread:
            raise RuntimeError("model mutations require its creating owner thread")
        if mutating and self._delivering:
            raise ValueError("RX observers may inspect state but must defer model mutations to the owner loop")

    def _check_owner(self, owner=None):
        self._check_thread()
        if self._owner is not owner:
            raise OwnershipError("remote client owns commands; disconnect or use desktop STOP")

    @property
    def capabilities(self):
        return deepcopy(self.profile.capabilities)

    @property
    def buffered_bytes(self):
        return len(self.stream.buffer)

    @property
    def owner(self):
        return "remote" if self._owner is not None else "local"

    def claim(self, owner):
        self._check_thread()
        if owner is None or self._owner not in (None, owner):
            raise OwnershipError("another client owns commands")
        self._owner = owner

    def release(self, owner):
        self._check_thread()
        if self._owner is not owner:
            raise OwnershipError("ownership mismatch")
        self._owner = None

    def subscribe_rx(self, callback):
        self._check_thread()
        self._observers.append(callback)
        return lambda: self._observers.remove(callback) if callback in self._observers else None

    def before_switch(self, callback):
        self._check_thread()
        self._switch_observers.append(callback)
        return lambda: self._switch_observers.remove(callback) if callback in self._switch_observers else None

    def get_state(self) -> TwinState:
        self._check_thread(mutating=False)
        state = deepcopy(self.profile.state())
        state.setdefault("target_speed", 0)
        return TwinState(model=self.model.value, generation=self.generation,
                         time=self.now_ns / 1e9, owner=self.owner, synthetic=True,
                         **{name: state[name] for name in TwinState.__dataclass_fields__
                            if name not in {"model", "generation", "time", "owner", "synthetic"}})

    def _point(self):
        s = self.get_state()
        self.history.append({"time": s.time, "actual": s.actual_speed, "target": s.target_speed,
                             "temperature": s.temperature, "unit": s.speed_unit})

    def _checkpoint(self):
        # Owner and listener are external lifecycle metadata, never wire fields.
        state = self.get_state().to_dict()
        state.pop("owner")
        return {"state": state, "input_hex": bytes(self.stream.buffer).hex(),
                "quarantine_remaining": self.stream.discard_remaining,
                "faults": deepcopy(self._faults), "response_serial": self._response_serial,
                "pending": [[due, serial, raw.hex()] for due, serial, raw in sorted(self._pending)],
                "overflow": self.overflow}

    def _record(self, operation, arguments, frames):
        if not self.record_enabled:
            return
        event = {"operation": operation, "input": deepcopy(arguments),
                 "rx_hex": [f.hex() for f in frames], "checkpoint": self._checkpoint()}
        self._recorded_bytes += len(json.dumps(event, indent=2))
        self.recording["actions"].append(event)

    def _capacity(self):
        if self.recording_full:
            raise RecordingLimitError("recording ended at its capacity; create a new session to start again")
        if self.record_enabled and (len(self.recording["actions"]) >= self.max_actions - 1
                                    or self._recorded_bytes >= 32_000_000 - 524288):
            if self.on_recording_full == "continue":
                self.record_enabled = False
                self.recording["truncated"] = True
                self.recording["ended"] = "capacity: recording truncated; simulation continued unrecorded"
                self.timeline.append({"event": "recording_truncated", "generation": self.generation})
                return
            self._disarm_impl()
            self._record("recording_limit_stop", {}, [])
            self.recording["ended"] = "capacity: synthetic STOP requested before rejected operation"
            self.record_enabled = False
            self.recording_full = True
            raise RecordingLimitError("recording capacity reached; STOP requested, save and create a new session")

    def _route(self, frames):
        for frame in frames:
            if self._faults["disconnected"]:
                continue
            self._response_serial += 1
            if self._faults["drop_next"]:
                self._faults["drop_next"] -= 1; continue
            raw = bytes(frame)
            if self._faults["corrupt_next"]:
                self._faults["corrupt_next"] -= 1
                position = -2 if self.model == DeviceModel.MCC else -1
                changed = bytearray(raw); changed[position] ^= 1; raw = bytes(changed)
            if self._pending_bytes + len(raw) > self.max_pending_bytes:
                self.overflow = True
                self._pending.clear(); self._pending_bytes = 0
                self.profile.stop()
                self.timeline.append({"event": "response_overflow", "generation": self.generation})
                break
            due = self.now_ns + round(self._faults["delay_seconds"] * 1e9)
            heapq.heappush(self._pending, (due, self._response_serial, raw))
            self._pending_bytes += len(raw)
        return self._drain()

    def _drain(self):
        frames = []
        while self._pending and self._pending[0][0] <= self.now_ns:
            _, _, raw = heapq.heappop(self._pending)
            self._pending_bytes -= len(raw)
            frames.append(raw)
            self.frames.append({"direction": "RX", "hex": raw.hex(" ").upper(),
                                "time": self.now_ns / 1e9, "model": self.model.value})
            generation = self.generation
            self._delivering = True
            try:
                for callback in tuple(self._observers):
                    try:
                        callback(raw, generation)
                    except Exception as exc:
                        self.timeline.append({"event": "observer_error", "reason": str(exc), "generation": generation})
            finally:
                self._delivering = False
        return frames

    def feed(self, raw: bytes, *, owner=None) -> list[bytes]:
        self._check_owner(owner); self._capacity()
        if not isinstance(raw, (bytes, bytearray, memoryview)) or len(raw) > 65536:
            raise ValueError("TX chunk must be bytes and <=65536 bytes")
        raw = bytes(raw)
        replies = []
        if not self._faults["disconnected"]:
            for frame in self.stream.feed(raw):
                try:
                    replies.extend(self.profile.feed_frame(frame))
                    self.command_count += 1
                except ValueError as exc:
                    self.timeline.append({"event": "rejected_command", "reason": str(exc)})
        self.frames.append({"direction": "TX", "hex": raw.hex(" ").upper(),
                            "time": self.now_ns / 1e9, "model": self.model.value})
        result = self._route(replies)
        self._point(); self._record("feed", {"hex": raw.hex()}, result)
        return result

    def start_motor(self, speed: int = 2, direction: str = "ccw", temperature: int = 0,
                    duration: int = 0, *, owner=None):
        self._check_owner(owner)
        raw = self.profile.encode_start(speed, direction, temperature, duration)
        return self.feed(raw, owner=owner)

    def stop_motor(self, *, owner=None):
        self._check_owner(owner)
        if self.recording_full:
            self._disarm_impl(); return []
        try:
            return self.feed(self.profile.encode_stop(), owner=owner)
        except RecordingLimitError:
            # The reserved terminal recording event has already requested STOP.
            return []

    def set_temperature(self, celsius: int, *, owner=None):
        """Reissue the current command with a new exact Celsius target.

        The running operation/program, speed, direction and (MCS) remaining
        countdown are preserved by the selected profile's own encoder.
        """
        self._check_owner(owner)
        return self.feed(self.profile.encode_temperature(celsius), owner=owner)

    def tare(self, *, owner=None):
        self._check_owner(owner)
        return self.feed(self.profile.encode_tare(), owner=owner)

    def advance(self, seconds: float):
        self._check_thread()
        delta = _seconds_ns(seconds)
        if not self.recording_full:
            self._capacity()
        if self._total_ns + delta > 86400 * 10**9:
            raise ValueError("one session virtual-time budget is 24 hours")
        tick_ns = round(self.profile.parameters.get("tick_seconds", 0.02) * 1e9)
        ticks = ((self.now_ns + delta)//tick_ns - self.now_ns//tick_ns) if self.model == DeviceModel.MCS else 0
        if self._total_ticks + ticks > 1_000_000:
            raise ValueError("session physics-work budget exceeded; create a new session")
        self.profile.advance_ns(delta)
        self._total_ns += delta
        self._total_ticks += ticks
        self.now_ns += delta
        result = self._drain()
        self._point(); self._record("advance", {"seconds": delta/1e9}, result)
        return self.get_state()

    def sample(self):
        self._check_thread()
        if not self.recording_full:
            self._capacity()
        result = self._route(self.profile.sample())
        self._record("sample", {}, result)
        return result

    def receive_ready(self):
        self._check_thread()
        if not self.recording_full:
            self._capacity()
        result = self._drain()
        self._record("receive_ready", {}, result)
        return result

    def set_sensors(self, **values):
        self._check_thread(); self._capacity()
        self.profile.set_sensors(**values)
        result = self._route(self.profile.sample())
        self._point(); self._record("set_sensors", values, result)
        return self.get_state()

    def set_faults(self, *, delay_seconds=0.0, drop_next=0, corrupt_next=0, disconnected=False):
        self._check_thread(); self._capacity()
        _seconds_ns(delay_seconds)
        if any(type(v) is not int or not 0 <= v <= 100000 for v in (drop_next, corrupt_next)):
            raise ValueError("fault counts must be integers 0..100000")
        if type(disconnected) is not bool:
            raise ValueError("disconnected must be bool")
        changes = dict(delay_seconds=float(delay_seconds), drop_next=drop_next,
                       corrupt_next=corrupt_next, disconnected=disconnected)
        if disconnected != self._faults["disconnected"]:
            self.stream.reset(); self.profile.reset_transport()
            self._pending.clear(); self._pending_bytes = 0
        self._faults = changes
        self._record("set_faults", changes, [])

    def _disarm_impl(self):
        self.profile.stop()
        self.stream.reset()
        self.profile.reset_transport()
        self._pending.clear(); self._pending_bytes = 0
        self.overflow = False

    def disarm(self):
        self._check_thread()
        if self.record_enabled:
            try:
                self._capacity()
            except RecordingLimitError:
                self._point(); return
        self._disarm_impl()
        self._record("disarm", {}, [])
        self._point()

    def switch_model(self, model: DeviceModel | str, *, parameters=None):
        self._check_thread()
        if self.recording_full:
            return self.new_session(model, parameters=parameters)
        selected = DeviceModel(model)
        candidate = _profile(selected, self.seed, parameters)
        try:
            self._capacity()
        except RecordingLimitError:
            return self.new_session(selected, parameters=parameters)
        for callback in tuple(self._switch_observers):
            callback()
        self._disarm_impl()
        self._owner = None
        self.profile, self.model = candidate, selected
        self.generation += 1
        self.now_ns = 0
        self.stream = SelectedStream(selected.value)
        self._faults = dict(delay_seconds=0.0, drop_next=0, corrupt_next=0, disconnected=False)
        self._response_serial = 0
        self.command_count = 0
        self.history.clear(); self._point()
        self._record("switch_model", {"model": selected.value, "parameters": deepcopy(candidate.parameters)}, [])
        return self.get_state()

    def new_session(self, model: DeviceModel | str | None = None, *, parameters=None):
        """Explicit fresh session; retain the completed trace as last_recording."""
        self._check_thread()
        selected = self.model if model is None else DeviceModel(model)
        # Validate the next profile before disconnecting the current session.
        _profile(selected, self.seed, parameters)
        for callback in tuple(self._switch_observers):
            callback()
        self._disarm_impl()
        old_recording, generation = self.recording, self.generation + 1
        observers, hooks = self._observers, self._switch_observers
        seed, actions, pending = self.seed, self.max_actions, self.max_pending_bytes
        policy = self.on_recording_full
        self.__init__(selected, seed=seed, parameters=parameters, max_actions=actions, max_pending_bytes=pending,
                      on_recording_full=policy)
        self.generation = generation
        self.recording["initial_generation"] = generation
        self._observers, self._switch_observers = observers, hooks
        self.last_recording = old_recording
        return self.get_state()

    def save(self, path: str | Path):
        self._check_thread()
        Path(path).write_text(json.dumps(self.recording, indent=2), encoding="utf-8")


def replay(recording: dict | str | Path, *, cancelled=None) -> DigitalTwin:
    """Validate and replay local data; no socket/file callbacks are evaluated."""
    if isinstance(recording, (str, Path)):
        path = Path(recording)
        if path.stat().st_size > 100_000_000:
            raise ValueError("recording file exceeds 100MB")
        recording = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(recording, dict) or recording.get("schema") != "monsieur-cuisine-recording-v1":
        raise ValueError("unsupported recording schema")
    actions = recording.get("actions")
    if not isinstance(actions, list) or len(actions) > 100000:
        raise ValueError("recording actions must be a list of at most100000")
    known = {"feed", "advance", "sample", "receive_ready", "set_sensors", "set_faults", "disarm", "switch_model", "recording_limit_stop"}
    total_ns = 0
    total_ticks = 0
    selected = DeviceModel(recording["model"])
    parameters = recording.get("parameters", {})
    profile_ns = 0
    for event in actions:
        if not isinstance(event, dict) or event.get("operation") not in known or not isinstance(event.get("input"), dict):
            raise ValueError("invalid recording operation")
        if event["operation"] == "advance":
            interval = _seconds_ns(event["input"].get("seconds"))
            total_ns += interval
            if selected == DeviceModel.MCS:
                tick = parameters.get("tick_seconds", 0.02)
                if type(tick) not in (int, float) or not math.isfinite(tick) or not 0.001 <= tick <= 1:
                    raise ValueError("invalid MCS replay tick")
                tick_ns = round(tick * 1e9)
                total_ticks += (profile_ns+interval)//tick_ns-profile_ns//tick_ns
            profile_ns += interval
        elif event["operation"] == "switch_model":
            selected = DeviceModel(event["input"].get("model"))
            parameters = event["input"].get("parameters", {})
            profile_ns = 0
        if total_ns > 86400*10**9:
            raise ValueError("recording total virtual-time budget exceeded")
        if total_ticks > 1_000_000:
            raise ValueError("recording physics-work budget exceeded")
    twin = DigitalTwin(recording["model"], seed=recording["seed"], parameters=recording["parameters"],
                       record=False, max_actions=recording["max_actions"], max_pending_bytes=recording["max_pending_bytes"])
    twin.generation = recording.get("initial_generation", 0)
    if type(twin.generation) is not int or twin.generation < 0:
        raise ValueError("invalid initial generation")
    # Validate every action's argument contract before executing any physics.
    # This dry session may encode/decode commands but never advances time.
    validator = DigitalTwin(recording["model"], seed=recording["seed"], parameters=recording["parameters"],
                            record=False, max_actions=recording["max_actions"], max_pending_bytes=recording["max_pending_bytes"])
    for event in actions:
        if not isinstance(event.get("rx_hex"), list) or not isinstance(event.get("checkpoint"), dict):
            raise ValueError("invalid recording result/checkpoint schema")
        for text in event["rx_hex"]:
            if not isinstance(text, str) or len(text)>131072:
                raise ValueError("invalid recorded response")
            bytes.fromhex(text)
        kind, args = event["operation"], deepcopy(event["input"])
        if kind == "advance":
            if set(args)!={"seconds"}:
                raise ValueError("invalid advance arguments")
        elif kind == "feed":
            if set(args)!={"hex"} or not isinstance(args["hex"],str) or len(args["hex"])>131072:
                raise ValueError("invalid recorded TX input")
            validator.feed(bytes.fromhex(args["hex"]))
        else:
            getattr(validator,"disarm" if kind=="recording_limit_stop" else kind)(**args)
    for index, event in enumerate(actions):
        if cancelled is not None and cancelled():
            raise ValueError("replay cancelled")
        operation, arguments = event["operation"], deepcopy(event["input"])
        if operation == "feed":
            text = arguments.pop("hex")
            if not isinstance(text, str) or len(text) > 131072:
                raise ValueError("recorded TX chunk exceeds bound")
            frames = twin.feed(bytes.fromhex(text))
        elif operation in {"sample", "receive_ready"}:
            frames = getattr(twin, operation)(**arguments)
        elif operation == "advance":
            # Advance emits delayed RX to observers; capture for byte comparison.
            emitted = []
            unsub = twin.subscribe_rx(lambda raw, generation: emitted.append(raw))
            try:
                twin.advance(**arguments)
            finally:
                unsub()
            frames = emitted
        elif operation == "set_sensors":
            emitted = []
            unsub = twin.subscribe_rx(lambda raw, generation: emitted.append(raw))
            try:
                twin.set_sensors(**arguments)
            finally:
                unsub()
            frames = emitted
        else:
            getattr(twin, "disarm" if operation == "recording_limit_stop" else operation)(**arguments)
            frames = []
        if [f.hex() for f in frames] != event["rx_hex"] or twin._checkpoint() != event["checkpoint"]:
            raise ValueError(f"recording mismatch at action {index}: {operation}")
    return twin
