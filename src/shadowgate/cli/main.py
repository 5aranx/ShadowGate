from __future__ import annotations

import argparse

from shadowgate.version import __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="shadowgate")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("server", help="run the control server")
    sub.add_parser("agent", help="run an agent")
    sub.add_parser("plugin", help="plugin management")
    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
        return 0
    print(f"shadowgate {args.cmd}: not yet wired; see src/shadowgate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
