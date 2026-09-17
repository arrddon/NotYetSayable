-- CSV master: three captured answers, Q4 map only. No rows are deleted.
-- Existing four-answer archives remain intact. Apply after migrations 001/002.
begin;
create or replace function public.nys_action(
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
    if p.question not between 1 and 3 then raise exception 'INVALID_TRANSITION'; end if;
    if p.consent_at is null then raise exception 'INVALID_TRANSITION'; end if;
    select coalesce(max(attempt), 0) + 1 into attempt_no from public.jobs
      where participant_id = p_id and generation = p_generation and question = p.question;
    insert into public.jobs(participant_id,generation,question,attempt,not_before,deadline)
      values(p_id,p_generation,p.question,attempt_no,now()+interval '3 seconds',now()+interval '180 seconds') returning id into job_id;
    -- A replacement submission immediately supersedes the previous answer.
    delete from public.responses where participant_id = p_id and generation = p_generation and question = p.question;
    update public.participants set status = 'countdown', countdown_ends_at = now()+interval '3 seconds',
      active_job_id = job_id, error_code = null where id = p_id;
  elsif p_action = 'continue' and p.step = 'question' and p.status = 'result' then
    -- Find the first unanswered question. Revisiting cannot accidentally skip a gap.
    select min(q) into next_question from generate_series(1,3) q where not exists
      (select 1 from public.responses where participant_id = p_id and generation = p_generation and question = q);
    if next_question is null then
      update public.participants set step = 'map', question = 4, status = 'ready', active_job_id = null where id = p_id;
    else
      update public.participants set question = next_question, status = 'ready', active_job_id = null where id = p_id;
    end if;
  elsif p_action = 'revisit' and p.step in ('question','map','complete') and p.status in ('ready','result','error') then
    next_question := (p_data->>'question')::integer;
    if next_question is null or next_question not between 1 and 3 then raise exception 'INVALID_TRANSITION'; end if;
    if not exists(select 1 from public.responses where participant_id = p_id and generation = p_generation and question = next_question) then
      raise exception 'INVALID_TRANSITION';
    end if;
    update public.participants set step = 'question', question = next_question, status = 'ready',
      active_job_id = null, error_code = null, pin = null where id = p_id;
  elsif p_action = 'pin' and p.step = 'map' then
    if (select count(*) from public.responses where participant_id = p_id and generation = p_generation and question between 1 and 3) <> 3 then
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

-- Stable accepted-job links for local images/JSON exports; worker-only permissions stay unchanged.
create or replace function public.nys_local_state(p_session_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform nys_private.assert_worker();
  if not exists(select 1 from public.sessions where id=p_session_id) then raise exception 'SESSION_NOT_FOUND'; end if;
  return jsonb_build_object('session_id',p_session_id,'server_now',now(),'participants',
    (select coalesce(jsonb_agg(to_jsonb(p) || jsonb_build_object('responses',
      (select coalesce(jsonb_agg(to_jsonb(r) || jsonb_build_object('job_id',j.id) order by r.question),'[]')
       from public.responses r left join public.jobs j on j.participant_id=r.participant_id
         and j.generation=r.generation and j.question=r.question and j.attempt=r.attempt and j.status='complete'
       where r.participant_id=p.id and r.generation=p.generation)) order by p.slot),'[]')
     from public.participants p where p.session_id=p_session_id));
end; $$;
commit;
