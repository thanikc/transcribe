@echo off
rem Windows launcher: keeps the virtualenv on a Windows drive, which matters when the repo lives in WSL.
if not defined UV_PROJECT_ENVIRONMENT set "UV_PROJECT_ENVIRONMENT=%LOCALAPPDATA%\transcribe\venv"
uv run --project "%~dp0." transcribe %*
