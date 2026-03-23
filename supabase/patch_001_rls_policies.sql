-- Si ya ejecutaste schema.sql antes de que existieran las políticas RLS,
-- corre SOLO este script en el SQL Editor (proyecto Supabase de Kenny Finanzas).

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
