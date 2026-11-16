@echo off
rem SSB Group - Windows'da bir bosishda ishga tushirish.
setlocal EnableDelayedExpansion
set PYTHONUTF8=1
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
cd /d "%~dp0"

where python >nul 2>nul || (echo Python topilmadi. https://www.python.org/downloads/ dan o'rnating. & pause & exit /b 1)

if not exist .venv (
  echo [1/5] Virtual muhit yaratilmoqda...
  python -m venv .venv || (pause & exit /b 1)
)
call ".\.venv\Scripts\activate.bat"

echo [2/5] Kutubxonalar tekshirilmoqda...
pip install -q -r requirements.txt || (pause & exit /b 1)

if not exist .env (
  echo [3/5] .env yaratilmoqda...
  for /f %%k in ('python -c "import secrets;print(secrets.token_urlsafe(50))"') do set KEY=%%k
  (
    echo DJANGO_DEBUG=True
    echo DJANGO_SECRET_KEY=!KEY!
    if exist .pgdata (
      echo DATABASE_URL=postgres://ssb@127.0.0.1:5433/ssb
    ) else (
      echo DATABASE_URL=postgres://postgres:postgres@localhost:5432/ssb
    )
  ) > .env
  echo .env yaratildi.
)

if exist .pg\bin\pg_ctl.exe (
  if not exist .setup mkdir .setup
  ".pg\bin\pg_ctl.exe" -D .pgdata status >nul 2>nul
  if errorlevel 1 (
    if exist .pgdata\postmaster.pid (
      ".pg\bin\pg_ctl.exe" -D .pgdata status >nul 2>nul || del /f /q .pgdata\postmaster.pid 2>nul
    )
    echo PostgreSQL ishga tushirilmoqda...
    ".pg\bin\pg_ctl.exe" -D .pgdata -l .setup\postgresql.log -w start
  )
)

echo [4/5] Baza yangilanmoqda...
python manage.py migrate || (echo PostgreSQL ishlamayapti yoki ssb bazasi yoq. & pause & exit /b 1)

python -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from apps.accounts.models import User;raise SystemExit(0 if User.objects.filter(role__is_owner=True).exists() else 1)"
if errorlevel 1 (
  echo Rahbar hisobi yaratilmoqda: login ssbgroup
  if defined SSB_FOUNDER_PASSWORD (
    python manage.py bootstrap_company --username ssbgroup --no-input
  ) else (
    python manage.py bootstrap_company --username ssbgroup
  )
  python manage.py seed_site
)

echo [5/5] Server ishga tushdi: http://127.0.0.1:8000/
start "" http://127.0.0.1:8000/
python manage.py runserver
if errorlevel 1 (
  echo.
  echo Server toxtadi.
  pause
)
