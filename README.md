# MaterialMind V3｜SAP 庫存差異分析完成版

## 本版修正

1. **儲格正式成為差異比對鍵的一部分**
   - `料號 + 評價 + 倉庫 + 儲格`
   - 同一料號在不同儲格不會再被錯誤合併。
2. **有變動材料表新增「儲格」欄位**
   - 可依儲格篩選。
   - 可依儲格→料號排列。
   - 可匯出儲格。
3. **總異動／增加／減少／新增／消失可直接點擊**
   - 點擊後自動套用狀態篩選並跳到異動表。
4. **消失資料完整保留**
   - 消失時材料名稱、評價、倉庫、儲格、昨日庫存、安全庫存等資訊從「上一份快照」帶入。
5. **重新建立歷史異動**
   - `migration_v3.sql` 會保留所有快照，只重建 `inventory_changes`。
6. **檔名日期更嚴格**
   - 不再把沒有日期的 Excel 自動當成今天。
7. **Excel 多工作表解析更穩定**
   - 每個工作表獨立尋找標題列。
8. **Windows Agent 修正**
   - 修正第一欄索引為 0 時被忽略的 bug。
   - Agent 直接查中央最新快照，不只依賴本機心跳。
   - 同日期不同 SHA-256 會停止自動覆蓋。
9. **安全**
   - GitHub / 前端只使用 Supabase Publishable Key。
   - 不包含 secret/service_role key。
   - Agent refresh token 使用 Windows DPAPI 保存。

## 既有 V2 資料庫升級

你目前已經有 V2 Supabase 資料，所以**不要重新執行 schema.sql**。

請在 Supabase SQL Editor 執行：

`supabase/migration_v3.sql`

執行完成後再更新 GitHub Pages 的 `index.html`。

## 新資料庫

如果是全新專案，執行：

`supabase/schema.sql`

再依需求執行 `supabase/admin_setup.sql`。

## Agent

預設監控：

`D:\excel庫存`

支援：

- `.xlsx`
- `.xlsm`
- 日期：`20260924`、`2026-09-24`、`2026_09_24`
- 每 5 分鐘掃描
- SHA-256
- 檔案寫入穩定性檢查
- 最小有效資料筆數安全門檻
- 同日期不同內容人工確認
- Supabase 中央最新快照比對

## 重要

不要把 Supabase Secret Key / service_role key 放入：

- GitHub
- config.js
- Agent 公開檔案
- 前端 JavaScript

本套件只要求 Publishable Key。
