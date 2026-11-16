@echo off
rem SSB Group — domendagi saytni to'xtatish (server + Cloudflare Tunnel).
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."
set STOPPED=0
for %%N in (tunnel server) do (
  if exist "deploy\run\%%N.pid" (
    set /p PID=<"deploy\run\%%N.pid"
    if not "!PID!"=="" (
      taskkill /PID !PID! /T /F >nul 2>nul && set STOPPED=1
    )
    del /f /q "deploy\run\%%N.pid" >nul 2>nul
  )
)
if "%~1"=="quiet" exit /b 0
echo.
if "%STOPPED%"=="1" (
  echo  Sayt to'xtatildi. ssbgroup.uz endi ochilmaydi.
) else (
  echo  Ishlayotgan server topilmadi.
)
echo  Qayta yoqish uchun: deploy\start.bat
echo.
timeout /t 5 >nul
