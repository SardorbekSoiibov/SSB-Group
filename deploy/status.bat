@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."
echo.
for %%N in (server tunnel) do (
  set STATE=to'xtagan
  if exist "deploy\run\%%N.pid" (
    set /p PID=<"deploy\run\%%N.pid"
    tasklist /FI "PID eq !PID!" 2>nul | find "!PID!" >nul && set STATE=ishlayapti
  )
  echo  %%N: !STATE!
)
echo.
pause
