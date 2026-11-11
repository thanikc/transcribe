@echo off
rem Run by the installer in a visible window, so the download's progress bars show.
title Transcribe - downloading the speech model
setlocal
rem Copies instead of symlinks in the model cache: RedirectionGuard, inherited from Setup, blocks
rem symlinks made without admin rights (Windows Developer Mode would otherwise enable them).
set "HF_HUB_DISABLE_SYMLINKS=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
set "PYTHONIOENCODING=utf-8"
echo Transcribe is downloading its speech model.
echo This can take a while on a slow connection. The window closes by itself when it is done.
echo.
"%~dp0venv\Scripts\transcribe.exe" download-models
exit /b %ERRORLEVEL%
