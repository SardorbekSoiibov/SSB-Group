@echo off
chcp 65001 >nul
title SSB Group — ssbgroup.uz ulash
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ulash.ps1"
