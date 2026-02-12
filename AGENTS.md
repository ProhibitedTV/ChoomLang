# Repository Conventions

## Development
- Python 3.10+
- Core implementation must use only Python standard library.
- Tests use `pytest`.

## Common commands
- Install editable package: `pip install -e .`
- Run tests: `pytest`
- Format/lint: keep style idiomatic and consistent (no enforced formatter requirement).

## Documentation expectations
- README and DEMO examples must use real CLI flags implemented in `src/choomlang/cli.py`.
- Onboarding docs should prioritize a concise quick-start and maintain Windows parity where practical.

## Project structure
- Source package: `src/choomlang/`
- Tests: `tests/`
- Specs/docs: root markdown files

## Determinism requirements
- Parser and serializer should be deterministic.
- JSON output should normalize aliases to canonical ops.
- DSL output from JSON should sort parameter keys for stable diffs.

## Commit expectations
- Keep commits focused and descriptive.
- Ensure tests pass before committing.
