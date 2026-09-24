# MaterialMind V4 測試報告

## 測試範圍

本次檢查涵蓋前端 HTML/JavaScript、V4 migration、歷史比對邏輯、匯出欄位、檔案安全與 V3 相容性。

> 限制：本環境沒有使用者目前 Supabase 專案的管理連線，因此無法在你的實際雲端資料庫上代為執行 migration。SQL 的最終雲端執行結果仍以你在 Supabase SQL Editor 執行後的結果為準。

## 已完成檢查

1. JavaScript `node --check`：PASS
2. HTML DOM ID 重複檢查：PASS（0 個重複 ID）
3. `getElementById()` 參照完整性：PASS（0 個缺少 DOM 元件）
4. HTML script 結構檢查：PASS
5. V4 必要 RPC 名稱與 GRANT：PASS（靜態檢查）
6. 歷史鍵確認包含 `part_no + rating + warehouse + storage_bin`：PASS
7. 基準日不與基準日前快照比較：PASS（SQL 邏輯檢查）
8. 新增資料的 full-key 保留邏輯：PASS（SQL 邏輯檢查）
9. 消失資料的 full-key 保留邏輯：PASS（SQL 邏輯檢查）
10. 消失事件不會在後續缺失快照中重複產生：PASS（合成資料測試）
11. `only_changes` 模式排除基準日與未變化資料：PASS
12. 單一材料時間軸在「只看變化」模式下仍重新讀取完整歷史：PASS
13. XSS 顯示欄位使用 `esc()`：PASS（歷史表／時間軸）
14. 歷史 Excel 匯出包含日期、狀態、料號、材料名稱、評價、倉庫、儲格、前日庫存、當日庫存、變化量、安全庫存：PASS
15. V3 `inventory_changes`、Agent、Auth、RLS 前端功能未被移除：PASS（靜態比對）
16. config 範例未包含 Secret Key / service_role：PASS
17. V4 migration 不使用 `truncate`、`drop table` 或刪除快照資料的語句：PASS
18. 既有 V3 migration 不需重新執行：PASS（升級路徑明確）

## 合成資料測試

測試資料：

- 09/21：A=100、B=50
- 09/22：A=95、B=50、C=10
- 09/23：A=95、C=15（B 消失）
- 09/24：A=120、C=15、B=5（B 重新出現）

預期：

- 09/21 A/B：基準日
- 09/22 A：減少 5
- 09/22 B：未變化
- 09/22 C：新增 10
- 09/23 B：消失 50
- 09/24 B：重新出現，判定為新增 5

結果：PASS。

## 重要資料語意

V4 不會自行創造不存在的日期。如果資料庫只有 09/21、09/23、09/25 三份快照，歷史查詢只會使用這三個實際快照日；09/23 會與前一份實際快照 09/21 比較。
