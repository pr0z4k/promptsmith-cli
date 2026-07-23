# PromptSmith-cli troubleshooting

## Installation

### `llama-cpp-python` fails to install

**Likely cause:** pip could not find a compatible wheel and attempted a native build without the required compiler toolchain.

**Check:**

```sh
python --version
python -m pip --version
```

**Fix:** Upgrade pip and retry the standard installation:

```sh
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows, a prebuilt CPU wheel may be required:

```sh
python -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python -m pip install -e .
```

Verify:

```sh
promptsmith --version
```

### `promptsmith` is not found

**Likely cause:** The virtual environment is inactive or the package was installed into another Python environment.

**Check:**

```sh
python -m pip show promptsmith-cli
```

**Fix:** Activate the intended environment and reinstall:

```sh
source .venv/bin/activate
python -m pip install -e .
```

## Model downloads

### Phi-4-mini returns HTTP 401, 403, or another download error

**Likely cause:** An outdated PromptSmith build used an obsolete model URL, the host returned a transient storage error, or network policy blocked the redirect.

**Check:**

```sh
promptsmith --version
```

Upgrade to current `main` or the latest release, ensure outbound HTTPS is available, and retry **Settings -> Download LLM Models**.

PromptSmith should download the preset through its secure streaming path and verify the known checksum before promotion.

### Download fails with `bad value(s) in fds_to_keep`

**Likely cause:** The installed build used the Hugging Face Hub transfer implementation from an earlier release candidate inside a Textual worker thread on macOS.

**Fix:** Upgrade to a version containing PR #10 or later. The current implementation uses PromptSmith's streamed HTTPS downloader and does not invoke that transfer path.

### A `.part` file remains

**Likely cause:** The process was forcibly terminated before normal cleanup.

**Check:** Inspect the PromptSmith model directory for `*.part` files.

**Fix:** Close PromptSmith, delete only the stale `.part` file, and retry. Do not delete a valid `.gguf` unless its checksum or GGUF validation fails.

### Custom model download is rejected

**Likely cause:** The URL is not HTTPS, the filename is unsafe, the response is not a regular GGUF file, or a redirect violates download policy.

**Fix:** Use a direct HTTPS URL ending in `.gguf` from a trusted publisher. Custom downloads without a checksum receive GGUF-header validation but not cryptographic identity verification.

## Model loading and switching

### The selected model does not change during the session

**Likely cause:** The application is older than the runtime model-refresh fix, or the selected path no longer exists.

**Check:** Open **Settings -> Model Status** and inspect the last model used.

**Fix:** Upgrade, select the model again, and run another refinement. Current versions unload the cached model and load the newly configured model before the next LLM or Hybrid inference.

### `No model path configured`

**Likely cause:** No valid `.gguf` exists in the model directory and `llm.model_path` is unset.

**Fix:** Download a preset or custom model, then select it through **Settings -> Switch Model**.

### The model cannot be loaded

**Likely cause:** The path is missing, the file is truncated or invalid, the model format is unsupported, or the system lacks memory.

**Check:**

- Confirm the file exists and ends in `.gguf`.
- Use **Settings -> Model Status**.
- Check available memory.

**Fix:** Redownload the preset or select a smaller model. TinyLlama is the lower-resource fallback.

### The model runs out of memory

**Behavior:** PromptSmith unloads the model. Hybrid should return its deterministic Rule result.

**Fix:** Close other applications, select TinyLlama, reduce competing workloads, or use a Rule profile.

## Refinement output

### `Model output contained no usable answer after reasoning was removed`

**Likely cause:** An older build deleted the entire output when a non-reasoning model emitted an unmatched `<think>` marker.

**Fix:** Upgrade to a version containing PR #10 or later. Current cleanup removes the stray marker while preserving usable text.

If the error persists, use Hybrid. Hybrid retains the deterministic result when model polish is unusable.

### Hybrid output is identical to Rule output

**Likely cause:** The local model was unavailable, returned an empty or malformed answer, or produced a result that failed degeneration checks.

**Behavior:** This is intentional safe fallback.

**Check:** Use **Settings -> Model Status** and inspect the status bar after refinement.

### A small model misunderstands the task

**Likely cause:** Tiny local models have limited reasoning and instruction-following capacity.

**Fix:** Use Hybrid, try Phi-4-mini, strengthen the prompt/profile, or retry. PromptSmith does not guarantee that every local-model rewrite improves the input.

## Terminal interface

### `Cmd+A` selects the terminal instead of the prompt

**Likely cause:** The macOS terminal application consumes `Cmd+A` before Textual can receive it.

**Fix:** Use `Ctrl+Shift+A` to focus the prompt editor and select all prompt text.

### The Analysis box says `Enter a prompt and press or`

**Likely cause:** An older Textual rendering path interpreted bracketed shortcut names as markup.

**Fix:** Upgrade. Current versions render the instruction as literal Textual `Content`.

### Buttons or modals overflow

**Fix:** Use a terminal width of approximately 80 columns or greater. Current layouts wrap the action buttons and have been manually validated at narrow width.

### Arrow keys move the cursor instead of scrolling output

**Likely cause:** The prompt editor still has focus.

**Fix:** Click or tab away from the editor, or use the terminal mouse/scroll support on the output area.

## Profiles and templates

### A profile edit does not appear

**Check:** Confirm the save succeeded and the profile appears in the selector.

Current versions reload profile options after editing. Built-in profiles are not modified directly; saving creates or updates a user override.

### Changing a profile backend has no effect

**Fix:** Save the profile and run a new refinement. Backend selection is evaluated per run. Verify the actual backend/model in History or Model Status.

### Invalid profile data is rejected

**Behavior:** The editor should retain the prior valid configuration rather than saving malformed YAML or an unsupported backend.

Correct the highlighted values and save again.

## History

### History is unavailable

**Likely cause:** The SQLite file could not be opened or recovered.

**Check:** Inspect the PromptSmith user-data directory and application log.

**Behavior:** History disables itself; analysis and refinement continue.

**Fix:** Back up the directory, close PromptSmith, and move the damaged `history.db` aside. Restart to create a clean database. Preserve any quarantined file for manual recovery.

### History contains sensitive prompts

History is plaintext and has no automatic expiry.

Use **History -> Clear All** or delete individual entries. On shared machines, clear history and remove sensitive exports after use.

### CSV export looks flattened

This is expected. CSV contains common fields plus serialized analysis data. Use JSON export when exact nested analysis structure matters.

## Logs and diagnostics

The log file lives in the PromptSmith user-data directory. Logs should contain operational events, paths, model names, and exception classes, not prompt or refined-output bodies.

Before sharing diagnostics:

1. Search for prompt fragments, tokens, domains, usernames, and private paths.
2. Remove or replace sensitive values.
3. Include the PromptSmith version, operating system, Python version, selected backend, and model filename.

## Release validation

Run from a clean development environment:

```sh
python -m pip install -e ".[dev,build]"
python tools/validate_release.py --keep-going
```

Review `release-validation.json`. Do not treat a GitHub Actions job that failed before checkout because of exhausted account minutes as a repository test failure or success.