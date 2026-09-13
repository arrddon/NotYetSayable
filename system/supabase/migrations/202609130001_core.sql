-- Supabase is authoritative. Apply once to a new project.
-- All writes go through narrow transactional functions; no browser table writes.
begin;
create schema if not exists nys_private;
revoke all on schema nys_private from public, anon, authenticated;

create table nys_private.operators (
  user_id uuid primary key
);
create table public.sessions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now()
);
create table public.participants (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions(id),
  slot text not null check (slot in ('A','B')),
  owner_id uuid,
  generation integer not null default 1,
  revision integer not null default 0,
  step text not null default 'consent' check (step in ('consent','tutorial','question','map','complete')),
  question integer not null default 1 check (question between 1 and 4),
  status text not null default 'ready' check (status in ('ready','countdown','processing','result','error')),
  consent_at timestamptz,
  countdown_ends_at timestamptz,
  active_job_id uuid,
  error_code text,
  pin jsonb,
  updated_at timestamptz not null default now(),
  unique (session_id, slot)
);
create table public.responses (
  participant_id uuid not null references public.participants(id),
  generation integer not null,
  question integer not null check (question between 1 and 4),
  attempt integer not null,
  result jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (participant_id, generation, question)
);
create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  participant_id uuid not null references public.participants(id),
  generation integer not null,
  question integer not null,
  attempt integer not null,
  status text not null default 'queued' check (status in ('queued','processing','complete','error','cancelled')),
  not_before timestamptz not null,
  deadline timestamptz not null,
  lease_id uuid,
  error_code text,
  created_at timestamptz not null default now(),
  finished_at timestamptz
);
create unique index one_active_job_per_participant on public.jobs(participant_id)
  where status in ('queued','processing');
create index job_queue on public.jobs(status, not_before);
create table nys_private.entries (
  participant_id uuid primary key references public.participants(id),
  token_hash bytea not null unique,
  expires_at timestamptz not null default now() + interval '4 days'
);
create table nys_private.receipts (
  request_id uuid primary key,
  actor_id uuid not null,
  payload jsonb not null,
  result jsonb,
  created_at timestamptz not null default now()
);
create table public.worker_health (
  id text primary key check (id = 'local'),
  last_seen_at timestamptz not null,
  mode text not null check (mode in ('mock','local'))
);

create function public.nys_is_operator() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select 1 from nys_private.operators where user_id = auth.uid());
$$;

create function nys_private.assert_operator() returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.nys_is_operator() then raise exception 'FORBIDDEN'; end if;
end; $$;

create function nys_private.assert_worker() returns void
language plpgsql security definer set search_path = '' as $$
begin
  if coalesce(auth.role(), '') <> 'service_role' then raise exception 'FORBIDDEN'; end if;
end; $$;

create function public.nys_snapshot(p_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare p public.participants; r jsonb;
begin
  select * into p from public.participants where id = p_id;
  if p.id is null or auth.uid() is null or
    (p.owner_id is distinct from auth.uid() and not public.nys_is_operator()) then
    raise exception 'FORBIDDEN';
  end if;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.question), '[]'::jsonb) into r
    from public.responses x where participant_id = p.id and generation = p.generation;
  return jsonb_build_object('participant', to_jsonb(p), 'responses', r, 'server_now', now());
end; $$;

create function public.nys_join(p_token text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.participants; target uuid;
begin
  if auth.uid() is null or length(p_token) > 200 then raise exception 'FORBIDDEN'; end if;
  select participant_id into target from nys_private.entries
    where token_hash = sha256(convert_to(p_token, 'UTF8')) and expires_at > now();
  select * into p from public.participants where id = target for update;
  -- Recheck under the participant lock: reset may have rotated the entry while we waited.
  if p.id is null or not exists(select 1 from nys_private.entries where participant_id = p.id
    and token_hash = sha256(convert_to(p_token, 'UTF8')) and expires_at > now()) then
    raise exception 'ENTRY_EXPIRED';
  end if;
  if p.owner_id is not null and p.owner_id <> auth.uid() then raise exception 'ENTRY_IN_USE'; end if;
  if p.owner_id is null then
    update public.participants set owner_id = auth.uid(), revision = revision + 1, updated_at = now() where id = p.id;
  end if;
  return public.nys_snapshot(p.id);
end; $$;

create function public.nys_create_session(p_request_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare sid uuid; pid uuid; s text; token text; output jsonb := '[]'; receipt nys_private.receipts;
begin
  perform nys_private.assert_operator();
  -- Serialize repeat requests even when the first response was lost.
  perform pg_advisory_xact_lock(hashtextextended(p_request_id::text, 0));
  select * into receipt from nys_private.receipts where request_id = p_request_id;
  if found then
    if receipt.actor_id <> auth.uid() or receipt.payload <> '"create_session"'::jsonb then raise exception 'REQUEST_REUSED'; end if;
    return receipt.result;
  end if;
  insert into public.sessions default values returning id into sid;
  foreach s in array array['A','B'] loop
    insert into public.participants(session_id, slot) values(sid, s) returning id into pid;
    token := gen_random_uuid()::text || gen_random_uuid()::text;
    insert into nys_private.entries(participant_id, token_hash) values(pid, sha256(convert_to(token, 'UTF8')));
    output := output || jsonb_build_array(jsonb_build_object('id',pid,'slot',s,'token',token));
  end loop;
  output := jsonb_build_object('session_id',sid,'entries',output);
  insert into nys_private.receipts values(p_request_id, auth.uid(), '"create_session"', output, now());
  return output;
end; $$;

create function public.nys_operator_state() returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
  perform nys_private.assert_operator();
  return jsonb_build_object(
    'sessions', (select coalesce(jsonb_agg(to_jsonb(s) order by s.created_at desc), '[]') from
      (select * from public.sessions order by created_at desc limit 20) s),
    'participants', (select coalesce(jsonb_agg(to_jsonb(p) order by p.slot), '[]') from public.participants p
      where session_id in (select id from public.sessions order by created_at desc limit 20)),
    'health', (select to_jsonb(h) from public.worker_health h where id = 'local'),
    'server_now', now());
end; $$;

create function public.nys_action(
  p_id uuid, p_generation integer, p_revision integer, p_request_id uuid,
  p_action text, p_data jsonb default '{}'
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  p public.participants; receipt nys_private.receipts; payload jsonb;
  job_id uuid; next_question integer; attempt_no integer; lng numeric; lat numeric;
begin
  select * into p from public.participants where id = p_id for update;
  if p.id is null or auth.uid() is null or p.owner_id is distinct from auth.uid() then raise exception 'FORBIDDEN'; end if;
  if p.generation <> p_generation then raise exception 'STALE_GENERATION'; end if;
  payload := jsonb_build_object('id',p_id,'generation',p_generation,'revision',p_revision,'action',p_action,'data',p_data);
  select * into receipt from nys_private.receipts where request_id = p_request_id;
  if found then
    if receipt.actor_id <> auth.uid() or receipt.payload <> payload then raise exception 'REQUEST_REUSED'; end if;
    return public.nys_snapshot(p_id);
  end if;
  if p.revision <> p_revision then raise exception 'STALE_STATE'; end if;
  if p_action = 'consent' and p.step = 'consent' then
    update public.participants set consent_at = now(), step = 'tutorial' where id = p_id;
  elsif p_action = 'tutorial' and p.step = 'tutorial' then
    update public.participants set step = 'question', question = 1, status = 'ready' where id = p_id;
  elsif p_action in ('confirm','retry') and p.step = 'question'
    and ((p_action = 'confirm' and p.status = 'ready') or (p_action = 'retry' and p.status = 'error')) then
    if p.consent_at is null then raise exception 'INVALID_TRANSITION'; end if;
    select coalesce(max(attempt), 0) + 1 into attempt_no from public.jobs
      where participant_id = p_id and generation = p_generation and question = p.question;
    insert into public.jobs(participant_id,generation,question,attempt,not_before,deadline)
      values(p_id,p_generation,p.question,attempt_no,now()+interval '3 seconds',now()+interval '90 seconds') returning id into job_id;
    -- A replacement submission immediately supersedes the previous answer.
    delete from public.responses where participant_id = p_id and generation = p_generation and question = p.question;
    update public.participants set status = 'countdown', countdown_ends_at = now()+interval '3 seconds',
      active_job_id = job_id, error_code = null where id = p_id;
  elsif p_action = 'continue' and p.step = 'question' and p.status = 'result' then
    -- Find the first unanswered question. Revisiting cannot accidentally skip a gap.
    select min(q) into next_question from generate_series(1,4) q where not exists
      (select 1 from public.responses where participant_id = p_id and generation = p_generation and question = q);
    if next_question is null then
      update public.participants set step = 'map', status = 'ready', active_job_id = null where id = p_id;
    else
      update public.participants set question = next_question, status = 'ready', active_job_id = null where id = p_id;
    end if;
  elsif p_action = 'revisit' and p.step in ('question','map','complete') and p.status in ('ready','result','error') then
    next_question := (p_data->>'question')::integer;
    if not exists(select 1 from public.responses where participant_id = p_id and generation = p_generation and question = next_question) then
      raise exception 'INVALID_TRANSITION';
    end if;
    update public.participants set step = 'question', question = next_question, status = 'ready',
      active_job_id = null, error_code = null where id = p_id;
  elsif p_action = 'pin' and p.step = 'map' then
    if (select count(*) from public.responses where participant_id = p_id and generation = p_generation) <> 4 then
      raise exception 'INVALID_TRANSITION';
    end if;
    lng := (p_data->>'lng')::numeric; lat := (p_data->>'lat')::numeric;
    if lng is null or lat is null or not (lng between -180 and 180) or not (lat between -90 and 90) then
      raise exception 'INVALID_COORDINATES';
    end if;
    update public.participants set pin = jsonb_build_object('lng',lng,'lat',lat), step = 'complete', status = 'ready' where id = p_id;
  else
    raise exception 'INVALID_TRANSITION';
  end if;
  update public.participants set revision = revision + 1, updated_at = now() where id = p_id;
  insert into nys_private.receipts values(p_request_id,auth.uid(),payload,null,now());
  return public.nys_snapshot(p_id);
end; $$;

create function public.nys_operator_action(p_id uuid, p_generation integer, p_revision integer, p_request_id uuid, p_action text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare p public.participants; token text; output jsonb; payload jsonb; receipt nys_private.receipts;
begin
  perform nys_private.assert_operator();
  select * into p from public.participants where id = p_id for update;
  if p.id is null then raise exception 'NOT_FOUND'; end if;
  payload := jsonb_build_object('id',p_id,'generation',p_generation,'revision',p_revision,'operator_action',p_action);
  select * into receipt from nys_private.receipts where request_id = p_request_id;
  if found then
    if receipt.actor_id <> auth.uid() or receipt.payload <> payload then raise exception 'REQUEST_REUSED'; end if;
    return receipt.result;
  end if;
  if p.generation <> p_generation or p.revision <> p_revision then raise exception 'STALE_STATE'; end if;
  if p_action = 'reset' then
    update public.jobs set status = 'cancelled', finished_at = now() where participant_id = p_id and status in ('queued','processing');
    update public.participants set generation = generation + 1, owner_id = null, step = 'consent', question = 1,
      status = 'ready', consent_at = null, pin = null, countdown_ends_at = null, active_job_id = null, error_code = null where id = p_id;
    token := gen_random_uuid()::text || gen_random_uuid()::text;
    update nys_private.entries set token_hash = sha256(convert_to(token,'UTF8')), expires_at = now()+interval '4 days' where participant_id = p_id;
  elsif p_action = 'recover' and p.step = 'question' and p.status in ('countdown','processing','error') then
    update public.jobs set status = 'cancelled', finished_at = now() where participant_id = p_id and status in ('queued','processing');
    update public.participants set status = 'error', active_job_id = null, countdown_ends_at = null, error_code = 'OPERATOR_RECOVERY' where id = p_id;
  elsif p_action = 'rotate_entry' then
    -- Reissue access without discarding answers. The previous browser loses ownership.
    update public.participants set owner_id = null where id = p_id;
    token := gen_random_uuid()::text || gen_random_uuid()::text;
    update nys_private.entries set token_hash = sha256(convert_to(token,'UTF8')), expires_at = now()+interval '4 days' where participant_id = p_id;
  else raise exception 'INVALID_TRANSITION';
  end if;
  update public.participants set revision = revision + 1, updated_at = now() where id = p_id;
  output := jsonb_build_object('snapshot',public.nys_snapshot(p_id),'token',token);
  insert into nys_private.receipts values(p_request_id,auth.uid(),payload,output,now());
  return output;
end; $$;

create function public.nys_worker_claim(p_mode text default 'local') returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.participants; j public.jobs;
begin
  perform nys_private.assert_worker();
  insert into public.worker_health values('local', now(), p_mode)
    on conflict(id) do update set last_seen_at = now(), mode = excluded.mode;
  -- Always acquire participant before job locks, matching reset and completion.
  for p in select * from public.participants where active_job_id is not null
    and status in ('countdown','processing') order by updated_at for update skip locked loop
    select * into j from public.jobs where id = p.active_job_id for update;
    if j.deadline < now() and j.status in ('queued','processing') then
      update public.jobs set status = 'error', error_code = 'TIMEOUT', finished_at = now() where id = j.id;
      update public.participants set status = 'error', error_code = 'TIMEOUT', countdown_ends_at = null,
        revision = revision + 1, updated_at = now() where id = p.id;
    elsif j.status = 'queued' and j.not_before <= now() then
      update public.jobs set status = 'processing', lease_id = gen_random_uuid() where id = j.id returning * into j;
      update public.participants set status = 'processing', countdown_ends_at = null,
        revision = revision + 1, updated_at = now() where id = p.id;
      return to_jsonb(j) || jsonb_build_object('slot',p.slot,'session_id',p.session_id);
    end if;
  end loop;
  return null;
end; $$;

create function public.nys_worker_finish(p_job_id uuid, p_lease_id uuid, p_result jsonb default null, p_error text default null)
returns boolean language plpgsql security definer set search_path = '' as $$
declare p public.participants; j public.jobs; target uuid;
begin
  perform nys_private.assert_worker();
  select participant_id into target from public.jobs where id = p_job_id;
  select * into p from public.participants where id = target for update;
  select * into j from public.jobs where id = p_job_id for update;
  if j.id is null or p.active_job_id is distinct from j.id or p.generation <> j.generation or j.lease_id is distinct from p_lease_id then return false; end if;
  if j.status = 'complete' then return true; end if;
  if j.status <> 'processing' then return false; end if;
  if j.deadline < now() then p_error := 'TIMEOUT'; end if;
  if p_error is null then
    if p_result is null or jsonb_typeof(p_result) <> 'object'
      or jsonb_typeof(p_result->'raw_response') is distinct from 'string'
      or jsonb_typeof(p_result->'translated_response') is distinct from 'string'
      or jsonb_typeof(p_result->'keywords') is distinct from 'array'
      or jsonb_typeof(p_result->'trace') is distinct from 'string'
      or not (p_result ? 'classification') then raise exception 'INVALID_RESULT'; end if;
    insert into public.responses(participant_id,generation,question,attempt,result)
      values(p.id,j.generation,j.question,j.attempt,p_result)
      on conflict(participant_id,generation,question) do update
        set attempt = excluded.attempt, result = excluded.result, updated_at = now();
    update public.jobs set status = 'complete', finished_at = now() where id = j.id;
    update public.participants set status = 'result', error_code = null, revision = revision+1, updated_at = now() where id = p.id;
  else
    update public.jobs set status = 'error', error_code = left(p_error,100), finished_at = now() where id = j.id;
    update public.participants set status = 'error', error_code = left(p_error,100), revision = revision+1, updated_at = now() where id = p.id;
  end if;
  return true;
end; $$;

alter table public.sessions enable row level security;
alter table public.participants enable row level security;
alter table public.responses enable row level security;
alter table public.jobs enable row level security;
alter table public.worker_health enable row level security;
create policy session_operator_read on public.sessions for select to authenticated using(public.nys_is_operator());
create policy participant_read on public.participants for select to authenticated using(owner_id = (select auth.uid()) or public.nys_is_operator());
create policy response_read on public.responses for select to authenticated using(exists(
  select 1 from public.participants p where p.id = responses.participant_id and p.generation = responses.generation and
    (p.owner_id = (select auth.uid()) or public.nys_is_operator())
));
create policy job_operator_read on public.jobs for select to authenticated using(public.nys_is_operator());
create policy health_operator_read on public.worker_health for select to authenticated using(public.nys_is_operator());
revoke all on public.sessions, public.participants, public.responses, public.jobs, public.worker_health from anon, authenticated;
grant select on public.sessions, public.participants, public.responses, public.jobs, public.worker_health to authenticated;

-- Supabase may install permissive default function grants. Explicitly scope every RPC.
revoke all on all functions in schema nys_private from public, anon, authenticated;
do $$ declare f record; begin
  for f in select oid::regprocedure as signature from pg_proc where pronamespace = 'public'::regnamespace and proname like 'nys_%' loop
    execute format('revoke all on function %s from public, anon, authenticated, service_role', f.signature);
    if f.signature::text like 'nys_worker_%' then
      execute format('grant execute on function %s to service_role', f.signature);
    else
      execute format('grant execute on function %s to authenticated', f.signature);
    end if;
  end loop;
end $$;
do $$ begin
  if exists(select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.participants;
  end if;
end $$;
commit;
