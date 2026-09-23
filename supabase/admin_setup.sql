-- After creating your Supabase Auth user, replace the email below and run this once.
-- This gives the account permission to run imports and the Windows Auto-Sync Agent.
update public.profiles p
set role='admin', display_name='MaterialMind 管理員'
from auth.users u
where p.user_id=u.id and u.email='YOUR_EMAIL@example.com';

-- If you want a separate account for the Windows Agent, set that account to operator instead:
-- update public.profiles p
-- set role='operator', display_name='MaterialMind Windows Agent'
-- from auth.users u
-- where p.user_id=u.id and u.email='AGENT_EMAIL@example.com';
