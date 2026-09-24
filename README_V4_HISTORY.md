# MaterialMind V4｜逐日歷史庫存時間軸

本版是在 MaterialMind V3「儲格級差異」基礎上新增「基準日 → 結束日」逐日歷史追蹤。

## V4 新增

### 1. 基準日到結束日逐日查看
例如選擇：

- 基準日：2026-09-21
- 結束日：2026-09-30

系統會依資料庫實際存在的 SAP 快照逐日顯示。

### 2. 每筆資料以完整鍵值追蹤
歷史比對鍵維持 V3 定義：

`料號 + 評價 + 倉庫 + 儲格`

每筆歷史紀錄包含：

- 日期
- 狀態
- 料號
- 材料名稱
- 評價
- 倉庫
- 儲格
- 前一份快照庫存
- 當日庫存
- 變化量
- 安全庫存

### 3. 狀態

- 基準日
- 增加
- 減少
- 新增
- 消失
- 未變化

「消失」只在實際從前一份快照存在、下一份快照不存在時產生；不會在後續每天重複產生同一筆消失事件。

### 4. 單一材料時間軸
點擊歷史表中的料號，可以開啟該「料號＋評價＋倉庫＋儲格」的完整時間軸。即使目前開啟「只顯示有變化」，材料時間軸仍會重新讀取完整逐日資料。

### 5. Excel 匯出
可以將目前歷史篩選結果匯出為 Excel。

---

# 升級方式

## A. 先升級 Supabase

你目前已經使用 V3 資料庫，因此**不要重新執行 `schema.sql`**，也不要重新執行 V3 migration。

在目前的 Supabase 專案 SQL Editor 執行：

`supabase/migration_v4_history.sql`

成功訊息應為：

`Success. No rows returned`

這個 migration 是唯讀歷史功能的資料庫升級，不會刪除既有：

- inventory_snapshots
- inventory_snapshot_rows
- inventory_changes

也不會重建或覆蓋既有庫存快照。

## B. 更新 GitHub Pages

將本版 `index.html`、`README_V4_HISTORY.md`、`VERSION.txt`、`CHANGELOG.md` 等檔案更新到 GitHub。

`config.js` 請保留你目前 GitHub 正在使用的 Supabase Project URL 與 Publishable Key；不要改成 `config.example.js` 的範例值。

**不要放入 Supabase Secret Key / service_role key。**

## C. 使用

登入 MaterialMind 後，頁面會自動取得目前資料庫中的快照日期。

在「逐日歷史庫存時間軸」：

1. 選基準日。
2. 選結束日。
3. 按「載入歷史」。
4. 可使用料號、評價、倉庫、儲格篩選。
5. 可勾選「只顯示有變化」。
6. 點擊任一料號查看完整材料時間軸。
7. 可匯出目前歷史篩選結果 Excel。

## 注意

系統只能顯示資料庫中實際已匯入的快照日。若 09/21、09/23、09/25 有快照，但 09/22、09/24 沒有 SAP 快照，系統不會虛構不存在的每日資料；09/23 會與前一個實際快照 09/21 比較。
