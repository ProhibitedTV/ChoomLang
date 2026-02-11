"""Command line interface for ChoomLang."""

from __future__ import annotations

import argparse
import json
import sys

from .dsl import DSLParseError, format_dsl, parse_dsl
from .protocol import build_guard_prompt, canonical_json_schema, script_to_dsl, script_to_jsonl
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
    p_validate.add_argument("--lenient", action="store_true", help="Allow trivial trailing punctuation token")

    p_fmt = sub.add_parser("fmt", help="Canonicalize one DSL line")
    p_fmt.add_argument("input", nargs="?", help="DSL line or '-' / stdin")
    p_fmt.add_argument("--lenient", action="store_true", help="Allow trivial trailing punctuation token")

    p_script = sub.add_parser("script", help="Process multi-line ChoomLang scripts")
    p_script.add_argument("path", help="Script path or '-' for stdin")
    p_script.add_argument("--to", choices=["jsonl", "dsl"], default="jsonl", help="Output format")
    mode = p_script.add_mutually_exclusive_group()
    mode.add_argument("--fail-fast", dest="fail_fast", action="store_true", default=True)
    mode.add_argument("--continue", dest="fail_fast", action="store_false")

    sub.add_parser("schema", help="Emit JSON Schema for canonical payload JSON")

    p_guard = sub.add_parser("guard", help="Print a reusable model repair prompt")
    p_guard.add_argument("--error", help="Optional parse/validation error text")
    p_guard.add_argument("--previous", help="Optional previous model output")

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
    p_relay.add_argument("--structured", action="store_true", help="Use Ollama structured output mode")
    p_relay.add_argument("--schema", action=argparse.BooleanOptionalAction, default=True, help="Use canonical JSON schema with --structured")
    p_relay.add_argument("--raw-json", action="store_true", help="Print raw JSON replies in relay output")
    p_relay.add_argument("--log", help="Append relay transcript records to JSONL file")
    p_relay.add_argument("--lenient", action="store_true", help="Allow trivial trailing punctuation token in DSL mode")

    return parser


def _read_input(value: str | None) -> str:
    if value is not None and value != "-":
        return value
    text = sys.stdin.read()
    if not text.strip():
        raise ValueError("input required via argument or stdin")
    return text.strip()


def _read_script(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


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
            parse_dsl(_read_input(args.input), lenient=args.lenient)
            print("ok")
            return 0

        if args.command == "fmt":
            print(format_dsl(_read_input(args.input), lenient=args.lenient))
            return 0

        if args.command == "script":
            script_text = _read_script(args.path)
            if args.to == "dsl":
                outputs, errors = script_to_dsl(script_text, fail_fast=args.fail_fast)
            else:
                outputs, errors = script_to_jsonl(script_text, fail_fast=args.fail_fast)

            for line in outputs:
                print(line)
            for err in errors:
                print(f"error: {err}", file=sys.stderr)

            if errors and not args.fail_fast:
                return 2
            if errors and args.fail_fast:
                return 2
            return 0

        if args.command == "schema":
            print(json.dumps(canonical_json_schema(), indent=2, sort_keys=True))
            return 0

        if args.command == "guard":
            print(build_guard_prompt(error=args.error, previous=args.previous))
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
                structured=args.structured,
                use_schema=args.schema if args.structured else False,
                raw_json=args.raw_json,
                log_path=args.log,
                lenient=args.lenient,
            )
            for speaker, dsl_line, payload, raw in transcript:
                print(f"{speaker}: {dsl_line}")
                print(json.dumps(payload, sort_keys=True))
                if args.raw_json and raw is not None:
                    print(f"raw: {raw}")
            return 0

        parser.error("unknown command")
    except (DSLParseError, ValueError, json.JSONDecodeError, RelayError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
