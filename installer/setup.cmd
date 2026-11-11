@echo off
rem Run by the installer: downloads the pinned libraries into a virtualenv on the bundled Python.
rem The installer ships Python as plain files because a uv-managed Python adds a junction that Inno Setup's
rem RedirectionGuard (inherited by this script) refuses to follow: "untrusted mount point (os error 448)".
setlocal
set "HERE=%~dp0"
set "UV_PROJECT_ENVIRONMENT=%HERE%venv"
set "UV_CACHE_DIR=%HERE%cache"
set "UV_PYTHON_DOWNLOADS=never"
"%HERE%uv.exe" sync --frozen --no-dev --no-editable --python "%HERE%runtime\python.exe" --project "%HERE%app" > "%HERE%install.log" 2>&1
exit /b %ERRORLEVEL%
