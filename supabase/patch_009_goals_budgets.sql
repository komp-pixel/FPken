-- Metas de ahorro mensual, presupuesto por rubro y objetivo de fondo de emergencia.
-- Ejecutar en Supabase SQL Editor después de los patches anteriores.

create table if not exists public.kf_savings_goal_month (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.kf_users (id) on delete cascade,
  ym text not null,
  currency text not null default 'USD',
  goal_mode text not null check (goal_mode in ('fixed_amount', 'percent_income')),
  target_numeric numeric(20, 8) not null check (target_numeric >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists kf_savings_goal_month_uk
  on public.kf_savings_goal_month (user_id, ym, currency);

create table if not exists public.kf_category_budget_month (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.kf_users (id) on delete cascade,
  ym text not null,
  currency text not null default 'USD',
  category text not null,
  budget_limit numeric(20, 8) not null check (budget_limit >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists kf_category_budget_month_uk
  on public.kf_category_budget_month (user_id, ym, currency, category);

create table if not exists public.kf_emergency_fund_target (
  user_id uuid primary key references public.kf_users (id) on delete cascade,
  account_id uuid references public.kf_account (id) on delete set null,
  target_amount numeric(20, 8),
  updated_at timestamptz not null default now()
);

alter table public.kf_savings_goal_month enable row level security;
alter table public.kf_category_budget_month enable row level security;
alter table public.kf_emergency_fund_target enable row level security;

drop policy if exists "kf_savings_goal_anon_all" on public.kf_savings_goal_month;
create policy "kf_savings_goal_anon_all"
  on public.kf_savings_goal_month for all to anon using (true) with check (true);
drop policy if exists "kf_savings_goal_auth_all" on public.kf_savings_goal_month;
create policy "kf_savings_goal_auth_all"
  on public.kf_savings_goal_month for all to authenticated using (true) with check (true);

drop policy if exists "kf_category_budget_anon_all" on public.kf_category_budget_month;
create policy "kf_category_budget_anon_all"
  on public.kf_category_budget_month for all to anon using (true) with check (true);
drop policy if exists "kf_category_budget_auth_all" on public.kf_category_budget_month;
create policy "kf_category_budget_auth_all"
  on public.kf_category_budget_month for all to authenticated using (true) with check (true);

drop policy if exists "kf_emergency_fund_anon_all" on public.kf_emergency_fund_target;
create policy "kf_emergency_fund_anon_all"
  on public.kf_emergency_fund_target for all to anon using (true) with check (true);
drop policy if exists "kf_emergency_fund_auth_all" on public.kf_emergency_fund_target;
create policy "kf_emergency_fund_auth_all"
  on public.kf_emergency_fund_target for all to authenticated using (true) with check (true);

comment on table public.kf_savings_goal_month is 'Meta de ahorro del mes: monto fijo o % sobre ingresos (por usuario y moneda de la cuenta activa).';
comment on table public.kf_category_budget_month is 'Tope de gasto por rubro y mes.';
comment on table public.kf_emergency_fund_target is 'Cuenta elegida para fondo de emergencia y saldo objetivo.';
