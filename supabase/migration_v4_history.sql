-- MaterialMind V4: 歷史庫存時間軸
-- 用途：以「基準日」為起點，逐日顯示每筆料號+評價+倉庫+儲格的庫存狀態與變化。
-- 安全：只讀 RPC，使用目前登入者；不繞過 RLS 寫入資料。

create index if not exists inventory_snapshots_date_idx
  on public.inventory_snapshots(snapshot_date desc);

create index if not exists inventory_snapshot_rows_history_idx
  on public.inventory_snapshot_rows(snapshot_id, part_no, rating, warehouse, storage_bin);

create or replace function public.get_inventory_history(
  p_start_date date,
  p_end_date date,
  p_part_no text default null,
  p_rating text default null,
  p_warehouse text default null,
  p_storage_bin text default null,
  p_only_changes boolean default false
)
returns table(
  snapshot_date date,
  snapshot_id uuid,
  previous_snapshot_id uuid,
  part_no text,
  material_name text,
  rating text,
  warehouse text,
  storage_bin text,
  previous_quantity numeric,
  current_quantity numeric,
  quantity_delta numeric,
  change_type text,
  safety_stock numeric,
  is_baseline boolean
)
language sql
stable
security definer
set search_path=''
as $$
with ordered_snapshots as (
  select
    s.id,
    s.snapshot_date,
    lag(s.id) over(order by s.snapshot_date) as previous_id
  from public.inventory_snapshots s
  where s.snapshot_date <= p_end_date
),
range_snapshots as (
  select id, snapshot_date, previous_id
  from ordered_snapshots
  where snapshot_date between p_start_date and p_end_date
),
aggregated_rows as (
  select
    r.snapshot_id,
    r.part_no,
    max(r.material_name) as material_name,
    r.rating,
    r.warehouse,
    r.storage_bin,
    sum(r.quantity) as quantity,
    max(r.safety_stock) as safety_stock
  from public.inventory_snapshot_rows r
  join range_snapshots rs on rs.id=r.snapshot_id
  group by r.snapshot_id,r.part_no,r.rating,r.warehouse,r.storage_bin
),
-- The first day is deliberately treated as the baseline: its quantity is the
-- starting state, not a change against the snapshot before the selected range.
baseline_rows as (
  select
    rs.snapshot_date,
    rs.id as snapshot_id,
    null::uuid as previous_snapshot_id,
    r.part_no,
    r.material_name,
    r.rating,
    r.warehouse,
    r.storage_bin,
    null::numeric as previous_quantity,
    r.quantity as current_quantity,
    null::numeric as quantity_delta,
    'baseline'::text as change_type,
    r.safety_stock,
    true as is_baseline
  from range_snapshots rs
  join aggregated_rows r on r.snapshot_id=rs.id
  where rs.snapshot_date=p_start_date
),
-- For each later snapshot compare it with the immediately preceding available
-- snapshot. Build the union of current and previous keys first so a completely
-- missing current row is still represented as a disappeared material/bin.
daily_keys as (
  select rs.snapshot_date,rs.id as snapshot_id,rs.previous_id as previous_snapshot_id,
         c.part_no,c.rating,c.warehouse,c.storage_bin
  from range_snapshots rs
  join aggregated_rows c on c.snapshot_id=rs.id
  where rs.snapshot_date>p_start_date and rs.previous_id is not null
  union
  select rs.snapshot_date,rs.id as snapshot_id,rs.previous_id as previous_snapshot_id,
         p.part_no,p.rating,p.warehouse,p.storage_bin
  from range_snapshots rs
  join aggregated_rows p on p.snapshot_id=rs.previous_id
  where rs.snapshot_date>p_start_date and rs.previous_id is not null
),
daily_rows as (
  select
    k.snapshot_date,
    k.snapshot_id,
    k.previous_snapshot_id,
    k.part_no,
    coalesce(c.material_name,p.material_name,'') as material_name,
    k.rating,
    k.warehouse,
    k.storage_bin,
    coalesce(p.quantity,0) as previous_quantity,
    coalesce(c.quantity,0) as current_quantity,
    coalesce(c.quantity,0)-coalesce(p.quantity,0) as quantity_delta,
    case
      when coalesce(p.quantity,0)=0 and coalesce(c.quantity,0)<>0 then 'new'
      when coalesce(p.quantity,0)<>0 and coalesce(c.quantity,0)=0 then 'disappeared'
      when coalesce(c.quantity,0)>coalesce(p.quantity,0) then 'increase'
      when coalesce(c.quantity,0)<coalesce(p.quantity,0) then 'decrease'
      else 'unchanged'
    end as change_type,
    coalesce(c.safety_stock,p.safety_stock,0) as safety_stock,
    false as is_baseline
  from daily_keys k
  left join aggregated_rows c
    on c.snapshot_id=k.snapshot_id
   and c.part_no=k.part_no and c.rating=k.rating
   and c.warehouse=k.warehouse and c.storage_bin=k.storage_bin
  left join aggregated_rows p
    on p.snapshot_id=k.previous_snapshot_id
   and p.part_no=k.part_no and p.rating=k.rating
   and p.warehouse=k.warehouse and p.storage_bin=k.storage_bin
),

combined as (
  select * from baseline_rows
  union all
  select * from daily_rows
)
select
  h.snapshot_date,
  h.snapshot_id,
  h.previous_snapshot_id,
  h.part_no,
  h.material_name,
  h.rating,
  h.warehouse,
  h.storage_bin,
  h.previous_quantity,
  h.current_quantity,
  h.quantity_delta,
  h.change_type,
  h.safety_stock,
  h.is_baseline
from combined h
where (p_part_no is null or p_part_no='' or lower(h.part_no) like '%'||lower(p_part_no)||'%')
  and (p_rating is null or p_rating='' or lower(h.rating) like '%'||lower(p_rating)||'%')
  and (p_warehouse is null or p_warehouse='' or lower(h.warehouse) like '%'||lower(p_warehouse)||'%')
  and (p_storage_bin is null or p_storage_bin='' or lower(h.storage_bin) like '%'||lower(p_storage_bin)||'%')
  and (not p_only_changes or (not h.is_baseline and h.quantity_delta<>0))
order by h.snapshot_date, h.storage_bin, h.part_no, h.rating, h.warehouse;
$$;

revoke all on function public.get_inventory_history(date,date,text,text,text,text,boolean)
  from public, anon;
grant execute on function public.get_inventory_history(date,date,text,text,text,text,boolean)
  to authenticated;

-- Date selector helper: only dates that actually have imported snapshots are shown.
create or replace function public.get_snapshot_dates()
returns table(snapshot_date date, row_count integer, source_file_name text)
language sql
stable
security definer
set search_path=''
as $$
  select s.snapshot_date,s.row_count,s.source_file_name
  from public.inventory_snapshots s
  order by s.snapshot_date;
$$;

revoke all on function public.get_snapshot_dates() from public, anon;
grant execute on function public.get_snapshot_dates() to authenticated;
