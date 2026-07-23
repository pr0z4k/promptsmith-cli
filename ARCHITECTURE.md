# PromptSmith-cli Architecture

## Purpose

PromptSmith is a local-first prompt preflight application. It analyzes a prompt deterministically, surfaces missing information and ambiguity, and optionally refines the prompt through deterministic rules or a local GGUF model.

```text
User input
   ↓
PromptAnalyzer
   ↓
Readiness score + smells + challenges
   ↓
Profile and optional template
   ↓
PromptRefiner
   ↓
Rule, LLM, or Hybrid backend
   ↓
Refined prompt + local history
```

## Runtime boundaries

PromptSmith's audited runtime follows four important boundaries:

1. **Local analysis**: prompt analysis and challenge generation are deterministic and require no network access.
2. **Explicit backends**: trusted backend classes are imported and registered by application code. Arbitrary plugin discovery and packaging entry points are not supported.
3. **Confined networking**: outbound HTTP clients are restricted to the reviewed GGUF model downloader.
4. **No command execution**: subprocess and shell execution are not part of the application runtime.

Static regression tests enforce the network and process boundaries so future changes must deliberately update the policy rather than bypass it accidentally.

## Core components

### PromptAnalyzer

`PromptAnalyzer` performs deterministic prompt inspection:

- prompt-type detection
- readiness scoring from 0 to 100
- missing-element detection
- ambiguity and smell detection
- rule-based clarification questions
- profile recommendations

Analysis runs before backend selection and behaves the same for rule, LLM, and hybrid refinement.

### PromptRefiner

`PromptRefiner` is the refinement orchestration boundary. It owns:

- profile lookup
- optional template expansion
- backend selection through `BackendRegistry`
- backend-instance caching
- deterministic fallback
- sanitized warning state
- final content-completeness checks
- backend lifecycle cleanup

Heavyweight backend instances are reused across refinements. `PromptRefiner.unload()` releases all cached backends and is idempotent.

### RefinementProfile

`RefinementProfile` is the shared typed contract used by refinement backends. It represents optional YAML-backed fields such as:

- role
- domain
- tone
- format
- constraints
- backend

Runtime schema validation remains the responsibility of the profile manager and YAML store.

### ModelBackend

`ModelBackend` defines the backend contract:

- `refine(prompt, profile)`
- `last_error`
- `unload()`

Backends return a refined prompt or `None` when no usable result can be produced. User-facing error details are sanitized; raw prompt or model output content is not written to logs.

### RuleBasedBackend

The deterministic backend applies profile role, domain, tone, format, and constraints without an LLM. It is the always-available fallback path.

### LLMBasedBackend

The LLM backend:

- discovers or accepts a configured GGUF model
- validates regular-file, symlink, extension, size, and GGUF-header requirements
- lazily loads `llama-cpp-python`
- serializes model loading, inference, and cleanup with a reentrant lock
- detects common Python, llama.cpp, CUDA, and Metal memory failures
- unloads the model after inference OOM
- strips unsupported reasoning blocks and output preambles
- calls native `close()` when available

The backend never downloads models itself. Downloading is a separate reviewed boundary.

### HybridBackend

Hybrid refinement composes two backend instances:

1. `RuleBasedBackend` creates a complete deterministic prompt.
2. `LLMBasedBackend` polishes that complete prompt.
3. If polishing fails or produces degenerate output, the deterministic result is returned.

Hybrid receives its dependencies through constructor injection, allowing behavior to be tested without loading a real model.

### BackendRegistry

`BackendRegistry` is a thread-safe in-process registry of trusted backend classes.

- names use a constrained identifier format
- duplicate replacement requires an explicit request
- snapshots are immutable
- constructor failures are wrapped in sanitized `BackendError` messages
- no filesystem, entry-point, or arbitrary-module discovery occurs

## Configuration and YAML storage

`ConfigManager` handles application configuration with dot-notation access.

`YAMLConfigStore` underpins profiles and templates. Storage protections include:

- strict entry-name validation
- directory confinement
- rejection of symlinked targets
- mapping-root validation
- safe YAML loading and dumping
- temporary sibling files
- flush and `fsync`
- atomic promotion with `os.replace`
- backup recovery for the primary application configuration

Built-in profiles and templates are package data. User overrides live in the user data directory and take precedence without modifying installed files.

## History storage

`HistoryStore` uses SQLite for local prompt history.

- WAL journal mode
- `synchronous=NORMAL`
- explicit busy timeout
- initialization `quick_check`
- corruption quarantine and clean recreation
- symlink rejection
- narrow routine error handling
- atomic JSON and CSV exports

History is best-effort. Its failure does not prevent prompt analysis or refinement.

## Model download boundary

The downloader is the only audited runtime component permitted to perform outbound network requests.

It enforces:

- HTTPS-only source and redirects
- rejection of credentials, fragments, malformed hosts, and control characters
- bounded connection and read timeouts
- bounded retries for transient failures
- immediate failure for deterministic client errors
- confined filenames and destinations
- exclusive partial-file creation
- stale partial cleanup
- symlink rejection
- size and GGUF-magic validation
- optional SHA-256 verification
- flush, `fsync`, and atomic promotion

Downloaded model content is never executed as Python code. It is consumed only by the local llama.cpp binding after file validation.

## Application and TUI layer

`src/promptsmith/cli/app.py` currently contains the Textual application, modal screens, event handlers, path setup, logging setup, backend registration, and service construction.

This remains the largest maintainability concern. Importing the module also performs filesystem and registry side effects. A wholesale rewrite is intentionally not part of the v1.0 audit because it would create more regression risk than it removes.

The bounded post-v1.0 extraction plan is:

1. move logging, path resolution, and trusted backend registration into bootstrap code;
2. introduce an application-services container;
3. split modal screens from the main app module;
4. wire application shutdown explicitly to `PromptRefiner.unload()`;
5. add tests proving UI imports do not mutate filesystem or registry state.

See `docs/adr/0001-backend-lifecycle-and-orchestration.md`.

## IntentCompiler status

An `IntentCompiler` abstraction exists for a unified analyze/refine/re-analyze pipeline, but the current TUI directly coordinates `PromptAnalyzer` and `PromptRefiner`.

The direct path is the production-tested path. The unused abstraction should not be described as the active runtime pipeline. A future architectural change should either adopt it deliberately with acceptance tests or remove it as dead compatibility code.

## Data locations

Typical source or wheel installation:

```text
~/.promptsmith/
├── config.yaml
├── history.db
├── promptsmith.log
├── profiles/
├── templates/
├── models/
└── exports/
```

Portable builds use a writable `user_data/` directory next to the executable.

## Versioning and packaging

`pyproject.toml` is the package metadata source for:

- distribution version
- runtime version display
- supported Python range
- dependencies and extras
- console entry points
- package data

The package exposes both `promptsmith` and `promptsmith-cli` console commands.

## Known architectural limitations

- The TUI module is oversized and has import-time side effects.
- The active TUI does not use the existing `IntentCompiler` abstraction.
- Profiles originate as YAML mappings; the typed refinement contract does not replace full schema validation.
- Model compatibility depends on `llama-cpp-python` and the selected GGUF architecture.
- Local history is plaintext and has no automatic retention policy.

These are documented limitations, not concealed guarantees wearing a fake mustache.