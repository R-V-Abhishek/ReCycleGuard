"""Minimal C00 CLI entry point."""

import argparse


def app() -> None:
    parser = argparse.ArgumentParser(prog="recycleguard")
    parser.add_argument(
        "--version",
        action="version",
        version="recycleguard 0.1.0 (protocol 1.1)",
    )
    parser.parse_args()


if __name__ == "__main__":
    app()
