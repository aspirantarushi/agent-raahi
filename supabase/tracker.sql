-- Agent Raahi: the clinic's shared case tracker (one institution).
-- Paste this whole file into Supabase > SQL Editor > New query, then press Run. Safe to run again.
--
-- One simple table holds the app's records (cases, drafts, timelines, visit logs inside the case
-- record, audit records, problem reports, evaluation sessions, the impact log).
-- Only the app's server uses it, with the secret key kept in the host's secret settings.
-- Row level security is ON and there are NO policies, and the public roles have no rights at all:
-- nothing can be read or written from outside the app (not with the publishable key, not signed in).
--
-- supabase/schema.sql (organisations, accounts) is kept for later and is NOT used now.

create table if not exists public.raahi_records (
  kind        text        not null check (kind in ('pending', 'drafts', 'cases', 'audit', 'timelines', 'tracker',
                                                   'eval_sessions', 'problems', 'impact', 'research',
                                                   'knowledge_added', 'practice_snapshot')),
  id          text        not null check (id ~ '^[A-Za-z0-9_.-]{1,80}$'),
  body        text        not null check (length(body) <= 200000),
  updated_at  timestamptz not null default now(),
  primary key (kind, id)
);

-- A second safety line (the app already removes these before saving):
-- no 10-digit Indian mobile numbers, no 12-digit Aadhaar-style numbers, no email addresses.
alter table public.raahi_records drop constraint if exists no_personal_numbers;
alter table public.raahi_records add constraint no_personal_numbers check (
  body !~ '(^|[^0-9])(\+?91[ -]?)?[6-9][0-9]{4}[ -]?[0-9]{5}([^0-9]|$)'
  and body !~ '(^|[^0-9])[2-9][0-9]{3} ?[0-9]{4} ?[0-9]{4}([^0-9]|$)'
  and body !~* '[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}'
);

alter table public.raahi_records enable row level security;
alter table public.raahi_records force row level security;
revoke all on public.raahi_records from anon, authenticated, public;
-- The app's server (secret key = service_role) is the only one allowed in. Needed because this
-- project has "Automatically expose new tables" switched off.
grant select, insert, update, delete on public.raahi_records to service_role;
-- (no policies on purpose: with row level security on, nobody but the server's secret key gets in)

-- Tables made earlier: allow the newer kinds of record ("Research this issue", and the Practice Clinic's
-- snapshot for "Reset the Practice Clinic"). Safe to run again.
alter table public.raahi_records drop constraint if exists raahi_records_kind_check;
alter table public.raahi_records add constraint raahi_records_kind_check check (kind in ('pending', 'drafts',
  'cases', 'audit', 'timelines', 'tracker', 'eval_sessions', 'problems', 'impact', 'research', 'knowledge_added',
  'practice_snapshot'));

create index if not exists raahi_records_kind on public.raahi_records (kind, id);
