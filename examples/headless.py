"""Run one deterministic common workflow using either explicit profile."""
import argparse
import json
from monsieur_cuisine_sdk import DigitalTwin, replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("mcc", "mcs"), required=True)
    args = parser.parse_args()
    twin = DigitalTwin(args.model, seed=292)
    twin.start_motor(2, "ccw", temperature=60)
    twin.advance(0.25)
    twin.sample()
    moving = twin.get_state()
    twin.stop_motor()
    twin.advance(2)
    twin.sample()
    assert replay(twin.recording).get_state() == twin.get_state()
    print(json.dumps({"model": args.model, "moving_speed": moving.actual_speed,
                      "speed_unit": moving.speed_unit, "state": twin.get_state().to_dict(),
                      "replay_matched": True}, indent=2))


if __name__ == "__main__":
    main()
