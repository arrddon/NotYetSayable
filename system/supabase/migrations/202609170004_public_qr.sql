-- A read-only, login-free display for one installation QR. The display ID is
-- separate from the participant entry token and stays stable across resets.
begin;

create table if not exists nys_private.qr_displays (
  participant_id uuid primary key references public.participants(id) on delete cascade,
  display_id uuid not null unique default gen_random_uuid(),
  entry_token text not null
);
alter table nys_private.qr_displays enable row level security;
revoke all on nys_private.qr_displays from public, anon, authenticated;

create or replace function public.nys_publish_qr(p_id uuid, p_token text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare p public.participants; result uuid;
begin
  perform nys_private.assert_operator();
  if p_token is null or length(p_token) > 200 then raise exception 'INVALID_ENTRY'; end if;
  select * into p from public.participants where id = p_id for update;
  if p.id is null or p.owner_id is not null or not exists (
    select 1 from nys_private.entries e where e.participant_id = p_id
      and e.token_hash = sha256(convert_to(p_token, 'UTF8')) and e.expires_at > now()
  ) then raise exception 'INVALID_ENTRY'; end if;
  insert into nys_private.qr_displays(participant_id, entry_token) values(p_id, p_token)
    on conflict (participant_id) do update set entry_token = excluded.entry_token
    returning display_id into result;
  return result;
end; $$;

create or replace function public.nys_public_qr(p_display_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare token text;
begin
  select d.entry_token into token from nys_private.qr_displays d
    join public.participants p on p.id = d.participant_id
    join nys_private.entries e on e.participant_id = p.id
    where d.display_id = p_display_id and p.owner_id is null
      and e.token_hash = sha256(convert_to(d.entry_token, 'UTF8'))
      and e.expires_at > now();
  if token is null then return jsonb_build_object('available', false); end if;
  return jsonb_build_object('available', true, 'token', token);
end; $$;

create or replace function public.nys_display_links(p_session_id uuid) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
  perform nys_private.assert_operator();
  return (select coalesce(jsonb_object_agg(d.participant_id, d.display_id), '{}'::jsonb)
    from nys_private.qr_displays d join public.participants p on p.id=d.participant_id
    where p.session_id=p_session_id);
end; $$;
revoke all on function public.nys_display_links(uuid) from public, anon, authenticated;
grant execute on function public.nys_display_links(uuid) to authenticated;
revoke all on function public.nys_publish_qr(uuid, text) from public, anon, authenticated;
grant execute on function public.nys_publish_qr(uuid, text) to authenticated;
revoke all on function public.nys_public_qr(uuid) from public, anon, authenticated;
grant execute on function public.nys_public_qr(uuid) to anon, authenticated;
commit;
