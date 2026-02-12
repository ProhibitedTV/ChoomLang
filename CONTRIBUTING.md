# Contributing to ChoomLang

Thanks for contributing to ChoomLang.

## Development install

- Python 3.10+
- Create and activate a virtual environment
- Install development dependencies in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Running tests

Run the full suite with pytest:

```bash
pytest
```

## Style guidelines

- Keep changes focused, deterministic, and consistent with existing code style.
- Core implementation in `src/choomlang/` should use only Python standard library.
- Prefer clear naming and small functions.
- Keep CLI examples aligned with real flags implemented in `src/choomlang/cli.py`.
- Update docs/examples when behavior changes.

## Before opening a PR

1. Run `pytest` and confirm all tests pass.
2. Verify packaging still works (`pip install .` and `python -m build`).
3. Ensure docs and examples remain accurate for Linux/macOS and Windows where practical.
