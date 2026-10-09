import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="Less local reading product")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("openapi")
    commands.add_parser("scheduler", help="Run morning and evening digests while this process lives")
    preview = commands.add_parser("preview", help="Generate an email preview without saving or sending")
    preview.add_argument("--slot", choices=("morning", "evening"), required=True)
    args = parser.parse_args()
    if args.command == "openapi":
        from less.api import app

        print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
    else:
        from less.digest import preview_digest, run_scheduler

        try:
            if args.command == "scheduler":
                run_scheduler()
            else:
                preview_digest(args.slot)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
