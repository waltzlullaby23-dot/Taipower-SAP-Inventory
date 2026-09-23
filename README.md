# MaterialMind V2 — SAP 庫存自動差異分析系統

## V2 的核心改變

V1 是「網頁手動匯入 Excel」。V2 改成真正的自動化資料管線：

```text
SAP 匯出 Excel
      ↓
D:\excel庫存
      ↓
Windows Auto-Sync Agent（背景監控）
      ↓
檢查最新日期 / SHA-256 / 資料筆數 / 欄位
      ↓
Supabase PostgreSQL
      ↓
與前一份完整快照自動比較
      ↓
MaterialMind GitHub Pages 儀表板
```

使用者日常不需要再按「匯入」。只要新的 SAP Excel 放進監控資料夾即可。

## 安全與可靠性設計

1. **GitHub Pages 不直接讀本機資料夾**：由 Windows Agent 負責本機檔案存取。
2. **中央資料庫**：庫存快照、異動、稽核、Agent 狀態存於 Supabase PostgreSQL。
3. **交易式匯入**：資料庫 RPC 一次完成快照、明細、材料主檔與差異；失敗會回滾。
4. **SHA-256 防重複**：同一檔案不會重複匯入。
5. **日期防誤判**：Agent 只處理檔名含可辨識日期的檔案，例如 `20260921全.xlsx`；沒有日期的 Excel 不會自動匯入。
6. **最新日期優先**：只自動處理比資料庫最後同步日期更新的檔案。
7. **同日不同檔保護**：同一日期出現不同內容的 Excel 時，V2 預設停止自動匯入並標記 WARNING，不覆蓋已確認的日快照。
8. **資料筆數安全門檻**：有效資料低於門檻時停止匯入，避免空檔、半份檔案或錯誤匯出污染資料庫。
9. **Windows DPAPI**：Agent 第一次登入取得的 Supabase refresh token 會以 Windows 使用者範圍加密保存，不把密碼寫入設定檔。
10. **檔案完整性保護**：Agent 會確認檔案大小/修改時間已穩定，並執行 XLSX ZIP 完整性檢查後才解析。
11. **日期合理性保護**：不接受未來日期，也不自動匯入超過設定天數的舊檔。
12. **Supabase 角色權限**：`admin`、`operator` 可以匯入；`viewer` 只能查詢。
13. **不使用 service_role key**：瀏覽器與 Agent 都使用 Publishable/anon key + 使用者登入權限。

## SAP Excel 解析

目前已針對常見 SAP 中文欄位建立別名辨識，包括：

- 物料編號 / 料號
- 名稱規範 / 材料名稱
- 評價
- 儲存地點 / 倉庫
- 儲格
- 庫存量
- 安全庫存
- 最後收料日期
- 最後使用日期

支援 `.xlsx` / `.xlsm`。舊式二進位 `.xls` 不在無第三方套件版本的自動解析範圍內。

## 你的資料格式測試

本版本已針對本次提供的 `20260921全.xlsx` 結構設計解析器：

```text
物料編號 | 名稱規範 | 評價 | 單位 | 儲存地點 | 儲格 | 庫存量 | 最後收料日期 | 最後使用日期
```

並保留「料號 + 評價 + 倉庫 + 儲格」的明細；真正比較時則依「料號 + 評價 + 倉庫」彙總，避免材料只是換儲格就被誤判為總庫存異動。

## 安裝順序

### 1. 建立 Supabase Project

建立專案後，在 SQL Editor 執行：

```text
supabase/schema.sql
```

再建立 Auth 使用者，最後執行：

```text
supabase/admin_setup.sql
```

把你的 Email 改成實際帳號。第一次建議給自己的帳號 `admin`。

### 2. 設定 GitHub Pages

複製：

```text
config.example.js → config.js
```

填入 Supabase Project URL 與 Publishable Key。

**不要把 service_role key 放進 config.js。**

### 3. Windows Agent

將 `agent` 整個資料夾放到固定位置，例如：

```text
C:\MaterialMind\agent
```

確定 Windows 有 Python 3.11+。

執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_agent.ps1
```

Agent 會建立 Windows 工作排程，在使用者登入時自動啟動。

### 4. 指定 SAP Excel 資料夾

第一次啟動時預設：

```text
D:\excel庫存
```

也可以改成你的實際資料夾。

建議：

```text
D:\excel庫存\
├─ 20260919全.xlsx
├─ 20260920全.xlsx
└─ 20260921全.xlsx
```

### 5. 首次測試

在真正自動上線前，可以只解析、不上傳：

```powershell
python .\materialmind_agent.py --dry-run "D:\excel庫存\20260921全.xlsx"
```

## V2 自動化狀態

網站會顯示：

- Agent 狀態
- 電腦名稱
- 最近檔案
- 最後同步日期
- 最後掃描時間
- 最近錯誤

狀態可能為：

- `等待新檔`
- `解析中`
- `同步完成`
- `已同步`
- `需人工確認`
- `錯誤`

## 重要限制

V2 可以做到「資料夾有新 Excel → 自動抓取 → 自動上傳 → 自動比對」。

但它**不會直接從 SAP 系統自己產生 Excel**。如果未來要做到完全無人化：

```text
SAP → 自動匯出 → D:\excel庫存 → Agent → Supabase → MaterialMind
```

還需要另外建立 SAP 匯出自動化（例如 SAP GUI Scripting、企業內部 RPA 或 SAP API），這一段要依公司資安政策與 SAP 權限決定。
