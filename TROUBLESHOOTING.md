# PromptSmith-cli Troubleshooting

## The application does not start

Run the installed entry point from a terminal:

```bash
promptsmith --version
promptsmith
```

For a source checkout:

```bash
python -m pip install -e .
promptsmith
```

Confirm that the active Python version is supported:

```bash
python --version
```

PromptSmith declares support for Python 3.10 through 3.14.

## `llama-cpp-python` will not install

`llama-cpp-python` contains native code. On some systems pip may attempt a local compile that requires platform build tools.

Options:

1. install a compatible prebuilt wheel published by the llama-cpp-python project;
2. install the required compiler and CMake toolchain;
3. use PromptSmith without the `llm` extra and select the `rule` backend.

Wheel commands and indexes change over time. Use the upstream project documentation for the current platform-specific installation method.

## No local model is detected

Check that the file:

- ends in `.gguf`;
- is a regular file, not a symlink;
- has a valid GGUF header;
- is larger than the minimum plausibility threshold;
- is located in the PromptSmith model directory or referenced by `llm.model_path`.

A configured path that does not exist is ignored during discovery.

## Model loading fails

Common causes:

- the model architecture is unsupported by the installed llama.cpp version;
- the model is damaged or incomplete;
- the selected quantization requires more memory than is available;
- the installed `llama-cpp-python` build is incompatible with the machine.

PromptSmith reports a sanitized error and does not expose raw model-loader details in the UI. Operational details may appear in the local log without prompt or generated-output content.

## The model runs out of memory

Choose a smaller model or quantization and close other memory-heavy applications.

PromptSmith detects common Python, llama.cpp, CUDA, and Metal allocation failures. If inference runs out of memory, it unloads the active model so the application can continue. Hybrid profiles fall back to their deterministic result when possible.

## A model download is rejected

The downloader requires HTTPS and validates redirects. It rejects:

- plain HTTP URLs;
- embedded usernames or passwords;
- URL fragments;
- malformed hosts;
- control characters;
- unsafe filenames or destination paths;
- symlinked targets;
- files that fail size or GGUF-header checks;
- checksum mismatches when SHA-256 is supplied.

A server returning an HTML error page with a successful status will still fail GGUF validation, as it should. Calling the file `.gguf` does not make it a model, despite the optimism involved.

## History is unavailable

History is optional. Prompt analysis and refinement continue when SQLite history cannot initialize.

Check the user data directory for:

```text
history.db
history.db-corrupt-<timestamp>
```

When integrity checks fail, PromptSmith preserves the damaged database under a quarantine name and creates a clean database.

Common causes include:

- filesystem permissions;
- another process holding a long database lock;
- an unwritable user data directory;
- a symlink at the configured database path;
- storage corruption.

## Prompt history contains sensitive text

History is stored locally in plaintext SQLite. Use the History screen to delete entries or clear all history. You may also close PromptSmith and delete `history.db` directly.

There is no automatic expiry or encryption layer in the current release.

## Profiles or templates do not appear

Confirm that files:

- use a `.yaml` or supported YAML filename;
- contain a YAML mapping at the document root;
- satisfy the relevant schema;
- use a safe filename without path separators;
- are regular files rather than symlinks.

User overrides belong in:

```text
~/.promptsmith/profiles/
~/.promptsmith/templates/
```

Portable builds use `user_data/profiles/` and `user_data/templates/`.

Restart the application after adding files.

## A user profile replaced a built-in profile

This is expected when both files have the same base name. User data takes precedence so customizations survive package upgrades.

Rename or remove the user file to restore the built-in profile.

## Refinement falls back to rules

Rule fallback occurs when:

- a configured backend name is unknown;
- backend construction fails;
- local model loading fails;
- inference fails;
- the model returns no usable content;
- hybrid output appears truncated or degenerate.

The status display and refiner warning describe the safe failure summary. The deterministic result remains available.

## The TUI behaves strangely after an upgrade

Reinstall the development checkout or package dependencies cleanly:

```bash
python -m pip install --upgrade --force-reinstall -e .
```

For source development, remove stale caches only after closing the application:

```bash
find . -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf .pytest_cache .mypy_cache .ruff_cache
```

Use the platform-equivalent commands on Windows.

## GitHub Actions did not execute any steps

The repository owner may have exhausted the included Actions minutes for private repositories. In that state, jobs can fail or remain blocked before checkout and produce no meaningful workflow logs.

Run the documented local checks and record their results in the pull request. A zero-step hosted failure is not a test failure, but neither is it a passing run.

## Logs

The application writes `promptsmith.log` to the user data directory. Logs are intended for operational diagnostics and exclude prompt and generated-output content.

When reporting an issue, include:

- PromptSmith version;
- operating system;
- Python version;
- installation method;
- selected backend;
- model filename and quantization, when relevant;
- sanitized log excerpts;
- reproduction steps.

Do not attach `history.db` unless you have reviewed its plaintext contents.