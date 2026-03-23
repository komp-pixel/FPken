-- Separa lógicamente: banco vs wallet crypto vs app de pagos (Zinly, Zelle…)

alter table public.kf_account add column if not exists account_kind text;

alter table public.kf_account drop constraint if exists kf_account_account_kind_check;

alter table public.kf_account add constraint kf_account_account_kind_check
  check (account_kind is null or account_kind in ('banco', 'wallet', 'app_pagos'));

comment on column public.kf_account.account_kind is
  'banco = cuenta bancaria; wallet = crypto/exchange; app_pagos = Zinly, Zelle, etc.';
