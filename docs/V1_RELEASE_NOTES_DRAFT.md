# PromptSmith-cli 1.0.0 — Draft Release Notes

PromptSmith-cli 1.0 establishes the project as a local-first prompt quality gateway: deterministic analysis and scoring before refinement, with optional local-LLM and hybrid preparation modes.

These notes remain a draft until the release checklist passes against the final candidate commit.

## Highlights

- Deterministic prompt analysis, readiness scoring, smell detection, missing-element detection, and clarifying challenges
- Rule-based, local-LLM, and hybrid refinement backends
- Local profiles and templates with user-space overrides
- Local SQLite prompt history with JSON and CSV export
- Textual terminal interface with packaged wheel and standalone-build support
- Explicit backend lifecycle management and model reuse

## Security and robustness

The v1.0 audit added or verified:

- atomic YAML, configuration, export, and model writes
- symlink and traversal protections around writable paths
- HTTPS-only model downloads with redirect validation
- optional SHA-256 verification for model downloads
- stale partial-file cleanup and atomic model promotion
- SQLite lock handling, corruption quarantine, and recovery
- sanitized backend and model errors
- prompt and generated-output exclusion from logs
- native model cleanup and safe out-of-memory recovery
- explicit in-process backend registration without arbitrary plugin discovery

## Architecture

- Backends now share a typed refinement profile contract
- `RuleBasedBackend` is an explicit backend rather than a private helper dependency
- `HybridBackend` composes deterministic and LLM backends
- `PromptRefiner` owns, reuses, and unloads backend instances
- Backend construction is centralized through the trusted registry

The large Textual application module remains a documented maintainability limitation. Its extraction is intentionally deferred until after v1.0 to avoid destabilizing the audited release candidate.

## Privacy

PromptSmith does not send prompts to a hosted service. Optional LLM inference runs through a local GGUF model.

Prompt history and logs are stored locally. History contains prompt and refined-output text in plaintext SQLite. Logs contain operational metadata but are designed not to contain prompt or generated-output content.

## Known release limitations

- GitHub-hosted Actions validation may be unavailable while the repository owner's included Actions minutes are exhausted. Local validation evidence is authoritative for this release candidate.
- Standalone artifacts must be built and validated independently on macOS, Linux, and Windows because PyInstaller does not cross-compile.
- The Textual application module still combines bootstrap, service construction, screens, and event orchestration; this is a post-v1.0 refactoring target.

## Installation

From PyPI, once published:

```bash
pip install promptsmith-cli
promptsmith
```

For local-LLM support:

```bash
pip install "promptsmith-cli[llm]"
```

Standalone packages may also be attached to the GitHub release after native-platform validation.
