# MaterialMind V2 — Windows Folder Auto-Sync Agent

## 目的

這個 Agent 在 Windows 背景執行，定期掃描指定資料夾（預設 `D:\excel庫存`），找到**檔名含日期的最新 SAP Excel**，確認它尚未同步後，自動解析並送到 Supabase 的 `import_inventory_snapshot` RPC。

它不需要 pandas、openpyxl、watchdog 或其他第三方 Python 套件；Excel `.xlsx/.xlsm` 由 Python 標準函式庫直接解析。

## 安全設計

- 不把 SAP 原始 Excel 上傳 GitHub。
- 不使用 Supabase `service_role` key。
- 第一次登入使用 Supabase Email/Password。
- refresh token 使用 Windows DPAPI 加密保存。
- Agent 只自動匯入**比資料庫最後同步日期更新**的檔案。
- 同一日期如果出現不同 SHA-256 的檔案，V2 預設停止自動匯入並標記 WARNING，避免覆蓋已確認的日快照。
- 解析後若資料筆數低於安全門檻，停止匯入。
- 檔名必須能解析 `YYYYMMDD`、`YYYY-MM-DD`、`YYYY_MM_DD` 等日期格式。

## 首次安裝

1. 安裝 Python 3.11+，安裝時勾選 `Add Python to PATH`。
2. 將整個 `agent` 資料夾放在固定位置，例如 `C:\MaterialMind\agent`。
3. 用 PowerShell 執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_agent.ps1
```

4. 安裝腳本會先以互動模式設定 Supabase URL、Publishable Key、登入 Email/Password，再建立 Windows 工作排程。
5. 之後 Windows 登入會自動啟動 Agent；排程本身不需要再輸入密碼。

## 測試而不連線

```powershell
python .\materialmind_agent.py --dry-run "D:\excel庫存\20260921全.xlsx"
```

它只解析檔案，不會上傳資料庫。

## 建議資料夾命名

```text
D:\excel庫存\
  20260919全.xlsx
  20260920全.xlsx
  20260921全.xlsx
```

Agent 會選擇日期最新者。沒有日期的檔案不會被自動匯入，以避免把其他 Excel 誤判為每日庫存快照。
