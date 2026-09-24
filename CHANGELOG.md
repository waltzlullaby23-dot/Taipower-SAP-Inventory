# CHANGELOG

## V4.0.0 — 逐日歷史庫存時間軸

### 新增
- 基準日／結束日歷史查詢。
- 逐日庫存狀態：基準日、增加、減少、新增、消失、未變化。
- 歷史查詢維持「料號＋評價＋倉庫＋儲格」完整鍵。
- 消失資料完整保留上一份快照資訊。
- 單一材料完整歷史時間軸視窗。
- 歷史資料搜尋與評價／倉庫／儲格篩選。
- 「只顯示有變化」模式。
- 歷史結果 Excel 匯出。
- `get_snapshot_dates()` RPC。
- `get_inventory_history()` RPC。

### 保留
- V3 儲格級差異。
- V3 完整消失資料。
- V3 總異動／增加／減少／新增／消失統計。
- V3 Windows Agent。
- V3 Supabase Auth / RLS。

### 資料安全
- V4 migration 不刪除既有快照與異動資料。
- 前端僅使用 Publishable Key。
- 不包含 Secret Key / service_role key。
