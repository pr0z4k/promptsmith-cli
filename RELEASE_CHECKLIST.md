# PromptSmith-cli Release Checklist

This checklist is the release gate for PromptSmith-cli releases. A checked
item means the command or scenario was actually executed against the
candidate commit. It must not be inferred from a workflow that failed
before checkout. The version referenced throughout is whatever
`pyproject.toml` currently declares for the candidate commit - update
that file first, then work through this checklist against it.

## Current constraint

Local validation is authoritative whenever GitHub-hosted CI capacity is
unavailable or exhausted (check the account's Actions usage before
assuming otherwise - this note itself goes stale). In that situation,
GitHub-hosted jobs may fail before creating steps or logs, so the local
gate below must record the operating system, Python version, command,
and result.

## Reproducible local gate

From a clean virtual environment:

```bash
python -m pip install --upgrade pip
python -m pip install -c requirements/constraints-release.txt -e ".[dev,build]"
python tools/validate_release.py --keep-going
```

The validator runs Ruff, Black, isort, mypy, pytest, package build, `twine check`, and a clean-wheel installation smoke test. It writes `release-validation.json` containing the candidate commit, Python runtime, operating system, commands, durations, and results. Do not commit reports containing machine-specific paths unless they have been reviewed first.

The validator is the baseline gate for one interpreter and platform. It does not replace the manual functional, LLM, platform, or frozen-build checks below.

## Candidate identity

- [ ] Candidate commit SHA recorded
- [ ] `pyproject.toml` version is the intended release version
- [ ] `promptsmith --version` matches `pyproject.toml` (verify against the
      installed wheel, not just an editable/source checkout - `--version`
      falls back to `0.0.0.dev0` when run against source without proper
      package metadata, which can mask a real mismatch)
- [ ] `promptsmith-cli --version` matches `pyproject.toml`
- [ ] `CHANGELOG.md` contains an entry for this version describing the
      audited behavior
- [ ] `docs/releases/<version>.md` exists (the portable-builds release
      workflow uses it as the GitHub Release body if present, and falls
      back to auto-generated notes otherwise)
- [ ] Repository URLs and package metadata point to GitHub

## Static quality checks

The validator runs:

```bash
python -m ruff check src
python -m black --check src
python -m isort --check-only src
python -m mypy src/promptsmith
python -m pytest src/tests
```

- [ ] Ruff passes
- [ ] Black passes
- [ ] isort passes
- [ ] mypy passes
- [ ] Full pytest suite passes
- [ ] Test count and duration recorded

## Package validation

The validator removes any existing `dist/` directory before building, then runs:

```bash
python -m build
python -m twine check <each generated artifact>
```

It also creates a temporary virtual environment, installs the generated wheel, verifies `--version`, and confirms packaged profiles are discoverable.

- [ ] Source distribution builds
- [ ] Wheel builds
- [ ] `twine check` passes
- [ ] Wheel contents include built-in profiles and templates
- [ ] Clean-environment wheel installation succeeds
- [ ] First and second launches retain built-in profiles and templates
- [ ] Both console commands launch from the installed wheel

## Functional acceptance

### Deterministic mode

- [ ] Analyze a short ambiguous prompt
- [ ] Readiness score, smells, missing elements, and challenges appear
- [ ] Rule refinement applies role, domain, tone, format, and constraints
- [ ] Template expansion works
- [ ] Unknown profile produces a clear error

### Local LLM mode

- [ ] Valid GGUF model loads
- [ ] LLM refinement returns usable text
- [ ] Hybrid runs deterministic refinement before LLM polish
- [ ] Hybrid falls back to deterministic output when the model is unavailable
- [ ] Invalid or undersized GGUF is rejected
- [ ] OOM produces a safe message and unloads the model
- [ ] Repeated refinements reuse the backend/model instance
- [ ] Application shutdown releases model resources

### Storage and privacy

- [ ] Configuration survives normal save and restart
- [ ] Interrupted-write recovery behavior is exercised
- [ ] Symlinked configuration targets are rejected
- [ ] History insert, list, preview, copy, delete, clear, JSON export, and CSV export work
- [ ] Corrupt history database is quarantined and recreated
- [ ] Prompt and refined content do not appear in logs
- [ ] Plaintext history behavior is disclosed in documentation

### Model downloader

- [ ] HTTPS preset download succeeds
- [ ] Plain HTTP URL is rejected
- [ ] Redirect to non-HTTPS is rejected
- [ ] Invalid filename and traversal attempts are rejected
- [ ] Invalid GGUF body is rejected
- [ ] Optional SHA-256 verification succeeds and fails correctly
- [ ] Interrupted or failed downloads do not promote partial files

## Platform matrix

At minimum, record one result per supported platform. Frozen builds must be produced on their native platform because PyInstaller does not cross-compile.

| Platform | Python | Wheel install | TUI smoke | Tests | Frozen build | Notes |
|---|---:|---:|---:|---:|---:|---|
| macOS | | | | | | |
| Linux | | | | | | |
| Windows | | | | | | |

Python support declared by the package is 3.10 through 3.14. Either
validate that matrix (all OS x Python combinations in `ci.yml` actually
green) or narrow `requires-python` and classifiers to the versions
actually tested. Narrowing to a *single* version - including the newest
- is not a substitute for validating the range: portable builds bundle
their own interpreter and are unaffected by this setting either way, so
`requires-python` only governs source/pip/Homebrew installs, where a
wider validated range serves more real installs than a narrower one.

## Standalone artifacts

- [ ] macOS build created on macOS
- [ ] Linux build created on Linux
- [ ] Windows build created on Windows
- [ ] Frozen `--version` smoke test passes
- [ ] Bundled llama.cpp native libraries are present when LLM support is included
- [ ] Rule-only build behaves correctly without llama-cpp-python
- [ ] Launchers work after extracting the ZIP
- [ ] Unsigned-software warnings are documented accurately
- [ ] Artifact SHA-256 checksums generated

## Release decision

Choose exactly one:

- [ ] **Ready**: all required checks passed
- [ ] **Ready with documented limitations**: remaining limitations do not compromise correctness, security, installation, or data safety
- [ ] **Not ready**: one or more release blockers remain

The following are release blockers:

- failing tests, lint, formatting, typing, build, or `twine check`
- version disagreement between metadata, commands, and artifacts
- inability to install and launch the wheel in a clean environment
- unverified model cleanup or OOM recovery
- documentation that contradicts current security behavior
- no successful validation on a claimed supported operating system

## Release actions

Only after the decision is Ready or Ready with documented limitations:

- [ ] Confirm `pyproject.toml` version is the intended release version
- [ ] Add the final changelog entry for this version
- [ ] Commit the release candidate
- [ ] Re-run the full release checklist against that exact commit
- [ ] Create annotated tag `v<pyproject.toml version>` (must match exactly
      - the portable-builds workflow only publishes a GitHub Release for
      tags matching `v*`, and reads `docs/releases/<version without the
      v prefix>.md` for the release body)
- [ ] Create GitHub release with concise release notes and known limitations
- [ ] Attach approved standalone artifacts and checksums
- [ ] Publish to PyPI only if PyPI distribution is intended and credentials are configured
