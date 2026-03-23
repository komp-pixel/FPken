-- Usuarios (Orlando, Kenny, etc.) y quién registró cada movimiento.
-- Ejecutar en el SQL Editor del proyecto Supabase de Kenny Finanzas (después de schema.sql).

create table if not exists public.kf_users (
  id uuid primary key default gen_random_uuid(),
  username text not null unique,
  display_name text not null,
  password_hash text not null,
  is_admin boolean not null default false,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

do $$
begin
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'kf_transaction' and column_name = 'user_id'
  ) then
    alter table public.kf_transaction
      add column user_id uuid references public.kf_users (id) on delete set null;
  end if;
end $$;

create index if not exists kf_transaction_user_id_idx on public.kf_transaction (user_id);

alter table public.kf_users enable row level security;

drop policy if exists "kf_users_anon_all" on public.kf_users;
create policy "kf_users_anon_all"
  on public.kf_users for all to anon using (true) with check (true);

drop policy if exists "kf_users_auth_all" on public.kf_users;
create policy "kf_users_auth_all"
  on public.kf_users for all to authenticated using (true) with check (true);

comment on table public.kf_users is 'Usuarios de la app (login bcrypt). is_admin puede crear usuarios.';
