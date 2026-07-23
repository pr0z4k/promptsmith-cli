# Contributing to PromptSmith-cli

PromptSmith is a local-first Python application with a Textual interface, deterministic prompt analysis, optional local GGUF inference, YAML-backed profiles and templates, and SQLite history.

## Development setup

```bash
git clone https://github.com/pr0z4k/promptsmith-cli.git
cd promptsmith-cli
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows, activate the environment with the appropriate `Scripts` command for your shell.

Install the optional local-model dependency only when working on LLM behavior:

```bash
python -m pip install -e ".[llm,dev]"
```

## Required local checks

Run these before opening a pull request:

```bash
python -m pytest src/tests
ruff check src
black --check src
isort --check-only src
mypy src/promptsmith
python -m build
python -m twine check dist/*
```

GitHub Actions may not run when the repository owner's included Actions budget is exhausted. A missing hosted run is not evidence that the checks passed; record the local commands and results in the pull request.

## Architectural rules

### Keep analysis deterministic

Prompt analysis, scoring, smell detection, and challenge generation must remain local and deterministic. Do not add network or model dependencies to the analyzer.

### Preserve runtime boundaries

- Do not add subprocess or shell execution to the runtime without an explicit security review.
- Do not add general-purpose HTTP clients outside the reviewed model downloader.
- Do not implement arbitrary plugin discovery from user paths, Python entry points, or configuration strings.
- Do not log prompt text or generated output.
- Do not expose raw backend exception messages to users.

Static regression tests enforce several of these rules. Update them only when the architecture decision itself has been reviewed.

### Backend contract

Backends implement `ModelBackend`:

- `refine(prompt, profile)` returns a string or `None`.
- `last_error` contains a safe user-facing summary when appropriate.
- `unload()` is idempotent and releases resources.

Register trusted backend classes explicitly through `BackendRegistry`. Heavyweight backends are owned and reused by `PromptRefiner`.

### Filesystem writes

Configuration, YAML entries, exports, and downloads must preserve the existing safeguards:

- confined names and paths
- symlink rejection
- temporary sibling files
- flush and `fsync`
- atomic `os.replace`

Do not replace these helpers with direct `write_text()` calls in production paths merely because the code becomes three lines shorter. Data loss is also concise.

## Profiles and templates

Built-in data lives under:

```text
src/promptsmith/data/profiles/
src/promptsmith/data/templates/
```

User-owned files must be written to the user data directory rather than package data.

When adding a profile:

- use a unique filename
- include a human-readable name and role
- keep domain and constraints specific
- choose `rule`, `llm`, or `hybrid` deliberately
- add schema and behavior tests when introducing new fields

Templates should work with the single input value supported by the current UI.

## Tests

Add focused regression tests for every bug fix or contract change. Prefer dependency injection and fake backends over loading a real GGUF model in unit tests.

Relevant suites cover:

- analyzers and scoring
- profile and template validation
- backend behavior and lifecycle
- history and export safety
- model download policy
- runtime network and process boundaries
- TUI behavior

## Pull requests

Keep each pull request coherent. Include:

- the problem being solved
- user-visible behavior changes
- architectural or security implications
- tests added or changed
- local validation commands and results
- known limitations or deferred work

Do not mix a broad TUI rewrite with unrelated backend, packaging, or documentation changes. The current app module already contains enough history for several civilizations.

## Architecture decisions

Significant design changes belong in `docs/adr/`. Use a short record containing context, decision, consequences, and deferred work.