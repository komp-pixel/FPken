-- Multiusuario (Fase 1): cada cuenta pertenece a un usuario de kf_users.
-- La app filtra por owner_user_id para que cada persona vea solo sus datos.

alter table public.kf_account
  add column if not exists owner_user_id uuid references public.kf_users (id) on delete set null;

-- Backfill seguro: si hay cuentas viejas sin owner, se asignan al primer admin activo;
-- si no existe admin, al primer usuario activo.
with _candidate as (
  select id
  from public.kf_users
  where active is true
  order by is_admin desc, created_at asc
  limit 1
)
update public.kf_account a
set owner_user_id = c.id
from _candidate c
where a.owner_user_id is null;

create index if not exists kf_account_owner_user_idx
  on public.kf_account (owner_user_id);

comment on column public.kf_account.owner_user_id is
  'Propietario de la cuenta dentro de la app Kenny Finanzas (aislamiento multiusuario).';
