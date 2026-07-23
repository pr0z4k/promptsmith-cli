#!/bin/bash
# Build a standalone PromptSmith-cli executable for macOS or Linux.
#
# Run this SCRIPT ON THE TARGET MACHINE - PyInstaller does not cross-compile.
# To build the Windows executable, run build_windows.bat on a Windows machine.
#
# Output layout - profiles/templates/models are deliberately kept as
# visible, directly editable folders, not buried in PyInstaller's internals:
#   PromptSmith-cli-<version>-<platform>-<arch>/
#   ├── PromptSmith-cli            <- the executable
#   ├── Start PromptSmith-cli.command  <- double-click launcher (macOS)
#   ├── profiles/                  <- edit or add .yaml files directly, no rebuild needed
#   ├── templates/                 <- same
#   ├── models/                    <- drop in additional .gguf files directly
#   ├── config.yaml
#   ├── READ ME FIRST.txt
#   └── _internal/                 <- Python runtime + dependencies only, not meant to be touched
#
# IMPORTANT - do this before running the script:
#   1. `pip install -e ".[llm]"` (gets llama-cpp-python bundled in)
#   2. Run `promptsmith`, go to Settings > Download LLM Models, and download
#      whichever model(s) you want shipped. Whatever's in models/ at build
#      time gets bundled - nothing is downloaded automatically by this script.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
BUILD_DIR="$PROJECT_ROOT/build"

# Single source of truth: read the version from pyproject.toml. Bumping it
# there automatically renames the build artifacts and updates the version
# the frozen app reports (via bundled package metadata, see --copy-metadata
# below). tomllib needs Python 3.11+; fall back to a plain parse otherwise.
VERSION=$(python3 "$PROJECT_ROOT/tools/get_version.py")
APP_NAME="PromptSmith-cli"
DATA_ROOT="$PROJECT_ROOT/src/promptsmith/data"

UNAME=$(uname -s)
ARCH=$(uname -m)
case "$UNAME" in
    Linux*)     PLATFORM="linux" ;;
    Darwin*)    PLATFORM="macos" ;;
    *)          echo "This script is for macOS/Linux. Use build_windows.bat on Windows."; exit 1 ;;
esac

BUILD_NAME="$APP_NAME-$VERSION-$PLATFORM-$ARCH"
DIST_PATH="$DIST_DIR/$BUILD_NAME"

echo "=================================================================="
echo " Building $APP_NAME v$VERSION for $PLATFORM-$ARCH"
echo "=================================================================="

rm -rf "$BUILD_DIR" "$DIST_PATH" "$DIST_DIR/$BUILD_NAME.zip"
mkdir -p "$DIST_DIR"
mkdir -p "$PROJECT_ROOT/models"

if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "Installing PyInstaller..."
    if ! pip install pyinstaller --quiet 2>/tmp/pyinstaller_install_err.txt; then
        if grep -q "externally-managed-environment" /tmp/pyinstaller_install_err.txt; then
            echo ""
            echo "ERROR: This Python is externally managed and won't allow a direct"
            echo "pip install (common with Homebrew Python on macOS, or system Python"
            echo "on some Linux distros)."
            echo ""
            echo "Fix: build inside a virtual environment instead -"
            echo "  python3 -m venv .venv"
            echo "  source .venv/bin/activate"
            echo "  pip install -e \".[llm]\""
            echo "  ./build_cli.sh"
            rm -f /tmp/pyinstaller_install_err.txt
            exit 1
        else
            cat /tmp/pyinstaller_install_err.txt
            rm -f /tmp/pyinstaller_install_err.txt
            exit 1
        fi
    fi
    rm -f /tmp/pyinstaller_install_err.txt
fi

# The frozen app reads its version from bundled package metadata, so the
# package itself must be installed (editable is fine) before building.
if ! python3 -c "import importlib.metadata as m; m.version('promptsmith-cli')" 2>/dev/null; then
    echo "ERROR: promptsmith-cli is not installed in this environment."
    echo "Run: pip install -e \".[llm]\"  (or at least pip install -e .)"
    exit 1
fi

# llama-cpp-python check: without it, only the rule-based backend ships.
HAS_LLAMA=0
if python3 -c "import llama_cpp" 2>/dev/null; then
    HAS_LLAMA=1
    echo "llama-cpp-python found - LLM backend will be bundled."
else
    echo ""
    echo "WARNING: llama-cpp-python is not importable in this environment."
    echo "The build will work, but only the 'rule' backend will function."
    echo "To bundle LLM support: pip install -e \".[llm]\" and re-run."
    echo ""
fi

MODEL_COUNT=$(find "$PROJECT_ROOT/models" -name "*.gguf" 2>/dev/null | wc -l | tr -d ' ')
if [ "$MODEL_COUNT" -eq 0 ]; then
    echo ""
    echo "WARNING: No .gguf model files found in models/."
    echo "This build will only have the rule-based backend available -"
    echo "'llm' and 'hybrid' profiles will not work until a model is added."
    echo "Run the app first, use Settings > Download LLM Models, then re-run this script."
    echo ""
    read -p "Continue without a bundled model? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "Bundling $MODEL_COUNT model file(s) from models/"
fi

# --onedir, not --onefile: a bundled multi-GB model would otherwise be
# re-extracted to a fresh temp directory on every single launch.
#
# --copy-metadata promptsmith-cli: bundles the package's dist-info so the
# frozen app can read its own version via importlib.metadata - this is
# what ties the About screen and --version to pyproject.toml in a build.
PYINSTALLER_ARGS=(
    --name="$APP_NAME"
    --onedir
    --console
    --noconfirm
    --copy-metadata promptsmith-cli
    --distpath="$DIST_DIR"
    --workpath="$BUILD_DIR"
    --specpath="$BUILD_DIR"
)

# --collect-all llama_cpp: llama-cpp-python carries its compiled library
# (libllama.dylib / libllama.so) as package data that PyInstaller's static
# analysis does not reliably discover on its own. Collecting the whole
# package pulls in the binaries, metadata, and any vendored data - the
# same class of missing-library failure the Windows build was hitting.
# Only passed when llama_cpp is actually importable.
if [ "$HAS_LLAMA" -eq 1 ]; then
    PYINSTALLER_ARGS+=(--collect-all llama_cpp)
fi

if [ "$PLATFORM" = "macos" ] && [ -f "$PROJECT_ROOT/assets/icon.icns" ]; then
    PYINSTALLER_ARGS+=(--icon="$PROJECT_ROOT/assets/icon.icns")
fi
if [ "$PLATFORM" = "linux" ] && [ -f "$PROJECT_ROOT/assets/icon.png" ]; then
    PYINSTALLER_ARGS+=(--icon="$PROJECT_ROOT/assets/icon.png")
fi

python3 -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$PROJECT_ROOT/src/promptsmith/cli/app.py"

# PyInstaller writes to dist/<APP_NAME> - rename to the versioned folder.
mv "$DIST_DIR/$APP_NAME" "$DIST_PATH"

# Copy (not --add-data) profiles/templates/models/config.yaml directly into
# the top-level folder, as visible siblings of the executable. --add-data
# would route them through PyInstaller's bundling into the hidden
# _internal/ runtime folder alongside the Python interpreter and compiled
# dependencies - fine for code, not for anything meant to be found and
# edited by hand. Built-in profiles/templates now live inside the package
# (src/promptsmith/data/), which is the canonical copy for both source
# installs and these builds.
cp -R "$DATA_ROOT/profiles" "$DIST_PATH/profiles"
cp -R "$DATA_ROOT/templates" "$DIST_PATH/templates"
cp -R "$PROJECT_ROOT/models" "$DIST_PATH/models"
cp "$PROJECT_ROOT/config.yaml" "$DIST_PATH/config.yaml"

# Double-click launcher. The binary itself works fine run directly, but a
# .command file is what Finder/Terminal actually double-click-launches on
# macOS, and it guarantees we're in the right working directory.
if [ "$PLATFORM" = "macos" ]; then
    cat > "$DIST_PATH/Start $APP_NAME.command" << 'LAUNCHEREOF'
#!/bin/bash
cd "$(dirname "$0")"
./PromptSmith-cli
LAUNCHEREOF
    chmod +x "$DIST_PATH/Start $APP_NAME.command"
    chmod +x "$DIST_PATH/$APP_NAME"

    # Ad-hoc codesign: doesn't satisfy Gatekeeper's "identified developer"
    # check (that needs a paid Apple Developer ID), but it does prevent the
    # separate "app is damaged" failure mode that an entirely unsigned
    # arm64 binary can hit. The user will still need to right-click > Open
    # the first time - that's expected for unsigned distribution, not a bug.
    if command -v codesign &> /dev/null; then
        echo "Ad-hoc signing the executable..."
        codesign --force --deep --sign - "$DIST_PATH/$APP_NAME" 2>/dev/null || \
            echo "  (codesign skipped - not fatal, Gatekeeper prompt will still work)"
    fi
fi

if [ "$PLATFORM" = "linux" ]; then
    cat > "$DIST_PATH/start-promptsmith-cli.sh" << 'LAUNCHEREOF'
#!/bin/bash
cd "$(dirname "$0")"
./PromptSmith-cli
LAUNCHEREOF
    chmod +x "$DIST_PATH/start-promptsmith-cli.sh"
    chmod +x "$DIST_PATH/$APP_NAME"
fi

cp "$PROJECT_ROOT/README.md" "$DIST_PATH/" 2>/dev/null || true
cp "$PROJECT_ROOT/LICENSE" "$DIST_PATH/" 2>/dev/null || true

if [ "$PLATFORM" = "macos" ]; then
    cat > "$DIST_PATH/READ ME FIRST.txt" << 'NOTEEOF'
PromptSmith-cli - macOS

TO RUN: double-click "Start PromptSmith-cli.command"

FIRST TIME ONLY: macOS will likely block this because it's from an
unidentified developer (it isn't signed with a paid Apple Developer
certificate). To allow it:
  1. Right-click (or Control-click) "Start PromptSmith-cli.command"
  2. Choose "Open"
  3. Click "Open" again in the dialog that appears
This only needs to be done once - after that, double-clicking works
normally.

This is expected behavior for software distributed outside the App
Store without an Apple Developer certificate, not a bug in the build.

Project home: https://codeberg.org/prozak/promptsmith-cli
Support:      https://codeberg.org/prozak/promptsmith-cli/issues
NOTEEOF
fi

# --- Post-build smoke test -----------------------------------------------
# The frozen binary must start, report the pyproject version, and exit 0.
# Catches the two most common frozen-build failures immediately: missing
# bundled metadata (version would fall back to 0.0.0.dev0) and
# import-time crashes.
echo "Running post-build smoke test..."
SMOKE_OUTPUT=$("$DIST_PATH/$APP_NAME" --version)
echo "  $SMOKE_OUTPUT"
if ! echo "$SMOKE_OUTPUT" | grep -q "$VERSION"; then
    echo "ERROR: built executable does not report version $VERSION."
    echo "The bundled package metadata is missing or stale - rebuild after"
    echo "reinstalling: pip install -e . && ./build_cli.sh"
    exit 1
fi
if [ "$HAS_LLAMA" -eq 1 ]; then
    if find "$DIST_PATH/_internal/llama_cpp" \( -name "*.so" -o -name "*.dylib" \) 2>/dev/null | grep -q .; then
        echo "  llama_cpp native library present in bundle."
    else
        echo "WARNING: llama_cpp was installed but its native library was not"
        echo "found in the bundle - LLM profiles may fail in this build."
    fi
fi

cd "$DIST_DIR"
zip -qr "$BUILD_NAME.zip" "$BUILD_NAME"
rm -rf "$BUILD_DIR"

echo ""
echo "=================================================================="
echo " Build complete"
echo "=================================================================="
echo " Folder:  $DIST_PATH"
echo " Archive: $DIST_DIR/$BUILD_NAME.zip"
echo ""
du -sh "$DIST_PATH" 2>/dev/null
echo ""
echo "Hand the .zip to anyone on the same OS/architecture. They unzip it"
echo "and double-click the launcher inside - no Python install needed."
