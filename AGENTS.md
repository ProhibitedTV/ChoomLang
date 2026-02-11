# Repository Conventions

## Development
- Python 3.10+
- Core implementation must use only Python standard library.
- Tests use `pytest`.

## Common commands
- Install editable package: `pip install -e .`
- Run tests: `pytest`
- Format/lint: keep style idiomatic and consistent (no enforced formatter required in v0.1).

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
