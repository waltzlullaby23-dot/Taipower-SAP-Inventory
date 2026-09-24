-- MaterialMind V3 migration for an existing V2 database.
-- IMPORTANT: this migration rebuilds inventory_changes from stored snapshots.
-- It does NOT delete inventory_snapshot_rows or inventory_snapshots.
-- Existing historical snapshots are preserved; their change rows are recalculated
-- with the correct key: part_no + rating + warehouse + storage_bin.

alter table public.inventory_changes
  add column if not exists storage_bin text not null default '';

do $$
declare
  c record;
begin
  for c in
    select con.conname
    from pg_constraint con
    join pg_class rel on rel.oid=con.conrelid
    join pg_namespace nsp on nsp.oid=rel.relnamespace
    where nsp.nspname='public'
      and rel.relname='inventory_changes'
      and con.contype='u'
      and array(
        select att.attname
        from unnest(con.conkey) with ordinality k(attnum,ord)
        join pg_attribute att on att.attrelid=rel.oid and att.attnum=k.attnum
        order by k.ord
      ) = array['to_snapshot_id','part_no','rating','warehouse']
  loop
    execute format('alter table public.inventory_changes drop constraint if exists %I',c.conname);
  end loop;
end $$;

drop index if exists inventory_changes_key_uq;
create unique index if not exists inventory_changes_key_uq
  on public.inventory_changes(to_snapshot_id, part_no, rating, warehouse, storage_bin);

create index if not exists inventory_changes_bin_idx
  on public.inventory_changes(to_snapshot_id, warehouse, storage_bin, part_no);

-- Rebuild all historical change rows so the new storage-bin dimension is correct.
truncate table public.inventory_changes restart identity;

do $$
declare
  s record;
  prev_id uuid;
begin
  for s in
    select id, snapshot_date
    from public.inventory_snapshots
    order by snapshot_date
  loop
    select id into prev_id
    from public.inventory_snapshots
    where snapshot_date < s.snapshot_date
    order by snapshot_date desc
    limit 1;

    if prev_id is not null then
      insert into public.inventory_changes(
        from_snapshot_id,to_snapshot_id,part_no,material_name,rating,warehouse,storage_bin,
        previous_quantity,current_quantity,quantity_delta,change_type,safety_stock
      )
      with prev as (
        select part_no,max(material_name) material_name,rating,warehouse,storage_bin,
               sum(quantity) quantity,max(safety_stock) safety_stock
        from public.inventory_snapshot_rows
        where snapshot_id=prev_id
        group by part_no,rating,warehouse,storage_bin
      ),
      curr as (
        select part_no,max(material_name) material_name,rating,warehouse,storage_bin,
               sum(quantity) quantity,max(safety_stock) safety_stock
        from public.inventory_snapshot_rows
        where snapshot_id=s.id
        group by part_no,rating,warehouse,storage_bin
      ),
      merged as (
        select coalesce(c.part_no,p.part_no) part_no,
               coalesce(c.material_name,p.material_name,'') material_name,
               coalesce(c.rating,p.rating,'') rating,
               coalesce(c.warehouse,p.warehouse,'') warehouse,
               coalesce(c.storage_bin,p.storage_bin,'') storage_bin,
               coalesce(p.quantity,0) previous_quantity,
               coalesce(c.quantity,0) current_quantity,
               coalesce(c.safety_stock,p.safety_stock,0) safety_stock
        from prev p
        full outer join curr c
          on p.part_no=c.part_no
         and p.rating=c.rating
         and p.warehouse=c.warehouse
         and p.storage_bin=c.storage_bin
      )
      select prev_id,s.id,part_no,material_name,rating,warehouse,storage_bin,
             previous_quantity,current_quantity,current_quantity-previous_quantity,
             case
               when previous_quantity=0 and current_quantity<>0 then 'new'
               when previous_quantity<>0 and current_quantity=0 then 'disappeared'
               when current_quantity>previous_quantity then 'increase'
               when current_quantity<previous_quantity then 'decrease'
             end,
             safety_stock
      from merged
      where current_quantity<>previous_quantity;
    end if;
  end loop;
end $$;

-- Replace the import RPC with the storage-bin-aware version.
create or replace function public.import_inventory_snapshot(
  p_snapshot_date date,p_source_file_name text,p_source_file_hash text,p_rows jsonb
)
returns jsonb language plpgsql security definer set search_path=''
as $$
declare
  v_user uuid := (select auth.uid());
  v_snapshot_id uuid;
  v_previous_id uuid;
  v_row_count integer;
  v_changes integer := 0;
begin
  if v_user is null then raise exception 'AUTH_REQUIRED'; end if;
  if not (select public.is_operator_or_admin()) then raise exception 'ROLE_NOT_ALLOWED'; end if;
  if jsonb_typeof(p_rows)<>'array' then raise exception 'ROWS_MUST_BE_ARRAY'; end if;
  if jsonb_array_length(p_rows)=0 then raise exception 'ROWS_EMPTY'; end if;
  if length(coalesce(p_source_file_hash,''))<>64 then raise exception 'INVALID_FILE_HASH'; end if;
  if p_snapshot_date is null then raise exception 'SNAPSHOT_DATE_REQUIRED'; end if;
  if exists(select 1 from public.inventory_snapshots where snapshot_date=p_snapshot_date)
    then raise exception 'SNAPSHOT_DATE_ALREADY_EXISTS'; end if;
  if exists(select 1 from public.inventory_snapshots where source_file_hash=p_source_file_hash)
    then raise exception 'DUPLICATE_FILE'; end if;

  select id into v_previous_id from public.inventory_snapshots
  where snapshot_date<p_snapshot_date order by snapshot_date desc limit 1;

  insert into public.inventory_snapshots(snapshot_date,source_file_name,source_file_hash,row_count,imported_by)
  values(p_snapshot_date,p_source_file_name,p_source_file_hash,jsonb_array_length(p_rows),v_user)
  returning id into v_snapshot_id;

  insert into public.inventory_snapshot_rows(
    snapshot_id,part_no,material_name,rating,warehouse,storage_bin,quantity,
    safety_stock,received_date,last_used_date
  )
  select v_snapshot_id,x.part_no,x.material_name,coalesce(x.rating,''),coalesce(x.warehouse,''),
         coalesce(x.storage_bin,''),coalesce(x.quantity,0),coalesce(x.safety_stock,0),
         x.received_date,x.last_used_date
  from jsonb_to_recordset(p_rows) as x(
    part_no text,material_name text,rating text,warehouse text,storage_bin text,
    quantity numeric,safety_stock numeric,received_date date,last_used_date date
  )
  where nullif(trim(x.part_no),'') is not null
    and nullif(trim(coalesce(x.warehouse,'')),'') is not null;

  select count(*) into v_row_count from public.inventory_snapshot_rows where snapshot_id=v_snapshot_id;
  if v_row_count=0 then raise exception 'NO_VALID_ROWS'; end if;
  update public.inventory_snapshots set row_count=v_row_count where id=v_snapshot_id;

  insert into public.materials(part_no,material_name,unit)
  select part_no,max(material_name),''
  from public.inventory_snapshot_rows
  where snapshot_id=v_snapshot_id group by part_no
  on conflict(part_no) do update
    set material_name=coalesce(excluded.material_name,public.materials.material_name);

  if v_previous_id is not null then
    insert into public.inventory_changes(
      from_snapshot_id,to_snapshot_id,part_no,material_name,rating,warehouse,storage_bin,
      previous_quantity,current_quantity,quantity_delta,change_type,safety_stock
    )
    with prev as (
      select part_no,max(material_name) material_name,rating,warehouse,storage_bin,
             sum(quantity) quantity,max(safety_stock) safety_stock
      from public.inventory_snapshot_rows where snapshot_id=v_previous_id
      group by part_no,rating,warehouse,storage_bin
    ),
    curr as (
      select part_no,max(material_name) material_name,rating,warehouse,storage_bin,
             sum(quantity) quantity,max(safety_stock) safety_stock
      from public.inventory_snapshot_rows where snapshot_id=v_snapshot_id
      group by part_no,rating,warehouse,storage_bin
    ),
    merged as (
      select coalesce(c.part_no,p.part_no) part_no,
             coalesce(c.material_name,p.material_name,'') material_name,
             coalesce(c.rating,p.rating,'') rating,
             coalesce(c.warehouse,p.warehouse,'') warehouse,
             coalesce(c.storage_bin,p.storage_bin,'') storage_bin,
             coalesce(p.quantity,0) previous_quantity,
             coalesce(c.quantity,0) current_quantity,
             coalesce(c.safety_stock,p.safety_stock,0) safety_stock
      from prev p
      full outer join curr c
        on p.part_no=c.part_no and p.rating=c.rating
       and p.warehouse=c.warehouse and p.storage_bin=c.storage_bin
    )
    select v_previous_id,v_snapshot_id,part_no,material_name,rating,warehouse,storage_bin,
           previous_quantity,current_quantity,current_quantity-previous_quantity,
           case
             when previous_quantity=0 and current_quantity<>0 then 'new'
             when previous_quantity<>0 and current_quantity=0 then 'disappeared'
             when current_quantity>previous_quantity then 'increase'
             when current_quantity<previous_quantity then 'decrease'
           end,
           safety_stock
    from merged where current_quantity<>previous_quantity;

    select count(*) into v_changes from public.inventory_changes where to_snapshot_id=v_snapshot_id;
  end if;

  insert into public.import_audit(snapshot_id,action,source_file_name,source_file_hash,row_count,success,operator_id)
  values(v_snapshot_id,'IMPORT',p_source_file_name,p_source_file_hash,v_row_count,true,v_user);

  return jsonb_build_object('snapshot_id',v_snapshot_id,'row_count',v_row_count,
                            'change_count',v_changes,'previous_snapshot_id',v_previous_id);
exception when others then
  insert into public.import_audit(action,source_file_name,source_file_hash,success,error_message,operator_id)
  values('IMPORT',p_source_file_name,p_source_file_hash,false,sqlerrm,v_user);
  raise;
end;
$$;

revoke all on function public.import_inventory_snapshot(date,text,text,jsonb) from public,anon;
grant execute on function public.import_inventory_snapshot(date,text,text,jsonb) to authenticated;

-- Dashboard counts remain based on the rebuilt change rows.
create or replace function public.get_dashboard()
returns jsonb language sql stable security definer set search_path=''
as $$
with latest as (
  select * from public.inventory_snapshots order by snapshot_date desc limit 1
),
counts as (
  select count(*) filter(where change_type='increase') increase_count,
         count(*) filter(where change_type='decrease') decrease_count,
         count(*) filter(where change_type='new') new_count,
         count(*) filter(where change_type='disappeared') disappeared_count
  from public.inventory_changes c join latest l on l.id=c.to_snapshot_id
)
select jsonb_build_object(
  'latest',(select row_to_json(latest) from latest),
  'counts',(select row_to_json(counts) from counts)
);
$$;
revoke all on function public.get_dashboard() from public,anon;
grant execute on function public.get_dashboard() to authenticated;

-- Verification query to run after migration:
-- select to_snapshot_id,count(*) total_changes,
--        count(*) filter(where storage_bin <> '') changes_with_bin
-- from public.inventory_changes
-- group by to_snapshot_id order by to_snapshot_id desc;

create or replace function public.get_latest_snapshot_status()
returns jsonb language sql stable security definer set search_path=''
as $$
  select coalesce(
    (select jsonb_build_object(
      'snapshot_id',id,'snapshot_date',snapshot_date,
      'source_file_name',source_file_name,'source_file_hash',source_file_hash,
      'row_count',row_count,'imported_at',imported_at)
     from public.inventory_snapshots order by snapshot_date desc limit 1),
    '{}'::jsonb
  );
$$;
revoke all on function public.get_latest_snapshot_status() from public,anon;
grant execute on function public.get_latest_snapshot_status() to authenticated;
