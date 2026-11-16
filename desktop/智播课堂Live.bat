@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0runtime\python\python.exe"
if not exist "%PY%" goto no_python
"%PY%" watch_live.py %*
set "RC=%errorlevel%"
if not "%RC%"=="0" pause
exit /b %RC%

:no_python
echo [ERROR] runtime\python\python.exe not found.
echo Please extract the whole zip again (keep the runtime folder).
pause
exit /b 1
