# PromptSmith-cli 1.0.0

PromptSmith has reached its first stable release.

This is not a declaration that the software is finished. Software is never finished; it is merely released before everyone involved loses the will to continue. Version 1.0 means something more useful: the product has a clear purpose, a stable interface, and an engineering baseline worth supporting.

## What PromptSmith does

PromptSmith is a local-first prompt preflight tool for the terminal.

It analyzes prompts before they are sent to another AI system, scores their readiness, identifies ambiguity and missing context, recommends improvements, and can refine them with deterministic rules, a local Small Language Model, or a hybrid of both.

It does not try to become a chatbot, prompt marketplace, agent framework, cloud platform, or lifestyle brand.

It improves the prompt and gets out of the way.

## Why 1.0 now

The beta cycle established the core product and then spent the less glamorous but more important time making it dependable:

- the prompt analysis and refinement workflow is complete
- rule, local LLM, and Hybrid backends are integrated
- profiles and templates are packaged and user-overridable
- model downloads and runtime switching are supported
- local SQLite history is available with export and deletion controls
- the Textual interface is stable across supported terminal widths
- source, wheel, and native portable build paths are documented and validated
- CI covers supported Python versions and operating systems
- dependencies and development tooling are pinned
- package metadata and entrypoints are consolidated
- filesystem, download, logging, and failure behavior received dedicated hardening passes

That is enough to make a stable promise.

## Highlights

### Deterministic prompt analysis

Every prompt receives a readiness score from 0 to 100, along with missing elements, prompt smells, recommendations, and clarifying challenges. This works without loading a model.

### Three refinement backends

- **Rule:** deterministic structure and constraint preservation
- **LLM:** direct local-model rewriting
- **Hybrid:** deterministic scaffold followed by local-model polishing

### Local SLM support

PromptSmith uses GGUF models through `llama-cpp-python`. Built-in presets include Microsoft Phi-4-mini-instruct and TinyLlama, with support for custom GGUF downloads.

### Profiles and templates

The stable release includes 35 built-in profiles and 22 templates. User overrides live outside the packaged application and survive upgrades.

### Prompt history

Successful refines are stored locally in SQLite with their analysis metadata, selected profile, template, backend, and model. History can be reviewed, copied, deleted, cleared, or exported to JSON and CSV.

### Native terminal interface

The green-on-black Textual interface is intentionally terminal-native, keyboard-friendly, and usable at approximately 80 columns.

### Release engineering

Version 1.0 includes cross-platform CI, Python 3.10 through 3.14 support, package-build validation, pinned dependencies and toolchains, pre-commit checks, Dependabot, and a consolidated application entrypoint.

## Privacy model

PromptSmith requires no account, cloud inference API, or telemetry service.

Prompt content stays on the local machine unless the user explicitly copies or exports it. Model downloads are the primary outbound network activity.

Prompt history contains full prompt and output text in an unencrypted local SQLite database. Users should clear it after sensitive work on shared systems.

## Known limitations

Version 1.0 deliberately leaves several improvements for later releases:

- the main TUI module should be split into clearer screen and service boundaries
- deterministic lockfiles and fully reproducible builds are not yet implemented
- release artifacts are not yet signed or notarized
- SBOM generation is not yet part of the release pipeline
- custom GGUF downloads without a supplied checksum cannot receive preset-level identity verification
- history has no automatic retention policy or full-text search

These are real limitations, not hidden surprises wearing roadmap makeup.

## Upgrade notes

The package version is now `1.0.0`.

The canonical console entrypoints are:

```text
promptsmith
promptsmith-cli
```

Both resolve to:

```text
promptsmith.cli.app:main
```

Project and support links now point to the GitHub repository:

```text
https://github.com/pr0z4k/promptsmith-cli
https://github.com/pr0z4k/promptsmith-cli/issues
```

Existing user profiles, templates, history, and downloaded models remain in the PromptSmith user-data directory and are not replaced by an upgrade.

## Validation before tagging

Run the complete release validator from a clean environment:

```sh
python -m pip install -e ".[dev,build]"
python tools/validate_release.py --keep-going
```

Then verify the runtime version:

```sh
promptsmith --version
```

Expected output shape:

```text
PromptSmith-cli 1.0.0 (1)
```

Build native artifacts on each target operating system and attach them to the GitHub release only after their local smoke tests pass.

## Thank you

PromptSmith started as a practical answer to a practical annoyance: people waste a surprising amount of time asking expensive models to compensate for incomplete instructions.

Version 1.0 keeps the answer intentionally small.

Analyze the prompt. Improve it locally. Send something better.