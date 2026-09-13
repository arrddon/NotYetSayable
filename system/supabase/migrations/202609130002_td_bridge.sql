begin;
-- Local bridge reads consent/tutorial/results as well as capture jobs.
create function public.nys_local_state(p_session_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform nys_private.assert_worker();
  if not exists(select 1 from public.sessions where id = p_session_id) then raise exception 'SESSION_NOT_FOUND'; end if;
  return jsonb_build_object('session_id',p_session_id,'server_now',now(),'participants',
    (select coalesce(jsonb_agg(to_jsonb(p) || jsonb_build_object('responses',
      (select coalesce(jsonb_agg(to_jsonb(r) order by r.question),'[]') from public.responses r
        where r.participant_id=p.id and r.generation=p.generation)) order by p.slot),'[]')
      from public.participants p where p.session_id=p_session_id));
end; $$;

-- A persisted claim UUID also acts as the lease. Repeating an uncertain claim
-- returns the same job instead of consuming another participant's job.
create function public.nys_td_claim(p_session_id uuid, p_claim_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.participants; j public.jobs;
begin
  perform nys_private.assert_worker();
  if p_claim_id is null then raise exception 'INVALID_CLAIM'; end if;
  perform pg_advisory_xact_lock(hashtextextended(p_claim_id::text,0));
  insert into public.worker_health values('local', now(), 'local')
    on conflict(id) do update set last_seen_at=now(), mode='local';
  select * into j from public.jobs where lease_id=p_claim_id;
  if found then
    if j.status <> 'processing' or not exists(select 1 from public.participants
      where id=j.participant_id and session_id=p_session_id and generation=j.generation and active_job_id=j.id)
      then return null; end if;
    select * into p from public.participants where id=j.participant_id;
    return to_jsonb(j) || jsonb_build_object('slot',p.slot,'session_id',p.session_id);
  end if;
  for p in select * from public.participants where session_id=p_session_id and active_job_id is not null
    and status in ('countdown','processing') order by updated_at for update skip locked loop
    select * into j from public.jobs where id=p.active_job_id for update;
    if j.deadline < now() and j.status in ('queued','processing') then
      update public.jobs set status='error', error_code='TIMEOUT', finished_at=now() where id=j.id;
      update public.participants set status='error', error_code='TIMEOUT', countdown_ends_at=null,
        revision=revision+1, updated_at=now() where id=p.id;
    elsif j.status='queued' and j.not_before<=now() then
      update public.jobs set status='processing', lease_id=p_claim_id where id=j.id returning * into j;
      update public.participants set status='processing', countdown_ends_at=null, revision=revision+1, updated_at=now() where id=p.id;
      return to_jsonb(j) || jsonb_build_object('slot',p.slot,'session_id',p.session_id);
    end if;
  end loop;
  return null;
end; $$;
create unique index unique_job_lease on public.jobs(lease_id) where lease_id is not null;
revoke all on function public.nys_local_state(uuid),public.nys_td_claim(uuid,uuid) from public,anon,authenticated;
grant execute on function public.nys_local_state(uuid),public.nys_td_claim(uuid,uuid) to service_role;
commit;
