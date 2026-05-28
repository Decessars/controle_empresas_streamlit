@echo off
cd /d "%~dp0"
py -m pip show streamlit >nul 2>&1
if errorlevel 1 (
  py -m pip install -r requirements.txt
)
py -m streamlit run app.py
