# Contributing to ChoomLang

## Quick setup

- Python 3.10+
- `pip install -e .`
- `pytest -q`

## Adding a profile

Profiles live in `profiles/` and must validate against `profiles/schema.json`.

Required fields:

- `name` (string)
- `defaults` (object)

Optional fields:

- `tags` (array of strings)
- `description` (string)
- `notes` (string)

Rules for `defaults` values:

- scalar only: string, number, boolean, or null
- no nested objects or arrays

Tag guidance:

- keep tags generic and reusable
- prefer lowercase words (`text`, `image`, `tool`, etc.)
- include 2-4 tags per profile where practical

Before opening a PR:

1. Run `pytest -q`
2. Run `choom profile list`
3. Ensure profile names and examples in docs match implemented CLI behavior
