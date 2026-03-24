-- Enlace entre cuentas en un mismo movimiento lógico (traspaso / P2P interno).
-- counterpart_account_id = la otra cuenta (de dónde vino o a dónde fue el dinero).
-- transfer_group_id = mismo UUID en el par egreso + ingreso de un traspaso.

alter table public.kf_transaction
  add column if not exists counterpart_account_id uuid references public.kf_account (id) on delete set null,
  add column if not exists transfer_group_id uuid;

create index if not exists kf_transaction_transfer_group_idx
  on public.kf_transaction (transfer_group_id)
  where transfer_group_id is not null;

comment on column public.kf_transaction.counterpart_account_id is 'Otra cuenta involucrada (ej. traspaso Zelle → Binance).';
comment on column public.kf_transaction.transfer_group_id is 'Agrupa el par de filas ingreso/egreso de un mismo traspaso.';
