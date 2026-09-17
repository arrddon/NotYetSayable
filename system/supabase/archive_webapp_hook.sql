-- Apply only after archive_setup.sql and WebApp migrations 001 then 002.
-- A completed pin transaction archives all three current-generation responses.
begin;
create or replace function nys_archive.capture_completed() returns trigger
language plpgsql security definer set search_path = '' as $$
declare qs jsonb; sid text; rid text; payload jsonb;
begin
  if new.step <> 'complete' or new.pin is null or
     (old.step = 'complete' and old.pin is not distinct from new.pin) then return new; end if;
  select jsonb_object_agg('Q' || r.question,
      jsonb_build_object('completed_at',r.updated_at,'result',r.result,
        'job_id',j.id,'attempt',r.attempt,
        'image_path','captures/' || new.slot || '/' || j.id::text || '.png')
      order by r.question)
    into qs from public.responses r
    join public.jobs j on j.participant_id=r.participant_id
      and j.generation=r.generation and j.question=r.question
      and j.attempt=r.attempt and j.status='complete'
    where r.participant_id=new.id and r.generation=new.generation and r.question between 1 and 3;
  if (select count(*) from jsonb_object_keys(coalesce(qs,'{}'::jsonb))) <> 3 then
    raise exception 'ARCHIVE_INCOMPLETE_JOB_LINKS';
  end if;
  rid := 'current_' || replace(new.id::text,'-','_') || '_g' || new.generation;
  sid := new.session_id::text || ':' || new.slot || ':g' || new.generation;
  payload := jsonb_build_object('source_version','V04',
    'row',jsonb_build_object('row_id',rid,'session_id',sid,'unit_id',new.id,
      'status','live_appended','created_at',new.updated_at,
      'map',new.pin || jsonb_build_object('placement_mode','participant_pin')),
    'flow_version','csv-3q-map-v1','questions',qs,'pin',new.pin,'completed_at',now());
  insert into nys_archive.records(row_id,session_id,record)
    values(rid,sid,payload)
    on conflict(row_id) do update set record=excluded.record,updated_at=now()
    where nys_archive.records.session_id=excluded.session_id;
  return new;
end; $$;

drop trigger if exists archive_on_complete on public.participants;
create trigger archive_on_complete after update of step,pin on public.participants
  for each row execute function nys_archive.capture_completed();
revoke all on function nys_archive.capture_completed() from public, anon, authenticated;
commit;
