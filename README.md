# Kenny Finanzas

App Streamlit para registrar **ingresos** y **egresos** (por ejemplo cuenta BofA — Orlando Linares), con **saldo inicial** desde Excel y datos en **Supabase**.

**Repositorio:** [github.com/komp-pixel/FPken](https://github.com/komp-pixel/FPken)

## Separación del sistema de la empresa

- **Kenny Finanzas** usa **otro proyecto de Supabase** y **otro SQL** que el ERP Movi.
- En este repo solo aplica **`supabase/schema.sql`** (raíz del proyecto).
- **No** uses los `patch_*.sql`, `schema_erp_*.sql` ni demás SQL del ERP de la empresa en esta base: son del negocio y no aplican aquí.

## 1. Proyecto en Supabase (dedicado)

1. Creá un **proyecto nuevo** en [Supabase](https://supabase.com) solo para finanzas personales.
2. En **SQL Editor**, ejecutá **únicamente** `supabase/schema.sql` de este repositorio.
3. Si la base la creaste antes (sin políticas RLS para `anon`) y la app falla al leer datos, ejecutá también `supabase/patch_001_rls_policies.sql`. O bien usá la clave **service_role** en Streamlit (ignora RLS).

## 2. Secretos locales

1. Copiá `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml`.
2. Pegá `SUPABASE_URL` y `SUPABASE_KEY`. Para uso solo personal desde tu PC, suele usarse la clave **service_role** (no la expongas en repositorios públicos).

## 3. Entorno y ejecución

```bash
git clone https://github.com/komp-pixel/FPken.git
cd FPken
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Saldo

El **saldo mostrado** = saldo inicial (fecha de referencia) + ingresos − egresos registrados en la app. Ajustá el saldo inicial en la pestaña correspondiente si alineás con Excel.
