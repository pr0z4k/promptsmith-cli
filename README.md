# PromptSmith-cli

**A local-first Prompt Quality Gateway** - analyzes, challenges, and prepares
your prompts before they consume AI tokens, so you spend compute on a
well-formed request instead of a vague one.

**100% Open Source · Local Only · Zero Commercial Dependencies**

- Home: https://codeberg.org/prozak/promptsmith-cli
- Issues / support: https://codeberg.org/prozak/promptsmith-cli/issues
- History: [CHANGELOG.md](CHANGELOG.md)
- License: MIT

The version is defined once, in `pyproject.toml`, and flows automatically
into the About screen, `--version`, and build artifact names - check
`promptsmith --version` for what you're running.

## Quick start

From a source checkout:

```bash
pip install -e .
promptsmith
```

Once published on PyPI as `promptsmith-cli`:

```bash
pip install promptsmith-cli
promptsmith        # or: promptsmith-cli - both launch the same app
```

For a standalone executable that needs no Python install at all, see
[BUILD.md](BUILD.md).

## The pipeline

```
Prompt -> Analyze -> Challenge -> Prepare -> Output
```

- **Analyze**: detects prompt type, scores readiness (0-100), flags
  ambiguous terms ("modern", "best", "optimize"), and recommends a profile
  - all deterministic, no LLM required, instant.
- **Challenge**: a small set of rule-based clarifying questions surfaced
  alongside the analysis - things like "what should actually vary here?"
  or "who is this for?" when the prompt doesn't say. Informational only,
  never blocks Refine, and applies identically no matter which profile,
  template, or backend you're using. Deliberately not LLM-generated:
  writing a genuinely useful clarifying question is a harder reasoning
  task than rewriting a prompt, and small local models aren't reliable at
  it - this only shows what a cheap, deterministic check can actually
  catch.
- **Prepare**: refines the prompt using your selected profile and
  (optional) template, through whichever backend that profile is
  configured to use.

## Backends

Set per-profile via the `backend:` field (default `rule`):

| Backend  | What it does |
|----------|--------------|
| `rule`   | Deterministic template/constraint application. Instant, free, always available, and guarantees every constraint from the profile survives verbatim in the output. |
| `llm`    | The local model rewrites the prompt directly, guided by the profile's role/domain/tone/format. More natural phrasing, but a small model can occasionally misunderstand the task or need a retry. |
| `hybrid` | Runs `rule` first (guaranteeing completeness), then asks the LLM to polish that already-complete text into clearer prose - falls back to the pure rule-based text if the LLM is unavailable or the polish looks broken. |

Whichever backend a profile uses, Analyze and Challenge behave identically -
they run before a backend is ever selected.

## Usage

1. Enter a rough prompt in the input box (multi-line supported)
2. **Ctrl+A** to analyze, or **Ctrl+R** to analyze + refine in one step
3. Review the analysis: type, score, missing elements, smells, and
   anything worth clarifying
4. Select a profile (auto-recommended based on your prompt) and,
   optionally, a template
5. **Ctrl+R** to refine
6. **Ctrl+Y** to copy the result

## Keyboard shortcuts

| Key      | Action          |
|----------|-----------------|
| Ctrl+A   | Analyze only    |
| Ctrl+R   | Refine (analyze + prepare) |
| Ctrl+Y   | Copy result     |
| Ctrl+S   | Save config     |
| Ctrl+Q   | Quit (or Back, on Settings) |
| ↑ / ↓    | Scroll the output box |

Buttons for Refine, Copy, Clear (wipes the input - there's no select-all
in the text box), Export, Analyze, History, and Settings sit below the
input box. On a narrow terminal the button row wraps onto a second line
so every button stays reachable.

## Look and feel

The public release renders black-on-green, in the spirit of a
green-phosphor terminal. If you're staring at green shades, you're
running the open-source PromptSmith-cli build.

## Prompt history

Every successful refine (Ctrl+R) is recorded to a local SQLite database,
so you build up a running record of what you asked, what the analyzer
flagged, and what came back. Open it with the **[ History ]** button on
the main screen.

The history browser shows your entries newest-first in a grid, with a
preview of the highlighted row and these actions:

- **Copy Refined** - copy the selected entry's refined output to the
  clipboard
- **Delete** - remove the selected entry
- **Export JSON** / **Export CSV** - write the *entire* history to a file
  under `exports/` (JSON preserves the full nested analysis; CSV flattens
  the key fields plus a raw-JSON column, so it opens cleanly in a
  spreadsheet)
- **Clear All** - wipe the history. This is a two-step action: the first
  press arms it (the button changes to "Confirm Clear?"), and only a
  second press actually deletes, so a misclick can't wipe your history.
  Pressing any other button cancels. There's no automatic size cap, so
  Clear All is how you reset.

The database lives in the user data directory
(`~/.promptsmith/history.db` from source, or `user_data/history.db` next
to the executable in a portable build) and uses Python's standard-library
`sqlite3` - no third-party dependency. History is best-effort: if the
database can't be opened, the feature disables itself and the rest of the
app is unaffected.

A note on privacy and retention: history is stored **unencrypted** in the
local SQLite file, and it keeps your full prompt text and refined output
in plaintext. That's a deliberate local-first tradeoff (the data never
leaves your machine, and a plain file is inspectable and portable), but it
means anyone with read access to your user directory can read your prompt
history. There is no automatic retention limit or expiry yet - the file
grows until you Clear All (or delete `history.db` directly). If you work
with sensitive prompts on a shared machine, clear your history when you're
done, or delete the database file.

## Settings

- **Export Source Code** - the project's source, packaging files
  (`pyproject.toml`, build scripts), and docs, ready to hand to someone
  to build themselves or move to another machine. This is source for
  rebuilding, not a runnable application on its own - it doesn't include
  a Python runtime or compiled dependencies. For an actual standalone
  executable, see [BUILD.md](BUILD.md). Excludes `.venv`, `__pycache__`,
  downloaded models, and prior exports.
- **Export Profiles** / **Export Templates** - the data, zipped,
  including any user overrides/additions (see below), not just what
  ships built-in.
- **Download LLM Models** - the built-in presets (see below), or **Download
  From URL** for any other direct `.gguf` link
- **Model Status** - what's downloaded on disk, and what backend/model
  actually served your last refinement
- **About** - product, version (read live from the package metadata),
  project link, license, and a Get Support button that opens the issue
  tracker

On the main screen, **[ Export ]** is different from the above - it saves
your *current session* (the prompt you're working on, the profile/template
used, and the refined output) to a timestamped markdown file, not the
source code.

## Profiles and templates

35 profiles and 22 templates ship built-in, covering software
engineering, cloud, architecture, business, and content roles - from
`react-developer` and `cloud-engineer-aws` to `technical-writer` and
`vibe-coding` (general AI-assisted software engineering).

Built-ins live inside the package (`src/promptsmith/data/`); in a
standalone build they appear as visible `profiles/` and `templates/`
folders next to the executable.

Two ways to add your own:

- **Built-in directories** - drop a `.yaml` file in and restart. Simple,
  but anything added here is lost the next time the app is updated or
  rebuilt from a fresh copy.
- **User directory** (`~/.promptsmith/profiles/`,
  `~/.promptsmith/templates/`; in a standalone build, the `user_data/`
  folder next to the executable) - the same idea, but this survives
  updates. A file here with the *same name* as a built-in profile
  overrides it (lets you customize `vibe-coding` without touching the
  shipped copy); a file with a new name is simply added alongside the
  built-in ones. This is the recommended place for anything you want to
  keep long-term.

Templates should use a single `{placeholder}` - the UI has one input
field, so a template with multiple distinct placeholders will have all
of them filled with the same text.

## LLM support (optional)

Install the LLM extra, then download a model (Settings > Download LLM
Models, or Settings > Download From URL for a custom `.gguf`):

```bash
pip install -e ".[llm]"
```

On Windows, if pip tries to compile llama-cpp-python from source and
fails, install a prebuilt CPU wheel instead:

```bash
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

The default preset is **Phi-4-mini-instruct** (Q4_K_M, ~2.5GB) - Microsoft's
small instruct model, MIT-licensed. A TinyLlama 1.1B preset is also
available for lower-resource machines.

By default the LLM backend auto-detects the first `.gguf` file in
`models/`. To pin a specific model explicitly, set `llm.model_path` in
`config.yaml`. Set a profile's `backend: llm` or `backend: hybrid` to route
its refinements through the local model.

Note: there's no RAM/resource check before loading a model - make sure your
machine has enough free memory for whichever `.gguf` you're using.

Downloaded models are validated by their GGUF header (the format's magic
number), so a URL that returns an error page, an empty response, or an
otherwise non-GGUF file is rejected up front rather than failing later
inside the model loader. This is a fast 4-byte header check, not a full
content hash: it catches files that aren't GGUF at all, but not a file
that starts with a valid header and is then truncated or corrupted
further in - detecting that would need a full content hash (a possible
future addition). Custom downloads over plain `http://` are permitted but
warn, since the file can't be verified against tampering in transit;
prefer `https://` when the source offers it.

## Development

```bash
pip install -e ".[dev]"
python -m pytest src/tests    # full regression suite
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions, and
[CHANGELOG.md](CHANGELOG.md) for the full fix/feature history.

## License

MIT
