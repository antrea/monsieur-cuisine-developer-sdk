"""Reproducible headless scenarios and seeded stress experiments.

Passing means the synthetic model obeyed its software expectations. It never
means that controller firmware, physical interlocks, or motor safety were tested.
"""

from __future__ import annotations

import math
import random

from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import Direction, FrameError, Operation, decode_frame, encode_tx
from monsieur_cuisine_sdk.profiles.mcc.protocol.program import IntermittentConfig, IntermittentProgram, ProgramState

from .model import PhysicsConfig, PowerBoardModel


SCENARIOS = (
    "start_stop", "directions", "intermittent", "wait_stop", "partial_corrupt",
    "stale", "disconnect", "response_loss", "lid", "error", "stop_phases",
    "late_timer", "interrupted",
)


def _new(config: PhysicsConfig | None = None) -> PowerBoardModel:
    return PowerBoardModel(config or PhysicsConfig(acceleration_rpm_s=1000, deceleration_rpm_s=2000))


def _start(model: PowerBoardModel, *, speed: int = 1, direction: Direction = Direction.CLOCKWISE) -> list[bytes]:
    return model.feed(encode_tx(Operation.STANDARD, speed=speed, direction=direction))


def _commands(log: list[dict[str, object]], operation: Operation) -> int:
    return sum(entry.get("event") == "tx" and entry.get("operation") == operation for entry in log)


class _Session:
    """Serialized memory adapter: never reenter a program from its send hook."""

    def __init__(self, *, physics: PhysicsConfig | None = None) -> None:
        self.model = _new(physics)
        rates = self.model.config
        self.brake_ms = math.ceil(rates.speed_rpm[1] / rates.deceleration_rpm_s * 1000)
        self.spin_ms = max(200, math.ceil(rates.speed_rpm[1] / rates.acceleration_rpm_s * 1000))
        self.step_ms = max(25, math.ceil(max(self.brake_ms, self.spin_ms) / 20))
        self.rest_ms = max(150, self.step_ms * 2)
        self.total_ms = max(1600, 2 * (self.spin_ms + self.brake_ms + self.rest_ms) + self.spin_ms)
        self.pending: list[bytes] = []
        self.program = IntermittentProgram(
            IntermittentConfig(spin_ms=self.spin_ms, rest_ms=self.rest_ms, total_ms=self.total_ms,
                               speed=1, direction=Direction.CLOCKWISE,
                               max_sample_age_ms=max(200, self.step_ms * 2), stop_timeout_ms=max(400, self.brake_ms + self.step_ms * 2)),
            lambda raw: self.pending.extend(self.model.feed(raw)),
        )
        self.program.receive(self.model.sample()[0], 0)
        self.program.start(0)
        self.drain()

    def drain(self) -> None:
        while self.pending:
            batch, self.pending = self.pending, []
            for raw in batch:
                self.program.receive(raw, self.model.now_ms)

    def step(self, delta_ms: int | None = None, *, telemetry: bool = True, tick: bool = True) -> None:
        if delta_ms is None:
            delta_ms = self.step_ms
        self.pending.extend(self.model.advance(delta_ms))
        if telemetry:
            self.pending.extend(self.model.sample())
        self.drain()
        if tick:
            self.program.tick(self.model.now_ms)
            self.drain()


def _scenario(name: str, seed: int, config: PhysicsConfig | None) -> tuple[PowerBoardModel, dict[str, bool], dict[str, object]]:
    model = _new(config)
    details: dict[str, object] = {}
    if name == "start_stop":
        _start(model, speed=2)
        model.advance(max(1, math.floor(model.controller.target_rpm / model.config.acceleration_rpm_s * 500)))
        before = model.snapshot()["velocity_rpm"]
        model.feed(encode_tx())
        immediate = model.snapshot()["velocity_rpm"]
        duration = max(1, math.ceil(abs(before) / model.config.deceleration_rpm_s * 1000))
        model.advance(duration)
        checks = {"acceleration_is_finite": 0 < before <= model.config.speed_rpm[2],
                  "stop_is_not_instant": immediate == before and before > 0,
                  "finite_stop_interval": duration > 0,
                  "eventual_stop": model.controller.actual_rpm == 0}
    elif name == "directions":
        _start(model)
        model.advance(max(1, math.ceil(model.controller.target_rpm / model.config.acceleration_rpm_s * 1000)))
        magnitude = model.controller.target_rpm
        _start(model, direction=Direction.COUNTER_CLOCKWISE)
        old_direction = model.controller.direction
        model.advance(max(1, math.ceil(magnitude / model.config.deceleration_rpm_s * 1000)))
        zero = model.controller.actual_rpm
        model.advance(max(1, math.ceil(magnitude / model.config.acceleration_rpm_s * 500)))
        checks = {"moving_direction_retained": old_direction == Direction.CLOCKWISE,
                  "reversal_passes_zero": zero == 0 or any(item["event"] == "direction_zero_crossing" for item in model.log),
                  "opposite_acceleration": model.snapshot()["velocity_rpm"] < 0}
    elif name in ("intermittent", "wait_stop", "lid", "error", "stop_phases", "late_timer", "interrupted"):
        if name == "stop_phases":
            outcomes = {}
            for phase in (ProgramState.SPIN, ProgramState.WAIT_STOP, ProgramState.REST):
                session = _Session(physics=config)
                while session.program.state != phase:
                    session.step()
                session.program.stop(session.model.now_ms)
                session.drain()
                for _ in range(20):
                    session.step()
                outcomes[phase.value] = session.program.state == ProgramState.STOPPED and session.model.controller.actual_rpm == 0 and _commands(session.model.log, Operation.STANDARD) == 1
                model = session.model
            checks = outcomes
            details["phases_tested"] = list(outcomes)
        else:
            session = _Session(physics=config)
            model = session.model
            if name == "wait_stop":
                while session.program.state == ProgramState.SPIN:
                    session.step()
                waiting = session.program.state == ProgramState.WAIT_STOP and model.controller.actual_rpm > 0
                session.step(session.brake_ms + session.step_ms)
                checks = {"waits_for_deceleration": waiting,
                          "post_stop_zero_enters_rest": session.program.state == ProgramState.REST,
                          "one_start_only_before_rest": _commands(model.log, Operation.STANDARD) == 1}
            elif name in ("lid", "error"):
                field = "lid_open" if name == "lid" else "error_code"
                model.set_sensors(**{field: True if name == "lid" else 5})
                session.pending.extend(model.sample())
                session.drain()
                model.set_sensors(**{field: False if name == "lid" else 0})
                for _ in range(20):
                    session.step()
                checks = {"event_latched": session.program.state == ProgramState.FAULT,
                          "no_restart_after_clear": _commands(model.log, Operation.STANDARD) == 1,
                          "stop_decelerated": model.controller.actual_rpm == 0}
            elif name == "late_timer":
                # Fresh RX followed by a single late tick past the total time.
                session.step(session.total_ms + 100, tick=False)
                session.program.tick(model.now_ms)
                session.drain()
                model.advance(session.brake_ms + 1)
                checks = {"deadline_wins": session.program.state == ProgramState.FINISHED,
                          "no_catch_up_starts": _commands(model.log, Operation.STANDARD) == 1,
                          "stop_decelerated": model.controller.actual_rpm == 0}
            elif name == "interrupted":
                model.disconnect()
                session.step(session.program.config.max_sample_age_ms + 1, telemetry=False)
                model.reconnect()
                for _ in range(12):
                    session.step()
                checks = {"stale_link_fault_is_terminal": session.program.state == ProgramState.FAULT,
                          "no_automatic_restart": _commands(model.log, Operation.STANDARD) == 1,
                          "failed_stop_not_claimed": model.controller.target_rpm == model.config.speed_rpm[1]}
            else:
                while model.now_ms < session.total_ms:
                    session.step(min(session.step_ms, session.total_ms-model.now_ms))
                model.advance(session.brake_ms + 1)
                states = [entry.get("state") for entry in session.program.log if entry.get("event") == "state"]
                checks = {"finished_at_total_deadline": session.program.state == ProgramState.FINISHED,
                          "multiple_spins": _commands(model.log, Operation.STANDARD) >= 2,
                          "wait_and_rest_observed": "WAIT_STOP" in states and "REST" in states,
                          "final_physical_model_stopped": model.controller.actual_rpm == 0}
            details["program_log"] = session.program.log
    elif name == "partial_corrupt":
        command = encode_tx(Operation.STANDARD, speed=2)
        partial = model.feed(command[:6])
        initial_target = model.controller.target_rpm
        complete = model.feed(command[6:])
        damaged = bytearray(encode_tx())
        damaged[13] ^= 1
        recovered = model.feed(bytes(damaged) + encode_tx())
        checks = {"partial_does_not_actuate": not partial and initial_target == 0,
                  "complete_fragmented_tx_accepted": len(complete) == 1,
                  "corrupt_tx_does_not_block_recovery": len(recovered) == 1 and model.controller.target_rpm == 0,
                  "corruption_logged": any(entry["event"] == "parse_issue" for entry in model.log)}
    elif name == "stale":
        delay = random.Random(seed).randint(100, 200)
        model.set_faults(delay_ms=delay)
        _start(model)
        early = model.advance(delay - 1)
        late = model.advance(1)
        response = decode_frame(late[0])
        checks = {"response_delayed": not early and len(late) == 1,
                  "snapshot_can_be_stale": response.actual_rpm == 0 and model.snapshot()["velocity_rpm"] > 0,
                  "wire_has_no_timestamp": "received_ms" not in response.to_dict()}
    elif name == "disconnect":
        _start(model)
        model.advance(math.ceil(model.config.speed_rpm[1] / model.config.acceleration_rpm_s * 1000))
        model.disconnect()
        replies = model.feed(encode_tx())
        model.advance(100)
        target_during_loss = model.controller.target_rpm
        model.reconnect()
        model.feed(encode_tx())
        model.advance(math.ceil(model.config.speed_rpm[1] / model.config.deceleration_rpm_s * 1000))
        checks = {"disconnected_stop_not_delivered": not replies and target_during_loss == model.config.speed_rpm[1],
                  "explicit_stop_after_reconnect": model.controller.actual_rpm == 0,
                  "link_available_again": model.connected}
    elif name == "response_loss":
        model.set_faults(drop_every=2, corrupt_every=3)
        batches = [model.sample() for _ in range(6)]
        validity = []
        for batch in batches:
            if batch:
                try:
                    decode_frame(batch[0])
                    validity.append(True)
                except FrameError:
                    validity.append(False)
        checks = {"every_second_response_lost": [bool(batch) for batch in batches] == [True, False, True, False, True, False],
                  "corruption_is_detectable": validity == [True, False, True]}
    else:
        raise ValueError(f"unknown scenario: {name}")
    return model, checks, details


def run_scenario(name: str, *, seed: int = 292, config: PhysicsConfig | None = None) -> dict[str, object]:
    """Return a JSON-compatible scenario result, checks, timeline and snapshot."""
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario {name!r}; choose one of {', '.join(SCENARIOS)}")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if config is not None and not isinstance(config, PhysicsConfig):
        raise ValueError("config must be PhysicsConfig or None")
    model, checks, details = _scenario(name, seed, config)
    passed = all(checks.values())
    return {"synthetic": True, "name": name, "seed": seed, "PASS": passed,
            "passed": passed, "checks": checks, "log": model.log,
            "final_state": model.snapshot(), **details}


def _stress_case(case_seed: int) -> dict[str, object]:
    rng = random.Random(case_seed)
    config = PhysicsConfig(acceleration_rpm_s=rng.randint(300, 12000),
                           deceleration_rpm_s=rng.randint(400, 15000),
                           coast_deceleration_rpm_s=rng.randint(100, 3000),
                           heating_c_s=rng.uniform(0.1, 3), cooling_c_s=rng.uniform(0.05, 1))
    model = PowerBoardModel(config)
    valid_responses = corrupt_responses = 0
    for event in range(48):
        action = rng.randrange(8)
        replies = []
        if action < 3:
            replies = model.feed(encode_tx(Operation.STANDARD, speed=rng.randint(0, 10),
                                           direction=Direction(rng.randrange(2)), temperature_level=rng.randint(0, 19)))
        elif action == 3:
            replies = model.feed(encode_tx(Operation.STOP))
        elif action == 4:
            model.set_sensors(weight=rng.randint(-5000, 5000), lid_open=bool(rng.randrange(2)),
                              error_code=rng.choice((0, 1, 3, 4, 5, 6, 7, 8)))
        elif action == 5:
            model.set_faults(delay_ms=rng.randint(0, 100), drop_every=rng.choice((0, 3, 5)),
                             corrupt_every=rng.choice((0, 4, 7)), disconnected=rng.randrange(8) == 0)
        elif action == 6:
            replies = model.sample()
        else:
            command = encode_tx(Operation.STOP)
            pivot = rng.randint(1, len(command)-1)
            replies = model.feed(command[:pivot]) + model.feed(command[pivot:])
        for raw in replies + model.advance(rng.randint(0, 300)):
            try:
                decode_frame(raw)
                valid_responses += 1
            except FrameError:
                corrupt_responses += 1
        snapshot = model.snapshot()
        velocity = snapshot["velocity_rpm"]
        invariants = {
            "finite_velocity": isinstance(velocity, float) and math.isfinite(velocity),
            "velocity_in_wire_range": abs(velocity) <= 65535,
            "measured_rpm_matches_velocity": model.controller.actual_rpm == round(abs(velocity)),
            "temperature_in_wire_range": 0 <= model.controller.actual_temperature <= 65535,
            "requested_rpm_uses_configured_table": model.controller.target_rpm == config.speed_rpm[model.controller.requested_speed_level],
            "direction_matches_velocity": model.controller.direction == (Direction.CLOCKWISE if velocity > 0 else Direction.COUNTER_CLOCKWISE if velocity < 0 else Direction(snapshot["requested_direction"])),
        }
        failed = [name for name, passed in invariants.items() if not passed]
        if failed:
            raise AssertionError(f"event {event}: {', '.join(failed)}")
    model.reconnect()
    model.set_faults()
    model.feed(encode_tx())
    stopping_ms = math.ceil(abs(model.snapshot()["velocity_rpm"]) / config.deceleration_rpm_s * 1000) + 1
    model.advance(stopping_ms)
    if model.controller.actual_rpm != 0 or model.snapshot()["velocity_rpm"] != 0.0:
        raise AssertionError("final explicit STOP did not reach zero within its synthetic braking interval")
    return {"valid_responses": valid_responses, "corrupt_responses": corrupt_responses, "events": 48}


def run_stress(count: int = 1000, seed: int = 292) -> dict[str, object]:
    """Run distinct seeded event sequences and report compact failure details."""
    if type(count) is not int or count <= 0:
        raise ValueError("count must be a positive integer")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    failures: list[dict[str, object]] = []
    totals = {"events": 0, "valid_responses": 0, "corrupt_responses": 0}
    for index in range(count):
        case_seed = seed + index * 1000003
        try:
            result = _stress_case(case_seed)
            for key in totals:
                totals[key] += result[key]
        except Exception as exc:
            failures.append({"case": index, "case_seed": case_seed,
                             "error": type(exc).__name__, "message": str(exc)})
    return {"synthetic": True, "seed": seed, "count": count,
            "passed": count-len(failures), "failed": len(failures),
            "PASS": not failures, "failures": failures, **totals}
