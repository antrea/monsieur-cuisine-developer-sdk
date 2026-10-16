"""Save and verify a synthetic common recording for the selected device."""
import argparse
import json
from pathlib import Path
from monsieur_cuisine_sdk import DigitalTwin, replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("mcc", "mcs"), required=True)
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    twin = DigitalTwin(args.model)
    twin.set_sensors(weight=-12)
    twin.start_motor(2, "cw")
    for _ in range(5):
        twin.advance(0.1)
        twin.sample()
    twin.stop_motor()
    twin.advance(2)
    twin.sample()
    twin.save(args.file)
    restored = replay(args.file)
    assert restored.get_state() == twin.get_state()
    print(json.dumps({"model": args.model, "file": str(args.file), "matched": True,
                      "actions": len(twin.recording["actions"])}, indent=2))


if __name__ == "__main__":
    main()
