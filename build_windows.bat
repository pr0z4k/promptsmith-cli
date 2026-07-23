@echo off
setlocal enabledelayedexpansion
REM PromptSmith-cli build script for Windows.
REM
REM Run this SCRIPT ON A WINDOWS MACHINE - PyInstaller does not cross-compile.
REM To build the macOS/Linux executable, run build_cli.sh on that machine.
REM
REM Output layout - profiles/templates/models are deliberately kept as
REM visible, directly editable folders, not buried in PyInstaller's internals:
REM   PromptSmith-cli-<version>-windows-x64\
REM   |-- PromptSmith-cli.exe          <- the executable
REM   |-- Start PromptSmith-cli.bat    <- double-click launcher
REM   |-- profiles\                    <- edit or add .yaml files directly, no rebuild needed
REM   |-- templates\                   <- same
REM   |-- models\                      <- drop in additional .gguf files directly
REM   |-- config.yaml
REM   |-- READ ME FIRST.txt
REM   `-- _internal\                   <- Python runtime + dependencies only, not meant to be touched
REM
REM IMPORTANT - do this before running the script:
REM   1. pip install -e ".[llm]"   (gets llama-cpp-python bundled in)
REM      On Windows, llama-cpp-python has no compiler-free source build:
REM      if pip tries to compile from source and fails, install a prebuilt
REM      CPU wheel instead:
REM        pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
REM   2. Run "promptsmith", go to Settings ^> Download LLM Models, and
REM      download whichever model(s) you want shipped. Whatever's in
REM      models\ at build time gets bundled - nothing is downloaded
REM      automatically by this script.

set PROJECT_ROOT=%~dp0
set APP_NAME=PromptSmith-cli
set DATA_ROOT=%PROJECT_ROOT%src\promptsmith\data
set DIST_DIR=%PROJECT_ROOT%dist
set BUILD_DIR=%PROJECT_ROOT%build

REM Single source of truth: read the version from pyproject.toml. Bumping
REM it there automatically renames the build artifacts and updates the
REM version the frozen app reports (via bundled package metadata below).
for /f "usebackq delims=" %%v in (`python "%PROJECT_ROOT%tools\get_version.py"`) do set VERSION=%%v
if "%VERSION%"=="" (
    echo ERROR: could not read version from pyproject.toml
    exit /b 1
)

set BUILD_NAME=%APP_NAME%-%VERSION%-windows-x64
set DIST_PATH=%DIST_DIR%\%BUILD_NAME%

echo ==================================================================
echo  Building %APP_NAME% v%VERSION% for Windows
echo ==================================================================

if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_PATH%" rmdir /s /q "%DIST_PATH%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%PROJECT_ROOT%models" mkdir "%PROJECT_ROOT%models"

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller --quiet
)

REM The frozen app reads its version from bundled package metadata, so
REM the package itself must be installed (editable is fine) first.
python -c "import importlib.metadata as m; m.version('promptsmith-cli')" 2>nul
if errorlevel 1 (
    echo ERROR: promptsmith-cli is not installed in this environment.
    echo Run: pip install -e ".[llm]"   ^(or at least pip install -e .^)
    exit /b 1
)

REM --- llama-cpp-python pre-flight ---------------------------------------
REM This is the historically weak part of the Windows build: llama-cpp's
REM compiled DLLs (llama.dll, ggml*.dll) ship as package data that
REM PyInstaller's static analysis does not reliably pick up, and a build
REM without them fails only later, at first LLM use, on someone else's
REM machine. So: verify it IMPORTS here (catches missing VC++ runtime and
REM broken wheels immediately), and bundle it with --collect-all so every
REM DLL travels with the app.
set HAS_LLAMA=0
python -c "import llama_cpp" 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: llama-cpp-python is not importable in this environment.
    echo The build will work, but only the 'rule' backend will function -
    echo 'llm' and 'hybrid' profiles will not.
    echo.
    echo To bundle LLM support, install a prebuilt CPU wheel and re-run:
    echo   pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
    echo If it installs but still fails to import, install the Microsoft
    echo Visual C++ Redistributable ^(x64^) - the DLLs depend on it:
    echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo.
    set /p CONTINUE="Continue without LLM support? [y/N] "
    if /i not "!CONTINUE!"=="y" exit /b 1
) else (
    set HAS_LLAMA=1
    echo llama-cpp-python found - LLM backend will be bundled.
)

REM Count .gguf files robustly. A naive `for %%f in (*.gguf)` executes ONCE
REM with the literal unexpanded pattern when no files match (a cmd.exe
REM quirk), which would miscount an empty models\ dir as having one model
REM and skip the warning below. `if exist` guards against that, and we only
REM increment for entries that are real files.
set MODEL_COUNT=0
if exist "%PROJECT_ROOT%models\*.gguf" (
    for %%f in ("%PROJECT_ROOT%models\*.gguf") do (
        if exist "%%f" set /a MODEL_COUNT+=1
    )
)
if %MODEL_COUNT%==0 (
    echo.
    echo WARNING: No .gguf model files found in models\.
    echo This build will only have the rule-based backend available -
    echo 'llm' and 'hybrid' profiles will not work until a model is added.
    echo Run the app first, use Settings ^> Download LLM Models, then re-run this script.
    echo.
    set /p CONTINUE="Continue without a bundled model? [y/N] "
    if /i not "!CONTINUE!"=="y" exit /b 1
) else (
    echo Bundling %MODEL_COUNT% model file^(s^) from models\
)

REM --onedir, not --onefile: a bundled multi-GB model would otherwise be
REM re-extracted to a fresh temp directory on every single launch.
REM --copy-metadata: bundles dist-info so the frozen app reads its own
REM version via importlib.metadata - ties About/--version to pyproject.
set LLAMA_ARGS=
if %HAS_LLAMA%==1 set LLAMA_ARGS=--collect-all llama_cpp

python -m PyInstaller ^
    --name=%APP_NAME% ^
    --onedir ^
    --console ^
    --noconfirm ^
    --copy-metadata promptsmith-cli ^
    %LLAMA_ARGS% ^
    --distpath="%DIST_DIR%" ^
    --workpath="%BUILD_DIR%" ^
    --specpath="%BUILD_DIR%" ^
    "%PROJECT_ROOT%src\promptsmith\cli\app.py"

if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

move "%DIST_DIR%\%APP_NAME%" "%DIST_PATH%" >nul

REM Copy (not --add-data) profiles/templates/models/config.yaml directly
REM into the top-level folder, as visible siblings of the executable.
REM --add-data would route them through PyInstaller's bundling into the
REM hidden _internal\ runtime folder - fine for code, not for anything
REM meant to be found and edited by hand. Built-in profiles/templates now
REM live inside the package (src\promptsmith\data\), the canonical copy
REM for both source installs and these builds.
xcopy /e /i /q "%DATA_ROOT%\profiles" "%DIST_PATH%\profiles" >nul
xcopy /e /i /q "%DATA_ROOT%\templates" "%DIST_PATH%\templates" >nul
xcopy /e /i /q "%PROJECT_ROOT%models" "%DIST_PATH%\models" >nul
copy "%PROJECT_ROOT%config.yaml" "%DIST_PATH%\config.yaml" >nul

REM Double-click launcher - opens the exe in its own console window from
REM the right working directory.
(
echo @echo off
echo cd /d "%%~dp0"
echo start "%APP_NAME%" "%APP_NAME%.exe"
) > "%DIST_PATH%\Start %APP_NAME%.bat"

copy "%PROJECT_ROOT%README.md" "%DIST_PATH%\" >nul 2>nul
copy "%PROJECT_ROOT%LICENSE" "%DIST_PATH%\" >nul 2>nul

(
echo PromptSmith-cli - Windows
echo.
echo TO RUN: double-click "Start PromptSmith-cli.bat"
echo.
echo FIRST TIME ONLY: Windows SmartScreen will likely warn that this is
echo an unrecognized app, since it isn't signed with a paid code-signing
echo certificate. To allow it:
echo   1. Click "More info" on the SmartScreen warning
echo   2. Click "Run anyway"
echo This only needs to be done once.
echo.
echo This is expected behavior for unsigned software, not a bug in the build.
echo.
echo IF LLM PROFILES FAIL with a DLL error: install the Microsoft Visual
echo C++ Redistributable ^(x64^), which llama.cpp's DLLs depend on:
echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
echo Project home: https://codeberg.org/prozak/promptsmith-cli
echo Support:      https://codeberg.org/prozak/promptsmith-cli/issues
) > "%DIST_PATH%\READ ME FIRST.txt"

REM --- Post-build smoke test ----------------------------------------------
REM The frozen exe must start, report the pyproject version, and exit 0.
REM Catches missing bundled metadata and import-time crashes right here,
REM instead of on the recipient's machine.
echo Running post-build smoke test...
"%DIST_PATH%\%APP_NAME%.exe" --version > "%TEMP%\ps_smoke.txt" 2>&1
if errorlevel 1 (
    echo ERROR: built executable failed to run. Output:
    type "%TEMP%\ps_smoke.txt"
    exit /b 1
)
findstr /c:"%VERSION%" "%TEMP%\ps_smoke.txt" >nul
if errorlevel 1 (
    echo ERROR: built executable does not report version %VERSION%.
    type "%TEMP%\ps_smoke.txt"
    echo The bundled package metadata is missing or stale - rebuild after
    echo reinstalling: pip install -e . ^&^& build_windows.bat
    exit /b 1
)
type "%TEMP%\ps_smoke.txt"
del "%TEMP%\ps_smoke.txt" >nul 2>nul

if %HAS_LLAMA%==1 (
    if exist "%DIST_PATH%\_internal\llama_cpp\lib\llama.dll" (
        echo   llama.dll present in bundle.
    ) else (
        dir /b /s "%DIST_PATH%\_internal\llama_cpp\*.dll" >nul 2>nul
        if errorlevel 1 (
            echo WARNING: llama_cpp was installed but no DLLs were found in
            echo the bundle - LLM profiles may fail in this build.
        ) else (
            echo   llama_cpp DLLs present in bundle.
        )
    )
)

cd /d "%DIST_DIR%"
powershell -NoProfile -Command "Compress-Archive -Path '%BUILD_NAME%' -DestinationPath '%BUILD_NAME%.zip' -Force"
rmdir /s /q "%BUILD_DIR%"

echo.
echo ==================================================================
echo  Build complete
echo ==================================================================
echo  Folder:  %DIST_PATH%
echo  Archive: %DIST_DIR%\%BUILD_NAME%.zip
echo.
echo Hand the .zip to anyone on 64-bit Windows. They unzip it and
echo double-click "Start %APP_NAME%.bat" - no Python install needed.

endlocal
