@echo off
chcp 65001 >nul
setlocal
title 吃什么？ - 启动
cd /d "%~dp0"

rem ============================================================
rem  吃什么？—— 家庭中晚餐菜单机器人  一键启动
rem  双击本文件即可：自动准备环境 → 启动服务 → 打开浏览器
rem  可选环境变量：
rem    CSM_PORT=8080        服务端口
rem    CSM_PYTHON=路径      直接指定 python.exe（跳过环境准备）
rem    CSM_FORCE_DOCKER=1   强制用 Docker 启动
rem    CSM_NO_BROWSER=1     不自动打开浏览器
rem ============================================================

set "PORT=8080"
if not "%CSM_PORT%"=="" set "PORT=%CSM_PORT%"
set "CSM_DATA_DIR=%CD%\data"
set "CSM_APP_URL=http://127.0.0.1:%PORT%/"

echo.
echo   ==============================================
echo      吃什么？ 家庭中晚餐菜单机器人
echo   ==============================================
echo.

rem ---------- 1. 决定启动方式：Docker 还是本机 Python ----------
if "%CSM_FORCE_DOCKER%"=="1" goto :use_docker
if not "%CSM_PYTHON%"=="" goto :use_python

where docker >nul 2>nul
if errorlevel 1 goto :use_python
docker info >nul 2>nul
if errorlevel 1 goto :use_python

echo   [1/3] 检测到 Docker，拉取现成镜像启动（NAS 上也是这个方式）
docker compose up -d
if errorlevel 1 (
  echo   [警告] Docker 启动失败，改用本机 Python 方式。
  goto :use_python
)
goto :wait_ready

:use_docker
echo   [1/3] 用 Docker 启动...
docker compose up -d
if errorlevel 1 (
  echo   [错误] docker compose 启动失败，请检查 Docker Desktop 是否已运行。
  pause
  exit /b 1
)
goto :wait_ready

rem ---------- 2. 本机 Python 方式 ----------
:use_python
set "PY=%CSM_PYTHON%"

if not "%PY%"=="" goto :launch
if exist ".venv\Scripts\python.exe" (
  set "PY=%CD%\.venv\Scripts\python.exe"
  goto :launch
)

echo   [1/3] 首次运行：准备 Python 环境（只需一次，约 1 分钟）
where uv >nul 2>nul
if not errorlevel 1 (
  call :setup_uv
) else (
  call :setup_venv
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   [错误] Python 环境准备失败。
  echo   请手动执行一次：
  echo       python -m venv .venv
  echo       .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo   或者安装 Docker Desktop 后重新双击本文件。
  echo.
  pause
  exit /b 1
)
set "PY=%CD%\.venv\Scripts\python.exe"

:launch
echo   [2/3] 启动服务（端口 %PORT%）...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start_server.ps1" -Python "%PY%" -Port %PORT%

:wait_ready
echo   [3/3] 等待服务就绪...
set /a TRIES=0

:wait_loop
set /a TRIES+=1
where curl >nul 2>nul
if errorlevel 1 goto :wait_sleep
curl -s -o nul --max-time 2 "http://127.0.0.1:%PORT%/healthz"
if not errorlevel 1 goto :ready

:wait_sleep
if %TRIES% geq 40 goto :timeout
ping -n 2 127.0.0.1 >nul
goto :wait_loop

:timeout
echo.
echo   [警告] 60 秒内没等到服务响应，可能还在首次安装依赖或端口被占用。
echo   请查看标题为「吃什么？服务」的窗口里的报错信息。
echo.
pause
exit /b 1

:ready
if "%CSM_NO_BROWSER%"=="1" goto :done
start "" "%CSM_APP_URL%"

:done
echo.
echo   ==============================================
echo      启动成功！
echo.
echo      打开地址：%CSM_APP_URL%
echo      默认账号：admin / admin123
echo      （登录后请在「设置」里立刻改密码）
echo.
echo      停止服务：双击 停止.bat，或关闭标题为
echo                「吃什么？服务」的那个黑色窗口
echo   ==============================================
echo.
ping -n 21 127.0.0.1 >nul
exit /b 0

rem ---------- 子过程：环境准备 ----------
:setup_uv
echo        使用 uv 创建虚拟环境...
uv venv .venv
if exist ".venv\Scripts\python.exe" (
  uv pip install --python "%CD%\.venv\Scripts\python.exe" -r requirements.txt
)
exit /b

:setup_venv
set "SYS_PY=python"
where py >nul 2>nul
if not errorlevel 1 set "SYS_PY=py -3"
echo        使用 %SYS_PY% 创建虚拟环境...
%SYS_PY% -m venv .venv
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
exit /b
