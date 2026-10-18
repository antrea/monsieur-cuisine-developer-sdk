"""Inventory an existing local backup without opening APK internals or personal files."""
import argparse
import json

from monsieur_cuisine_sdk.backup.inventory import inventory_session

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', help='Existing local backup_session folder')
    args = parser.parse_args()
    print(json.dumps(inventory_session(args.session).to_dict(), indent=2))
