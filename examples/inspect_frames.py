"""Build one profile command and inspect its actual independent byte layout."""
import argparse
from monsieur_cuisine_sdk import DigitalTwin
from monsieur_cuisine_sdk.cli import main as tools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("mcc", "mcs"), required=True)
    args = parser.parse_args()
    twin = DigitalTwin(args.model, record=False)
    raw = twin.profile.encode_start(2, "ccw", 60, 0)
    return tools(["--model", args.model, "inspect", "--hex", raw.hex(), "--direction", "tx"])


if __name__ == "__main__":
    raise SystemExit(main())
