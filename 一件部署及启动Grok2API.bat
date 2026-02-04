@echo off
chcp 65001 >nul
title Grok2API 服务管理
color 0A

REM === 配置区域 ===
set "PROJ_DIR=grok2api"
set "PORT=8000"

echo ================================================
echo         Grok2API 自动化部署工具
echo ================================================

REM 1. 检查是否已经拉取过仓库
if exist "%PROJ_DIR%\main.py" (
    echo [信息] 项目已存在，准备启动...
    goto :START_FLOW
) else (
    echo [信息] 项目不存在，正在拉取...
    git clone https://github.com/chenyme/grok2api
    if %errorlevel% neq 0 (
        echo [错误] 克隆失败，请检查网络！
        pause & exit /b 1
    )
)

:START_FLOW
cd /d "%~dp0%PROJ_DIR%"

REM 2. 清理可能残留的后台进程
echo [信息] 正在检查端口 %PORT% 占用...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%"') do (
    taskkill /f /pid %%a >nul 2>nul
)

REM 3. 环境同步
echo [信息] 正在同步环境...
call uv sync

REM 4. 展示登录信息并运行
cls
echo ================================================
echo         Grok2API 服务已启动
echo ================================================
echo.
echo    管理界面: http://127.0.0.1:%PORT%/admin
echo    默认密码: grok2api
echo.
echo    提示: 请保持此窗口开启，关闭即停止服务。
echo ================================================
echo.

REM 5. 执行运行指令
call uv run main.py

pause