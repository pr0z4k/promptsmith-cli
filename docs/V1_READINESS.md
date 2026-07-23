# PromptSmith-cli v1.0 Readiness Assessment

Date: 2026-07-23

Status: **Not ready for final v1.0 tag yet**

This is not a negative assessment of the code. It means the engineering audit is substantially complete, while release-candidate validation and metadata reconciliation have not yet been executed against one exact commit.

## Completed audit passes

### Pass 1: release engineering

Completed and merged. The repository contains a cross-platform quality workflow, pinned development/build tooling, packaging validation, pre-commit configuration, and dependency automation.

### Pass 2: security and robustness

Completed and merged. The audited runtime now includes atomic and symlink-safe persistence, SQLite corruption recovery and lock handling, HTTPS-only model downloads, redirect and filename validation, optional checksums, constrained backend registration, safe logging, local-only execution boundaries, model OOM recovery, and idempotent native-resource cleanup.

### Pass 3: code review and architecture

Completed and merged. Backend contracts and lifecycle ownership were formalized; Hybrid no longer reaches into a private deterministic helper; PromptRefiner owns and reuses backend instances; backend construction and fallback behavior are centralized and sanitized. The large TUI module remains a documented maintainability limitation, not a v1.0 correctness blocker.

### Pass 4: documentation

Core documentation completed and merged: README, architecture, contribution guidance, and troubleshooting. The remaining release-specific documentation task is to reconcile the historical changelog with the final audited behavior and add the v1.0 entry.

## Current release blockers

1. **No completed release-candidate validation record.** The full lint, format, import-order, typing, test, build, and `twine check` commands must be executed against the candidate commit.
2. **GitHub Actions minutes are exhausted.** Hosted jobs currently fail before checkout. This is understood and acceptable for development, but local validation must replace it for the release candidate.
3. **Version remains beta.** `pyproject.toml` still declares `0.6.0b2`; it should not be changed to `1.0.0` until validation passes.
4. **Changelog is historically stale in places.** Earlier 0.6 text describes plain HTTP downloads as permitted and GGUF validation as header-only. The final v1.0 entry must clearly supersede those statements with the audited HTTPS-only, size/header/checksum behavior.
5. **Supported-platform evidence is incomplete.** The package claims Python 3.10 through 3.14 and OS independence. At least one clean wheel/TUI validation per claimed operating system is required, and the Python matrix should either be exercised or narrowed.
6. **Standalone artifacts are not yet validated as release candidates.** Native-platform builds, frozen `--version`, launcher behavior, and bundled llama.cpp libraries remain to be checked.

## Non-blocking known limitations

- `src/promptsmith/cli/app.py` remains a large module with startup side effects and mixed UI/bootstrap responsibilities.
- Prompt history is plaintext, unencrypted, and has no automatic retention policy; this is documented.
- Model files are large and local memory availability varies; safe OOM fallback exists, but hardware suitability cannot be guaranteed.
- GitHub-hosted CI is temporarily unavailable due to account minute exhaustion.

## Recommended decision path

1. Run `RELEASE_CHECKLIST.md` locally on the primary development machine.
2. Fix any failures on this Pass 5 branch.
3. Validate wheel installation in a fresh virtual environment.
4. Validate at least macOS, Linux, and Windows smoke paths, using native systems for frozen builds.
5. Add the v1.0 changelog entry and update version metadata only after the candidate passes.
6. Re-run the checklist against the exact release commit.
7. Tag and publish.

Until those steps are recorded, the correct decision is **Not ready**, with no evidence of a known unresolved security or architecture defect blocking continued development.
