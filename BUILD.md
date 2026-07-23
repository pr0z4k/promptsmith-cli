# Building PromptSmith-cli standalone packages

**Last reviewed:** 2026-07-23  
**Applies to version:** v1 release candidate

PromptSmith-cli can be packaged as a self-contained folder and ZIP for macOS, Linux, or Windows. The recipient does not need Python, pip, Git, or a compiler.

The portable layout is intentional:

```text
PromptSmith-cli-<version>-<platform>-<arch>/
├── PromptSmith-cli(.exe)                 # executable
├── platform launcher (.command/.sh/.bat)
├── profiles/                             # editable built-in profiles
├── templates/                            # editable built-in templates
├── models/                               # bundled or user-added GGUF files
├── config.yaml
├── READ ME FIRST.txt
├── user_data/                            # created at runtime
└── _internal/                            # Python runtime and dependencies
```

Keep the whole folder together. The executable depends on `_internal/` and the adjacent data folders.

## Platform rule

PyInstaller does not cross-compile.

- Build macOS artifacts on macOS.
- Build Linux artifacts on Linux.
- Build Windows artifacts on Windows.
- Build separately for each required architecture.

A macOS Apple Silicon artifact will not run on Windows, Linux, or an Intel-only Mac. Label release files with both platform and architecture.

## Versioning

The version is defined in `pyproject.toml`. The build scripts read it through `tools/get_version.py`, include package metadata in the frozen application, and use it in output folder and ZIP names.

After changing the version:

```sh
python -m pip install -e .
```

Verify before building:

```sh
promptsmith --version
```

## Prepare the build machine

Run from the repository root.

### macOS or Linux

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
```

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
```

The standard PromptSmith installation already includes `llama-cpp-python`; the historical `[llm]` extra is no longer required.

### Windows native-runtime note

If `llama-cpp-python` fails to install from source, install the prebuilt CPU wheel:

```powershell
python -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

If importing `llama_cpp` fails after installation, install the Microsoft Visual C++ Redistributable for x64. Do this on the build machine before creating an artifact so the build preflight can detect a working native runtime.

## Decide whether to bundle models

Run PromptSmith and use **Settings -> Download LLM Models** before building.

The scripts copy the current contents of `models/` into the portable folder.

| Build choice | Result |
|---|---|
| Bundle Phi-4-mini | Larger ZIP; Rules, LLM, and Hybrid work immediately |
| Bundle TinyLlama | Smaller model footprint; lower refinement quality |
| Bundle both | Largest ZIP; recipient can switch models immediately |
| Bundle no model | Smallest ZIP; Rules work immediately and models can be downloaded later |

Models are large. Consider publishing two artifacts:

- a smaller base ZIP without models
- a ready-to-run ZIP with the recommended model bundled

Do not use PyInstaller `--onefile` for model-bearing builds. A one-file package would re-extract multi-gigabyte content on every launch. PromptSmith uses `--onedir` so extraction happens once, at build time.

## Build commands

### macOS

```sh
./build_cli.sh
```

Expected artifacts:

```text
dist/PromptSmith-cli-<version>-macos-<arch>/
dist/PromptSmith-cli-<version>-macos-<arch>.zip
```

The folder includes `PromptSmith-cli`, `Start PromptSmith-cli.command`, and `READ ME FIRST.txt`.

### Linux

```sh
./build_cli.sh
```

Expected artifacts:

```text
dist/PromptSmith-cli-<version>-linux-<arch>/
dist/PromptSmith-cli-<version>-linux-<arch>.zip
```

The folder includes `PromptSmith-cli` and `start-promptsmith-cli.sh`.

### Windows

Run from Command Prompt or PowerShell:

```bat
build_windows.bat
```

Expected artifacts:

```text
dist\PromptSmith-cli-<version>-windows-x64\
dist\PromptSmith-cli-<version>-windows-x64.zip
```

The folder includes `PromptSmith-cli.exe`, `Start PromptSmith-cli.bat`, and `READ ME FIRST.txt`.

## What the scripts verify

The native build scripts perform these checks:

1. Read the package version from `pyproject.toml`.
2. Verify `llama_cpp` imports before packaging.
3. Build with PyInstaller in `--onedir` mode.
4. Collect the full `llama_cpp` package, including native libraries.
5. Copy profiles, templates, configuration, and current models.
6. Confirm native llama.cpp libraries are present under `_internal/`.
7. Run the frozen executable with `--version`.
8. Compare frozen output with the package version.
9. Create the distributable ZIP.

A build that passes only PyInstaller compilation is not sufficient. The post-build smoke test matters because native library or metadata omissions often appear only when the frozen executable starts.

## Verify the artifact before sharing

Test the extracted ZIP on the build machine, not only the uncompressed build directory.

### Basic verification

1. Extract the generated ZIP into a new temporary directory.
2. Launch using the included platform launcher.
3. Confirm the About screen reports the expected version.
4. Analyze a prompt with `Ctrl+Enter`.
5. Refine with Rules.
6. If a model is bundled, test LLM and Hybrid.
7. Switch models during the same session when more than one is bundled.
8. Close and reopen the application.
9. Confirm `user_data/` and history behavior are writable.

### Terminal verification

macOS or Linux:

```sh
./PromptSmith-cli --version
```

Windows:

```powershell
.\PromptSmith-cli.exe --version
```

## Distribute the ZIP

The generated ZIP is the product you share. Do not send only the executable.

Suitable distribution methods include:

- GitHub Releases
- shared cloud storage
- internal file shares
- USB media
- direct transfer to friends or teammates

The recipient should:

1. Download the ZIP for their operating system and architecture.
2. Extract the complete ZIP.
3. Keep all files and folders together.
4. Start PromptSmith using the included launcher.

### macOS Gatekeeper

Unsigned or ad-hoc-signed builds will usually trigger Gatekeeper.

The recipient should right-click `Start PromptSmith-cli.command`, choose **Open**, and confirm **Open**. This is normally needed only once.

The build script uses ad-hoc signing where available to avoid some damaged-binary failures, but ad-hoc signing is not Apple Developer ID signing and does not provide notarization.

For public releases intended for strangers, the proper long-term path is:

1. sign with an Apple Developer ID certificate
2. notarize with Apple
3. staple the notarization ticket

Do not tell recipients to disable Gatekeeper globally.

### Windows SmartScreen

Unsigned builds may trigger SmartScreen. The recipient can choose **More info** and then **Run anyway** after verifying the ZIP came from the expected source.

For broader public distribution, sign the executable and installer artifacts with a trusted Windows code-signing certificate.

Do not tell recipients to disable SmartScreen globally.

### Linux permissions

Some ZIP tools do not preserve executable bits. When needed:

```sh
chmod +x PromptSmith-cli start-promptsmith-cli.sh
```

Then launch:

```sh
./start-promptsmith-cli.sh
```

## Integrity for release artifacts

For public or semi-public sharing, publish a SHA-256 checksum beside every ZIP.

macOS or Linux:

```sh
shasum -a 256 dist/PromptSmith-cli-<version>-<platform>-<arch>.zip
```

Linux alternative:

```sh
sha256sum dist/PromptSmith-cli-<version>-linux-<arch>.zip
```

Windows PowerShell:

```powershell
Get-FileHash .\dist\PromptSmith-cli-<version>-windows-x64.zip -Algorithm SHA256
```

Recipients can compare the checksum before extracting. A checksum proves the file matches what you published; it does not replace code signing.

## What is included

| Included | Not included |
|---|---|
| Python runtime | Apple or Windows commercial signing certificate |
| PromptSmith dependencies | Automatic trust from Gatekeeper or SmartScreen |
| `llama-cpp-python` and native libraries | Cross-platform compatibility |
| Package metadata | Models not present in `models/` at build time |
| Profiles, templates, and configuration | Automatic future upgrades |
| Any bundled GGUF models | Encrypted local history |
| Launchers and first-run instructions | |

## Updating a portable installation

Portable builds do not auto-update.

Recommended update process:

1. Back up the recipient's `user_data/` directory.
2. Extract the new release into a new folder.
3. Copy the old `user_data/` directory into the new folder.
4. Copy any custom GGUF files that are not included in the new release.
5. Test the new version before deleting the previous folder.

Do not overwrite `_internal/` piecemeal. Replace the complete application folder while preserving user-owned data.

## Editing profiles and templates

The top-level `profiles/` and `templates/` folders are readable and editable. Changes there affect that extracted distribution but may be replaced by a future build.

Persistent user additions belong under:

```text
user_data/profiles/
user_data/templates/
```

User-space entries override same-named built-ins and survive replacement of the application folder when `user_data/` is carried forward.

## Wheel and source installs

Portable ZIPs are one distribution method, not the only one.

- Source checkout: `python -m pip install -e .`
- Built wheel: `python -m pip install dist/promptsmith_cli-<version>-py3-none-any.whl`
- Future PyPI release: `python -m pip install promptsmith-cli`
- Portable native folder: extract the platform ZIP and use the launcher

Wheel and source installations store user data under `~/.promptsmith/`. Portable builds store it under `user_data/` beside the executable.
