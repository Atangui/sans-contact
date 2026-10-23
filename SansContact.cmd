@echo off
rem Launch SansContact without a console window (never as administrator).
setlocal
set "PYTHONPATH=%~dp0src"
start "" "%~dp0.venv\Scripts\pythonw.exe" -m sanscontact %*
