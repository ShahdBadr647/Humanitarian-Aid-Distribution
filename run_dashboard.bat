@echo off
REM Start the dashboard using the Python environment installed on drive D:
cd /d "%~dp0"
"D:\aid-venv\Scripts\streamlit.exe" run app.py
pause
