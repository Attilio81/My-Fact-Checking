@echo off
cd /d "%~dp0"
echo === FactChecking Bot ===
".venv\Scripts\python.exe" -m bot.main
pause
