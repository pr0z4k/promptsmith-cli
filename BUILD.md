# Building PromptSmith-cli - Standalone Executables

This produces a self-contained folder for macOS, Linux, or Windows with
everything needed to run. The layout is deliberate:

```
PromptSmith-cli-<version>-<platform>/
├── PromptSmith-cli(.exe)            <- the executable
├── Start PromptSmith-cli.command/.bat   <- double-click launcher
├── profiles/                        <- visible, edit or add .yaml files directly
├── templates/                       <- same
├── models/                          <- drop in additional .gguf files directly
├── config.yaml
├── READ ME FIRST.txt
└── _internal/                       <- Python runtime + dependencies only
```

`profiles/`, `templates/`, `models/`, and `config.yaml` sit at the top
level, visible and directly editable with nothing more than a text editor
- no digging into PyInstaller's internals, no rebuild needed to add a
profile or drop in another model. Everything else needed to actually run
(the Python interpreter, compiled dependencies like llama-cpp-python) is
bundled separately in `_internal/`, which isn't meant to be touched.

The person you hand this to needs nothing installed - unzip, double-click,
done.

**PyInstaller does not cross-compile.** Build the macOS executable on a
Mac, and the Windows executable on a Windows machine. There's no way
around this from a single machine - the two scripts below are meant to be
run separately, one per platform, by whoever has access to that OS.

## Versioning - one place, bumped everywhere

The version is defined once, in `pyproject.toml`. Both build scripts read
it from there via `tools/get_version.py`, so the artifact folder and zip
names track it automatically. The frozen app reports the same value at
runtime because the scripts pass `--copy-metadata promptsmith-cli` -
PyInstaller bundles the installed package's metadata, and the app reads it
back through `importlib.metadata` (see `src/promptsmith/_version.py`).
The About screen and `--version` are both fed from that single value.

To cut a new version: bump `pyproject.toml`, `pip install -e .` (refreshes
the metadata), rebuild. Nothing else to touch.

## Before you build (on each machine)

1. **Set up a virtual environment** - some Python installs (Homebrew on
   recent macOS, some Linux distros) refuse a plain `pip install` outside
   one:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   ```
2. **Install with the LLM extra**, so llama-cpp-python's compiled bindings
   get bundled in:
   ```bash
   pip install -e ".[llm]"
   ```
   **Windows note:** llama-cpp-python may try to compile from source and
   fail if no C++ toolchain is present. Install a prebuilt CPU wheel
   instead:
   ```bat
   pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
   ```
   If it installs but then fails to *import*, the machine is missing the
   Microsoft Visual C++ Redistributable (x64), which llama.cpp's DLLs
   link against: https://aka.ms/vs/17/release/vc_redist.x64.exe
3. **Download whichever model(s) you want shipped.** Run `promptsmith`,
   go to Settings > Download LLM Models, and download Phi-4-mini-instruct
   (or whatever you want bundled). The build script picks up whatever's
   sitting in `models/` at build time - nothing is downloaded
   automatically by the script itself. If you skip this, the build still
   works, but only the `rule` backend will function (no `llm`/`hybrid`
   profiles) until a model is added.

## Building

### macOS / Linux
```bash
./build_cli.sh
```
Produces `dist/PromptSmith-cli-<version>-<platform>-<arch>/`, zipped
alongside it. Inside: `PromptSmith-cli` (the binary), a double-click
launcher (`Start PromptSmith-cli.command` on macOS,
`start-promptsmith-cli.sh` on Linux), and `READ ME FIRST.txt` (macOS).

### Windows
```bat
build_windows.bat
```
Produces `dist\PromptSmith-cli-<version>-windows-x64\`, zipped alongside
it. Inside: `PromptSmith-cli.exe`, `Start PromptSmith-cli.bat` (the
double-click launcher), and `READ ME FIRST.txt`.

## How llama-cpp-python is bundled (and why it used to break)

llama-cpp-python ships its compiled engine (`llama.dll`/`ggml*.dll` on
Windows, `libllama.so`/`.dylib` elsewhere) as *package data*, which
PyInstaller's static import analysis does not reliably discover. A build
missing those libraries looks fine and only fails later, at first LLM
use, on someone else's machine. Both scripts now close this end to end:

1. **Pre-flight import check** - the script verifies `import llama_cpp`
   actually works *before* building. On Windows this immediately catches
   the two common failure modes (broken source build, missing VC++
   redistributable) with specific fix instructions, instead of shipping
   a build that carries the problem.
2. **`--collect-all llama_cpp`** - collects the entire package, compiled
   libraries and metadata included, rather than trusting import analysis.
3. **Post-build bundle check** - after building, the script confirms the
   native library actually landed in `_internal/llama_cpp/` and warns if
   it didn't.

If llama-cpp-python isn't installed, the scripts say so and offer to
continue with a rule-backend-only build rather than failing outright.

## Post-build smoke test

Both scripts finish by running the frozen executable with `--version` and
checking the output against the pyproject version. This catches the two
most common frozen-build failures on the build machine instead of the
recipient's: import-time crashes, and missing bundled metadata (which
would make the app misreport its version).

## Why `--onedir`, not `--onefile`

A `--onefile` build re-extracts its entire contents to a fresh temp
directory on *every single launch*. With a multi-gigabyte `.gguf` model
bundled in, that means a multi-GB copy operation every time someone opens
the app. `--onedir` unpacks once, at build time, and every launch after
that just reads files directly off disk. Both scripts use `--onedir` for
this reason - don't switch to `--onefile` if models are going to be
bundled.

## Distributing the build

Zip the whole output folder (both scripts already do this for you) and
hand it over. The recipient:
1. Unzips it
2. Double-clicks the launcher

**First launch will almost certainly trigger a security prompt** - this
is expected for software that isn't signed with a paid Apple Developer
certificate or Windows code-signing certificate, not a bug in the build:

- **macOS (Gatekeeper):** right-click the launcher, choose "Open," click
  "Open" again in the dialog. Only needed once. The build script ad-hoc
  signs the binary (`codesign --force --deep --sign -`), which prevents a
  separate "app is damaged" failure some unsigned arm64 binaries hit, but
  it does not satisfy Gatekeeper's identified-developer check - that
  requires a paid Apple Developer ID, which is a separate decision from
  the build process itself.
- **Windows (SmartScreen):** click "More info," then "Run anyway." Only
  needed once.

Both `READ ME FIRST.txt` files explain this to whoever you send the build
to, so you shouldn't need to walk them through it live.

## What's actually bundled

| Included | Not included |
|---|---|
| Full Python runtime | A code-signing certificate (see above) |
| All pip dependencies, incl. llama-cpp-python (when installed) | Auto-downloading models - you download once, before building |
| Package metadata (powers the version display) | |
| `profiles/`, `templates/`, `config.yaml` | |
| Whatever `.gguf` files are in `models/` at build time | |

## Editing profiles/templates in a built distribution

Open the `profiles/` or `templates/` folder sitting next to the
executable, edit or add `.yaml` files with any text editor, restart the
app. Discovery is a plain directory scan at startup - no manifest to
update, no rebuild required.

For anything you want to survive a future update, use the `user_data/`
folder next to the executable instead (created on first save from the
in-app profile editor): user-space profiles/templates override same-named
built-ins and are never touched by a rebuild. The old caveat about
hand-added profiles being lost on redistribution only applies to files
added directly into `profiles/`/`templates/` - `user_data/` is the
supported answer to it.

## Wheel installs

`pip install promptsmith-cli` (from a wheel or PyPI) is fully supported:
built-in profiles and templates ship inside the package itself
(`src/promptsmith/data/`), and per-user files (config, exports, custom
profiles) live under `~/.promptsmith/`. The old known limitation - where
`package-data` pointed at the wrong location and a wheel install couldn't
find its built-ins - is fixed and covered by tests.
