-- Point.ai Database Schema v2
-- Run this in Supabase SQL Editor
-- Structure: User → Projects → Plans (each plan = one floor plan with 2D + 3D state)

-- ============================================================
-- Drop old schema if exists (v1 migration)
-- ============================================================

drop trigger if exists projects_updated_at on projects;
drop trigger if exists plans_updated_at on plans;
drop function if exists update_updated_at();
drop table if exists plans;
drop table if exists projects;

-- ============================================================
-- Projects: top-level container (e.g., "Casa Martinez")
-- ============================================================

create table projects (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references auth.users(id) on delete cascade not null,
  name        text not null default 'Untitled Project',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index idx_projects_user on projects(user_id, updated_at desc);

-- ============================================================
-- Plans: each floor plan within a project
-- ============================================================

create table plans (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid references projects(id) on delete cascade not null,
  name            text not null default 'Untitled Plan',

  -- Floor plan image (base64 stored directly or Storage path)
  image_data      text,

  -- Backend parse result
  structure       jsonb,

  -- 2D Editor state
  annotations_2d  jsonb not null default '[]'::jsonb,

  -- 3D Editor state
  placed_items_3d jsonb not null default '[]'::jsonb,
  floor_material  text not null default 'hardwood',
  wall_material   text not null default 'white-paint',

  -- Metadata
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index idx_plans_project on plans(project_id, updated_at desc);

-- ============================================================
-- Row Level Security
-- ============================================================

alter table projects enable row level security;
alter table plans enable row level security;

-- Projects: user sees own
create policy "Users read own projects" on projects for select using (auth.uid() = user_id);
create policy "Users insert own projects" on projects for insert with check (auth.uid() = user_id);
create policy "Users update own projects" on projects for update using (auth.uid() = user_id);
create policy "Users delete own projects" on projects for delete using (auth.uid() = user_id);

-- Plans: user sees plans in own projects
create policy "Users read own plans" on plans for select
  using (project_id in (select id from projects where user_id = auth.uid()));
create policy "Users insert own plans" on plans for insert
  with check (project_id in (select id from projects where user_id = auth.uid()));
create policy "Users update own plans" on plans for update
  using (project_id in (select id from projects where user_id = auth.uid()));
create policy "Users delete own plans" on plans for delete
  using (project_id in (select id from projects where user_id = auth.uid()));

-- ============================================================
-- Auto-update updated_at
-- ============================================================

create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger projects_updated_at before update on projects
  for each row execute function update_updated_at();

create trigger plans_updated_at before update on plans
  for each row execute function update_updated_at();
