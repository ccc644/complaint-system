@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo =============================================
echo  Complaint System v3.5.0 启动脚本
echo =============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请确保已安装并添加到 PATH。
    pause
    exit /b 1
)

:: 检查 Node.js
set SKIP_BUILD=0
node --version >nul 2>&1
if errorlevel 1 (
    echo [提醒] 未找到 Node.js，跳过前端构建（使用已有静态文件）。
    set SKIP_BUILD=1
)

:: ============ 后端 ============
echo [1/2] 准备后端...
cd /d "%~dp0backend"

:: 0804 便携部署：环境持久化到本机固定路径，项目替换不受影响
:: 首次需等待 pip install，之后秒级启动
set "SYS_VENV=%USERPROFILE%\.complaint-system\venv"
set "SYS_PYTHON=%SYS_VENV%\Scripts\python.exe"

if exist "%SYS_PYTHON%" (
    "%SYS_PYTHON%" --version >nul 2>&1
    if errorlevel 1 (
        echo [提醒] 固定环境失效，重建中...
        rmdir /s /q "%SYS_VENV%"
    )
)

if not exist "%SYS_PYTHON%" (
    echo 首次运行 — 创建持久化 Python 环境（仅此一次，请稍候）...
    python -m venv "%SYS_VENV%"
    if errorlevel 1 (
        echo [错误] 环境创建失败，请检查 Python 安装。
        pause
        exit /b 1
    )
    echo 安装后端依赖（首次稍慢，后续秒启）...
    echo 不行就使用清华源 pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    "%SYS_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
    echo ✅ 环境就绪，下次启动无需等待。
) else (
    echo 检测到已有运行环境，跳过安装
    echo 快速检查新依赖，已安装时秒级完成
    "%SYS_PYTHON%" -m pip install -r requirements.txt
)

:: 检查 .env
if not exist .env (
    echo.
    echo ╔════════════════════════════════════════════╗
    echo ║  [警告] 未找到 backend\.env 配置文件     ║
    echo ║  请创建 .env 并填入 DEEPSEEK_API_KEY      ║
    echo ║  可参考 .env.example 模板                 ║
    echo ╚════════════════════════════════════════════╝
    echo.
)

cd /d "%~dp0"

:: ============ 前端构建 ============
echo [2/2] 准备前端...
cd /d "%~dp0frontend"

if "%SKIP_BUILD%"=="1" goto skip_build

echo 安装/更新前端依赖...
call npm install --no-audit --no-fund
if errorlevel 1 (
    echo [错误] npm install 失败，请检查 Node.js 和网络连接。
    pause
    exit /b 1
)

echo 构建前端...
call npm run build
if errorlevel 1 (
    echo [错误] 前端构建失败。
    pause
    exit /b 1
)

:skip_build

cd /d "%~dp0"

echo =============================================
echo 启动后端服务 (端口 8506)...
echo.
echo   系统访问: http://localhost:8506
echo   API 文档: http://localhost:8506/docs
echo.
echo +====================================================+
echo ^|                                                    ^|
echo ^|   *** 后端正在另一个终端窗口中运行 ***              ^|
echo ^|   *** 后端正在另一个终端窗口中运行 ***              ^|
echo ^|                                                    ^|
powershell -Command "Write-Host '|   *** 此窗口用不到 -- 按任意键关闭此窗口即可 ***    |' -ForegroundColor Red"
powershell -Command "Write-Host '|   *** 此窗口用不到 -- 按任意键关闭此窗口即可 ***    |' -ForegroundColor Red"
powershell -Command "Write-Host '|   *** 不要关闭另一个窗口 ***    |' -ForegroundColor Red"
powershell -Command "Write-Host '|   *** 不要关闭另一个窗口 ***    |' -ForegroundColor Red"
echo ^|   *** 浏览器输入 http://localhost:8506 访问  ***    ^|
echo ^|                                                    ^|
echo +====================================================+
echo.
echo =============================================

:: 杀掉旧的后端进程（占用 8506 端口），确保新代码生效
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8506.*LISTENING"') do (
    echo 关闭旧后端进程 PID=%%a...
    taskkill /F /PID %%a >nul 2>&1
)

:: 0804 使用固定路径环境启动后端
cd /d "%~dp0backend"
start "Complaint System v3.5.0" cmd /k "cd /d ""%~dp0backend"" && ""%SYS_PYTHON%"" -m uvicorn main:app --host 0.0.0.0 --port 8506"

cd /d "%~dp0"
pause
