@echo off
rem Бэкенд (форма + /upload): через сайт http://localhost:8080/upload
rem Пароль/TOTP берутся из backend\config.env; если файла нет — временный логин admin / test без TOTP.
cd /d "%~dp0backend"
if not exist venv (
  python -m venv venv
  venv\Scripts\pip install -r requirements.txt
)
if not exist config.env (
  set ADMIN_USER=admin
  for /f "delims=" %%h in ('venv\Scripts\python -c "import bcrypt;print(bcrypt.hashpw(b'test', bcrypt.gensalt()).decode())"') do set ADMIN_PASS_HASH=%%h
)
set TRUST_PROXY=0
set COOKIE_SECURE=0
venv\Scripts\uvicorn app:app --host 127.0.0.1 --port 8100 --no-server-header
