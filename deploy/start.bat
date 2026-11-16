@echo off
rem SSB Group — saytni ssbgroup.uz domenida ishga tushirish (server + Cloudflare Tunnel).
setlocal EnableDelayedExpansion
chcp 65001 >nul
title SSB Group — ishga tushirish
set PYTHONUTF8=1
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
cd /d "%~dp0.."
set "ROOT=%CD%"
if not exist "deploy\run" mkdir "deploy\run"
if not exist "deploy\logs" mkdir "deploy\logs"
if not exist "deploy\bin" mkdir "deploy\bin"

echo.
echo  ==============================================
echo     SSB Group  ^|  ssbgroup.uz  ^|  START
echo  ==============================================
echo.

rem ---- allaqachon ishlayaptimi? Unda eski nusxani to'xtatib, eng yangi kod bilan qayta yoqamiz
rem      (aks holda domenda eski versiya qolib ketadi).
if exist "deploy\run\server.pid" (
  set /p OLDPID=<"deploy\run\server.pid"
  tasklist /FI "PID eq !OLDPID!" 2>nul | find "!OLDPID!" >nul && (
    echo  Eski server to'xtatilmoqda - yangi versiya bilan qayta yoqiladi...
    call "%~dp0stop.bat" quiet
    timeout /t 2 /nobreak >nul
  )
)

rem ---- sozlamalarni o'qish
if not exist "deploy\production.env" (echo  deploy\production.env topilmadi. & pause & exit /b 1)
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("deploy\production.env") do if not "%%A"=="" set "%%A=%%B"
if "%SSB_PORT%"=="" set SSB_PORT=8080
if "%CLOUDFLARE_TUNNEL_TOKEN%"=="" set CLOUDFLARE_TUNNEL_TOKEN=BU_YERGA_TOKENNI_QOYING
set "TUNNEL_MODE=token"
if exist "deploy\cloudflared.yml" set "TUNNEL_MODE=config"
if "%TUNNEL_MODE%"=="token" if "%CLOUDFLARE_TUNNEL_TOKEN%"=="BU_YERGA_TOKENNI_QOYING" (
  echo  [!] Domen hali ulanmagan.
  echo      Avval deploy\ULASH.bat ni bosing - u ssbgroup.uz ni bir marta ulab beradi.
  echo.
  pause
  exit /b 1
)

rem ---- port bandmi? (oddiy start.bat ham 8000-portda ishlaydi, u bilan to'qnashmaydi)
netstat -ano | findstr /R /C:":%SSB_PORT% .*LISTENING" >nul && (
  echo  [!] %SSB_PORT%-port band. Boshqa dastur shu portni ishlatyapti.
  pause
  exit /b 1
)

where python >nul 2>nul || (echo  Python topilmadi. https://www.python.org/downloads/ & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (
  echo  [1/6] Virtual muhit yaratilmoqda...
  python -m venv .venv || (pause & exit /b 1)
)
set "PY=%ROOT%\.venv\Scripts\python.exe"

echo  [1/6] Kutubxonalar tekshirilmoqda...
"%PY%" -m pip install -q -r requirements.txt || (echo  Kutubxonalarni o'rnatib bo'lmadi. Internetni tekshiring. & pause & exit /b 1)

echo  [2/6] Ma'lumotlar bazasi...
if exist ".pg\bin\pg_ctl.exe" (
  if not exist ".setup" mkdir ".setup"
  ".pg\bin\pg_ctl.exe" -D .pgdata status >nul 2>nul
  if errorlevel 1 (
    if exist ".pgdata\postmaster.pid" del /f /q ".pgdata\postmaster.pid" 2>nul
    ".pg\bin\pg_ctl.exe" -D .pgdata -l .setup\postgresql.log -w start >nul
  )
)
"%PY%" manage.py migrate --noinput >deploy\logs\migrate.log 2>&1 || (echo  Bazani yangilashda xato. deploy\logs\migrate.log ni oching. & pause & exit /b 1)

echo  [3/6] Sayt fayllari yig'ilmoqda...
"%PY%" manage.py collectstatic --noinput >deploy\logs\collectstatic.log 2>&1 || (echo  Statik fayllarda xato. deploy\logs\collectstatic.log ni oching. & pause & exit /b 1)

echo  [4/6] Cloudflare Tunnel dasturi...
if not exist "deploy\bin\cloudflared.exe" (
  echo        cloudflared.exe yuklab olinmoqda - rasmiy Cloudflare GitHub sahifasidan
  curl -L -s -o "deploy\bin\cloudflared.exe" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
  if not exist "deploy\bin\cloudflared.exe" (echo  cloudflared.exe yuklanmadi. Internetni tekshiring. & pause & exit /b 1)
)

echo  [5/6] Server ishga tushmoqda (127.0.0.1:%SSB_PORT%)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%PY%' -ArgumentList 'deploy\serve.py' -WorkingDirectory '%ROOT%' -WindowStyle Hidden -RedirectStandardOutput '%ROOT%\deploy\logs\server.log' -RedirectStandardError '%ROOT%\deploy\logs\server-error.log' -PassThru; Set-Content -Path '%ROOT%\deploy\run\server.pid' -Value $p.Id"

set /a TRIES=0
:waitserver
set /a TRIES+=1
timeout /t 1 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:%SSB_PORT%/ > deploy\run\check.txt 2>nul
set /p CODE=<deploy\run\check.txt
if "%CODE%"=="200" goto serverok
if %TRIES% LSS 20 goto waitserver
echo  [!] Server javob bermadi. deploy\logs\server-error.log ni oching.
call "%~dp0stop.bat" quiet
pause
exit /b 1
:serverok

echo  [6/6] ssbgroup.uz ga ulanmoqda (Cloudflare Tunnel)...
if "%TUNNEL_MODE%"=="config" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%ROOT%\deploy\bin\cloudflared.exe' -ArgumentList 'tunnel','--no-autoupdate','--logfile','deploy\logs\tunnel.log','--config','deploy\cloudflared.yml','run' -WorkingDirectory '%ROOT%' -WindowStyle Hidden -PassThru; Set-Content -Path '%ROOT%\deploy\run\tunnel.pid' -Value $p.Id"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%ROOT%\deploy\bin\cloudflared.exe' -ArgumentList 'tunnel','--no-autoupdate','--logfile','deploy\logs\tunnel.log','run','--token','%CLOUDFLARE_TUNNEL_TOKEN%' -WorkingDirectory '%ROOT%' -WindowStyle Hidden -PassThru; Set-Content -Path '%ROOT%\deploy\run\tunnel.pid' -Value $p.Id"
)
timeout /t 4 /nobreak >nul
set /p TPID=<"deploy\run\tunnel.pid"
tasklist /FI "PID eq %TPID%" 2>nul | find "%TPID%" >nul || (
  echo  [!] Tunnel ishga tushmadi. deploy\logs\tunnel.log ni oching yoki ULASH.bat ni qayta bosing.
  call "%~dp0stop.bat" quiet
  pause
  exit /b 1
)

echo.
echo  ----------------------------------------------
echo   TAYYOR!  Sayt:        https://ssbgroup.uz
echo            Boshqaruv:   https://ssbgroup.uz/management/
echo   To'xtatish uchun:    deploy\stop.bat
echo   Bu oynani yopsangiz ham sayt ishlashda davom etadi.
echo  ----------------------------------------------
echo.
start "" https://ssbgroup.uz
timeout /t 8 >nul
exit /b 0
