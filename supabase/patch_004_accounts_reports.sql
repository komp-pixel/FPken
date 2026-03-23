-- Cuentas: datos bancarios / crypto. Movimientos: comisiones y notas (Zelle→Binance, futuros, etc.)
-- Mayor precisión para USDT.

alter table public.kf_account
  add column if not exists institution_kind text,
  add column if not exists account_number text,
  add column if not exists routing_or_swift text,
  add column if not exists wallet_address text,
  add column if not exists zelle_email_or_phone text;

alter table public.kf_transaction
  add column if not exists fee_amount numeric(20, 8),
  add column if not exists fee_currency text,
  add column if not exists transaction_notes text,
  add column if not exists transfer_tag text;

alter table public.kf_transaction
  alter column amount type numeric(20, 8) using amount::numeric(20, 8);

alter table public.kf_account
  alter column opening_balance type numeric(20, 8) using opening_balance::numeric(20, 8);

comment on column public.kf_account.institution_kind is 'Banesco, Banca Amiga, Binance, BofA, Zelle, etc.';
comment on column public.kf_account.wallet_address is 'Wallet on-chain o UID exchange (sensible; no compartir el repo).';
comment on column public.kf_transaction.fee_amount is 'Comisión del movimiento (ej. puente Zelle→Binance).';
comment on column public.kf_transaction.transfer_tag is 'Etiqueta libre: Zelle→Binance, P2P, futuros, etc.';
