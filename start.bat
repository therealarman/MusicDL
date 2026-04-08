@echo off
cd /d "%~dp0"
cls
echo ============================================
echo   MusicDL - Music Downloader
echo ============================================
echo.
powershell -NoProfile -Command "$e=[char]27; Write-Host ('  Server:  ' + $e + ']8;;http://127.0.0.1:8000' + $e + '\http://127.0.0.1:8000' + $e + ']8;;' + $e + '\')"
echo   Stop:    Ctrl+C
echo.
echo Starting server, browser will open shortly...
echo.
start /b cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
