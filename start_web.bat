@echo off
setlocal

set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%/"

cd /d "%~dp0"

echo ========================================
echo DownloadVideoProcessor Web Launcher
echo Project: %CD%
echo URL:     %URL%
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/api/metadata' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch { } exit 1"
if "%ERRORLEVEL%"=="0" (
    echo Web service is already running. Opening browser...
    start "" "%URL%"
    exit /b 0
)

where python >nul 2>nul
if not "%ERRORLEVEL%"=="0" (
    echo Python was not found in PATH.
    echo Install Python or add it to PATH, then run this launcher again.
    echo.
    pause
    exit /b 1
)

if not exist "scripts\run_similarity.py" (
    echo scripts\run_similarity.py was not found.
    echo Make sure this launcher stays in the project root directory.
    echo.
    pause
    exit /b 1
)

if not exist "output\video_similarity\data.json" (
    echo output\video_similarity\data.json was not found.
    echo Run a similarity scan once before starting the Web workspace.
    echo.
    pause
    exit /b 1
)

echo Starting Web service...
echo Close this window to stop the backend service.
echo.
python scripts\run_similarity.py --server-only

echo.
echo Web service stopped.
pause
