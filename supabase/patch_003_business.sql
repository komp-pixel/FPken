-- Origen del ingreso (Movi Motors, Cuentas Delivery, Asistente Zemog, etc.)
alter table public.kf_transaction
  add column if not exists business text;

comment on column public.kf_transaction.business is 'Negocio fuente del ingreso. NULL en egresos o sin clasificar.';
comment on column public.kf_transaction.category is 'Rubro del egreso (Casa, Carro, Hijos, …). NULL en ingresos.';
