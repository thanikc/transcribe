@echo off
rem Windows launcher: keeps the virtualenv on a Windows drive, which matters when the repo lives in WSL.
if not defined UV_PROJECT_ENVIRONMENT set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\transcribe\venv"
rem Claude Desktop may not pass the shell's PATH, so fall back to uv's default install location.
set "UV=uv"
where uv >nul 2>nul || set "UV=%USERPROFILE%\.local\bin\uv.exe"
"%UV%" run --project "%~dp0." transcribe %*
