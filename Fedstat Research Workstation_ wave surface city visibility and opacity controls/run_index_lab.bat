@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python index_lab_qt_app.py
pause
