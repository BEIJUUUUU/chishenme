@echo off
chcp 65001 >nul
setlocal
title 吃什么？ - 停止
cd /d "%~dp0"

set "PORT=8080"
if not "%CSM_PORT%"=="" set "PORT=%CSM_PORT%"

echo.
echo   正在停止「吃什么？」服务...
echo.

rem ---------- 1. 停止 Docker 容器（如果存在） ----------
where docker >nul 2>nul
if errorlevel 1 goto :kill_python
docker info >nul 2>nul
if errorlevel 1 goto :kill_python
docker compose down >nul 2>nul
if not errorlevel 1 echo   [完成] Docker 容器已停止。

rem ---------- 2. 停止本机 Python 服务 ----------
:kill_python
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\stop_server.ps1" -Port %PORT%

echo.
echo   数据保存在 data 目录里，不会丢失。
echo.
ping -n 9 127.0.0.1 >nul
exit /b 0
