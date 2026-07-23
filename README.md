# PromptSmith-cli

**A local-first prompt preflight tool for your terminal.** PromptSmith analyzes a prompt before it consumes AI tokens, scores its readiness, flags ambiguity and missing context, and can refine it using deterministic rules, a local small language model, or both.

PromptSmith is not a prompt library, hosted AI service, or cloud wrapper. Its purpose is narrower: help you improve the prompt before you send it elsewhere.

**Open source · Local-first · No telemetry · No required cloud service**

- Source and issues: https://github.com/pr0z4k/promptsmith-cli
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Build instructions: [BUILD.md](BUILD.md)
- License: MIT

## Status

PromptSmith is preparing for its v1.0 release. The current package version remains defined in `pyproject.toml`; run `promptsmith --version` to see the installed version.

## What it does

```text
Prompt → Analyze → Challenge → Refine → Copy or Export
```

- **Analyze** scores prompt readiness from 0 to 100 using deterministic checks.
- **Challenge** surfaces rule-based questions for unclear scope, audience, success criteria, quantities, and integration constraints.
- **Refine** applies a profile and optional template through one of three local backends.
- **History** stores successful refinements locally in SQLite.
- **Export** saves the current session or the complete local history.

Analysis and challenge generation do not require an LLM.

## Installation

PromptSmith supports Python 3.10 through 3.14.

From a source checkout:

```bash
python -m pip install -e .
promptsmith
```

With local LLM support:

```bash
python -m pip install -e ".[llm]"
promptsmith
```

The package exposes both `promptsmith` and `promptsmith-cli`; they launch the same application.

Standalone executable builds are documented in [BUILD.md](BUILD.md).

## Basic usage

1. Enter a rough prompt.
2. Press **Ctrl+A** to analyze it.
3. Review the score, missing elements, prompt smells, and clarification questions.
4. Select a profile and optional template.
5. Press **Ctrl+R** to refine it.
6. Press **Ctrl+Y** to copy the result.

### Keyboard shortcuts

| Key | Action |
|---|---|
| Ctrl+A | Analyze |
| Ctrl+R | Analyze and refine |
| Ctrl+Y | Copy refined output |
| Ctrl+S | Save configuration |
| Ctrl+Q | Quit or go back |
| Up / Down | Scroll output |

The main screen also provides buttons for Analyze, Refine, Copy, Clear, Export, History, and Settings.

## Refinement backends

Backends are selected per profile through the `backend` field.

| Backend | Behavior |
|---|---|
| `rule` | Deterministic refinement. Always local, fast, and available without a model. |
| `llm` | Uses a local GGUF model through `llama-cpp-python` to rewrite the prompt. |
| `hybrid` | Applies deterministic rules first, then asks the local model to polish the complete result. Falls back to the rule result if the model fails or returns unusable output. |

Backend instances are owned and reused by the refiner so heavyweight local models are not reconstructed for every request.

## Profiles and templates

Built-in profiles and templates ship inside `src/promptsmith/data/`.

User-owned files belong in:

```text
~/.promptsmith/profiles/
~/.promptsmith/templates/
```

In portable builds, they live under the `user_data/` directory next to the executable.

A user file with the same name as a built-in file overrides the built-in version without modifying package data. This is the recommended customization path because it survives upgrades.

A profile may define:

```yaml
name: Example Developer
role: Senior software engineer
domain:
  - Python
  - CLI applications
tone: Technical and concise
format: Markdown
constraints:
  - Include tests.
backend: hybrid
```

Templates may use placeholders such as `{topic}`. Because the UI supplies one input value, multiple placeholders are filled from that same input.

## Local LLM support

PromptSmith uses GGUF models through `llama-cpp-python`.

Models can be downloaded from the Settings screen or placed in the model directory manually. The default preset is Phi-4-mini-instruct Q4_K_M; TinyLlama is available for lower-resource systems.

Model downloads are hardened as follows:

- HTTPS is required for the initial URL and every redirect.
- Embedded credentials, malformed hosts, fragments, and control characters are rejected.
- Partial files are written separately and promoted atomically.
- Existing symlink targets are rejected.
- File size and GGUF magic are validated before promotion.
- Optional SHA-256 validation is supported when a checksum is available.
- Transient network and server failures use bounded retries.

The model loader validates that a configured file is a regular, non-symlinked `.gguf` file with a valid header and a plausible minimum size.

PromptSmith does not guarantee that every GGUF model will fit into available memory. If model loading or inference runs out of memory, the model is unloaded and the application continues with a safe failure or deterministic fallback.

### Windows installation note

If `llama-cpp-python` attempts a local compile and fails, install a compatible prebuilt wheel for your system. Wheel availability and supported indexes change over time, so consult the llama-cpp-python project documentation rather than relying on one permanently correct command, because apparently packaging native Python extensions remains a cultural experiment.

## Privacy and data storage

PromptSmith does not send prompts, generated output, analytics, or telemetry to a hosted PromptSmith service.

Prompt and output text are excluded from diagnostic logs. Logs contain operational metadata and sanitized failure summaries.

Successful refinements are stored in a local SQLite history database unless history is unavailable. The database contains the original prompt and refined output in plaintext.

Default locations:

```text
Source or wheel install: ~/.promptsmith/history.db
Portable build:          user_data/history.db
```

Anyone with read access to that file can read its contents. There is currently no automatic retention period. Use History → Clear All or delete the database when local retention is not appropriate.

SQLite history uses WAL mode, lock waiting, integrity checks, and corruption quarantine. If the active database is corrupt, PromptSmith preserves the corrupt file and creates a clean replacement rather than deleting evidence or disabling history indefinitely.

## Configuration and exports

Application configuration, profiles, templates, model downloads, and history exports use confined paths and atomic writes. PromptSmith rejects traversal names and symlinked write targets.

History can be exported as JSON or CSV. The current working session can be exported separately as Markdown.

## Development

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the local quality checks:

```bash
python -m pytest src/tests
ruff check src
black --check src
isort --check-only src
mypy src/promptsmith
python -m build
python -m twine check dist/*
```

GitHub Actions runs the supported Python and packaging matrix when account minutes are available. Local checks remain the required fallback when hosted Actions cannot start.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution rules and [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common failures.

## Architecture and security boundaries

Important design constraints:

- Prompt analysis is deterministic and local.
- Runtime network access is confined to the reviewed model downloader.
- Backends are explicitly registered in-process; arbitrary module discovery is not supported.
- Runtime subprocess and shell execution are not part of the audited application boundary.
- Backend errors are sanitized before being shown to users.
- LLM lifecycle ownership belongs to the refiner and composed backends.

See [ARCHITECTURE.md](ARCHITECTURE.md) and the architecture decision records under `docs/adr/`.

## License

MIT