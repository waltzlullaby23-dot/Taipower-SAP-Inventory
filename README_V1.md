# MaterialMind｜SAP 材料庫存差異分析系統 V1

## 架構
- GitHub Pages：前端
- Supabase Auth：登入與身分
- Supabase PostgreSQL：中央資料庫（正式資料，不存於瀏覽器）
- RLS：資料庫層權限
- Browser XLSX parser：直接在瀏覽器解析 SAP Excel
- IndexedDB：本版本不作為正式資料庫；瀏覽器只保存登入 session

因此換電腦、手機或瀏覽器後，登入同一帳號即可讀取中央資料。

## 第一次設定
1. 建立 Supabase project。
2. 在 Supabase SQL Editor 執行 `supabase/schema.sql`。
3. 在 Authentication / Users 建立第一個使用者（Email + Password）。
4. 執行：
   `update public.profiles set role='admin' where user_id='你的-user-uuid';`
5. 複製 `config.example.js` 成 `config.js`。
6. 填入 Supabase Project URL 與 Publishable Key。
   - 不要放 service_role key。
7. 將 `index.html`、`config.js`、`.nojekyll` 放到 GitHub repository。
8. 開啟 GitHub Pages。

## 使用
- 第一次匯入目前基準 `2026全.xlsx`。
- 之後每日匯入新的 SAP 全倉庫存。
- 系統自動找「該日期之前最近的一份快照」作為比較基準。
- 比對鍵：物料編號 + 評價 + 儲存地點。
- 相同鍵分散在多個儲格時，先彙總數量再比較。
- 系統會產生 increase / decrease / new / disappeared。
- 相同檔案 SHA-256 或相同日期會拒絕重複匯入。
- 匯入與異動計算在 PostgreSQL RPC 交易中一次完成；失敗會回滾，不留下半套資料。

## SAP Excel 必要欄位
物料編號、評價、儲存地點、庫存量。
可選：名稱規範、儲格、安全庫存、最後收料日期、最後使用日期、單位。

## 安全
GitHub repository 不要放真實 SAP Excel。
只把程式與 `config.js`（publishable key）放上去；不要放 service_role key。
RLS 已在 schema.sql 中啟用。
