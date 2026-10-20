"""Drive an MCC Digital Twin through a build-292 preset with the virtual CookingHost (no hardware).

Prints the commands the host latches over virtual time, the service callbacks it
raises and the LED state, for 'kneading', 'roasting' or 'steaming'.
"""
import argparse
import json

from monsieur_cuisine_sdk import DigitalTwin
from monsieur_cuisine_sdk.profiles.mcc import programs
from monsieur_cuisine_sdk.profiles.mcc.cooking import CookingHost
from monsieur_cuisine_sdk.profiles.mcc.protocol.codec import decode_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=sorted(programs.PRESETS), default="kneading")
    parser.add_argument("--seconds", type=int, help="session time; default is the preset's own")
    parser.add_argument("--step", type=float, default=1.0, help="virtual seconds between printed rows")
    args = parser.parse_args()
    host = CookingHost(DigitalTwin("mcc", record=False))
    host.start_program(args.preset, seconds=args.seconds)
    rows, previous = [], None
    while host.state == "RUN":
        host.advance(args.step)
        frame = decode_frame(host.latched)
        latched = (frame.operation_name, frame.speed_level,
                   frame.direction.name if frame.direction is not None else None, frame.temperature_level)
        if latched != previous:
            rows.append({"time_s": round(host.twin.now_ns / 1e9, 3), "step": host.step_index, "latched": latched,
                         "twin_speed": host.twin.get_state().requested_speed, "led": host.led_rgb()})
            previous = latched
    print(json.dumps({"preset": args.preset, "final_state": host.state, "rows": rows,
                      "callbacks": [e for e in host.events if e["event"].startswith("on_")][:20],
                      "led_after_finish": host.led_rgb(),
                      "evidence": "static app logic above a synthetic twin; no appliance involved"}, indent=2))


if __name__ == "__main__":
    main()
