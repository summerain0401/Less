import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="Less local reading product")
    parser.add_subparsers(dest="command", required=True).add_parser("openapi")
    args = parser.parse_args()
    if args.command == "openapi":
        from less.api import app

        print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
