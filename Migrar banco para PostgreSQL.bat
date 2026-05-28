@echo off
cd /d "%~dp0"
if "%DATABASE_URL%"=="" (
  echo Defina a variavel DATABASE_URL antes de rodar.
  echo Exemplo:
  echo set DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/banco
  pause
  exit /b 1
)
python scripts\migrar_sqlite_para_postgres.py --replace
pause
