# PromptSmith-cli

> A local-first prompt quality gateway that analyzes and refines prompts before they consume remote AI tokens.

PromptSmith-cli combines deterministic prompt analysis with local small language model (SLM) refinement. It scores prompt readiness, surfaces ambiguity and missing context, applies reusable profiles and templates, and keeps a local history of prompt evolution.

- Source: https://github.com/pr0z4k/promptsmith-cli
- Issues: https://github.com/pr0z4k/promptsmith-cli/issues
- Releases: [CHANGELOG.md](CHANGELOG.md)
- License: [MIT](LICENSE)

## Why this exists

Weak prompts waste time, tokens, and attention. PromptSmith performs a local preflight before a prompt reaches another AI system:

```text
Prompt -> Analyze -> Challenge -> Refine -> Verify -> Export
```

Deterministic analysis remains available without loading a model. LLM and Hybrid profiles use a local GGUF model through `llama-cpp-python`, so prompt content stays on the machine.

## Features

- Deterministic prompt scoring from 0 to 100
- Missing-context, ambiguity, smell, and challenge detection
- Rule, local LLM, and Hybrid refinement backends
- 35 built-in profiles and 22 built-in templates
- Editable user profiles that survive upgrades
- Secure preset and custom GGUF downloads
- Runtime model switching without restarting the application
- Local SQLite prompt history with JSON and CSV export
- Terminal UI that remains usable at approximately 80 columns
- Native portable builds for macOS, Linux, and Windows

### Non-goals

- PromptSmith is not a cloud prompt manager or model-hosting service.
- It does not send prompts to remote inference APIs.
- It does not replace the target coding assistant, chatbot, or model.
- It does not guarantee that a small local model will improve every prompt.

## Prerequisites

For a source installation:

- Python 3.10 through 3.14
- macOS, Linux, or Windows
- A terminal with Unicode support
- Enough memory for the selected GGUF model
  - TinyLlama: suitable for lower-resource systems
  - Phi-4-mini Q4_K_M: approximately 2.5 GB on disk; 16 GB system RAM recommended
- Network access only when downloading models or dependencies

Recipients of a portable ZIP do not need Python, pip, Git, or a compiler. They need only a compatible operating system and enough memory for any bundled model.

## Quick start

Run from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
promptsmith
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

A standard installation includes the local SLM runtime. The historical `[llm]` extra remains accepted for compatibility but is no longer required.

### Verify

```sh
promptsmith --version
```

Expected result:

```text
PromptSmith-cli <installed version> (...)
```

Then launch `promptsmith`, enter a prompt, and press `Ctrl+Enter` to analyze it.

## Build native portable packages

PromptSmith can be packaged as a self-contained folder and ZIP for people who do not have Python installed. Builds are native to the operating system that creates them because PyInstaller does not cross-compile.

| Target | Build on | Command | Output |
|---|---|---|---|
| macOS | macOS | `./build_cli.sh` | `dist/PromptSmith-cli-<version>-macos-<arch>.zip` |
| Linux | Linux | `./build_cli.sh` | `dist/PromptSmith-cli-<version>-linux-<arch>.zip` |
| Windows | Windows | `build_windows.bat` | `dist\PromptSmith-cli-<version>-windows-x64.zip` |

Prepare the build environment first:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
```

Windows PowerShell equivalent:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
```

Download any GGUF models you want to include before building. The build scripts copy the contents of `models/` into the portable package. Omitting models produces a smaller package where deterministic Rules work immediately and the recipient can download a model later from Settings.

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

### Share the ZIP

The generated ZIP is the distributable artifact. You can attach it to a GitHub release, copy it to shared storage, or send it directly to friends or teammates.

The recipient:

1. Downloads and extracts the complete ZIP.
2. Keeps the extracted folder together. The executable depends on `_internal/` and the adjacent data folders.
3. Starts PromptSmith with the included launcher.
4. Handles the operating-system security prompt on first launch:
   - macOS: right-click the launcher, choose **Open**, then confirm **Open**.
   - Windows: choose **More info**, then **Run anyway** if SmartScreen appears.
   - Linux: ensure the launcher is executable with `chmod +x start-promptsmith-cli.sh` when archive permissions were not preserved.

Unsigned community builds may trigger Gatekeeper or SmartScreen. That is expected until releases are signed and, on macOS, notarized. Do not advise recipients to disable operating-system security globally.

Portable ZIPs are platform- and architecture-specific. A macOS Apple Silicon build will not run on Windows, Linux, or an Intel-only Mac. Build and label each artifact separately.

See [BUILD.md](BUILD.md) for native dependency checks, model bundling, signing behavior, artifact verification, and release distribution details.

## Configuration

PromptSmith uses `config.yaml` plus profile and template YAML files.

| Setting | Required | Default | Secret | Purpose |
|---|---:|---|---:|---|
| `default_profile` | No | `general` | No | Profile selected at startup |
| `default_template` | No | none | No | Template selected at startup |
| `llm.model_path` | No | first valid `.gguf` in `models/` | No | Explicit local model path |

Configuration precedence is:

```text
built-in defaults -> config.yaml -> user profile/template overrides -> runtime Settings choices
```

User data normally lives under `~/.promptsmith/`. Portable builds use a `user_data/` directory beside the executable.

## Usage

1. Enter a prompt in the editor.
2. Press `Ctrl+Enter` to analyze it.
3. Review readiness, missing elements, smells, recommendations, and clarifying challenges.
4. Select a profile and optional template.
5. Press `Ctrl+R` to refine.
6. Copy or export the result.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+Enter` | Analyze |
| `Ctrl+R` | Refine |
| `Ctrl+Shift+A` | Focus the prompt editor and select all prompt text |
| `Ctrl+Y` | Copy refined output |
| `Ctrl+S` | Save configuration |
| `Ctrl+Q` | Quit, or return from Settings |
| `Up` / `Down` | Scroll output |

On macOS, `Cmd+A` is usually consumed by the terminal application and selects terminal content. Use `Ctrl+Shift+A` for PromptSmith's in-app Select Prompt action.

## Backends

Backends are selected per profile through the `backend` field.

| Backend | Behavior |
|---|---|
| `rule` | Deterministic refinement that preserves profile constraints and is always available |
| `llm` | Direct rewrite through the selected local GGUF model |
| `hybrid` | Rule refinement followed by local-model polishing, with deterministic fallback |

Analysis and challenge generation are deterministic and run before backend selection.

## Local models

Open **Settings -> Download LLM Models** to download the built-in presets:

- Microsoft Phi-4-mini-instruct Q4_K_M
- TinyLlama 1.1B Chat Q4_K_M

Preset downloads use HTTPS streaming, redirect validation, retries, GGUF validation, known SHA-256 verification where supplied, partial-file cleanup, `fsync`, and atomic promotion into the model directory.

Use **Settings -> Switch Model** to select a downloaded model. Cached LLM and Hybrid backends detect model-path changes, unload the old model, and load the new model during the same application session.

Custom downloads must use HTTPS and a `.gguf` filename. PromptSmith validates the GGUF header, but a custom model without a supplied checksum cannot receive the same identity verification as a built-in preset.

## Profiles and templates

Built-ins are packaged under `src/promptsmith/data/`.

Persistent user overrides live under:

```text
~/.promptsmith/profiles/
~/.promptsmith/templates/
```

A user file with the same name as a built-in entry overrides it without modifying the shipped copy. Profile changes made through the editor are reloaded immediately, including backend changes.

Templates should use one logical prompt input. Multiple placeholders are filled from the same editor content.

## Prompt history

Every successful refinement is recorded in a local SQLite database. History stores timestamps, selected profile and template, backend and model, original and refined prompts, and analysis metadata.

The History screen supports preview, deletion, complete clearing, and JSON or CSV export.

History is stored unencrypted. It contains full prompt and output text and has no automatic retention limit. Clear it after sensitive work on shared systems.

Typical locations:

```text
~/.promptsmith/history.db
user_data/history.db   # portable build
```

## Architecture

The application separates deterministic analysis, profile/template storage, backend orchestration, local model execution, secure model acquisition, and SQLite history. Backend instances are reused for performance, while runtime model-path refresh prevents stale cached models.

See [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries, data flow, invariants, failure behavior, and the source map.

## Operations and security

- Prompt content remains local unless the user manually exports or copies it elsewhere.
- No account, token, or cloud inference service is required.
- Model downloads are the primary outbound network activity.
- Logs are written to the PromptSmith user-data directory and must not include prompt bodies.
- Models and history should be backed up only when their local contents are acceptable to retain.

See [SECURITY.md](SECURITY.md).

## Troubleshooting

### A preset model fails to download

Check the status-bar error, network access, free disk space, and whether a stale `.part` file remains. Restart the download after upgrading to current `main`.

### A selected model is not used

Use **Settings -> Model Status** to inspect the last backend and model. Re-select the model and run another refinement; switching should not require an application restart.

### A portable build does not start

Confirm that the whole extracted folder is intact, not only the executable. Review `READ ME FIRST.txt`, then run the executable from a terminal to see the actual error. On Windows, install the Microsoft Visual C++ Redistributable if the bundled llama.cpp libraries cannot load.

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for additional cases.

## Development

```sh
python -m pip install -e ".[dev,build]"
python tools/validate_release.py --keep-going
```

The release validator runs formatting, linting, type checking, tests, package build, Twine checks, and a clean wheel-install smoke test.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Releases

See [CHANGELOG.md](CHANGELOG.md) and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Article

PromptSmith-cli is a candidate for a future prozak.org article after the v1 release is frozen and reproducible from a clean environment.

## License

[MIT](LICENSE)

## Acknowledgements

PromptSmith builds on Textual, llama.cpp through `llama-cpp-python`, PyInstaller, and the GGUF model ecosystem published through Hugging Face.
