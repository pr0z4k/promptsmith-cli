# Contributing to PromptSmith-cli

PromptSmith-cli welcomes focused fixes, tests, profiles, templates, documentation, and backend improvements that preserve its local-first design.

## Development setup

Run from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

## Validate a change

Run the complete local gate:

```sh
python tools/validate_release.py --keep-going
```

This covers formatting, linting, imports, typing, tests, package build, Twine checks, and clean wheel installation.

For a faster development loop:

```sh
python -m pytest src/tests
ruff check .
black --check .
isort --check-only .
mypy src
```

Do not claim a platform or test result that was not actually executed.

## Change requirements

A pull request should:

- solve one coherent problem
- include regression coverage for defects
- preserve deterministic Rule fallback
- preserve model-download confinement and atomic promotion
- preserve runtime model refresh for cached LLM and Hybrid backends
- avoid logging prompt or output bodies
- update user-facing and architecture documentation when behavior changes
- update the changelog when the change is release-facing

## Profiles and templates

Built-in profiles and templates live under `src/promptsmith/data/`.

When adding or changing one:

- use valid YAML
- keep identifiers stable and descriptive
- avoid real domains, credentials, customer names, or internal infrastructure
- state the intended backend explicitly when it matters
- verify the item appears in the TUI
- test at least one representative prompt

## Backend changes

Backends implement the shared backend contract and are constructed through `BackendRegistry`.

New or modified backends must document and test:

- lifecycle and cleanup
- failure behavior
- fallback behavior
- model or external-resource ownership
- output validation
- sensitive logging

Backend instances are reused. Changes must not cause repeated model loads, stale model selection, or double cleanup.

## Model-download changes

Preserve these invariants:

- HTTPS only
- validated redirects
- safe filenames
- confined destination paths
- no writes through symlinks
- partial files never replace valid models
- GGUF validation before promotion
- checksum verification for known presets
- cleanup on interruption or failure
- atomic final replacement

## Documentation

Follow the project documentation standard:

- README for outcome, setup, verification, and navigation
- ARCHITECTURE for boundaries, flows, invariants, and source map
- SECURITY for trust assumptions and reporting
- troubleshooting for symptom-to-resolution guidance
- changelog for user-visible release changes

Commands must be copy-ready, tested, and followed by a verification step where appropriate.

## Commit and pull-request style

Use a concise imperative commit message, for example:

```text
fix: refresh cached model after settings change
```

Pull-request descriptions should include:

- problem and observed behavior
- implementation summary
- tests performed
- documentation changed
- known limitations or deferred work

## Release changes

Version changes, final release notes, and changelog reconciliation belong in a dedicated release pull request after the release candidate has passed validation.