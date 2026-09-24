# MaterialMind V3 驗證報告

本版本在交付前完成 16 項程式與資料模型檢查。

| # | 檢查 | 結果 |
|---|---|---|
| 1 | Python Agent AST 語法檢查 | PASS |
| 2 | 前端 JavaScript `node --check` | PASS |
| 3 | 所有 `getElementById` 參照均有對應 DOM ID | PASS |
| 4 | 所有按鈕事件均有對應 handler | PASS |
| 5 | SQL 差異唯一鍵包含 `storage_bin` | PASS |
| 6 | 消失資料使用上一份快照的材料名稱/儲格 fallback | PASS |
| 7 | V2→V3 migration 保留 snapshots/rows 並重建 changes | PASS |
| 8 | Agent 第一欄 index=0 解析問題已修正 | PASS |
| 9 | Agent 改以中央最新快照判斷，避免換電腦重複匯入 | PASS |
| 10 | 程式碼未包含 Supabase Secret/service_role key | PASS |
| 11 | 前端不再將無日期檔案誤判為今天 | PASS |
| 12 | 五種統計卡片均可觸發狀態篩選 | PASS |
| 13 | Agent 多工作表各自找標題列並成功解析測試 XLSX | PASS |
| 14 | 20260924 / 2026-09-24 / 2026_09_24 日期格式測試 | PASS |
| 15 | 料號補零、`.0` 清理、非數字料號拒絕測試 | PASS |
| 16 | 同料號不同儲格、消失資料完整回溯的差異邏輯測試 | PASS |

## 已特別針對本次問題驗證

### 儲格
差異鍵已固定為：

`料號 + 評價 + 倉庫 + 儲格`

因此同一料號位於 A01、A02 時，兩個庫位會是兩筆獨立異動。

### 消失
今天不存在、昨天存在的資料，會從昨天快照取得：

- 料號
- 材料名稱
- 評價
- 倉庫
- 儲格
- 昨日庫存
- 安全庫存

因此不會再只顯示材料編號。

### 統計卡片
總異動、增加、減少、新增、消失均可直接點擊並套用篩選。

## 尚未能做的驗證

此交付包沒有直接連線到你的 Supabase 生產資料庫執行 migration，因此沒有宣稱「已在你的正式資料庫執行成功」。

正式上線前必須先執行：

`supabase/migration_v3.sql`

再刷新 GitHub Pages。

