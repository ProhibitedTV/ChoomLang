"""Command line interface for ChoomLang."""

from __future__ import annotations

import argparse
import json
import sys

from .dsl import DSLParseError
from .teach import explain_dsl
from .translate import dsl_to_json, json_text_to_dsl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="choom", description="ChoomLang CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_translate = sub.add_parser("translate", help="Translate DSL <-> JSON")
    p_translate.add_argument("input", help="DSL line or JSON string (with --reverse)")
    p_translate.add_argument("--reverse", action="store_true", help="Translate JSON -> DSL")

    p_teach = sub.add_parser("teach", help="Explain DSL token-by-token")
    p_teach.add_argument("input", help="DSL line")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "translate":
            if args.reverse:
                print(json_text_to_dsl(args.input))
            else:
                payload = dsl_to_json(args.input)
                print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        if args.command == "teach":
            print(explain_dsl(args.input))
            return 0

        parser.error("unknown command")
    except (DSLParseError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
