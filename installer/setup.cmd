@echo off
rem Run by the installer: downloads Python 3.12 and the pinned libraries into this folder.
setlocal
set "HERE=%~dp0"
set "UV_PROJECT_ENVIRONMENT=%HERE%venv"
set "UV_PYTHON_INSTALL_DIR=%HERE%python"
set "UV_CACHE_DIR=%HERE%cache"
set "UV_PYTHON_PREFERENCE=only-managed"
"%HERE%uv.exe" sync --frozen --no-dev --no-editable --project "%HERE%app" > "%HERE%install.log" 2>&1
exit /b %ERRORLEVEL%
