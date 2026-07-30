@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m collector.collect --config config/sources.yaml
