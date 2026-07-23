# Changelog

## 0.6.0b2 - history feature, fixes, and hardening

Second beta. Adds prompt history, closes the wheel-install and button
regressions, hardens model downloads, and addresses two rounds of
external review.

### Fixed (second review pass)

- **Windows build misdetected an empty `models\` dir as containing one
  model.** A `for %%f in (*.gguf)` loop runs once with the literal
  unexpanded pattern when nothing matches (a cmd.exe quirk), so the
  "no models" warning was skipped and a model-less build looked like it
  had one. Now guarded with `if exist` and a per-file existence check.
- **Clear All in the history browser now requires confirmation.** It was
  a single irreversible press; it's now two-step (first press arms and
  relabels the button to "Confirm Clear?", second press executes, any
  other button cancels), so a misclick can't wipe the history.

### Documentation corrected (second review pass)

- History is no longer described as "searchable" - the browser has a grid
  and preview, not a search control.
- The GGUF validation description no longer claims to catch "truncated"
  files. The 4-byte header check catches files that aren't GGUF at all
  (error pages, empty responses); it does not catch a file that starts
  with a valid header and is then truncated - that needs a full content
  hash (a documented future item).
- Added a privacy/retention note: history is stored unencrypted in plain
  SQLite, keeps full prompt/output text, and has no automatic size cap;
  guidance added for sensitive-prompt and shared-machine use.

### Fixed

- **Wheel install lost all built-in profiles/templates on the second
  launch (release blocker).** In a `pip install`, `get_project_root()`
  falls back to `~/.promptsmith`, which is also where the user
  profile/template override dirs live. Once the app created
  `~/.promptsmith/profiles` as the *user* dir, the next launch's
  `get_asset_path("profiles")` resolved that same (empty) folder as the
  *built-in* dir - handing ProfileManager one path for both and dropping
  35 profiles to 0. `get_asset_path()` now branches on run mode: frozen
  builds still prefer the visible sibling folder next to the executable,
  but source/wheel installs prefer the packaged `promptsmith/data/` copy
  first, so the built-in lookup is independent of the user-data root.
  Reproduced across two launches in a clean external venv (35 -> 0 before,
  35 -> 35 after) and covered by tests for both run modes.
- **`python -m promptsmith.cli.app --version` emitted a runpy
  double-import warning.** `cli/__init__.py` imported `app` eagerly, so
  the module loaded twice (once as `promptsmith.cli.app`, once as
  `__main__`). The import is now lazy via module `__getattr__`, keeping
  `from promptsmith.cli import PromptSmithApp` working without the double
  load.

### Changed

- **Disabled the command palette (Ctrl+P).** Every color in the TUI is a
  fixed hex literal rather than a theme token, so Textual's built-in
  theme switcher changed nothing visible - and theme-switching would
  undercut the green-on-black identity that distinguishes the public
  build from the internal one. `ENABLE_COMMAND_PALETTE = False` removes
  the non-functional switcher and its `^p palette` footer hint.

### Hardened

- **Model files are now validated as real GGUF before being trusted.**
  Every valid GGUF starts with the 4-byte `GGUF` magic number; the
  downloader now checks it in two places. On download, the completed file
  is verified before the atomic rename, so a URL that returns an HTML
  error page, a login/consent wall, or any non-model body is rejected
  with a clear message (`InvalidModelFileError`) and leaves nothing
  behind, instead of saving garbage as a `.gguf` that later crashes deep
  in llama.cpp's native loader. On the existing-file skip path, a file
  already sitting at the destination is header-checked too, so a copy
  corrupted on disk (bad copy, interrupted sync, bit-rot) is detected and
  re-downloaded rather than trusted forever. An invalid download is
  treated as deterministic and not retried. This is a fast header check,
  not a full content hash - subtle mid-file corruption is out of scope
  (a documented future item; a multi-second hash of a multi-GB file for a
  much rarer failure).
- **Plain-HTTP custom download URLs now warn.** `http://` is still
  permitted (some users have legitimate internal model mirrors without
  TLS), but a download over plain HTTP logs a tamper-in-transit warning
  recommending `https://`. Defense-in-depth: the file is only ever loaded
  as model data, not executed, so this is a modest hardening rather than
  a closed hole.

### Added - prompt history (detail)

The first feature that diverges the public edition from the internal
build: a local prompt history, and a couple of fixes surfaced while
adding it.

### Added

- **Prompt history, backed by SQLite.** Every successful refine (Ctrl+R)
  is recorded to a local database: the original prompt, a snapshot of the
  analyzer's findings (type, score, readiness, missing elements,
  recommendation/smell/challenge counts), the refined output, and the
  profile/template/backend/model used. Uses the standard-library
  `sqlite3` - no third-party dependency, consistent with the "local only,
  zero commercial dependencies" stance. (SQLite over DuckDB deliberately:
  this is an insert/list/delete workload, not analytical aggregation.)
- **History browser** (`[ History ]` button on the main screen): a
  selectable grid of entries newest-first, a preview pane for the
  highlighted row, and actions to **Copy Refined**, **Delete** a single
  entry, **Export JSON**, **Export CSV**, and **Clear All**. Per-entry
  copy/delete plus whole-history JSON+CSV export; no automatic size cap,
  so Clear All is the reset. Exports land in `exports/`.
- The database lives in the user data directory
  (`~/.promptsmith/history.db` from source, `user_data/history.db` next
  to a portable executable). History is best-effort: if the DB can't be
  opened it disables itself and never disturbs the refine flow.
- New module `promptsmith.core.history` (`HistoryStore`, `HistoryEntry`)
  and 14 tests covering the store's CRUD/export, graceful degradation,
  and the full UI flow (refine records an entry, modal lists it, copy/
  delete/clear/export all work).

### Fixed

- **The main-screen action buttons overflowed off-screen on narrow
  terminals.** Adding a seventh button (History) pushed Settings past the
  right edge below ~120 columns, making it unclickable. The button row is
  now a wrapping grid (four per row) instead of a single horizontal row,
  so every button stays reachable down to ~80 columns.
- **Button labels rendered empty after the Textual 8 upgrade.** Bracketed
  labels like `[ Analyze ]` were parsed as content markup and consumed,
  leaving blank buttons. Labels are now built as explicit `Content`
  objects with a color span, bypassing markup parsing entirely - the
  literal text is preserved and the palette color is baked into the
  render output rather than relying on Button CSS `color` (which Textual
  8 doesn't apply to label text in a real terminal). Guarded by a
  regression test that renders each screen and asserts every button has a
  non-empty, color-spanned label.

## 0.6.0b1 - Public open-source release ("PromptSmith-cli")

First release prepared for publication at
https://codeberg.org/prozak/promptsmith-cli under the MIT license.

### Changed

- **Product renamed to PromptSmith-cli** end to end: UI banner, About
  screen, session export headers/filenames, build artifact and launcher
  names, and all documentation. The Python import package remains
  `promptsmith` (hyphens aren't valid in Python identifiers, and the
  PyPI distribution was already `promptsmith-cli`); the console command
  `promptsmith` still works, with `promptsmith-cli` added as an alias.
- **Version is now single-sourced from `pyproject.toml`.**
  `promptsmith._version` reads it back through `importlib.metadata`;
  the About screen, the new `--version`/`-V` flag, and both build
  scripts (via `tools/get_version.py`) all derive from it. Frozen builds
  bundle the package metadata (`--copy-metadata promptsmith-cli`) so the
  standalone executable reports the same value - verified by a new
  post-build smoke test in both scripts. Releasing a new version is now:
  bump `pyproject.toml`, reinstall, rebuild.
- **About screen rebuilt**: product name, live version ("Version 0.6
  Beta", formatted from PEP 440 by `display_version()`), project URL,
  "2026 - MIT License", and a **Get Support** button that opens the
  issue tracker (https://codeberg.org/prozak/promptsmith-cli/issues).
- **Green-phosphor theme.** The entire TUI palette moved from orange
  shades to green on black (`#00CC33` primary, `#66FF66` focus,
  `#33FF33` accents, `#1E661E` dim) - the visual cue that you're running
  the public build. Guarded by a regression test that fails if any of
  the old orange hex values reappear.
- **All dependencies bumped to current releases**, most notably
  **Textual 0.6x -> 8.2** (see Fixed below for the migration), plus
  PyYAML 6.0.3, pyperclip 1.11, psutil 7.2, requests 2.34, tqdm 4.68,
  llama-cpp-python 0.3.30+, and the dev toolchain (pytest 9, black 26,
  ruff 0.15, mypy 2.3). `requires-python` raised to 3.10.

### Fixed

- **Textual 8 migration.** Three API changes were absorbed:
  `Static.renderable` was removed (now `.content`, in app code and
  tests); `Select.BLANK` degraded to a plain `False` while the real
  no-selection sentinel became `Select.NULL` (a `NoSelection` instance),
  so every blank-value guard now goes through one
  `_is_blank_select_value()` helper checking both identity and type; and
  the main screen's `Select.Changed` handler gained the same guard so an
  options rebuild can no longer write a sentinel into the config. Full
  suite passes on 8.2.8.
- **Wheel installs can now find their built-in profiles/templates** -
  the long-standing `package-data` known limitation. Built-ins moved
  into the package (`src/promptsmith/data/`), `get_asset_path()` falls
  back to the packaged copy when no top-level directory exists, and
  `get_project_root()` no longer crashes without a `pyproject.toml`
  (installed-wheel case) - it falls back to `~/.promptsmith` for config
  and exports. Verified: a built wheel now carries all 35 profiles and
  22 templates.
- **Windows llama-cpp-python bundling hardened** (the historically weak
  part of the Windows build). Both build scripts now: pre-flight-check
  that `import llama_cpp` actually works before building, with specific
  guidance for the two common Windows failures (no C++ toolchain ->
  prebuilt CPU wheel index; missing MSVC runtime -> VC++ redistributable
  link); pass `--collect-all llama_cpp` so the compiled
  libraries (`llama.dll`/`ggml*.dll`/`libllama.so`/`.dylib`) that
  PyInstaller's static analysis misses are bundled; and verify after the
  build that the native library actually landed in the bundle. The
  recipient-facing `READ ME FIRST.txt` also documents the VC++
  redistributable fix.

### Added

- `--version` / `-V` flag - prints name and version without starting the
  TUI; used by the build scripts' smoke tests.
- `tools/get_version.py` - shared pyproject version reader for both
  build scripts (tomllib on 3.11+, regex fallback on 3.10).
- `promptsmith-cli` console command alias alongside `promptsmith`.
- Project URLs (homepage, issues, changelog) in package metadata.
- 15 new regression tests (`test_version_and_about.py`): version/
  pyproject consistency, display formatting, product identity constants,
  `--version` behavior, About screen contents and Get Support wiring,
  no-orange-palette guard, and packaged-data resolution. Suite total:
  214 tests.

### Removed

- `SESSION1_NOTES.md` (internal scaffolding notes; history lives here).
- The placeholder author email in `pyproject.toml`.

## Earlier unreleased work - response to an independent code review

An independent review flagged several issues. Verified each claim against
the actual codebase before acting - reproduced every one that's listed as
fixed below with a standalone script first, then fixed and added a
regression test.

### Fixed

- **`IntentCompiler`'s auto-recommended profile was never actually
  applied.** `PromptAnalyzer.TYPE_PROFILE_MAP` returns human-readable
  display names ("React Developer"), but profile lookup keys on file ids
  ("react-developer"). Every pipeline run that didn't pass an explicit
  profile_name failed lookup, was caught, and silently returned the
  original prompt unchanged with only a warning - reproduced exactly
  as described. Added `ProfileManager.resolve_id()` (exact id -> slugified
  name -> case-insensitive display-name match) and wired it into
  `get_profile()`, so both ids and display names resolve correctly.
- **Model downloads could leave a corrupt file treated as complete
  forever.** Confirmed real, though more narrowly than initially
  described: existing code already cleaned up on caught Python
  exceptions, but anything that terminates the process without running
  an `except` block (killed, crashed, power loss, `Ctrl+C` - which is a
  `BaseException`, not caught by `except Exception`) left a truncated
  file at the final path, and future runs' `if dest_path.exists(): skip`
  trusted it as complete. Now downloads to a `.part` sibling, verifies
  the byte count against `Content-Length` when the server provides it,
  and only atomically renames to the final path on a verified-complete
  write - `dest_path` now only ever exists in its complete form.
- **A stale warning could survive into a later, successful refine.**
  `PromptRefiner.last_warning` was only ever assigned on a failure path,
  never reset on success. Now reset at the top of every `refine()` call.
- **A profile with non-string items in `domain`/`constraints` (or a
  non-string `role`) passed schema validation cleanly and only crashed
  later** with an opaque `AttributeError` inside `_apply_rules()`,
  far from the malformed source file. Schema validation now checks list
  *contents*, not just the outer container type, and rejects a non-string
  `role` - reproduced the exact crash first, confirmed the fix converts
  it into a clear validation error at load time instead.
- **Type detection was brittle for combined technologies.** A prompt
  mentioning both AEM and Next.js separately (rather than as one of the
  explicit "nextjs aem" compound patterns) could be misclassified as
  plain `aem`, because a single highly-specific phrase match ("aem
  component", weight 2) could outscore the combined type's own raw
  weight sum even with both technologies clearly present. Added a
  tie-breaking rule: when both single-technology parent types
  (`react`/`aem`, `nextjs`/`aem`) have independent signal, the combined
  type now wins regardless of raw weight sums.
- **`src/promptsmith/test_e2e.py` was dead code**, not a working
  integration test: broken import when run as a script (`from
  src.promptsmith...`), zero actual `test_*` functions (so pytest
  silently collected and ran nothing from it), and references to a
  template and profile (`summary_template`, `test_profile`) that don't
  exist in the shipped `templates/`/`profiles/`. Removed; the same
  scenarios it gestured at are covered properly, with real assertions,
  by `test_pipeline.py` and `test_refiner.py`.

### Confirmed, documented, not fixed this pass (needs more than a patch)

- **A normal `pip install promptsmith-cli` from a wheel is broken.**
  `pyproject.toml`'s `package-data` declares `profiles/*`/`templates/*`
  relative to the package directory (`src/promptsmith/`), but those
  folders live at the project root instead; a wheel build silently
  excludes them, and `get_project_root()`'s non-frozen fallback (walk up
  looking for `pyproject.toml`) can't find that file inside a
  `site-packages` install either. This is already documented in
  `BUILD.md` as a known, out-of-scope limitation from an earlier
  session - confirmed still accurate, not re-litigated here. Doesn't
  affect the PyInstaller builds (they bundle these directories directly,
  bypassing setuptools packaging). Real fix needs `importlib.resources`
  for the shipped assets, which is a structural change deserving its own
  pass, not a drive-by patch.
- **`BUILD.md` also contains an separately-stale claim**: it says there's
  no separation between shipped and user-added profiles, but the
  `user_dir` override layer (added in a later session) means there now
  is. Worth a doc pass alongside the packaging fix above.
- **Release identity is inconsistent** (`pyproject.toml`/`build_cli.sh`
  say `0.1.0`; `README.md`/the About screen say "v0.5 Beta"). Already
  flagged in the previous entry below - still unresolved, still a
  product decision, not something to silently guess at.
- Windows build model-detection glob edge case, and the feature requests
  (template editor, output-trust layer, more robust model manager with
  resumable downloads/checksums) are legitimate roadmap items, not bugs -
  left for prioritization rather than implemented speculatively here.

### Investigated and found to be a non-issue as described

- Three `except Exception: pass` blocks previously flagged as "broad
  exception handling masking real errors" were re-checked individually:
  all three are legitimate best-effort UI no-ops (a settings-button
  disable toggle, and two scroll actions), not swallowed failures.

### Noted, not chased further

- A single flaky failure appeared in
  `test_profile_editor_create_edit_delete_roundtrip` during a full-suite
  run (stale `backend` value after a second save-under-same-id) but did
  not reproduce across three repeated full-suite runs or three isolated
  runs of just that test. An isolated `ProfileManager`-level reproduction
  of the same save-twice sequence (bypassing the TUI entirely) worked
  correctly, which points at a timing race in the TUI's async
  reload/Select-widget update rather than the underlying data layer -
  noted for awareness rather than fixed blind, since it couldn't be
  reliably reproduced enough to diagnose confidently.

## Unreleased - end-to-end validation pass: keybindings, layout, path resolution, thinking-model handling

A full defect sweep across the app, prompted by four separate real-world bug
reports in one working session plus a deliberate look for the same bug
*classes* elsewhere in the codebase, not just the exact reported instances.

### Bugs fixed

- **`ctrl+q` quit the whole app instead of going back** on Settings, Model
  Switch, and Profile Editor. `Binding("ctrl+q", "pop_screen", ...)`
  resolves against the screen it's declared on, but `action_pop_screen`
  only exists on `App` - Textual silently fails to dispatch and falls
  through to the App's own `ctrl+q -> quit` binding. Fixed by pointing at
  `"app.pop_screen"` on all three screens.
- **`ctrl+s` / `ctrl+a` did nothing in the Profile Editor** (visibly - a
  save appeared to succeed but wasn't reaching the actual save logic).
  Neither key had a screen-level binding, so both fell through to
  App-level bindings acting on the *main* screen's hidden prompt input and
  a status bar the user couldn't see. Added explicit bindings: `ctrl+s`
  now calls the existing (previously button-only) `action_save`; `ctrl+a`
  now gives explicit "not available here" feedback instead of silently
  running the wrong action.
- **Vendor, Backend, and the Save/Delete/Back buttons were invisible and
  unreachable** in the Profile Editor on any terminal shorter than the
  form's full height. The outer wrapper was a plain `Container`, which
  clips overflow by default; swapped for `VerticalScroll` (matching the
  pattern the main screen already used correctly). Found and fixed the
  same latent bug in `SettingsScreen` and `ModelSwitchScreen`.
- **Saving a profile gave no visible confirmation of the copy-on-write
  behavior**, and a separate bug in the same code path meant the
  "renamed" status message displayed the *new* id twice instead of
  showing what it was renamed from (id was reassigned before the message
  read it). The save message now always shows the real file path and
  explicitly confirms "(your copy - the built-in version ships
  untouched)" when applicable.
- **A profile's role/tone/format framing text leaked into the tail of
  generated output** (e.g. "Act as if I am Adobe Experience Manager (AEM)
  Developer... Use a Technical and precise tone..." appended after real
  TSX code). `PromptRefiner` was re-running the full prompt-framing rules
  against already-generated content. Split into two functions:
  `_apply_rules` (prompt framing, used to build the LLM's input) and the
  new `_ensure_content_completeness` (only tops up missing domain/
  constraint terms - the actual regression-tested safety net for an LLM
  polish pass dropping required content - never re-injects role/tone/
  format sentences into finished output).
- **A Qwen3 (thinking-model) response could be entirely consumed by an
  unclosed `<think>` reasoning block**, with the fixed 512-token budget
  exhausted before the real answer was ever generated. The existing
  degenerate-output check only looked at length, so a long-but-truncated
  thinking block passed straight through as if it were a valid answer.
  `LLMBasedBackend` now strips `<think>...</think>` blocks and, critically,
  treats an *unclosed* think tag as a failed generation (returns `None`,
  triggering `HybridBackend`'s existing fallback to the rule-based text).
  Also appends Qwen3's documented `/no_think` switch for detected Qwen3
  models, to avoid the situation proactively rather than only recovering
  from it.
- **Saved profile/template edits were invisible in a distributed/portable
  build.** `get_asset_path()` (built-in profiles/templates/models)
  correctly resolves next to the executable when frozen, but
  `get_user_data_dir()` (everything a user actually saves) ignored
  `is_frozen()` entirely and always wrote to `~/.promptsmith` - a hidden
  OS home-directory location nowhere near the folders someone building a
  portable app would actually be looking at. A third, independent copy of
  the same hardcoded home-dir default existed for the log file. All three
  now go through one frozen-aware function: a `user_data/` sibling folder
  next to the executable when frozen, `~/.promptsmith` when running from
  source (unchanged), `PROMPTSMITH_LOG_DIR` overriding either way.

### Checked, not changed

- `AboutScreen`'s `Container` does *not* need the `VerticalScroll` fix -
  it uses `height: auto` (sizes to content) rather than `height: 100%`,
  and its content is short enough to never overflow. Converting it would
  have fought against its intentional centered-dialog layout.
- Three `except Exception: pass` blocks (a settings-button disable toggle,
  and the two scroll actions) are legitimate best-effort UI no-ops, not
  swallowed real errors - left as-is.
- The build script (`build_cli.sh`) already copies `profiles/`,
  `templates/`, `models/`, and `config.yaml` as visible siblings of the
  executable; the `get_user_data_dir()` fix above aligns with this
  exactly (`user_data/` as a new sibling, no collision).

### Known limitation (not fixed - low severity, framework-level)

- On a terminal short enough that a button lands within a few rows of a
  `VerticalScroll`'s clipped viewport boundary, an automated/precise
  click exactly on that boundary row can miss the widget and hit the
  scroll container instead (reproduced on Settings' "About" button at a
  45-row terminal; confirmed absent at 100 rows, and absent for any
  widget comfortably within the visible area regardless of overflow).
  Appears to be a Textual compositor/region-reporting edge case at the
  exact clip boundary, not something introduced by or fixable from
  application code; a real user would see the button is cut off and
  scroll first.

### Open item - needs a decision, not fixed silently

- **Version string inconsistency**: `pyproject.toml` says `0.1.0`
  (matches `build_cli.sh`'s hardcoded `VERSION="0.1.0"`), but
  `README.md` and the About screen both say "v0.5 Beta". Left unresolved
  since it's a product decision, not a code defect - pick one and I'll
  sync all three (plus the About screen text).

## Unreleased - HuggingFace Xet CAS-bridge download failures

Not a regression from the previous session's cleanup - confirmed
`package_models.py` (the download code) wasn't touched in that pass at
all. This is an external HuggingFace infrastructure issue, well
documented: a `403 Forbidden` from `cas-bridge.xethub.hf.co`, the bridge
HuggingFace uses to serve legacy/plain HTTP downloads from their newer
"Xet" storage backend. Multiple independent reports of this exact
failure, unrelated to this project, span from mid-2025 through 2026 -
it's a recurring reliability issue on HF's side, not something specific
to this app or this model.

- **Detect this specific failure and retry it**, rather than treating
  every 403 as immediately fatal. Unlike a genuine 404/401 (wrong
  filename, gated/unauthorized model - retrying those wastes time for no
  reason), the Xet bridge failure is reported as intermittent in many
  cases, and each retry gets a freshly-signed URL. If retries are
  exhausted, the error message now says plainly what's actually
  happening - a known HuggingFace-side issue, typically resolving within
  hours - instead of leaving it looking like a bug in this app.
- **Caught a real bug in my own first attempt at this fix, via
  end-to-end testing, not just unit tests.** The initial version checked
  whether the *original* request URL contained "xethub"/"cas-bridge" -
  but that never matches in practice, since the original URL is always
  an ordinary `huggingface.co/.../resolve/...` link; only the URL
  `requests` gets transparently redirected *to* (where the 403 actually
  happens) is on the xethub/cas-bridge domain, and that's a different
  string. The fix silently never triggered for a real download. Caught
  this specifically because I ran the actual TUI end-to-end with a
  simulated failure rather than trusting the unit tests alone, which had
  the same blind spot (they passed the xethub URL directly as input,
  sidestepping the exact distinction that matters). Fixed to check
  `response.url` - the actual, final, post-redirect URL - and rewrote
  the tests to simulate the real shape of the problem: an ordinary input
  URL whose *response* redirects elsewhere.
- **The specific error reason now actually reaches the user**, not just
  the log file. `package_models.py`'s `main()` previously returned only
  `{model_key: bool}` - the detailed, actionable error message (like the
  Xet explanation above) was logged but discarded before reaching the
  caller, so the TUI could only ever show a generic "check logs"
  message. Changed to return `{model_key: {"success": bool, "error":
  Optional[str]}}`, and updated the one caller (`app.py`'s download
  handler) to surface the first real failure's specific message directly
  in the status bar.
- No existing test coverage existed for the download code at all before
  this; added `test_package_models.py` covering the retry behavior, the
  final error message content, and two regression guards (a non-Xet 403
  and an ordinary 404 must still fail immediately, unaffected by the new
  Xet-specific path).

## Unreleased - response to external architecture review

An external review of the codebase raised several points; agreed with
some, pushed back on others (see the discussion this is based on for the
full reasoning). This entry covers what was actually acted on.

### New features

- **User/built-in profile and template separation.** Previously flagged
  independently both by us and by the external review: with no
  distinction between "profiles PromptSmith ships" and "profiles a user
  added," anyone who hand-customized a profile lost that customization
  the next time the app was updated or rebuilt. Fixed by adding an
  optional `user_dir` to `YAMLConfigStore` (the shared base behind both
  `ProfileManager` and `TemplateManager`): built-in profiles load first,
  user-space ones load second and override by name, and new
  additions/deletions (`add_profile`/`delete_profile` and their template
  equivalents) always write to the user directory, never touching the
  bundled defaults. User profiles/templates live in `~/.promptsmith/`,
  the same convention already used for logs. Deleting a user's override
  of a built-in profile correctly reveals the built-in one again rather
  than removing it outright - verified directly, along with the override
  and additive-merge behavior, the write-target behavior, and that
  callers who don't pass `user_dir` at all see identical single-directory
  behavior as before (this is purely additive, not a breaking change).
  "Export Profiles"/"Export Templates" now include user overrides too,
  merged with correct precedence, not just the built-in set.

### Renamed for clarity

- **PyPI package renamed to `promptsmith-cli`** - "promptsmith" is
  already taken on PyPI, so this needed to change before the project
  could be published there. Only the distribution name changed: the
  `import promptsmith` module path, the `promptsmith` console command,
  and the on-disk `src/promptsmith/` package are all untouched -
  distribution name and import name are independently namespaced in
  Python packaging (e.g. `pip install beautifulsoup4` gives you
  `import bs4`), so this is a safe, low-risk rename.
- **"Export Full Application" renamed to "Export Source Code"**, along
  with the underlying `export_full_application()` function (now
  `export_source_code()`) and its output filename prefix. The external
  review flagged genuine confusion here - it read the button as if it
  should produce a working, runnable application (Python runtime,
  compiled dependencies included) and dinged it for not doing that. That
  critique was aimed at the wrong target (the actual standalone
  executable comes from `build_cli.sh`/`build_windows.bat`, a separate
  workflow this button was never meant to replace) - but the fact that
  an experienced reviewer got confused about what this button does is
  itself a real signal the name was ambiguous. Also fixed a stale
  reference to `build_all.sh` (removed in an earlier cleanup) in the
  file list this export includes; `build_windows.bat` was missing from
  that list entirely and is now included.

### Removed

- **Dropped the unused `pydantic` dependency entirely, rather than
  migrating to it.** The review correctly identified this as real
  technical debt: `pydantic>=2.0.0` was a hard dependency doing nothing,
  imported defensively in a try/except and never referenced. Where the
  review and this response disagree is the fix - migrating `profiles.py`
  and `templates.py`'s validation to Pydantic touches every place that
  constructs or consumes a profile/template dict, for a payoff that's
  aesthetic, not functional, against hand-rolled validation that's
  already been exercised through this project's entire bug-finding
  history. Removed the dependency instead. In the process, found that
  `schemas.py`'s `ProfileSchema`/`TemplateSchema` - hand-rolled but more
  complete than the validation actually wired in, since they type-check
  optional fields and fill in sensible defaults - were themselves dead
  code, never actually called by the live validation path. Wired them in
  properly via `YAMLConfigStore`'s existing `config_schema` parameter
  (designed for exactly this, previously unused), removing the
  now-redundant duplicate checks in `profiles.py`/`templates.py`.
  Verified all 35 existing profiles and 22 templates pass the stricter
  validation with no changes needed.
- **Removed `src/promptsmith/scripts/build.py`** - an orphaned, outdated
  build script, not referenced anywhere, that predates the
  `build_cli.sh`/`build_windows.bat` work: it bundled profiles/templates/
  models via `--add-data`, exactly the approach later found to bury
  everything inside PyInstaller's hidden `_internal/` folder instead of
  keeping it visible and editable. Also referenced `fonts/` and
  `assets/icon.icns` paths that don't exist in this project, which would
  have made it fail outright if anyone had tried to run it.
- Cleaned up a genuinely dead local variable (`readiness_color` in
  `app.py`, superseded by CSS-class-based color toggling but never
  removed) and roughly a dozen unused imports across the codebase,
  found via `ruff` and verified one by one against a backup rather than
  applied blindly. Also fixed a handful of small, non-cosmetic issues
  the same pass surfaced: two implicit-`Optional` type hints in
  `exceptions.py`, a type comparison using `==` instead of `is` in the
  schema validation code just wired in, an unused loop variable, and one
  re-raise inside an `except` block missing `from None` (produces a
  confusing double-traceback otherwise). Deliberately did not chase the
  full ~300-issue output of an unrestricted `ruff check` - the vast
  majority of that is whitespace/formatting noise unrelated to dead code,
  a different and much larger-blast-radius task than what was asked for.

### Added

- **`webui/README.md`** - explicit placeholder stating a web interface
  is not planned for this cycle, so the empty directory isn't mistaken
  for an abandoned half-built feature by whoever finds it next.

### Deliberately left alone

- **`IntentCompiler`/`pipeline.py`** - still not wired into the TUI,
  still fully functional and tested on its own. The external review
  called this the single biggest architectural debt; we disagree with
  that ranking, though not with the underlying fact. `app.py`'s direct
  calls to `PromptAnalyzer`/`PromptRefiner` are exactly the path that's
  been through this project's entire real-bug-finding history. Wiring in
  an unused orchestrator is a maintainability improvement, not a
  correctness fix, and ranks below it accordingly. Left untouched, not
  removed either - it remains available if a real need for it comes up.
- **Speculative roadmap items from the review** (remote profile
  repository, API server mode, IDE/LSP integration) - not pursued. These
  cut directly against this project's own stated positioning (100% Open
  Source, Local Only, Zero Commercial Dependencies): a remote profile
  repo is a server someone has to run and trust, an API server is a new
  deployment story and attack surface. Not wrong ideas in a vacuum, but
  a meaningfully different direction than what's been built, and not
  something to grow into by default.

## v0.5 Beta

This is the first comprehensive documentation pass covering the full review
and fix history since the original MVP. Organized by area rather than by
date, since many of these were found and fixed across many iterative rounds.

### New features

- **Challenge step** (Analyze → *Challenge* → Prepare): deterministic,
  rule-based clarifying questions surfaced alongside the existing analysis
  (vague scope words, missing success criteria, missing audience, vague
  quantities, unstated integration constraints). Informational only - never
  blocks Refine. Applies identically across every profile, template, and
  backend, since it runs during Analysis, before a backend is ever selected.
  Deliberately not LLM-generated: producing a genuinely useful clarifying
  question is a harder reasoning task than rewriting a prompt, and small
  local models are not reliable at it.
- **Hybrid backend** (`backend: hybrid`): runs the deterministic rule engine

  first (guaranteeing every constraint from the profile is present,
  verbatim), then asks the local LLM to polish that already-complete text
  into clearer prose, rather than generating structured content from a bare
  prompt. Falls back cleanly to the pure rule-based text if the LLM is
  unavailable or produces something that looks truncated/degenerate.
- **Custom model URL download**: Settings > Download From URL, for any
  direct `.gguf` link, not just the two built-in presets.
- **Model Status view**: Settings > Model Status shows what's downloaded on
  disk and which backend/model actually served the last refinement.
- **View LLM Run Log**: Settings > View LLM Run Log shows llama.cpp's own
  native output (model load stats, inference timing) from the most recent
  run, captured via OS-level file descriptor redirection since this output
  bypasses Python's logging entirely. A first step toward a future SQLite
  transaction log.
- **About popup**: Settings > About.
- **Clear button**: wipes the prompt input in one click (Ctrl+A doesn't
  select-all in this widget - it's bound to cursor-line-start by default).
- Persistent backend indicator: selecting a profile immediately shows its
  configured backend (`Profile: vibe-coding [llm]`) in the status bar,
  without needing to open Settings.
- Live, backend-aware status during refine (`Refining with llm backend
  (this can take a while)...`) instead of only showing feedback after
  completion.

### Model

- Replaced Phi-3-mini-4k-instruct with **Phi-4-mini-instruct** (same size
  class, ~2.5GB Q4_K_M) - Microsoft's direct successor, MIT-licensed, with
  a training focus on instruction adherence.
- Switched from raw text completion to `create_chat_completion()` with
  proper role-structured messages, so the model gets a real chat template
  instead of a hand-simulated one.
- Chat format names are now validated against the installed
  llama-cpp-python version's actual registry before use (a hardcoded guess
  like `"phi3"` isn't reliably registered across versions - this was
  found in production and previously produced a confusing silent fallback
  to the rule-based backend with the real error buried in a warning).

### Correctness fixes

- **Prompt Analyzer type detection** used naive substring matching with no
  word boundaries - short patterns like `"api"`, `"cq"`, `"roi"` matched
  *inside* unrelated words (`"capital"` → coding, `"acquire"` → AEM).
  Fixed with word-boundary regex matching.
- **Prompt Analyzer generic-word false positives**: common English words
  in type patterns (`state`, `method`, `notes`, `estimate`, `budget`,
  `design`, `props`, `component`, `context`) caused confident
  misclassification of unrelated everyday prompts. Removed the confirmed
  offenders; added regression tests for both bug classes.
- **Analyzer recommended two profiles that didn't exist** (`Technical
  Writer`, `Research Analyst`) - created both; added a test that checks
  every analyzer-recommended profile resolves to a real file.
- **`"as a"` counted toward both** "Audience/Role" and "Output Format"
  completeness checks, so a natural role phrase silently satisfied the
  format check even when no format was ever specified.
- **5 of 22 templates had multiple placeholders** (`{recipient}`,
  `{tone}`, `{purpose}`, etc.), all silently filled with the same raw user
  text since the UI has one input field, producing nonsense output
  (`"Draft an email for X to X... Tone: X"`). Rewrote all 5 to a single
  `{details}` placeholder.
- **`_apply_rules()`'s format check** tested whether the literal word
  *"format"* appeared anywhere in the text, not whether the profile's
  specific format value did - any template mentioning "Format:" for
  something unrelated silently dropped the profile's own format
  preference.
- **LLM backend was registered with no model path at all** - `model_path`
  was always `None` regardless of downloaded models, so `backend: llm`
  silently fell back to rule-based every time. Now auto-discovers the
  first `.gguf` in `models/` (respecting an explicit `llm.model_path`
  config override).
- **LLM output was truncated to just a header** (`"Improved prompt:"` and
  nothing else) - an overly aggressive stop token (`\n\n`) fired the
  instant the model's natural header-then-blank-line response pattern
  appeared. Cued the model to complete directly into content instead, and
  added defensive header-stripping as a second layer.
- **LLM confused the meta-task with the object-task**: asked to rewrite a
  prompt, it would sometimes just answer the coding request directly
  (writing full React code instead of a refined prompt). Rewrote the
  system prompt to be explicit that this is a text-editing task, not a
  task-completion task, with a one-shot example.
- **LLM would loop and generate multiple rewrite attempts** in one
  completion, separated by self-generated headers (`"Rewritten prompt:"`),
  truncated mid-sentence by `max_tokens`. Added detection that keeps only
  the first complete section (only triggers on a *repeated* header after
  real content, so a single legitimate leading header can't be mistaken
  for a repeat).
- **LLM-refined output silently dropped the profile's explicit framing**
  (role/domain/tone/constraints) - that context was only ever used to
  steer the model's own rewrite, never guaranteed to appear in the visible
  text. Now applied as a universal final pass regardless of backend
  (idempotent for rule-based, which already includes it).
- **`_apply_rules()`'s domain check** used "does ANY ONE domain term
  appear anywhere" logic - if even one of a profile's several domain areas
  happened to be mentioned in the text, the *entire* "Focus on X, Y, Z"
  clause was skipped, silently dropping every other domain area that was
  never actually mentioned. Confirmed directly in production via the
  circular test: a response mentioning only "Testing" caused "Software
  Engineering, Architecture, Refactoring, Code Quality" to vanish entirely
  on a second refinement pass. Fixed to check each domain term
  individually and only append what's genuinely missing, matching how
  `constraints` already correctly worked.
- **HybridBackend's completeness guarantee had a real gap**: the LLM's
  polish step was trusted completely once it passed a coarse length check,
  with no verification that role/domain/tone/format/constraints actually
  survived the rewrite. The universal completeness pass was deliberately
  skipped for hybrid specifically, to avoid bolting on a duplicate,
  differently-worded copy of content the LLM had already paraphrased.
  Confirmed this is a real gap, not just a theoretical one, and that the
  domain-check fix above made the concern moot: since `_apply_rules` is
  now per-item granular rather than all-or-nothing, it's safe to apply
  universally - it only adds back what's genuinely missing, never
  duplicates what's already there. Removed the hybrid exception.
- **`#readiness_container` had zero explicit CSS**, silently inheriting
  Textual's default `Container` height of `1fr` - meaning it competed for
  a "fair share" of flexible vertical space against the actual output
  box, creating a large empty gap between the READY/NEEDS WORK indicator
  and the analysis text below it. Same bug class as the earlier `#buttons`
  issue. Scoped explicitly to `height: auto`.
- **"View LLM Run Log" always showed nothing was captured**, even after
  real LLM runs - `verbose=False` was set on the model (to reduce
  terminal chatter, before proper fd-level capture existed) and left
  llama.cpp with nothing to say. Now that native output is captured to a
  file rather than the terminal regardless of verbosity, `verbose=False`
  was silently defeating the log feature entirely. Re-enabled verbose
  output; verified it's captured to the file and nothing leaks to the
  real terminal.
- **Clear only cleared the prompt input**, leaving stale refined output
  and analysis visible. Now also resets the output box and analysis
  display.
- **No visible feedback while Refine is working**, especially on a second
  or later refine where a fixed one-time status message could be
  overwritten by the final result before a human eye ever registered it.
  Replaced with a ticking animation (dots + elapsed time) that updates
  every 0.4s for the duration of the refine, guaranteeing at least one
  visible update regardless of how fast the operation completes. Verified
  the timer stops cleanly on both success and every error path, with no
  stray background timer left running afterward.
- **The refine animation bled status text onto whatever screen was
  active**, not just the main screen it was meant for. Reproduced
  directly: navigating to Settings (or opening any modal, like the LLM
  Run Log) while a refine was still running in the background caused the
  ticking "Refining... (elapsed: Xs+)" text to keep overwriting that
  screen's status bar, with no connection to anything actually happening
  there. This is a strong, unified explanation for two separately
  reported symptoms: garbled/fragmented rendering when opening the LLM
  Run Log modal during an active refine (a high-frequency timer forcing
  redraws colliding with a modal's more complex compositing), and
  confusion about whether a refine had "finished" (looking at a screen
  whose status had frozen on a stale snapshot instead of the live
  result). Fixed by only updating the animation - and the final
  completion status - when the main screen is actually the active one;
  the actual output widget still always updates correctly regardless.
  Added two regression tests covering both the non-bleeding behavior and
  correct resumption after returning to the main screen.
- **Reverted `verbose=True` on the LLM model back to `verbose=False`** as
  a precaution after a reported complete application hang during a
  refine. Not fully proven, but there's a concrete, specific mechanism:
  some llama.cpp verbose modes emit output *per-token* during generation
  (not just at model load), which combined with file-based capture could
  plausibly cause severe slowdown that looks exactly like "never
  finished" rather than a clean crash. Given the severity, trading away
  the LLM Run Log's usefulness for stability was the right call until
  this can be verified safe through further testing.
- **Hardened the animation timer against any internal exception** -
  previously had no error handling at all; a timer callback runs on its
  own schedule independent of the refine's actual lifecycle, and should
  never be able to destabilize the app regardless of what triggers a
  failure inside it. Now stops itself cleanly on any error instead.
- **Settings navigation is now blocked entirely while a refine is in
  progress**, superseding an earlier, insufficient fix. The previous
  round made the animation "screen-aware" (only updating the status bar
  of whichever screen was actually active) to stop status text from
  bleeding across screens - a real improvement, but it turned out not to
  be sufficient on its own. A second, more severe report showed opening
  the LLM Run Log modal during an active refine still produced fragmented,
  garbled rendering - a high-frequency background timer forcing redraws
  while a modal is compositing appears to be inherently risky, not just a
  text-bleeding cosmetic issue. Rather than continue trying to make
  concurrent navigation safe, it's now prevented outright: the Settings
  button is disabled (with a clear status message if triggered anyway)
  for the duration of any refine, and re-enabled the moment it completes.
  Verified with a real simulated click during an active refine (not just
  checking internal flags) that navigation is genuinely blocked, and that
  it correctly re-enables afterward.
- **Removed native LLM output capture entirely** after further reports
  showed the corruption persisted even *after* a refine had fully
  completed, not just during a concurrent one - ruling out the earlier
  timing-based explanation as the full story. Found the real structural
  flaw: `capture_native_stderr`'s `os.dup2()`-based file descriptor
  redirection is process-global, and the module's lock only prevented two
  calls to the function from colliding with *each other* - it provided no
  protection against Textual's own rendering (running on the main
  asyncio thread) writing to the same file descriptor while a background
  worker thread had it redirected to a log file. A literal fragment of a
  torn ANSI escape sequence (`40;0;48;2;0;0;0m`) appearing as visible
  text, plus status text rendering outside the app's own border entirely,
  is consistent with exactly this kind of race. Given the severity of
  the symptoms (repeated garbled rendering, repeated loss of mouse
  input) against the value of a diagnostic-only feature, removed the fd
  redirection entirely rather than continue patching around it. "View
  LLM Run Log" now explains why the feature is off instead of silently
  showing nothing.
- **Removed the "View LLM Run Log" feature entirely**, per explicit
  request, after it could not be made safe (see the fd-redirection race
  condition documented above). The button, its modal screen, and the
  now-unused capture utility have all been deleted rather than left
  disabled with an explanation - if a feature can't work, it shouldn't
  linger as dead weight in the UI.
- **"Export Full Application" didn't export the application** - it called
  the exact same function as the main screen's Export button, which only
  ever bundles `profiles/`, `templates/`, and `config.yaml`. Confirmed by
  inspecting a real exported zip directly: zero `.py` files, no
  `pyproject.toml`, no `README.md` - nothing needed to actually run or
  redistribute the app. Added a genuinely different
  `export_full_application()` function that includes the real source
  tree, packaging files (`pyproject.toml`, build scripts), and docs,
  while excluding `.venv`, `__pycache__`, downloaded models, and prior
  exports. Uses a visibly different filename (`PromptSmith-FullApp-*`)
  so the two export types can't be confused again. 4 new tests confirm
  what's included and what's correctly excluded.
- **The main screen's `[ Export ]` button made no sense in context** - it
  triggered the same "export the whole app's profiles/templates" action
  as the Settings button above, with no connection to whatever the user
  was actually working on. Changed to export the current session (the
  prompt, the profile/template used, and the refined output) to a
  timestamped markdown file - what a button in that position should
  reasonably do.
- **`sales-manager.yaml` had a duplicate `backend:` key** (`"sales"` then
  `"rule"`) - PyYAML silently used the last value, so it happened to work
  by accident. Fixed; ran a systematic duplicate-key scan across all
  profiles and templates to confirm it was the only offender.

### UI / rendering fixes

- **The "Refined Output" section could vanish entirely on smaller
  terminals** - not just show fewer visible lines, but not render at all.
  Confirmed directly at 80x24 (a very common default terminal size): the
  label and box were completely absent from the render, while the
  underlying data was fine (Copy worked correctly, since it reads the
  widget's content directly rather than what's visually painted).
  Root cause: `#main_container` was a plain `Container` with Textual's
  default `overflow: hidden` - when the cumulative height of everything
  above it (title, input, buttons, both selects, the analysis box) added
  up to more than the terminal's actual height, the excess was silently
  clipped rather than made reachable. Fixed by making `#main_container` a
  `VerticalScroll` instead, so the whole page scrolls when content
  doesn't fit. Verified the fix directly: confirmed the section is now
  reachable by scrolling (`max_scroll_y > 0`, content present after
  scrolling to the end) at 80x24, and confirmed zero behavior change at
  a large terminal size where everything already fit (`max_scroll_y ==
  0`, unchanged from before the fix).

Several of these share a root cause worth naming: things that were
logically correct in the widget's internal state but not actually visible
on screen. Caught via real SVG-render inspection, not just checking
`.renderable` content.

- **Terminal corruption**: `logging.StreamHandler()` wrote log lines
  directly to the terminal while Textual had exclusive control of it -
  every interaction slowly corrupted the display. Logging now goes to
  `~/.promptsmith/promptsmith.log`, never the terminal.
- **Status bar showed nothing**: `border-top` plus `height: 1` meant the
  border consumed the widget's only row, leaving zero rows for text.
- **Status bar and Footer overlapped** at the same screen region (both
  `dock: bottom` at the Screen level) - one silently won, hiding the
  other. Rescoped so each docks to its actual intended parent.
- **Buttons stacked in one column wasting the whole screen**: a generic
  `Container { height: 100%; border: double... }` CSS rule matched *every*
  `Container` widget, including the small button row nested inside the
  main one, inflating it from ~12 rows to 36. Scoped the rule to the
  specific container it was meant for.
- **Dropdown selected value invisible**: the label text and the dropdown's
  built-in focus border are two different problems that both hid the same
  text. The label's color wasn't targeted by the app's CSS at all
  (Textual's `SelectCurrent > Static#label` has its own explicit color).
  Separately, overriding the focus border with `border: tall` painted
  block-character glyphs directly over the label's row, erasing it
  regardless of color. Fixed both; verified by extracting literal
  character rows from a rendered screenshot, not just checking computed
  styles.
- **Output box didn't scroll**: a plain `Static` never computed a real
  scrollable size for its content (`scroll_y` stayed `0.0` regardless of
  how many scroll calls were made). Wrapped in `VerticalScroll`, the
  correct Textual pattern for scrollable text.
- **Prompt input was single-line**: `Input` truncates any pasted text at
  the first newline. Replaced with `TextArea`.
- **Refine and Download LLM Models blocked the main UI thread**: for a
  slow LLM call, this meant the entire app would freeze - no redraw, no
  input, `"Refining..."` never got a chance to actually paint before the
  freeze. Both now run in background workers; status messages are visible
  and the UI stays responsive for the whole duration.
- **Analysis box was a fixed 5-row window**, already tight for
  Missing/Recommendations alone; the new Challenges section made
  previously-visible content require scrolling to discover. Increased to
  12 rows.

### Packaging / distribution

- **Fixed the blocker preventing standalone macOS/Windows executables
  entirely**: `get_project_root()` walked up looking for `pyproject.toml`
  to locate profiles/templates/config - a build-time file never shipped
  inside a PyInstaller bundle. Worse, it ran at *module import time* in
  `app.py`, so a built executable couldn't get past import before
  crashing - the UI never had a chance to start. Fixed by detecting
  PyInstaller's frozen runtime (`sys.frozen` + `sys._MEIPASS`, set
  identically by PyInstaller for both `--onefile` and `--onedir` builds)
  and resolving against the bundle's own resource directory instead of
  searching for a file that will never be there. Verified with more than
  unit tests: built an actual PyInstaller executable in CI, ran it, and
  confirmed via the log output that it loaded all 35 profiles and 22
  templates from the correct bundle-relative path, not a stale or
  hardcoded one. 6 new regression tests cover the frozen/non-frozen
  branches directly.
- **Rewrote the build scripts** (`build_cli.sh` for macOS/Linux,
  new `build_windows.bat` for Windows - no bash/WSL dependency) to use
  `--onedir` consistently rather than mixing `--onefile` for Windows: a
  `--onefile` build re-extracts its entire contents, model files
  included, to a fresh temp directory on *every single launch* - with a
  multi-GB `.gguf` bundled in, that's a multi-GB copy operation every time
  someone opens the app. `--onedir` unpacks once, at build time.
  Both scripts now also bundle whatever `.gguf` files are present in
  `models/` at build time, add a double-click launcher
  (`Start PromptSmith.command` / `Start PromptSmith.bat`), ad-hoc
  codesign the macOS binary (prevents a separate "app is damaged" failure
  mode, though it doesn't satisfy Gatekeeper's identified-developer
  check - that needs a paid Apple Developer ID), and ship a
  `READ ME FIRST.txt` explaining the expected first-launch
  Gatekeeper/SmartScreen security prompt so the recipient isn't left
  thinking the build is broken. Removed the old `build_all.sh`, which
  overlapped with `build_cli.sh` and assumed bash/MSYS was available on
  Windows - not a safe assumption.
- **Reworked the build output layout so profiles/templates/models are
  visible and directly editable**, not buried inside PyInstaller's
  internals. The first version of the fix above resolved bundled
  resources against `sys._MEIPASS`, which works, but in a PyInstaller 6.x
  `--onedir` build that path points at a hidden `_internal/` folder
  alongside the executable - confirmed directly by building a real
  executable and comparing `sys._MEIPASS` against `sys.executable`'s
  directory, which differ. Switched resolution to `sys.executable`'s
  parent directory instead, and changed both build scripts to copy
  profiles, templates, models, and config.yaml directly into the
  top-level output folder as ordinary, visible files - no different from
  editing them in a source checkout. Verified end-to-end with an
  already-built executable: hand-edited an existing profile and
  hand-added a new one with nothing but a text editor, relaunched the
  compiled binary with no rebuild, and confirmed both changes were
  picked up correctly.
- `pyproject.toml`'s `package-data` still points at `promptsmith/profiles/*`
  (inside the installed package) but the real data lives at the repo root,
  a sibling of `src/` - a real (non-editable) `pip install` or built wheel
  ships with **zero profiles/templates**. Verified by building an actual
  wheel. **Not yet fixed** - needs a decision: move the data under
  `src/promptsmith/` and use `importlib.resources`, or keep the
  editable-install-only workflow and document it clearly (current state).
  This is separate from the PyInstaller fix above and doesn't affect it -
  the build scripts bundle `profiles/`/`templates/` directly via
  `--add-data`, bypassing setuptools packaging entirely.
- `llama-cpp-python` is an optional extra (`pip install -e ".[llm]"`), not
  part of the base install - the original error message suggested a bare
  `pip install llama-cpp-python`, inconsistent with how the project is
  actually packaged. Fixed the message and documented the extra properly.

### Known, deliberately unfixed

- `pydantic` is a declared dependency but completely unused - `schemas.py`
  imports it inside a try/except and never references it; validation is
  hand-rolled `isinstance()` checks. Flagged repeatedly, low priority.
- `core/pipeline.py`'s `IntentCompiler` - a fully-built, fully-tested
  orchestrator matching this project's own stated architecture - is never
  actually called by the app. `action_analyze`/`action_refine` duplicate
  its logic by hand instead. Worth a real decision (wire it in, or remove
  it) rather than leaving it as dead weight that looks load-bearing.
- `src/promptsmith/test_e2e.py` lives inside the installable package, not
  `src/tests/`, and isn't picked up by pytest.
- `webui/__init__.py` is an empty stub with no content.
