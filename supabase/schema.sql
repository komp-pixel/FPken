-- =============================================================================
-- Kenny Finanzas — SOLO finanzas personales (Orlando / BofA, etc.)
-- =============================================================================
-- Este archivo es INDEPENDIENTE del ERP de la empresa (Movi / schema_erp / patch_0xx).
-- Creá un proyecto Supabase NUEVO para Kenny Finanzas y ejecutá ÚNICAMENTE este script.
-- NO ejecutes aquí los patches del repo `supabase/` de la empresa: son otra base de datos.
-- =============================================================================
-- Supabase → SQL Editor → New query → pegar → Run.

create extension if not exists "pgcrypto";

-- Cuenta (ej. BofA Orlando Linares)
create table if not exists public.kf_account (
  id uuid primary key default gen_random_uuid(),
  label text not null,
  bank_name text,
  holder_name text,
  currency text not null default 'USD',
  opening_balance numeric(14, 2) not null default 0,
  opening_balance_date date not null default (current_date),
  notes text,
  created_at timestamptz not null default now()
);

-- Usuarios de la app (Orlando, Kenny, …)
create table if not exists public.kf_users (
  id uuid primary key default gen_random_uuid(),
  username text not null unique,
  display_name text not null,
  password_hash text not null,
  is_admin boolean not null default false,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

-- Movimientos
create table if not exists public.kf_transaction (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.kf_account (id) on delete cascade,
  user_id uuid references public.kf_users (id) on delete set null,
  tx_type text not null check (tx_type in ('ingreso', 'egreso')),
  amount numeric(14, 2) not null check (amount > 0),
  tx_date date not null,
  description text not null default '',
  category text,
  business text,
  created_at timestamptz not null default now()
);

create index if not exists kf_transaction_account_date_idx
  on public.kf_transaction (account_id, tx_date desc);

create index if not exists kf_transaction_user_id_idx on public.kf_transaction (user_id);

alter table public.kf_account enable row level security;
alter table public.kf_users enable row level security;
alter table public.kf_transaction enable row level security;

-- Con la clave **anon** (PostgREST), sin políticas no se ve ninguna fila → error en la app.
-- La clave **service_role** ignora RLS; igual estas políticas no molestan.
-- Ojo: la clave anon no debe exponerse en frontends públicos; en Streamlit Cloud (solo servidor) es aceptable.
drop policy if exists "kf_account_anon_all" on public.kf_account;
create policy "kf_account_anon_all"
  on public.kf_account for all to anon using (true) with check (true);

drop policy if exists "kf_transaction_anon_all" on public.kf_transaction;
create policy "kf_transaction_anon_all"
  on public.kf_transaction for all to anon using (true) with check (true);

drop policy if exists "kf_account_auth_all" on public.kf_account;
create policy "kf_account_auth_all"
  on public.kf_account for all to authenticated using (true) with check (true);

drop policy if exists "kf_transaction_auth_all" on public.kf_transaction;
create policy "kf_transaction_auth_all"
  on public.kf_transaction for all to authenticated using (true) with check (true);

drop policy if exists "kf_users_anon_all" on public.kf_users;
create policy "kf_users_anon_all"
  on public.kf_users for all to anon using (true) with check (true);

drop policy if exists "kf_users_auth_all" on public.kf_users;
create policy "kf_users_auth_all"
  on public.kf_users for all to authenticated using (true) with check (true);

comment on table public.kf_account is 'Cuentas bancarias / efectivo (saldo inicial desde Excel u otro origen).';
comment on table public.kf_users is 'Usuarios de la app (login bcrypt). is_admin puede crear usuarios.';
comment on table public.kf_transaction is 'Ingresos y egresos; user_id = quién lo registró.';
