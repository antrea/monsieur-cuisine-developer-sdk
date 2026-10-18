"""Recorded OEM-reference comparisons, independent of Digital Twin physics.

Comparing a supplied dataset proves agreement with those bytes. The dataset's
origin needs separate evidence; this module never labels user input OEM-verified.
"""
from collections import Counter
import json
from pathlib import Path

from .profiles.mcc import oem_policy
from .profiles.mcc.protocol.codec import (Direction, FrameError, Operation, TxFrame,
    actual_speed_level, decode_frame, encode_tx, encode_calibration)

OPERATIONS = {"MOTOR_ON_HEATER_ON": Operation.STANDARD, "MOTOR_OFF_HEATER_OFF": Operation.STOP,
              "MOTOR_OFF_HEATER_ON": Operation.STANDARD, "MOTOR_ON_HEATER_OFF_TURBO_MODE": Operation.TURBO,
              "STEAM": Operation.STEAM, "TOAST": Operation.TOAST, "KNEAD": Operation.KNEAD, "SLEEP": Operation.SLEEP}
DIRECTIONS = {"CLOCKWISE": Direction.CLOCKWISE, "COUNTER_CLOCKWISE": Direction.COUNTER_CLOCKWISE}
ERRORS = {1: "SERIAL_PORT_COMMUNICATION", 3: "POWER_INPUT_OVERVOLTAGE", 4: "POWER_INPUT_UNDERVOLTAGE", 5: "MOTOR",
          6: "NO_WATER", 7: "MOTOR_OVERHEAT", 8: "MAX_RUNTIME_EXCEEDED"}
MOTOR_HEATER = {0: "MOTOR_OFF_HEATER_OFF", 1: "MOTOR_ON_HEATER_ON", 2: "MOTOR_OFF_HEATER_ON",
                3: "MOTOR_ON_HEATER_OFF_TURBO_MODE"}
EXTENDED = {3: "STEAM", 4: "TOAST", 5: "KNEAD"}
CALIBRATION = {0: "INITIALIZING", 1: "ZERO_POINT", 2: "FIRST_LOAD_1_KG", 3: "SECOND_LOAD_3_KG", 4: "SUCCESS",
               5: "OVERLOAD", 7: "FAILURE"}


def compare_tx(v):
    oem = bytes.fromhex(v["frame"])
    decoded = decode_frame(oem)  # every OEM frame must be structurally valid for the SDK
    problems = []
    if not isinstance(decoded, TxFrame):
        return ["OEM TX frame decoded as RX"]
    if v["calibration"] != "EXIT":
        command = "enter" if v["calibration"] == "ENTER" else "start"
        if encode_calibration(command) != oem:
            problems.append("calibration serialization differs")
        expected = 0xE6 if v["calibration"] == "ENTER" else 0xE9
        if decoded.calibration != expected or any(oem[3:12]):
            problems.append("calibration frame layout differs")
        return problems
    in_range = 0 <= v["speed"] <= 10 and 0 <= v["level"] <= 19
    kwargs = dict(speed=v["speed"], temperature_level=v["level"], direction=DIRECTIONS[v["direction"]],
                  tare=v["tare"])
    if in_range:
        sdk = encode_tx(OPERATIONS[v["command"]], **kwargs)
        if sdk != oem:
            problems.append(f"encode differs: sdk {sdk.hex()} oem {oem.hex()}")
    else:
        try:
            encode_tx(OPERATIONS[v["command"]], **kwargs)
            problems.append("SDK accepted an out-of-range value the OEM serializer replaces with 0")
        except FrameError:
            pass
        # Documented difference: the OEM substitutes 0; the SDK decoder must read that 0 back.
        if decoded.speed_level != (v["speed"] if 0 <= v["speed"] <= 10 else 0):
            problems.append("substituted speed not decoded as 0")
        if decoded.temperature_level != (v["level"] if 0 <= v["level"] <= 19 else 0):
            problems.append("substituted level not decoded as 0")
    return problems


def compare_rx(v):
    raw = bytes.fromhex(v["frame"])
    try:
        f = decode_frame(raw)
    except FrameError:
        return [] if not v["valid"] else ["SDK rejected a frame the OEM accepts"]
    if not v["valid"]:
        return ["SDK accepted a frame the OEM rejects"]
    expected = {
        "stable": f.scale_stable, "actual_rpm": f.actual_rpm, "actual_level": f.actual_speed_level,
        "actual_temperature": f.actual_temperature, "error": ERRORS.get(f.error_code, "UNDEFINED"),
        "firmware": f.firmware_version, "extended": EXTENDED.get(f.extended_state, "UNDEFINED"),
        "motor_heater": MOTOR_HEATER[f.motor_heater_state], "not_available": f.unknown_byte_24_signed,
        "calibration_step": CALIBRATION.get(f.calibration_step, "NOT_AVAILABLE"),
        "scale_state": f.android_scale_state.upper(), "weight": f.weight, "target_rpm": f.target_rpm,
        "target_level": f.target_speed_level_signed, "target_temperature": f.target_temperature,
        "target_temperature_level": f.target_temperature_level_signed, "lid_open": f.lid_open,
        "above_target": f.above_target_temperature, "ntc": f.bowl_ntc_detected,
        "error_detected": f.error_detected, "clockwise": f.direction == Direction.CLOCKWISE,
    }
    return [f"{k}: sdk {expected[k]!r} oem {v[k]!r}" for k in expected if expected[k] != v[k]]


def compare(v):
    kind = v["kind"]
    if kind == "tx":
        return compare_tx(v)
    if kind == "rx":
        return compare_rx(v)
    if kind == "celsius":
        out = []
        if oem_policy.recipe_temperature_level(v["celsius"]) != v["level"]:
            out.append("recipe level differs")
        if oem_policy.knob_temperature_level(v["celsius"]) != v["knob_step"]:
            out.append("knob level differs")
        return out
    if kind == "level":
        out = []
        if oem_policy.recipe_level_celsius(v["level"]) != v["celsius"]:
            out.append("recipe celsius differs")
        if oem_policy.knob_level_celsius(v["level"]) != v["knob_celsius"]:
            out.append("knob celsius differs")
        return out
    if kind == "time_limit":
        return [] if oem_policy.max_time_ms(v["speed"]) == v["ms"] else ["time limit differs"]
    if kind == "rpm_level":
        # The generator wrote the RPM into the two big-endian RX bytes, so negative inputs reach the
        # OEM getter as their unsigned 16-bit wire value.
        return [] if actual_speed_level(v["rpm"] & 0xFFFF) == v["level"] else ["rpm bin differs"]
    return [f"unknown vector kind {kind}"]


def compare_reference(path, *, max_vectors=100000, cancelled=None):
    """Stream and compare a bounded JSONL dataset; never import OEM executable code."""
    path = Path(path)
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError("reference dataset exceeds 64 MiB")
    counts = Counter()
    failures = []
    disagreements = 0
    with path.open("r", encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if cancelled and cancelled():
                raise InterruptedError("comparison cancelled")
            if number > max_vectors or len(line) > 32768:
                raise ValueError("reference dataset exceeds comparison bounds")
            if not line.strip():
                continue
            vector = json.loads(line)
            problems = compare(vector)
            counts[vector["kind"]] += 1
            disagreements += len(problems)
            if problems and len(failures) < 100:
                failures.append({"line": number, "kind": vector["kind"], "problems": problems})
    if not counts:
        raise ValueError("reference dataset is empty")
    return {"matched": disagreements == 0, "vectors": sum(counts.values()), "kinds": dict(counts),
            "disagreements": disagreements, "examples": failures,
            "evidence": "recorded-reference comparison; dataset provenance requires separate evidence",
            "hardware_verified": False}
