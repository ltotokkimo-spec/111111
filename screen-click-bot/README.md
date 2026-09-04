# Screen Click Bot 桌面 OCR / 圖像自動點擊工具

一個簡單的桌面小工具：框選螢幕上的某個區域，持續監控該區域，
一旦偵測到你指定的**文字**（OCR）或**圖片**（模板比對），就自動幫你點擊該位置。

適合用來做：等待某個按鈕出現就自動點、遊戲/表單的重複性小動作、
監控某段文字出現就觸發點擊等場景。

> ⚠️ 這是自動化滑鼠操作工具，請只用在你自己有權限操作的畫面上，
> 並遵守目標軟體/網站/遊戲的使用條款。作者不對誤用或違規使用負責。

## 功能特色

- 🖱️ **拖曳選取監控區域**：不用手動輸入座標，用滑鼠框選就好
- 🔤 **文字模式**：用 Tesseract OCR 辨識畫面文字，支援中英文（含繁體中文）
- 🖼️ **圖像模式**：用 OpenCV 模板匹配，找到指定小圖就點擊，可調相似度門檻
- ⏱️ **可調掃描頻率、點擊後冷卻時間**，避免重複誤觸
- 🛑 **一次性點擊模式**：找到目標點一次就自動停止
- 💾 **自動記住設定**：下次開啟不用重新設定（存在 `config.json`）
- 🚨 **安全機制**：滑鼠移到螢幕左上角可立即中止自動點擊（pyautogui 內建 failsafe）

## 螢幕截圖

```
┌─────────────────────────────┐
│ 1. 監控區域   [選取螢幕區域]  │
│ 2. 偵測模式   ◉文字 ○圖像    │
│ 3. 執行參數   間隔/冷卻時間   │
│    [開始監控]  [停止監控]     │
│ ── 狀態記錄 ──────────────── │
│  [12:30:01] 開始監控...       │
│  [12:30:03] 命中！點擊 (500,300)│
└─────────────────────────────┘
```

## 安裝

### 1. 取得原始碼

```bash
git clone https://github.com/<你的帳號>/screen-click-bot.git
cd screen-click-bot
```

### 2. 安裝 Python 套件

建議使用虛擬環境：

```bash
python3 -m venv venv
source venv/bin/activate      # Windows 用: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 安裝 Tesseract OCR（文字模式必需）

若只使用圖像比對模式，可跳過這一步。

| 系統 | 安裝方式 |
|------|----------|
| Windows | 到 [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) 下載安裝，安裝時記得勾選「Additional language data」加入中文 |
| macOS | `brew install tesseract tesseract-lang` |
| Linux (Debian/Ubuntu) | `sudo apt install tesseract-ocr tesseract-ocr-chi-tra tesseract-ocr-chi-sim` |

安裝好後，程式會自動嘗試從系統 PATH 找到 `tesseract`。
如果 Windows 沒有把它加進 PATH，可以在程式介面的「Tesseract 執行檔路徑」欄位手動指定，例如：

```
C:\Program Files\Tesseract-OCR\tesseract.exe
```

（也可以設定環境變數 `TESSERACT_CMD` 指到這個路徑）

## 使用方式

```bash
python3 screen_watcher.py
```

1. 點「選取螢幕區域」，拖曳框選你要監控的畫面範圍（按 Esc 可取消）
2. 選擇「文字」或「圖像比對」模式
   - **文字模式**：輸入要偵測的文字、OCR 語言（如 `chi_tra+eng`），
     可選是否「完全符合」整個字串
   - **圖像模式**：選取一張範本圖片（建議用小工具/系統內建截圖工具，
     截取你要辨識的按鈕/圖示，存成 png），並設定相似度門檻（0.5~1.0，預設 0.85）
3. 設定掃描間隔、點擊後冷卻時間，需要的話勾選「只點擊一次」
4. 按「開始監控」，程式會在背景持續掃描；找到符合條件的內容時自動點擊該座標
5. 按「停止監控」或關閉視窗即可停止

所有設定會自動存到執行目錄下的 `config.json`，下次開啟會自動帶入。

## 打包成執行檔（給不想裝 Python 環境的使用者）

使用 [PyInstaller](https://pyinstaller.org/) 打包成單一執行檔：

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name ScreenClickBot screen_watcher.py
```

打包完成後執行檔會在 `dist/` 資料夾裡：
- Windows: `dist/ScreenClickBot.exe`
- macOS: `dist/ScreenClickBot`（或用 `--windowed` 產生 `.app`）
- Linux: `dist/ScreenClickBot`

也可以直接執行專案內附的打包腳本：

```bash
# macOS / Linux
bash build.sh

# Windows
build.bat
```

> 注意：PyInstaller 只會打包 Python 程式本身，**不會**內建 Tesseract OCR，
> 使用者的電腦仍需要另外安裝 Tesseract（見上方安裝章節）。

## 專案結構

```
screen-click-bot/
├── screen_watcher.py     # 主程式（GUI + 監控邏輯）
├── requirements.txt      # Python 依賴套件
├── build.sh              # macOS/Linux 打包腳本
├── build.bat             # Windows 打包腳本
├── templates/            # 存放圖像比對用的範本截圖（自行放入）
├── config.json            # 執行後自動產生的個人化設定（已加入 .gitignore）
├── .gitignore
├── LICENSE
└── README.md
```

## 常見問題

**Q: OCR 辨識不到我要的文字？**
A: 嘗試：(1) 縮小監控範圍讓文字佔比更大 (2) 確認 `ocr_lang` 語言包有安裝
(如中文要裝 `chi_tra` 或 `chi_sim`) (3) 目標文字所在的背景/前景對比度太低時，OCR 準確率會下降。

**Q: 圖像比對抓不到？**
A: 模板比對對縮放/旋轉敏感，範本圖片建議直接從同一台螢幕、同樣解析度下截取，
並適度調低相似度門檻（如 0.75）。

**Q: 找到文字/圖片了，但點擊位置不準？**
A: 文字模式點擊的是 OCR 偵測框的中心；圖像模式點擊的是範本比對區塊的中心。
若畫面有縮放（如 Retina/HiDPI），可能需要調整系統顯示縮放設定為 100% 再測試。

**Q: 可以同時監控多組「文字/圖片 → 點擊」規則嗎？**
A: 目前版本一次只支援一組規則。如需多規則，歡迎開 issue 或 PR。

## 授權

MIT License，詳見 [LICENSE](LICENSE)。
