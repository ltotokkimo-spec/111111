@echo off
REM 打包成單一執行檔 (Windows)
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo 找不到 pyinstaller，正在安裝...
    pip install pyinstaller
)

pyinstaller --noconfirm --onefile --windowed --name ScreenClickBot screen_watcher.py

echo.
echo 打包完成！執行檔位於 dist\ScreenClickBot.exe
pause
