@echo off

REM NoteAI 启动脚本
REM 支持开发模式和构建模式

echo ==============================
echo NoteAI 启动脚本
echo ==============================

echo 1. 开发模式 (cargo tauri dev)
echo 2. 构建应用 (cargo tauri build)
echo 3. 退出

echo ==============================
set /p choice=请选择操作: 

if "%choice%"=="1" goto dev
if "%choice%"=="2" goto build
if "%choice%"=="3" goto exit

echo 无效选择，请重新运行脚本
goto exit

:dev
echo 检查 Rust 是否安装...
cargo --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: Rust 未安装，请先安装 Rust
    echo 下载地址: https://www.rust-lang.org/tools/install
    pause
    goto exit
)

echo 检查 Python 依赖...
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: Python 未安装，请先安装 Python
    echo 下载地址: https://www.python.org/downloads/
    pause
    goto exit
)

echo 安装 Python 依赖...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo 错误: 安装依赖失败
    pause
    goto exit
)

echo 启动开发模式...
cargo tauri dev

if %errorlevel% neq 0 (
    echo 错误: 启动失败
    pause
    goto exit
)

goto exit

:build
echo 检查 Rust 是否安装...
cargo --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: Rust 未安装，请先安装 Rust
    echo 下载地址: https://www.rust-lang.org/tools/install
    pause
    goto exit
)

echo 检查 Python 依赖...
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: Python 未安装，请先安装 Python
    echo 下载地址: https://www.python.org/downloads/
    pause
    goto exit
)

echo 安装 Python 依赖...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo 错误: 安装依赖失败
    pause
    goto exit
)

echo 构建应用...
cargo tauri build

if %errorlevel% neq 0 (
    echo 错误: 构建失败
    pause
    goto exit
)

echo 构建完成！
echo 可执行文件位置: src-tauri\target\release\bundle
pause
goto exit

:exit
echo 退出脚本...
pause
