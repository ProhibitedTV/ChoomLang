"""Command line interface for ChoomLang."""

from __future__ import annotations

import argparse
import json
import sys

from .dsl import DSLParseError, parse_dsl
from .relay import OllamaClient, RelayError, run_relay
from .teach import explain_dsl
from .translate import dsl_to_json, json_text_to_dsl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="choom", description="ChoomLang CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_translate = sub.add_parser("translate", help="Translate DSL <-> JSON")
    p_translate.add_argument("input", nargs="?", help="DSL line, JSON string, or '-' / stdin")
    p_translate.add_argument("--reverse", action="store_true", help="Translate JSON -> DSL")
    p_translate.add_argument(
        "--compact",
        action="store_true",
        help="Use compact JSON output for DSL -> JSON",
    )

    p_teach = sub.add_parser("teach", help="Explain DSL token-by-token")
    p_teach.add_argument("input", help="DSL line")

    p_validate = sub.add_parser("validate", help="Validate a DSL line")
    p_validate.add_argument("input", nargs="?", help="DSL line or '-' / stdin")

    p_relay = sub.add_parser("relay", help="Run a local Ollama-backed relay")
    p_relay.add_argument("--a-model", required=True, help="Model name for speaker A")
    p_relay.add_argument("--b-model", required=True, help="Model name for speaker B")
    p_relay.add_argument("--turns", type=int, default=6, help="Number of A/B turn pairs")
    p_relay.add_argument("--seed", type=int, help="Optional Ollama seed")
    p_relay.add_argument("--system-a", help="Optional system prompt for speaker A")
    p_relay.add_argument("--system-b", help="Optional system prompt for speaker B")
    p_relay.add_argument("--start", help="Optional initial ChoomLang line")
    p_relay.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require valid ChoomLang from each model with one retry",
    )

    return parser


def _read_input(value: str | None) -> str:
    if value is not None and value != "-":
        return value
    text = sys.stdin.read()
    if not text.strip():
        raise ValueError("input required via argument or stdin")
    return text.strip()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "translate":
            text = _read_input(args.input)
            if args.reverse:
                print(json_text_to_dsl(text))
            else:
                stripped = text.lstrip()
                if stripped.startswith("{"):
                    print(json_text_to_dsl(text))
                else:
                    payload = dsl_to_json(text)
                    if args.compact:
                        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
                    else:
                        print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        if args.command == "teach":
            print(explain_dsl(args.input))
            return 0

        if args.command == "validate":
            parse_dsl(_read_input(args.input))
            print("ok")
            return 0

        if args.command == "relay":
            transcript = run_relay(
                client=OllamaClient(),
                a_model=args.a_model,
                b_model=args.b_model,
                turns=args.turns,
                seed=args.seed,
                system_a=args.system_a,
                system_b=args.system_b,
                start=args.start,
                strict=args.strict,
            )
            for speaker, dsl_line, payload in transcript:
                print(f"{speaker}: {dsl_line}")
                print(json.dumps(payload, sort_keys=True))
            return 0

        parser.error("unknown command")
    except (DSLParseError, ValueError, json.JSONDecodeError, RelayError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
