-- Not used: kept for a later multi-clinic version.
-- Legal aid agent: database setup for Supabase (Postgres).
-- Paste the whole file into Supabase > SQL Editor > New query, and click Run. Safe to run once.
--
-- Rules the DATABASE itself enforces (not only the app):
--   * Each organisation sees only its own cases, audit records and problem reports.
--   * Only verified organisations can create cases.
--   * Only a supervisor of the case's organisation can approve or send back a draft. They can
--     never approve a draft they made themselves or were the last to resend.
--   * Every approval records who approved (their name) and when.
--   * Case text is refused if it contains a phone number, Aadhaar number or email address.
--   * No names of people seeking help, no pasted notes: the app never sends them, and the
--     tables have no place for them.
-- Roles: member (volunteer, makes drafts), supervisor, organisation admin, platform admin.

-- ---------- helpers ----------

create or replace function public.has_personal_numbers(t text)
returns boolean language sql immutable as $$
  select coalesce(t, '') ~ '(^|[^[:alnum:]])(\+?91[ -]?|0)?[6-9][0-9]{4}[ -]?[0-9]{5}([^[:alnum:]]|$)'
      or coalesce(t, '') ~ '(^|[^[:alnum:]])[0-9]{4}[ -]?[0-9]{4}[ -]?[0-9]{4}([^[:alnum:]]|$)'
      or coalesce(t, '') ~ '[[:alnum:]._%+-]+@[[:alnum:]-]+(\.[[:alnum:]-]+)+'
$$;

-- ---------- tables ----------

-- One row per signed-in person (volunteers, supervisors, admins). Staff names are fine here.
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text not null default '' check (char_length(full_name) <= 100),
  created_at timestamptz not null default now()
);

-- Platform admins (Arushi). Added only from the SQL Editor, never from the app.
create table public.platform_admins (
  user_id uuid primary key references auth.users (id) on delete cascade
);

create table public.organisations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 2 and 150),
  kind text not null check (kind in ('Village legal aid clinic', 'College legal aid clinic', 'NGO', 'Other')),
  state text not null default '',
  district text not null default '',
  verified boolean not null default false,
  is_practice boolean not null default false,
  created_by uuid references auth.users (id) default auth.uid(),
  created_at timestamptz not null default now()
);

-- Every member can make drafts (volunteer). The organisation admin decides who is a supervisor.
create table public.memberships (
  org_id uuid not null references public.organisations (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  is_supervisor boolean not null default false,
  is_org_admin boolean not null default false,
  added_by uuid references auth.users (id) default auth.uid(),
  added_at timestamptz not null default now(),
  primary key (org_id, user_id)
);

-- An organisation admin invites someone by email; it becomes a membership when they sign in.
create table public.invitations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organisations (id) on delete cascade,
  email text not null check (email = lower(email) and position('@' in email) > 1),
  is_supervisor boolean not null default false,
  is_org_admin boolean not null default false,
  invited_by uuid references auth.users (id) default auth.uid(),
  created_at timestamptz not null default now(),
  accepted_at timestamptz,
  unique (org_id, email)
);

create table public.cases (
  id text primary key check (id ~ '^U-[0-9]{8}-[a-z][0-9a-z]{3}$'),
  org_id uuid not null references public.organisations (id),
  case_type text not null default 'Undertrial',
  status text not null check (status in ('waiting', 'sent back', 'approved', 'submitted')),
  facts jsonb not null,                       -- checked facts only: dates, sections, yes/no answers
  draft text not null,                        -- the draft as sent (or as resent)
  ai_model text,                              -- null = no AI was used
  ai_audit jsonb not null default '{}',       -- what the AI extracted and what the volunteer changed
  reason text not null default '',            -- supervisor's reason when sent back
  created_by uuid not null references auth.users (id) default auth.uid(),
  created_at timestamptz not null default now(),
  last_resent_by uuid references auth.users (id),   -- who last fixed and resent it (cannot approve it)
  approved_by uuid references auth.users (id),
  approved_by_name text,
  approved_at timestamptz,
  approved_draft text,
  case_file text,
  next_step text not null default '',
  next_step_due date,
  submitted_on date,
  check (not public.has_personal_numbers(facts::text)),
  check (not public.has_personal_numbers(draft)),
  check (not public.has_personal_numbers(approved_draft)),
  check (not public.has_personal_numbers(case_file)),
  check (not public.has_personal_numbers(reason)),
  check (not public.has_personal_numbers(ai_audit::text))
);
create index cases_org_idx on public.cases (org_id, status);

create table public.audit_events (
  id bigint generated always as identity primary key,
  case_id text not null references public.cases (id) on delete cascade,
  org_id uuid not null references public.organisations (id),
  event_at timestamptz not null default now(),
  event text not null,
  by_user uuid references auth.users (id),
  by_name text not null default '',
  by_role text not null default '',
  details text not null default '' check (not public.has_personal_numbers(details))
);
create index audit_case_idx on public.audit_events (case_id);

create table public.problems (
  id bigint generated always as identity primary key,
  org_id uuid references public.organisations (id),
  case_id text,
  reported_at timestamptz not null default now(),
  place text not null,
  message text not null check (char_length(message) between 1 and 500 and not public.has_personal_numbers(message)),
  reported_by uuid not null references auth.users (id) default auth.uid()
);

-- ---------- who is who (used by the rules below) ----------

create or replace function public.is_platform_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from platform_admins where user_id = auth.uid())
$$;

create or replace function public.is_member(org uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from memberships where org_id = org and user_id = auth.uid())
$$;

create or replace function public.is_supervisor(org uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from memberships where org_id = org and user_id = auth.uid() and is_supervisor)
$$;

create or replace function public.is_org_admin(org uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from memberships where org_id = org and user_id = auth.uid() and is_org_admin)
$$;

create or replace function public.my_name() returns text
language sql stable security definer set search_path = public as $$
  select coalesce(nullif(full_name, ''), 'name not set') from profiles where id = auth.uid()
$$;

-- A profile is created for every new account, with the name given at sign-up.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into profiles (id, full_name)
  values (new.id, left(coalesce(new.raw_user_meta_data ->> 'full_name', ''), 100));
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- row level security: who can see and change what ----------

alter table public.profiles enable row level security;
alter table public.platform_admins enable row level security;
alter table public.organisations enable row level security;
alter table public.memberships enable row level security;
alter table public.invitations enable row level security;
alter table public.cases enable row level security;
alter table public.audit_events enable row level security;
alter table public.problems enable row level security;

-- Profiles: yourself, people in your organisations, or everyone for the platform admin.
create policy profiles_select on public.profiles for select to authenticated using (
  id = auth.uid() or public.is_platform_admin()
  or exists (select 1 from memberships a join memberships b on a.org_id = b.org_id
             where a.user_id = auth.uid() and b.user_id = profiles.id));
create policy profiles_update_own on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

create policy platform_admins_select on public.platform_admins for select to authenticated
  using (user_id = auth.uid());

-- Organisations: members see their own; the platform admin sees, creates and verifies all.
create policy orgs_select on public.organisations for select to authenticated
  using (public.is_member(id) or public.is_platform_admin());
create policy orgs_insert on public.organisations for insert to authenticated
  with check (public.is_platform_admin());
create policy orgs_update on public.organisations for update to authenticated
  using (public.is_platform_admin()) with check (public.is_platform_admin());

-- Memberships: members see their organisation's list; org admins (and the platform admin) manage it.
create policy members_select on public.memberships for select to authenticated
  using (public.is_member(org_id) or public.is_platform_admin());
create policy members_insert on public.memberships for insert to authenticated
  with check (public.is_org_admin(org_id) or public.is_platform_admin());
create policy members_update on public.memberships for update to authenticated
  using (public.is_org_admin(org_id) or public.is_platform_admin())
  with check (public.is_org_admin(org_id) or public.is_platform_admin());
create policy members_delete on public.memberships for delete to authenticated
  using (public.is_org_admin(org_id) or public.is_platform_admin());

create policy invites_select on public.invitations for select to authenticated
  using (public.is_org_admin(org_id) or public.is_platform_admin());
create policy invites_insert on public.invitations for insert to authenticated
  with check (public.is_org_admin(org_id) or public.is_platform_admin());
create policy invites_delete on public.invitations for delete to authenticated
  using (public.is_org_admin(org_id) or public.is_platform_admin());

-- Cases and audit records: members of the organisation can read. All changes go through the
-- functions below, which check the rules (there are no insert/update policies on purpose).
create policy cases_select on public.cases for select to authenticated using (public.is_member(org_id));
create policy audit_select on public.audit_events for select to authenticated using (public.is_member(org_id));

-- Problems: members report for their organisation; members see their organisation's reports.
create policy problems_select on public.problems for select to authenticated
  using (public.is_member(org_id) or public.is_platform_admin());
create policy problems_insert on public.problems for insert to authenticated
  with check (reported_by = auth.uid() and (org_id is null or public.is_member(org_id)));

-- ---------- actions (each checks the rules, then writes an audit event) ----------

create or replace function public.accept_invitations() returns integer
language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  insert into memberships (org_id, user_id, is_supervisor, is_org_admin, added_by)
  select i.org_id, auth.uid(), i.is_supervisor, i.is_org_admin, i.invited_by
  from invitations i
  where i.email = lower(auth.jwt() ->> 'email') and i.accepted_at is null
  on conflict (org_id, user_id) do nothing;
  get diagnostics n = row_count;
  update invitations set accepted_at = now()
  where email = lower(auth.jwt() ->> 'email') and accepted_at is null;
  return n;
end $$;

create or replace function public.submit_case(p_id text, p_org uuid, p_case_type text, p_facts jsonb,
  p_draft text, p_ai_model text, p_ai_audit jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not is_member(p_org) then raise exception 'You are not a member of this organisation.'; end if;
  if not exists (select 1 from organisations where id = p_org and verified) then
    raise exception 'This organisation has not been verified yet.';
  end if;
  insert into cases (id, org_id, case_type, status, facts, draft, ai_model, ai_audit, created_by)
  values (p_id, p_org, p_case_type, 'waiting', p_facts, p_draft, p_ai_model, coalesce(p_ai_audit, '{}'), auth.uid());
  insert into audit_events (case_id, org_id, event, by_user, by_name, by_role)
  values (p_id, p_org, 'sent to supervisor', auth.uid(), my_name(), 'volunteer');
end $$;

create or replace function public.reject_case(p_id text, p_reason text) returns void
language plpgsql security definer set search_path = public as $$
declare c cases;
begin
  select * into c from cases where id = p_id for update;
  if c.id is null or not is_supervisor(c.org_id) then raise exception 'Only a supervisor of this organisation can do this.'; end if;
  if c.created_by = auth.uid() then raise exception 'A supervisor cannot review a draft they made themselves.'; end if;
  if c.status <> 'waiting' then raise exception 'Only waiting drafts can be sent back.'; end if;
  if coalesce(trim(p_reason), '') = '' then raise exception 'Please give a reason for sending it back.'; end if;
  update cases set status = 'sent back', reason = trim(p_reason) where id = p_id;
  insert into audit_events (case_id, org_id, event, by_user, by_name, by_role, details)
  values (p_id, c.org_id, 'sent back', auth.uid(), my_name(), 'supervisor', 'reason: ' || trim(p_reason));
end $$;

create or replace function public.resend_case(p_id text, p_draft text) returns void
language plpgsql security definer set search_path = public as $$
declare c cases;
begin
  select * into c from cases where id = p_id for update;
  if c.id is null or not is_member(c.org_id) then raise exception 'You are not a member of this organisation.'; end if;
  if c.status <> 'sent back' then raise exception 'Only drafts that were sent back can be fixed and resent.'; end if;
  update cases set status = 'waiting', draft = p_draft, reason = '', last_resent_by = auth.uid() where id = p_id;
  insert into audit_events (case_id, org_id, event, by_user, by_name, by_role, details)
  values (p_id, c.org_id, 'fixed and resent', auth.uid(), my_name(), 'volunteer', 'earlier reason: ' || c.reason);
end $$;

create or replace function public.approve_case(p_id text, p_final_draft text, p_case_file text, p_edited boolean,
  p_next_step text, p_next_step_due date) returns void
language plpgsql security definer set search_path = public as $$
declare c cases;
begin
  select * into c from cases where id = p_id for update;
  if c.id is null or not is_supervisor(c.org_id) then raise exception 'Only a supervisor of this organisation can approve.'; end if;
  if c.created_by = auth.uid() then raise exception 'A supervisor cannot approve a draft they made themselves.'; end if;
  if c.last_resent_by = auth.uid() then raise exception 'A supervisor cannot approve a draft they resent themselves.'; end if;
  if c.status <> 'waiting' then raise exception 'Only waiting drafts can be approved.'; end if;
  update cases set status = 'approved', approved_by = auth.uid(), approved_by_name = my_name(),
    approved_at = now(), approved_draft = p_final_draft, case_file = p_case_file,
    next_step = coalesce(p_next_step, ''), next_step_due = p_next_step_due
  where id = p_id;
  insert into audit_events (case_id, org_id, event, by_user, by_name, by_role, details)
  values (p_id, c.org_id, 'approved', auth.uid(), my_name(), 'supervisor',
          case when p_edited then 'edited by the supervisor before approval' else 'approved as sent' end);
end $$;

create or replace function public.mark_submitted(p_id text, p_on date) returns void
language plpgsql security definer set search_path = public as $$
declare c cases;
begin
  select * into c from cases where id = p_id for update;
  if c.id is null or not is_member(c.org_id) then raise exception 'You are not a member of this organisation.'; end if;
  if c.status <> 'approved' then raise exception 'Only approved drafts can be marked as submitted.'; end if;
  update cases set status = 'submitted', submitted_on = p_on where id = p_id;
  insert into audit_events (case_id, org_id, event, by_user, by_name, by_role, details)
  values (p_id, c.org_id, 'marked as submitted', auth.uid(), my_name(), 'volunteer', 'submitted on ' || p_on);
end $$;

create or replace function public.set_next_step(p_id text, p_step text, p_due date) returns void
language plpgsql security definer set search_path = public as $$
declare c cases;
begin
  select * into c from cases where id = p_id for update;
  if c.id is null or not is_member(c.org_id) then raise exception 'You are not a member of this organisation.'; end if;
  update cases set next_step = coalesce(p_step, ''), next_step_due = p_due where id = p_id;
  insert into audit_events (case_id, org_id, event, by_user, by_name, by_role, details)
  values (p_id, c.org_id, 'next step changed', auth.uid(), my_name(), 'member',
          coalesce(p_step, '') || coalesce(' (due ' || p_due || ')', ''));
end $$;

-- Only signed-in users may call the actions; never anonymous visitors.
revoke all on function public.accept_invitations(), public.submit_case(text, uuid, text, jsonb, text, text, jsonb),
  public.reject_case(text, text), public.resend_case(text, text),
  public.approve_case(text, text, text, boolean, text, date), public.mark_submitted(text, date),
  public.set_next_step(text, text, date) from public, anon;
grant execute on function public.accept_invitations(), public.submit_case(text, uuid, text, jsonb, text, text, jsonb),
  public.reject_case(text, text), public.resend_case(text, text),
  public.approve_case(text, text, text, boolean, text, date), public.mark_submitted(text, date),
  public.set_next_step(text, text, date) to authenticated;

-- ---------- table access ----------
-- New tables are not exposed automatically in this project, so access is granted here, to
-- signed-in users only (role "authenticated"); nothing is granted to anonymous visitors.
-- Row level security (above) still decides WHICH rows each person can see or change.
-- cases and audit_events get no insert/update/delete: they change only through the functions.

grant usage on schema public to authenticated;

grant select on public.profiles, public.platform_admins, public.organisations, public.memberships,
  public.invitations, public.cases, public.audit_events, public.problems to authenticated;
grant update (full_name) on public.profiles to authenticated;
grant insert, update on public.organisations to authenticated;
grant insert, update, delete on public.memberships to authenticated;
grant insert, delete on public.invitations to authenticated;
grant insert on public.problems to authenticated;

-- problems.id is numbered automatically; inserting a problem needs use of that numbering.
do $$ begin
  execute format('grant usage on sequence %s to authenticated',
                 pg_get_serial_sequence('public.problems', 'id'));
end $$;

-- Helper functions: signed-in users only (the row rules use them). The sign-up trigger
-- function is never called directly.
revoke all on function public.has_personal_numbers(text), public.is_platform_admin(), public.is_member(uuid),
  public.is_supervisor(uuid), public.is_org_admin(uuid), public.my_name() from public, anon;
grant execute on function public.has_personal_numbers(text), public.is_platform_admin(), public.is_member(uuid),
  public.is_supervisor(uuid), public.is_org_admin(uuid), public.my_name() to authenticated;
revoke all on function public.handle_new_user() from public, anon, authenticated;
