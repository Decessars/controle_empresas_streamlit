@echo off
cd /d "%~dp0"
py -m pip show streamlit >nul 2>&1
if errorlevel 1 (
  py -m pip install -r requirements.txt
)
start "Exelencia Contabilidade" /b cmd /c py -m streamlit run "Exelencia Contabilidade.py" --server.headless true --server.address localhost --server.port 8501

set "READY=0"
for /l %%i in (1,1,30) do (
  powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://localhost:8501 -TimeoutSec 1).StatusCode | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    set "READY=1"
    goto :open_browser
  )
  timeout /t 1 /nobreak >nul
)

:open_browser
start "" http://localhost:8501
