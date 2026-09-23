-- DESIGN ONLY. Do not apply to production from the VERA ARK v0.1 runtime.
-- Append-only operational events are observations, not controller authority or canonical memory.

create table if not exists public.vera_ark_operational_events (
    event_id uuid primary key,
    schema_version text not null check (schema_version = 'VERA_ARK_OPERATIONAL_EVENT_V1'),
    sequence bigint not null check (sequence > 0),
    record_time timestamptz not null,
    kind text not null check (length(kind) between 1 and 100),
    payload jsonb not null,
    inserted_at timestamptz not null default clock_timestamp(),
    unique (event_id, sequence)
);

alter table public.vera_ark_operational_events enable row level security;
alter table public.vera_ark_operational_events force row level security;

create or replace function public.vera_ark_reject_operational_event_mutation()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
    raise exception 'VERA ARK operational events are append-only';
end;
$$;

drop trigger if exists vera_ark_operational_events_no_update_delete
on public.vera_ark_operational_events;

create trigger vera_ark_operational_events_no_update_delete
before update or delete on public.vera_ark_operational_events
for each row execute function public.vera_ark_reject_operational_event_mutation();

revoke all on public.vera_ark_operational_events from public, anon, authenticated;

comment on table public.vera_ark_operational_events is
'Optional append-only mirror for VERA ARK local operational events. Rows do not authorize actions, prove delivery, or constitute canonical memory.';
