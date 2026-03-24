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
3. Parches según tu caso: `patch_001` … `patch_004_accounts_reports.sql` (datos de cuenta, comisiones). `patch_005_account_kind.sql` clasifica **banco / wallet / app** (Zinly aparte de Binance y del banco). `patch_007_transaction_counterpart.sql` habilita **traspasos entre cuentas** y la columna **cuenta relacionada** en Movimientos.
4. La app pide **primer administrador** la primera vez; después puede crear usuarios (Orlando, Kenny, etc.). **Importar Excel**: pestaña Movimientos → Importar (mapeo de columnas).

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

En PowerShell, si falla `Activate.ps1`, usá `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` y `.\.venv\Scripts\python.exe -m streamlit run app.py`.

## 4. Ejecutar en la nube (Streamlit Cloud)

Guía paso a paso: **[DEPLOY_STREAMLIT_CLOUD.md](DEPLOY_STREAMLIT_CLOUD.md)**. Resumen: conectás este repo en [share.streamlit.io](https://share.streamlit.io), **Main file** `app.py`, y en **Settings → Secrets** pegás el mismo TOML que en `.streamlit/secrets.toml` (`[connections.supabase]` con URL y **service_role**).

## Saldo

El **saldo mostrado** = saldo inicial (fecha de referencia) + ingresos − egresos registrados en la app. Ajustá el saldo inicial en la pestaña correspondiente si alineás con Excel.
