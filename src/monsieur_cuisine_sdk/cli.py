"""Explicit-profile offline tools. No command opens a physical device or socket."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, is_dataclass
from importlib import resources
import json
from pathlib import Path
import sys

from . import __version__

MAX_INPUT_BYTES = 100_000_000
MAX_FRAMES = 100_000


def _read(path: Path) -> str:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("input exceeds 100 MB")
    return path.read_text(encoding="utf-8-sig")


def _json(path: Path):
    return json.loads(_read(path))


def _object(text: str) -> dict:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("--params must be a JSON object")
    return value


def _profile(model: str, seed=292):
    if model == "mcc":
        from .profiles.mcc import MCCProfile
        return MCCProfile(seed=seed)
    from .profiles.mcs.profile import MCSProfile
    return MCSProfile(seed=seed)


def _decode(model: str, raw: bytes, direction: str):
    if model == "mcc":
        from .profiles.mcc.protocol.codec import decode_frame
        return decode_frame(raw).to_dict()
    from .profiles.mcs.protocol import decode
    return decode(raw, direction=direction)


def _one_frame(args) -> bytes:
    text = args.hex_option if args.hex_option is not None else args.hex
    if args.hex_option is not None and args.hex is not None:
        raise ValueError("provide one hex source")
    if text is not None and args.file is not None:
        raise ValueError("choose hex or --file")
    if text is not None:
        if args.input_format == "binary":
            raise ValueError("binary input requires --file")
        return bytes.fromhex(text)
    if args.file is None:
        raise ValueError("provide hexadecimal input or --file")
    if args.file.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("input exceeds 100 MB")
    if args.input_format == "binary":
        return args.file.read_bytes()
    return bytes.fromhex(" ".join(line.split("#", 1)[0] for line in _read(args.file).splitlines()))


def _chunks(path: Path, kind: str):
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("input exceeds 100 MB")
    if kind == "binary":
        with path.open("rb") as stream:
            while block := stream.read(4096):
                yield block
    else:
        with path.open(encoding="utf-8-sig") as stream:
            for number, line in enumerate(stream, 1):
                text = line.split("#", 1)[0].strip()
                if text:
                    try:
                        yield bytes.fromhex(text)
                    except ValueError as exc:
                        raise ValueError(f"invalid hex at line {number}") from exc


def _scan(model: str, chunks, direction="rx") -> dict:
    frames, issues = [], []
    if model == "mcc":
        from .profiles.mcc.protocol.stream import StreamParser
        parser = StreamParser()
        for chunk in chunks:
            frames.extend(frame.to_dict() for frame in parser.feed(chunk))
            if len(frames) > MAX_FRAMES:
                raise ValueError("input exceeds 100000 decoded frames")
            issues.extend(issue.to_dict() for issue in parser.issues)
            parser.issues.clear()
        try:
            parser.finish()
        except ValueError as exc:
            issues.append({"code": "truncated", "message": str(exc)})
    else:
        from .profiles.mcs.protocol import StreamParser
        parser = StreamParser()
        for chunk in chunks:
            for raw in parser.feed(chunk):
                try:
                    frames.append(_decode(model, raw, direction))
                except ValueError as exc:
                    issues.append({"code": "layout", "message": str(exc)})
            if len(frames) > MAX_FRAMES:
                raise ValueError("input exceeds 100000 decoded frames")
        parser.finish()
        issues.extend(dict(issue) for issue in parser.errors)
    return {"model": model, "valid": bool(frames) and not issues,
            "scope": "offline framing and decoded fields; no hardware verification",
            "frame_count": len(frames), "frames": frames, "issues": issues}


def _build(args):
    params = _object(args.params)
    if args.kind != "start" and any(value is not None for value in (args.speed, args.direction, args.temperature, args.duration)):
        raise ValueError("--speed/--direction/--temperature/--duration apply only to build start; native builders use --params")
    if args.kind in ("start", "stop", "tare", "query"):
        if params:
            raise ValueError("common build kinds use --speed/--direction/--temperature/--duration; --params is for native kinds")
        profile = _profile(args.model)
        if args.kind == "start":
            raw = profile.encode_start(2 if args.speed is None else args.speed,
                                       "cw" if args.direction is None else args.direction,
                                       0 if args.temperature is None else args.temperature,
                                       0 if args.duration is None else args.duration)
        else:
            raw = getattr(profile, "encode_" + args.kind)()
        if raw is None:
            raise ValueError(f"{args.model.upper()} has no verified query opcode; use sample() for synthetic telemetry")
    elif args.model == "mcc":
        if args.kind != "tx":
            raise ValueError(f"native build kind {args.kind!r} is unsupported for MCC; use tx")
        from .profiles.mcc.protocol.codec import Direction, Operation, encode_tx
        if isinstance(params.get("operation"), str):
            params["operation"] = Operation[params["operation"].upper()]
        if isinstance(params.get("direction"), str):
            params["direction"] = {"cw": Direction.CLOCKWISE, "ccw": Direction.COUNTER_CLOCKWISE}[params["direction"]]
        raw = encode_tx(**params)
    else:
        from .profiles.mcs.protocol import encode_manual, encode_operation, encode_ota
        builders = {"manual": encode_manual, "operation": encode_operation, "ota": encode_ota}
        if args.kind not in builders:
            raise ValueError(f"native build kind {args.kind!r} is unsupported for MCS")
        if "data_hex" in params:
            params["data"] = bytes.fromhex(params.pop("data_hex"))
        raw = builders[args.kind](**params)
    return {"model": args.model, "synthetic": True, "hex": raw.hex(" ").upper(),
            "decoded": _decode(args.model, raw, "tx")}


def _recording_analysis(args):
    from .api import replay
    data = _json(args.file)
    if not isinstance(data, dict) or data.get("model") != args.model:
        raise ValueError("recording initial model differs from --model")
    replay(data)
    frames, issues = [], []
    for event in data["actions"]:
        state = event["checkpoint"]["state"]
        for text in event["rx_hex"]:
            try:
                frames.append({"model": state["model"], "observed_time": state["time"],
                               **_decode(state["model"], bytes.fromhex(text), "rx")})
            except ValueError as exc:
                issues.append({"model": state["model"], "time": state["time"], "hex": text, "message": str(exc)})
    return {"model": args.model, "valid": not issues, "frame_count": len(frames), "frames": frames,
            "issues": issues, "scope": "verified synthetic recording RX; wire carries no host timestamp"}


def _analyze(args):
    if args.input_format == "recording":
        return _recording_analysis(args)
    if args.input_format == "jsonl":
        records = [json.loads(line) for line in _read(args.file).splitlines() if line.strip()]
        if len(records) > MAX_FRAMES:
            raise ValueError("input exceeds 100000 JSONL records")
        if args.model == "mcs":
            from .profiles.mcs.tools.logs import analyze_records
            result = analyze_records(records)
            issues = [issue for values in result["stream_diagnostics"].values() for issue in values]
            return {**result, "model": args.model, "frame_count": len(result["frames"]),
                    "issues": issues, "valid": bool(result["frames"]) and not issues}
        # Keep independent TX and RX streams; never join different directions.
        from .profiles.mcc.protocol.stream import StreamParser
        parsers = {direction: StreamParser() for direction in ("tx", "rx")}
        frames, issues = [], []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError("JSONL rows must be objects")
            direction = record.get("direction", "rx")
            if direction not in parsers:
                raise ValueError("JSONL direction must be tx or rx")
            parser = parsers[direction]
            for frame in parser.feed(bytes.fromhex(record["hex"])):
                frames.append({"observed_time": record.get("time", index), **frame.to_dict()})
        for direction, parser in parsers.items():
            issues.extend({"direction": direction, **issue.to_dict()} for issue in parser.issues)
            try:
                parser.finish()
            except ValueError as exc:
                issues.append({"direction": direction, "code": "truncated", "message": str(exc)})
        return {"model": args.model, "frame_count": len(frames), "frames": frames,
                "issues": issues, "valid": bool(frames) and not issues}
    return _scan(args.model, _chunks(args.file, args.input_format), args.direction)


def _telemetry(analysis):
    rows = []
    for frame in analysis["frames"]:
        model = frame.get("model", analysis["model"])
        if model == "mcc":
            if frame.get("kind") != "RX":
                continue
            values = dict(speed=frame["actual_rpm"], speed_unit="rpm", temperature=frame["actual_temperature"],
                          weight=frame["weight"], error_code=frame["error_code"], sequence=None)
        else:
            if frame.get("direction") != "rx" or "actual_temperature" not in frame.get("fields", {}):
                continue
            fields = frame["fields"]
            values = dict(speed=fields["speed_level"], speed_unit="raw_motor_level", temperature=fields["actual_temperature"],
                          weight=fields["weight_raw"], error_code=fields["error"], sequence=frame["sequence"])
        rows.append({"model": model, "time": frame.get("observed_time", frame.get("time")), **values})
    return rows


def _conformance(args):
    if args.model == "mcc" and args.corpus != "operational":
        raise ValueError("MCC has no MCS envelope-reference corpus")
    name = "mcc-golden-tx-292.json" if args.model == "mcc" else f"mcs-{args.corpus}-900.json"
    rows = _json(args.vectors) if args.vectors else json.loads(resources.files("monsieur_cuisine_sdk").joinpath("data", name).read_text(encoding="utf-8"))
    corpus = rows.get("vectors") if isinstance(rows, dict) else rows
    if not isinstance(corpus, list) or not 1 <= len(corpus) <= MAX_FRAMES:
        raise ValueError("conformance corpus must contain 1..100000 vector objects")
    if any(not isinstance(row, dict) for row in corpus):
        raise ValueError("conformance vectors must be objects")
    if args.write_vectors:
        args.write_vectors.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    if args.model == "mcs" and args.corpus == "operational":
        from .profiles.mcs.tools.conformance import check_vectors
        return {"model": args.model, "corpus": args.corpus, **check_vectors(rows)}
    if args.model == "mcc":
        from .profiles.mcc.protocol.codec import Direction, encode_tx
        rows = corpus
        failures = []
        for index, row in enumerate(rows):
            raw = encode_tx(row["operation"], speed=row["speed"], temperature_level=row["temperature_level"],
                            direction=Direction(row["android_direction"]), tare=row["tare"])
            if raw != bytes.fromhex(row["hex"]):
                failures.append({"index": index, "reason": "bytes differ"})
    else:
        from .profiles.mcs.protocol import pack
        failures = [{"index": index, "reason": "bytes differ"} for index, row in enumerate(rows)
                    if pack(bytes.fromhex(row["payload_hex"]), sequence=row["sequence"]).hex() != row["frame_hex"]]
    return {"model": args.model, "corpus": args.corpus, "count": len(rows), "passed": not failures,
            "failures": failures, "scope": "frozen offline byte conformance; no hardware verification"}


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--model", choices=("mcc", "mcs"), required=True, help="explicit protocol; never inferred from bytes")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("decode", "validate", "inspect"):
        sub = commands.add_parser(name)
        sub.add_argument("hex", nargs="?")
        sub.add_argument("--hex", dest="hex_option")
        sub.add_argument("--file", type=Path)
        sub.add_argument("--input-format", choices=("hex", "binary"), default="hex")
        sub.add_argument("--direction", choices=("tx", "rx"), default="rx", help="MCS payload interpretation; MCC kind is in its frame")
    build = commands.add_parser("build")
    build.add_argument("kind", nargs="?", default="start", choices=("start", "stop", "tare", "query", "tx", "manual", "operation", "ota"))
    build.add_argument("--speed", type=int)
    build.add_argument("--direction", choices=("cw", "ccw"))
    build.add_argument("--temperature", type=int)
    build.add_argument("--duration", type=int)
    build.add_argument("--params", default="{}", help="JSON keyword arguments for native tx/manual/operation/ota builders")
    for name in ("analyze", "telemetry"):
        sub = commands.add_parser(name)
        sub.add_argument("file", type=Path)
        sub.add_argument("--input-format", choices=("hex", "binary", "jsonl", "recording"), default="hex")
        sub.add_argument("--direction", choices=("tx", "rx"), default="rx")
        if name == "telemetry":
            sub.add_argument("--csv", type=Path)
    for name in ("simulate", "scenario"):
        sub = commands.add_parser(name)
        sub.add_argument("name", nargs="?", default="start_stop")
        sub.add_argument("--seed", type=int, default=292)
    stress = commands.add_parser("stress")
    stress.add_argument("--count", type=int, default=1000)
    stress.add_argument("--seed", type=int, default=292)
    record = commands.add_parser("record")
    record.add_argument("--file", type=Path, required=True)
    record.add_argument("--seconds", type=float, default=1.0)
    record.add_argument("--speed", type=int, default=2)
    record.add_argument("--direction", choices=("cw", "ccw"), default="cw")
    record.add_argument("--temperature", type=int, default=0)
    record.add_argument("--duration", type=int, default=0)
    record.add_argument("--seed", type=int, default=292)
    commands.add_parser("replay").add_argument("file", type=Path)
    conformance = commands.add_parser("conformance")
    conformance.add_argument("--vectors", type=Path)
    conformance.add_argument("--write-vectors", type=Path)
    conformance.add_argument("--corpus", choices=("operational", "envelope"), default="operational")
    commands.add_parser("capabilities")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            result = _build(args)
        elif args.command in ("decode", "inspect", "validate"):
            if args.command == "validate" and args.file is not None and args.hex is None and args.hex_option is None:
                result = _scan(args.model, _chunks(args.file, args.input_format), args.direction)
            else:
                raw = _one_frame(args)
                decoded = _decode(args.model, raw, args.direction)
                result = {"model": args.model, "valid": True, "decoded": decoded}
                if args.command == "inspect":
                    if args.model == "mcc":
                        from .profiles.mcc.tools.inspector import inspect_frame
                        result["inspection"] = inspect_frame(raw)
                    else:
                        from .profiles.mcs.protocol import inspect_frame
                        result["inspection"] = inspect_frame(raw, direction=args.direction)
        elif args.command in ("analyze", "telemetry"):
            result = _analyze(args)
            if args.command == "telemetry":
                rows = _telemetry(result)
                if args.csv:
                    with args.csv.open("w", newline="", encoding="utf-8") as stream:
                        writer = csv.DictWriter(stream, fieldnames=["model", "time", "speed", "speed_unit", "temperature", "weight", "error_code", "sequence"])
                        writer.writeheader(); writer.writerows(rows)
                result = {"model": args.model, "valid": result["valid"], "rows": rows, "issues": result["issues"]}
        elif args.command in ("simulate", "scenario", "stress"):
            from .scenarios import run_scenario, run_stress
            if args.command == "stress":
                if not 1 <= args.count <= 10000:
                    raise ValueError("stress count must be in 1..10000")
                result = run_stress(args.model, count=args.count, seed=args.seed)
            else:
                result = run_scenario(args.model, args.name, seed=args.seed)
        elif args.command == "record":
            from .api import DigitalTwin, RecordingLimitError, replay
            import math
            if not math.isfinite(args.seconds) or not 0 <= args.seconds <= 3600:
                raise ValueError("record seconds must be finite in 0..3600")
            twin = DigitalTwin(args.model, seed=args.seed)
            ended = None
            try:
                twin.start_motor(args.speed, args.direction, args.temperature, args.duration)
                remaining = round(args.seconds * 1e9)
                while remaining:
                    step = min(remaining, 100_000_000)
                    twin.advance(step / 1e9); twin.sample(); remaining -= step
                twin.stop_motor(); twin.advance(1); twin.sample()
            except RecordingLimitError as exc:
                # The common recorder reserves a terminal disarm. Preserve that
                # valid ended trace instead of discarding a long CLI session.
                ended = str(exc)
            replay(twin.recording)
            twin.save(args.file)
            result = {"model": args.model, "passed": ended is None, "ended": ended, "file": str(args.file),
                      "actions": len(twin.recording["actions"]), "state": twin.get_state().to_dict()}
        elif args.command == "replay":
            from .api import replay
            data = _json(args.file)
            if not isinstance(data, dict) or data.get("model") != args.model:
                raise ValueError("recording initial model differs from --model")
            twin = replay(data)
            result = {"model": args.model, "passed": True, "actions": len(data["actions"]), "state": twin.get_state().to_dict()}
        elif args.command == "conformance":
            result = _conformance(args)
        else:
            result = _profile(args.model).capabilities
        if is_dataclass(result):
            result = asdict(result)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 1 if isinstance(result, dict) and any(result.get(key) is False for key in ("valid", "PASS", "passed")) else 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        print(json.dumps({"model": args.model, "error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
