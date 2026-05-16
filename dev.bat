@echo off
chcp 65001 >nul
title 麦威 Dev Server

cd /d "%~dp0"

:: 检查虚拟环境是否存在，不存在则创建
if not exist "venv\Scripts\activate.bat" (
    echo [1/3] 正在创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo 错误: 创建虚拟环境失败，请确保已安装 Python 3
        pause
        exit /b 1
    )
) else (
    echo [1/3] 虚拟环境已存在，跳过创建
)

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: 安装依赖
echo [2/3] 正在安装依赖...
pip install -r requirements.txt -q

:: 启动开发服务器
echo [3/3] 正在启动开发服务器...
echo.
echo ========================================
echo   探活动 开发服务器
echo   地址: http://127.0.0.1:5000
echo   按 Ctrl+C 停止服务器
echo ========================================
echo.

set FLASK_DEBUG=1
set PYTHONUNBUFFERED=1
set PYTHONTRACEBACK=1
python -u run.py 2>&1
if errorlevel 1 (
    echo.
    echo ========================================
    echo   服务器异常退出，请检查上方错误信息
    echo ========================================
    pause
)
