-- MaterialMind V3
-- 建立 Auth user 後，將 Email 改成實際帳號並執行一次。
update public.profiles p
set role='admin', display_name='MaterialMind 管理員'
from auth.users u
where p.user_id=u.id and u.email='YOUR_EMAIL@example.com';

-- Windows Agent 可使用 operator 帳號：
-- update public.profiles p
-- set role='operator', display_name='MaterialMind Windows Agent'
-- from auth.users u
-- where p.user_id=u.id and u.email='AGENT_EMAIL@example.com';
