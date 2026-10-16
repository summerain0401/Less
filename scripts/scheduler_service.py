"""Compatibility commands; all Less services now start and stop together."""

import argparse

from less.services import agent_config, start, status, stop


def launch_agent(provider: str) -> dict:
    return agent_config("scheduler", provider)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "status", "uninstall"))
    args = parser.parse_args()
    print("Use make start / stop / status; these commands control all Less services.")
    {"install": start, "status": status, "uninstall": stop}[args.action]()


if __name__ == "__main__":
    main()
