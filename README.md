# PromptSmith-cli

> A local-first prompt preflight tool for your terminal.

PromptSmith does not generate code. It does not replace your favorite AI, maintain a giant prompt library, or invent another cloud account for you to forget the password to.

It helps you send **better prompts before you spend tokens**.

Every prompt is analyzed locally, scored from 0 to 100, checked for ambiguity and missing context, and optionally refined with deterministic rules, a local Small Language Model (SLM), or both.

No cloud inference dependency. No telemetry. No subscription. No prompt-shaped cargo cult.

Just a better prompt before the expensive machine gets involved.

- **Source:** https://github.com/pr0z4k/promptsmith-cli
- **Issues:** https://github.com/pr0z4k/promptsmith-cli/issues
- **Releases:** [CHANGELOG.md](CHANGELOG.md)
- **License:** [MIT](LICENSE)

## Why PromptSmith exists

Every AI conversation starts with a prompt.

Most prompts are written in a hurry. They are vague, underspecified, missing context, or quietly depend on assumptions that exist only inside the author's head. The model then produces a mediocre answer and everyone begins the traditional ritual of regenerating it five times.

PromptSmith breaks this cycle.

Instead of fixing a bad response after the fact, it performs a local preflight before the prompt reaches ChatGPT, Claude, Gemini, Copilot, a local model, or whatever impressive new autocomplete has appeared this week.

```text
Prompt
  |
  v
Deterministic analysis
  |
  +-- readiness score
  +-- missing context
  +-- ambiguity and smells
  +-- recommended profile
  +-- clarifying challenges
  |
  v
Optional refinement
  |
  +-- rules
  +-- local SLM
  +-- hybrid
  |
  v
A better prompt
```

AI models are becoming cheaper (sort of...). Human attention is not.

Spending thirty seconds improving a prompt is usually cheaper than spending ten minutes runing adversary network mental frameworks with a poor response.

## PromptSmith is not

PromptSmith is deliberately narrow.

It is not:

- a cloud prompt manager
- a prompt marketplace
- an AI chatbot
- an OpenAI wrapper
- an agent framework
- an MCP client
- a replacement for the model that will actually do the work

PromptSmith is a **prompt quality gateway**. It prepares a prompt, then gets out of the way. Software is allowed to have boundaries and roles.

## Design principles

### Local first

Prompt content remains on your machine unless you explicitly copy or export it. Deterministic analysis works offline. LLM and Hybrid refinement use local GGUF models through `llama-cpp-python`.

### Deterministic before generative

The analyzer does not need a model to tell you that a prompt lacks context, constraints, an expected format, or a clear outcome. Rules handle the predictable work first. A local model is used only where generation can add value.

### Terminal native

PromptSmith is built for the place where developers and technical teams already work. It is a Textual TUI, not a browser application wearing a terminal costume, besides, it looks cool.

### One job, done properly

PromptSmith improves prompts. Features that do not serve that job should have an excellent argument before they are allowed through the door.

### Human time matters more than tokens

Saving tokens is useful. Saving attention, retries, and frustration is better.

## Features

- Deterministic prompt scoring from 0 to 100
- Missing-context, ambiguity, smell, and challenge detection
- Rule, local LLM, and Hybrid refinement backends
- 35 built-in profiles and 22 built-in templates
- Editable user profiles that survive upgrades
- Secure preset and custom GGUF downloads
- Runtime model switching without restarting the application
- Local SQLite prompt history with JSON and CSV export
- Responsive terminal interface usable at approximately 80 columns
- Native portable builds for macOS, Linux, and Windows
- No cloud API keys or remote inference service required

## Requirements

For a source installation:

- Python 3.10 through 3.14
- macOS, Linux, or Windows
- A terminal with Unicode support
- Enough memory for the selected GGUF model
- Network access only for dependency or model downloads

Model guidance:

- **TinyLlama:** useful on lower-resource systems
- **Phi-4-mini Q4_K_M:** approximately 2.5 GB on disk; 16 GB system RAM recommended

Portable-build users do not need Python, pip, Git, or a compiler. They need only a compatible operating system and enough memory for any bundled model.

## Installation

### From source

Run from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
promptsmith
```

Windows PowerShell activation:

```powershell
.venv\Scripts\Activate.ps1
```

A standard installation includes the local SLM runtime. The historical `[llm]` extra remains accepted for compatibility but is no longer required.

Verify the installation:

```sh
promptsmith --version
```

Expected shape:

```text
PromptSmith-cli 1.0.0 (1)
```

## Quick start

1. Launch `promptsmith`.
2. Enter a prompt in the editor.
3. Press `Ctrl+Enter` to analyze it.
4. Review readiness, missing elements, smells, recommendations, and clarifying challenges.
5. Select a profile and, optionally, a template.
6. Press `Ctrl+R` to refine.
7. Copy or export the result to the AI system that will actually perform the task.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+Enter` | Analyze the current prompt |
| `Ctrl+R` | Refine the current prompt |
| `Ctrl+Shift+A` | Focus the prompt editor and select all prompt text |
| `Ctrl+Y` | Copy refined output |
| `Ctrl+S` | Save configuration |
| `Ctrl+Q` | Quit, or return from Settings |
| `Up` / `Down` | Scroll output |

On macOS, `Cmd+A` is usually consumed by the terminal and selects terminal content. Use `Ctrl+Shift+A` for PromptSmith's in-app **Select Prompt** action.

## How refinement works

Analysis always runs first and remains deterministic. Refinement behavior is selected per profile.

| Backend | Behavior | Model required |
|---|---|---:|
| `rule` | Builds a structured prompt while preserving profile constraints | No |
| `llm` | Rewrites the prompt through the selected local GGUF model | Yes |
| `hybrid` | Builds a deterministic scaffold, then asks the local model to polish it | Yes |

The Hybrid backend falls back to deterministic output if the model is unavailable. A missing model should reduce capability, not turn the application into a decorative traceback generator.

## Profiles and templates

Profiles describe the role, domain, tone, output format, constraints, vendor assumptions, and refinement backend for a task.

Templates provide reusable prompt structures. They are optional and receive the prompt editor content as their logical input.

Built-in content is packaged under:

```text
src/promptsmith/data/profiles/
src/promptsmith/data/templates/
```

Persistent user overrides normally live under:

```text
~/.promptsmith/profiles/
~/.promptsmith/templates/
```

Portable builds keep user data beside the executable under `user_data/`.

A user file with the same name as a built-in entry overrides the packaged copy without modifying it. Profile changes made through the editor are reloaded immediately.

## Local models

Open **Settings -> Download LLM Models** to download the built-in presets:

- Microsoft Phi-4-mini-instruct Q4_K_M
- TinyLlama 1.1B Chat Q4_K_M

Preset downloads use HTTPS streaming, redirect validation, retries, GGUF header validation, known SHA-256 verification where supplied, partial-file cleanup, `fsync`, and atomic promotion into the model directory.

Use **Settings -> Switch Model** to select a downloaded model. Cached LLM and Hybrid backends detect model-path changes and load the new model without requiring an application restart.

Custom downloads must use a `.gguf` filename. HTTPS is strongly recommended. PromptSmith validates the GGUF header, but a custom model without a supplied checksum cannot receive the same identity verification as a built-in preset.

## Prompt history

Every successful refinement is recorded in a local SQLite database with:

- original prompt
- refined output
- timestamp
- profile and template
- backend and model
- analysis metadata

The History screen supports preview, copying, deletion, complete clearing, and JSON or CSV export.

History is stored unencrypted and contains full prompt and output text. It has no automatic retention limit. Clear it after sensitive work on shared systems, because privacy policies are less useful after someone has already opened the database.

Typical locations:

```text
~/.promptsmith/history.db
user_data/history.db   # portable build
```

## Configuration

PromptSmith uses `config.yaml` plus profile and template YAML files.

| Setting | Required | Default | Purpose |
|---|---:|---|---|
| `default_profile` | No | `general` | Profile selected at startup |
| `default_template` | No | none | Template selected at startup |
| `llm.model_path` | No | first valid `.gguf` in `models/` | Explicit local model path |

Configuration precedence:

```text
built-in defaults -> config.yaml -> user overrides -> runtime Settings choices
```

## Native portable builds

PromptSmith can be packaged as a self-contained folder and ZIP for users without Python installed. PyInstaller builds are native to the operating system that creates them; it does not cross-compile merely because humans would find that convenient.

| Target | Build on | Command | Output |
|---|---|---|---|
| macOS | macOS | `./build_cli.sh` | `dist/PromptSmith-cli-<version>-macos-<arch>.zip` |
| Linux | Linux | `./build_cli.sh` | `dist/PromptSmith-cli-<version>-linux-<arch>.zip` |
| Windows | Windows | `build_windows.bat` | `dist\PromptSmith-cli-<version>-windows-x64.zip` |

Prepare the build environment:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
```

Download any GGUF models you want to bundle before building. Omitting models creates a smaller artifact where deterministic Rules work immediately and models can be downloaded later from Settings.

Each ZIP contains:

```text
PromptSmith-cli-<version>-<platform>/
├── PromptSmith-cli(.exe)
├── platform launcher (.command, .sh, or .bat)
├── profiles/
├── templates/
├── models/
├── config.yaml
├── READ ME FIRST.txt
└── _internal/
```

Unsigned community builds may trigger Gatekeeper or SmartScreen. That is expected until releases are signed and, on macOS, notarized. Do not disable operating-system security globally to make a hobby project feel more authoritative.

See [BUILD.md](BUILD.md) for dependency checks, model bundling, signing behavior, artifact verification, and distribution details.

## Architecture

PromptSmith separates:

- deterministic analysis
- profile and template storage
- backend orchestration
- local model execution
- secure model acquisition
- SQLite history
- Textual presentation

Backend instances are reused for performance. Runtime model-path refresh prevents cached backends from continuing to use stale models.

See [ARCHITECTURE.md](ARCHITECTURE.md) for data flow, boundaries, invariants, failure behavior, and the source map.

## Security and privacy

- Prompt content stays local unless manually copied or exported.
- No account, API key, or cloud inference service is required.
- Model downloads are the primary outbound network activity.
- Logs are written to the PromptSmith user-data directory and must not contain prompt bodies.
- History and model files should be backed up only when their contents are acceptable to retain.

See [SECURITY.md](SECURITY.md) for the threat model, security boundaries, and reporting process.

## Development

Install the development and build toolchains:

```sh
python -m pip install -e ".[dev,build]"
```

Run the complete release validator:

```sh
python tools/validate_release.py --keep-going
```

The validator runs formatting, import sorting, linting, type checking, tests, package build, Twine checks, and a clean wheel-install smoke test.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

### 1.1

- split the large TUI module into clearer screen and service boundaries
- expand deterministic analysis rules
- improve history navigation and filtering
- add more focused profiles and templates
- strengthen model integrity verification
- continue accessibility and narrow-terminal testing

### Later

- reproducible lockfiles and builds
- SBOM generation
- signed release artifacts
- macOS notarization and Windows signing (like in a looong time)

The roadmap is intentionally modest. PromptSmith is your helper, not GLaDOS.

## Release information

- [Changelog](CHANGELOG.md)
- [Release checklist](RELEASE_CHECKLIST.md)
- [v1.0 release notes](RELEASE_NOTES.md)

## Contributing

Bug reports, focused improvements, tests, and profile or template contributions are welcome.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. New features should preserve the local-first model and support PromptSmith's primary job: improving a prompt before it reaches another AI system.

## License

PromptSmith-cli is released under the [MIT License](LICENSE).

## Acknowledgements

PromptSmith builds on Textual, llama.cpp through `llama-cpp-python`, PyInstaller, SQLite, and the GGUF model ecosystem distributed through Hugging Face.

The dependencies do the difficult low-level work. PromptSmith merely arranges them into a useful machine and then pretends the terminal was always supposed to glow green.