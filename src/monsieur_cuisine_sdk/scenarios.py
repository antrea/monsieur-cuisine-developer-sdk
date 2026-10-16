"""Small bounded shared scenarios; protocol/model behavior stays profile-specific."""
import random
from .api import DigitalTwin, DeviceModel, replay

SCENARIOS = ("start_stop", "directions", "reversal", "intermittent", "wait_stop", "partial_corrupt",
             "stale", "disconnect", "response_loss", "lid", "error", "stop_phases", "late_timer",
             "interrupted", "thermal", "link_faults")


def run_scenario(model, name="start_stop", *, seed=292, cancelled=None):
    if name not in SCENARIOS:
        raise ValueError("unknown scenario; choose " + ", ".join(SCENARIOS))
    twin = DigitalTwin(model, seed=seed)
    checks = {}
    def tick(seconds=.05):
        if cancelled and cancelled():
            raise ValueError("scenario cancelled")
        twin.advance(seconds); twin.sample()
    def stopped():
        for _ in range(200):
            if twin.get_state().actual_speed == 0:
                return True
            tick()
        return False
    if name in ("start_stop", "wait_stop", "intermittent"):
        cycles = 3 if name == "intermittent" else 2 if name == "wait_stop" else 1
        for cycle in range(cycles):
            checks[f"cycle_{cycle}_begins_at_zero"] = twin.get_state().actual_speed == 0
            twin.start_motor(2, "ccw"); tick(.2)
            checks["motion"] = twin.get_state().actual_speed > 0
            twin.stop_motor()
            checks["finite_braking"] = twin.get_state().actual_speed > 0
            checks["waited_for_zero"] = stopped()
            for key in ("motion", "finite_braking", "waited_for_zero"):
                checks[f"cycle_{cycle}_{key}"] = checks[key]
            tick(.1)
    elif name in ("directions", "reversal"):
        twin.start_motor(3, "cw"); tick(1)
        twin.start_motor(2, "ccw"); tick(.01)
        checks["initial_old_direction"] = twin.get_state().actual_direction == "cw"
        tick(2)
        checks["new_direction"] = twin.get_state().actual_direction == "ccw"
        twin.stop_motor(); checks["stopped"] = stopped()
    elif name == "stale":
        raw = twin.profile.encode_start(2, "ccw", 0, 0)
        twin.feed(raw[:7]); twin.disarm(); twin.feed(raw[7:])
        checks["old_tail_cannot_complete_command"] = twin.command_count == 0
        checks["old_tail_cannot_start_motor"] = twin.get_state().requested_speed == 0
        # A stale tail can itself end in AA, an ambiguous partial MCS header.
        # A new transport session clears that remainder before fresh commands;
        # guessing a nested local command would weaken foreign-frame isolation.
        twin.disarm()
        twin.feed(raw)
        checks["separate_new_command_works"] = twin.get_state().requested_speed == 2
        twin.stop_motor(); checks["stopped"] = stopped()
    elif name == "partial_corrupt":
        raw = twin.profile.encode_start(2, "ccw", 0, 0)
        twin.feed(raw[:7]); checks["no_partial_actuation"] = twin.get_state().requested_speed == 0
        twin.feed(raw[7:]); checks["completed_command"] = twin.get_state().requested_speed == 2
        changed = bytearray(raw); changed[-2 if twin.model == DeviceModel.MCC else -1] ^= 1
        twin.feed(changed); checks["corruption_diagnosed"] = twin.stream.rejected > 0
        twin.disarm(); checks["transport_cleared"] = twin.buffered_bytes == 0
    elif name in ("disconnect", "interrupted"):
        twin.start_motor(2); tick(.2); twin.disarm()
        checks["disarmed"] = twin.get_state().requested_speed == 0
        tick(2); checks["no_restart"] = twin.get_state().actual_speed == 0
    elif name in ("response_loss", "link_faults"):
        twin.set_faults(drop_next=1)
        checks["response_lost"] = twin.start_motor(2) == []
        checks["command_applied"] = twin.get_state().requested_speed == 2
        twin.set_faults(delay_seconds=.2, corrupt_next=1)
        checks["delayed"] = twin.sample() == []
        tick(.3); twin.set_faults(); twin.disarm()
    elif name in ("lid", "error"):
        twin.start_motor(2); tick(.2)
        twin.set_sensors(**({"lid_open": True} if name == "lid" else {"error_code": 3}))
        state = twin.get_state()
        checks["injected_state"] = state.lid_open if name == "lid" else state.error_code == 3
        # Common test application requests STOP explicitly; no shared MCU interlock invented.
        twin.stop_motor(); checks["stopped"] = stopped()
    elif name == "thermal":
        twin.start_motor(1, temperature=60); before = twin.get_state().temperature
        tick(2); checks["heating"] = twin.get_state().temperature > before
        twin.set_sensors(weight=-123); checks["signed_weight"] = twin.get_state().weight == -123
        twin.tare(); checks["tare"] = twin.get_state().weight == 0
        twin.stop_motor()
    elif name == "stop_phases":
        for phase in ("idle", "accelerating", "cruising", "braking", "reversing", "lid", "error"):
            twin.set_sensors(lid_open=False, error_code=0)
            if phase != "idle":
                twin.start_motor(3, "cw"); tick(3 if phase == "cruising" else .1)
            if phase == "braking":
                twin.stop_motor(); tick(.01)
            elif phase == "reversing":
                twin.start_motor(3, "ccw"); tick(.005)
            elif phase in ("lid", "error"):
                twin.set_sensors(**({"lid_open": True} if phase == "lid" else {"error_code": 3}))
            twin.stop_motor()
            checks[f"{phase}_target_removed"] = twin.get_state().requested_speed == 0
            checks[f"{phase}_stopped"] = stopped()
            tick(.3)
            state = twin.get_state()
            checks[f"{phase}_no_restart"] = state.requested_speed == 0 and state.actual_speed == 0
    elif name == "late_timer":
        if twin.model == DeviceModel.MCS:
            twin.start_motor(3, duration=1); tick(1.2)
            checks["native_timer_expired"] = twin.get_state().requested_speed == 0
            checks["expired_motor_stopped"] = stopped()
            twin.start_motor(2, duration=1); tick(.1); twin.stop_motor(); stopped()
            tick(2)
            state = twin.get_state()
            checks["stop_before_deadline_no_restart"] = state.requested_speed == 0 and state.actual_speed == 0
        else:
            try:twin.start_motor(2, duration=1)
            except ValueError:checks["unsupported_wire_timer_rejected"] = True
            else:checks["unsupported_wire_timer_rejected"] = False
            twin.start_motor(3); tick(.1); twin.stop_motor(); stopped(); tick(2)
            state = twin.get_state()
            checks["late_clock_no_restart"] = state.requested_speed == 0 and state.actual_speed == 0
    else:
        raise AssertionError("declared scenario has no implementation")
    result = replay(twin.recording)
    checks["deterministic_replay"] = result.get_state() == twin.get_state()
    return {"PASS": all(checks.values()), "model": twin.model.value, "name": name, "seed": seed,
            "synthetic": True, "checks": checks, "final_state": twin.get_state().to_dict(),
            "recording": twin.recording}


def run_stress(model, count=1000, *, seed=292):
    if type(count) is not int or not 1 <= count <= 10000 or type(seed) is not int:
        raise ValueError("count must be1..10000 and seed integer")
    failures = []
    for case in range(count):
        rng = random.Random(seed + case*1000003)
        twin = DigitalTwin(model, seed=seed+case, record=False)
        try:
            for _ in range(24):
                action = rng.randrange(6)
                if action < 2:
                    twin.start_motor(rng.randrange(5), rng.choice(("cw", "ccw")))
                elif action == 2:
                    twin.stop_motor()
                elif action == 3:
                    twin.set_sensors(weight=rng.randrange(-5000, 5000))
                elif action == 4:
                    twin.sample()
                else:
                    twin.set_faults(drop_next=rng.randrange(2), corrupt_next=rng.randrange(2))
                twin.advance(rng.randrange(10)/50)
                state = twin.get_state()
                assert state.actual_speed >= 0
                assert (state.actual_rpm is None) == (twin.model == DeviceModel.MCS)
            twin.disarm(); twin.advance(10)
            assert twin.get_state().actual_speed == 0
        except Exception as exc:
            failures.append({"case": case, "error": str(exc)})
    return {"PASS": not failures, "model": DeviceModel(model).value, "count": count,
            "seed": seed, "events": count*48, "passed": count-len(failures), "failures": failures}
