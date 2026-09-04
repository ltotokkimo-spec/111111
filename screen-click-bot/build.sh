#!/usr/bin/env bash
# 打包成單一執行檔 (macOS / Linux)
set -e

cd "$(dirname "$0")"

if ! command -v pyinstaller &> /dev/null; then
    echo "找不到 pyinstaller，正在安裝..."
    pip install pyinstaller
fi

pyinstaller --noconfirm --onefile --windowed \
    --name ScreenClickBot \
    screen_watcher.py

echo ""
echo "打包完成！執行檔位於 dist/ScreenClickBot"
