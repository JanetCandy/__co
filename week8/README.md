IC EDA Python 專案 (Visual Studio Code 開發環境)

本專案是一個輕量級的 EDA (電子設計自動化) 模擬與 Verilog 解析工具範例，專門為 Visual Studio Code (VS Code) 開發環境設計。

📁 專案結構

.
├── .vscode/
│   ├── settings.json   # VS Code 工作區設定 (Python 與 Formatting)
│   └── launch.json     # VS Code 偵錯 (Debug) 設定
├── eda_tool.py         # 主要 Python 腳本 (包含 Verilog 解析與邏輯模擬)
├── requirements.txt    # 專案套件依賴清單
└── README.md           # 專案說明文件


🛠️ 前置需求與環境建置

1. 軟體需求

Python: 建議安裝 3.8 以上版本。

Visual Studio Code: 請至 VS Code 官網 下載安裝。

2. 推薦 VS Code 擴充套件 (Extensions)

在 VS Code 中按下 Ctrl + Shift + X (Mac: Cmd + Shift + X) 搜尋並安裝以下套件：

Python：提供 Python 語法高亮、IntelliSense 自動補全及 Debug 功能。

Pylance：提供高效能的 Python 靜態型態檢查。

Verilog-HDL/SystemVerilog/Bluespec：若需在專案中開啟 .v 或 .sv 的 RTL 檔，提供 Verilog 語法高亮。

Markdown Preview Enhanced：實時預覽本 README.md 文件。

🚀 在 VS Code 中快速上手

步驟 1：開啟專案資料夾

開啟 VS Code，選單點選 檔案 (File) -> 開啟資料夾 (Open Folder...)，選擇本專案根目錄。

步驟 2：建立並啟用 Python 虛擬環境

開啟 VS Code 整合終端機（快速鍵：Ctrl + `  或 Cmd + ` ）：

Windows (PowerShell):

python -m venv venv
.\venv\Scripts\Activate.ps1


macOS / Linux:

python3 -m venv venv
source venv/bin/activate


步驟 3：選擇 Python 解譯器 (Interpreter)

按下 Ctrl + Shift + P (Mac: Cmd + Shift + P) 開啟指令面板。

輸入並選擇 Python: Select Interpreter。

選擇虛擬環境 ./venv/bin/python (或 .\venv\Scripts\python.exe)。

⚙️ VS Code 推薦設定檔

可於專案根目錄建立 .vscode 資料夾，並加入以下設定檔：

.vscode/settings.json

{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.analysis.typeCheckingMode": "basic",
  "editor.formatOnSave": true,
  "files.trimTrailingWhitespace": true
}


.vscode/launch.json (偵錯設定)

{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: 執行當前 EDA 腳本",
      "type": "debugpy",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "justMyCode": true
    }
  ]
}


🏃 執行與除錯 (Debug)

執行方式

圖形介面：開啟 eda_tool.py，點擊編輯器右上角的 播放按鈕 (▷)。

終端機指令：

python eda_tool.py


除錯 (Debug) 方式

在 eda_tool.py 中，於要檢查的行號左側點擊滑鼠左鍵設定 中斷點 (Breakpoint)。

按下 F5 啟動偵錯模式，即可步進（Step Over / Step Into）觀察變數數值。

💡 常用 VS Code 快速鍵整理

功能

Windows / Linux

macOS

開啟指令面板

Ctrl + Shift + P

Cmd + Shift + P

開啟/關閉終端機

Ctrl + ~

Cmd + ~

執行並除錯

F5

F5

格式化程式碼

Shift + Alt + F

Shift + Option + F

快速搜尋檔案

Ctrl + P

Cmd + P

📖 核心功能展示

本專案 eda_tool.py 包含以下邏輯：

Verilog RTL 抽象解析：利用正則表達式快速提取 Module 名稱與 Pin 腳位狀態。

邏輯閘行為模擬：建立 2-Input AND/OR 邏輯閘函數，並自動印出真值表 (Truth Table)。