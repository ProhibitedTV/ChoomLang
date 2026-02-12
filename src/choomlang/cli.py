"""Command line interface for ChoomLang."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .dsl import DSLParseError, format_dsl, parse_dsl
from .protocol import (
    KNOWN_OPS,
    KNOWN_TARGETS,
    build_guard_prompt,
    canonical_json_schema,
    script_to_dsl,
    script_to_jsonl,
)
from .relay import OllamaClient, RelayError, run_probe, run_relay
from .run import RunError, run_toolcall
from .teach import explain_dsl
from .translate import dsl_to_json, json_text_to_dsl
from .profiles import ProfileError, apply_profile_to_dsl, list_profiles, read_profile


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

    p_lint = sub.add_parser("lint", help="Warn on non-canonical or suspicious DSL patterns")
    p_lint.add_argument("input", nargs="?", help="DSL line or '-' / stdin")
    p_lint.add_argument("--lenient", action="store_true", help="Allow standalone trailing punctuation tokens")
    p_lint.add_argument("--strict-ops", action="store_true", help="Warn for unknown ops")
    p_lint.add_argument("--strict-targets", action="store_true", help="Warn for unknown targets")

    p_profile = sub.add_parser("profile", help="Manage and apply parameter profiles")
    profile_sub = p_profile.add_subparsers(dest="profile_command", required=True)
    profile_sub.add_parser("list", help="List available profiles")
    p_profile_show = profile_sub.add_parser("show", help="Show one profile JSON")
    p_profile_show.add_argument("name", help="Profile name")
    p_profile_apply = profile_sub.add_parser("apply", help="Apply profile defaults to a DSL line")
    p_profile_apply.add_argument("name", help="Profile name")
    p_profile_apply.add_argument("dsl", help="DSL line")

    p_run = sub.add_parser("run", help="Execute safe local toolcall adapters")
    p_run.add_argument("input", help="DSL line or path to a .choom file")
    p_run.add_argument("--dry-run", action="store_true", help="Print what would execute")
    p_run.add_argument("--out-dir", default="out", help="Safe output directory for file-writing adapters")

    p_script = sub.add_parser("script", help="Process multi-line ChoomLang scripts")
    p_script.add_argument("path", help="Script path or '-' for stdin")
    p_script.add_argument("--to", choices=["jsonl", "dsl"], default="jsonl", help="Output format")
    mode = p_script.add_mutually_exclusive_group()
    mode.add_argument("--fail-fast", dest="fail_fast", action="store_true", default=True)
    mode.add_argument("--continue", dest="fail_fast", action="store_false")

    p_schema = sub.add_parser("schema", help="Emit JSON Schema for canonical payload JSON")
    p_schema.add_argument("--mode", choices=["strict", "permissive"], default="strict", help="Schema strictness mode")

    p_guard = sub.add_parser("guard", help="Print a reusable model repair prompt")
    p_guard.add_argument("--error", help="Optional parse/validation error text")
    p_guard.add_argument("--previous", help="Optional previous model output")

    p_completion = sub.add_parser("completion", help="Print shell completion script")
    p_completion.add_argument("shell", nargs="?", choices=["bash", "zsh", "powershell"], help="Shell type")

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
    p_relay.add_argument("--allow-unknown-op", action="store_true", help="Allow unknown op values in structured relay validation")
    p_relay.add_argument("--allow-unknown-target", action="store_true", help="Allow unknown target values in structured relay validation")
    p_relay.add_argument("--raw-json", action="store_true", help="Print raw JSON replies in relay output")
    p_relay.add_argument("--log", help="Append relay transcript records to JSONL file")
    p_relay.add_argument("--lenient", action="store_true", help="Allow trivial trailing punctuation token in DSL mode")
    p_relay.add_argument("--timeout", type=float, default=180.0, help="HTTP timeout in seconds for relay requests")
    p_relay.add_argument("--keep-alive", dest="keep_alive", type=float, default=300.0, help="Ollama keep_alive value in seconds")
    p_relay.add_argument("--no-fallback", action="store_true", help="Disable structured schema/json automatic fallback")
    p_relay.add_argument("--probe", action="store_true", help="Probe Ollama connectivity/model readiness and exit")
    p_relay.add_argument("--warm", action="store_true", help="Pre-warm both relay models before turn exchange")

    p_demo = sub.add_parser("demo", help="Run a predefined structured relay demo")
    p_demo.add_argument("--timeout", type=float, default=180.0, help="HTTP timeout in seconds for relay requests")
    p_demo.add_argument("--keep-alive", dest="keep_alive", type=float, default=300.0, help="Ollama keep_alive value in seconds")

    return parser


def _detect_shell() -> str:
    if os.name == "nt":
        return "powershell"
    shell = os.environ.get("SHELL", "")
    if shell.endswith("zsh"):
        return "zsh"
    return "bash"


def _completion_script(shell: str) -> str:
    if shell == "bash":
        return """# bash completion for choom\n_choom_complete() {\n  local cur prev words cword\n  _init_completion || return\n  local cmds=\"translate teach validate fmt lint profile run script schema guard completion relay demo\"\n  if [[ $cword -eq 1 ]]; then\n    COMPREPLY=( $(compgen -W \"$cmds\" -- \"$cur\") )\n    return\n  fi\n}\ncomplete -F _choom_complete choom\n"""
    if shell == "zsh":
        return """#compdef choom\n_arguments '1:command:(translate teach validate fmt lint profile run script schema guard completion relay demo)'\n"""
    if shell == "powershell":
        return """Register-ArgumentCompleter -CommandName choom -ScriptBlock {\n  param($wordToComplete, $commandAst, $cursorPosition)\n  'translate','teach','validate','fmt','lint','profile','run','script','schema','guard','completion','relay','demo' |\n    Where-Object { $_ -like \"$wordToComplete*\" } |\n    ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }\n}\n"""
    raise ValueError("shell must be one of: bash, zsh, powershell")


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


def _read_run_input(value: str) -> str:
    maybe_path = Path(value)
    if maybe_path.exists() and maybe_path.is_file():
        return maybe_path.read_text(encoding="utf-8").strip()
    return value


def _lint_dsl(text: str, *, lenient: bool, strict_ops: bool, strict_targets: bool) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    raw_tokens = text.strip().split()
    if not lenient:
        for token in raw_tokens[2:]:
            if token in {".", ",", ";", ":", "!", "?"}:
                warnings.append(f"suspicious standalone punctuation token: {token!r}")
    try:
        parsed = parse_dsl(text, lenient=lenient)
    except DSLParseError as exc:
        errors.append(str(exc))
        return warnings, errors

    canonical = format_dsl(text, lenient=lenient)
    if canonical != text.strip():
        warnings.append("non-canonical DSL formatting; run `choom fmt`")

    if strict_ops and parsed.op not in KNOWN_OPS:
        warnings.append(f"unknown op '{parsed.op}' in strict registry mode")
    if strict_targets and parsed.target not in KNOWN_TARGETS:
        warnings.append(f"unknown target '{parsed.target}' in strict registry mode")

    for key in parsed.params:
        if not key.replace("_", "a").replace("-", "a").replace(".", "a").isalnum() or " " in key:
            warnings.append(f"param key '{key}' is non-conventional; use [A-Za-z0-9_.-] without spaces")
    return warnings, errors


def _print_validation_suggestions(text: str, err: DSLParseError, *, lenient: bool) -> None:
    message = str(err)
    if "missing '='" in message:
        print("hint: key/value params must use key=value (example: gen txt prompt=hello)", file=sys.stderr)
    if "missing '='" in message and " in token '" in message:
        token = message.split(" in token '", 1)[1].split("'", 1)[0]
        print(f"hint: did you mean {token}=<value>?", file=sys.stderr)
    if "index" in message and not lenient:
        print("hint: if input ends with '.', try --lenient", file=sys.stderr)
    if "trailing punctuation" in text or text.strip().endswith((".", ",", ";")):
        if not lenient:
            print("hint: trailing punctuation is common; try --lenient", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    validate_text: str | None = None

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
            validate_text = _read_input(args.input)
            parsed = parse_dsl(validate_text, lenient=args.lenient)
            if parsed.op not in KNOWN_OPS:
                print(f"hint: unknown op '{parsed.op}'. supported ops: {', '.join(KNOWN_OPS)}", file=sys.stderr)
            if parsed.target not in KNOWN_TARGETS:
                print(
                    f"hint: unknown target '{parsed.target}'. supported targets: {', '.join(KNOWN_TARGETS)}",
                    file=sys.stderr,
                )
            print("ok")
            return 0

        if args.command == "fmt":
            print(format_dsl(_read_input(args.input), lenient=args.lenient))
            return 0

        if args.command == "lint":
            lint_text = _read_input(args.input)
            warnings, errors = _lint_dsl(
                lint_text,
                lenient=args.lenient,
                strict_ops=args.strict_ops,
                strict_targets=args.strict_targets,
            )
            for warning in warnings:
                print(f"warn: {warning}", file=sys.stderr)
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            if errors:
                return 2
            return 1 if warnings else 0

        if args.command == "profile":
            if args.profile_command == "list":
                for name in list_profiles():
                    print(name)
                return 0
            if args.profile_command == "show":
                print(json.dumps(read_profile(args.name), indent=2, sort_keys=True))
                return 0
            if args.profile_command == "apply":
                print(apply_profile_to_dsl(args.name, args.dsl))
                return 0

        if args.command == "run":
            result = run_toolcall(_read_run_input(args.input), out_dir=args.out_dir, dry_run=args.dry_run)
            print(result)
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
            print(json.dumps(canonical_json_schema(mode=args.mode), indent=2, sort_keys=True))
            return 0

        if args.command == "guard":
            print(build_guard_prompt(error=args.error, previous=args.previous))
            return 0

        if args.command == "completion":
            shell = args.shell or _detect_shell()
            print(_completion_script(shell), end="")
            return 0

        if args.command == "demo":
            print("=== ChoomLang Relay Demo (v0.6) ===")
            print("Models: llama3.2:latest <-> qwen2.5:latest")
            print("Saving transcript to choom_demo.jsonl")
            demo_args = [
                "relay",
                "--a-model",
                "llama3.2:latest",
                "--b-model",
                "qwen2.5:latest",
                "--turns",
                "4",
                "--structured",
                "--start",
                'gen txt prompt="ChoomLang in action: describe a client-server protocol in 5 lines"',
                "--log",
                "choom_demo.jsonl",
                "--timeout",
                str(args.timeout),
                "--keep-alive",
                str(args.keep_alive),
            ]
            return main(demo_args)

        if args.command == "relay":
            client = OllamaClient(timeout=args.timeout, keep_alive=args.keep_alive)
            if args.probe:
                ok, report = run_probe(client=client, models=[args.a_model, args.b_model])
                print("probe report:")
                for entry in report:
                    if entry["kind"] == "tags":
                        status = "ok" if entry["ok"] else "fail"
                        print(
                            f"- /api/tags: {status} http={entry.get('http_status')} elapsed_ms={entry.get('elapsed_ms')}"
                        )
                        if entry.get("reason"):
                            print(f"  reason: {entry['reason']}")
                    else:
                        status = "ok" if entry["ok"] else "fail"
                        print(
                            f"- model {entry['model']}: {status} http={entry.get('http_status')} elapsed_ms={entry.get('elapsed_ms')}"
                        )
                        if entry.get("reason"):
                            print(f"  reason: {entry['reason']}")
                return 0 if ok else 2

            transcript = run_relay(
                client=client,
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
                allow_unknown_op=args.allow_unknown_op,
                allow_unknown_target=args.allow_unknown_target,
                fallback_enabled=not args.no_fallback,
                raw_json=args.raw_json,
                log_path=args.log,
                lenient=args.lenient,
                warm=args.warm,
            )
            for speaker, dsl_line, payload, raw in transcript:
                print(f"{speaker}: {dsl_line}")
                print(json.dumps(payload, sort_keys=True))
                if args.raw_json and raw is not None:
                    print(f"raw: {raw}")
            return 0

        parser.error("unknown command")
    except DSLParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.command == "validate":
            _print_validation_suggestions(validate_text or "", exc, lenient=args.lenient)
        return 2
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ProfileError, RunError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RelayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.command == "relay":
            print(
                "hint: relay failed early. Try: choom relay --probe --a-model X --b-model Y",
                file=sys.stderr,
            )
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
