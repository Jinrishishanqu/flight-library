@echo off
chcp 65001 >nul
title 飞行图书馆 · 本地阅读站
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 找不到 Python 运行环境：.venv\Scripts\python.exe
  pause
  exit /b 1
)
if not exist "采集工具\书库\data\library.db" (
  echo [提示] 数据库不存在，先重建：
  echo        .venv\Scripts\python.exe 采集工具\书库\build_db.py --rebuild
  pause
  exit /b 1
)

echo 飞行图书馆 · 正在启动本地服务 http://127.0.0.1:8770/
start "" http://127.0.0.1:8770/
pushd "采集工具\书库"
"..\..\.venv\Scripts\python.exe" server.py 127.0.0.1 8770
popd
pause