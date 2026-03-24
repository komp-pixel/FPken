# Kenny Finanzas en la nube (Streamlit Community Cloud)

Publicación gratuita en [share.streamlit.io](https://share.streamlit.io) con cuenta GitHub.

## Requisitos

1. **Este repositorio en GitHub** (`app.py` y `requirements.txt` en la raíz), p. ej. [github.com/komp-pixel/FPken](https://github.com/komp-pixel/FPken).
2. **Proyecto Supabase dedicado** a finanzas personales, con `supabase/schema.sql` y los parches que uses en el SQL Editor.
3. Clave **`service_role`** de Supabase solo en **Secrets** de Streamlit Cloud (nunca en el repo).

## Pasos en Streamlit Cloud

1. Entrá en [share.streamlit.io](https://share.streamlit.io) e iniciá sesión con GitHub.
2. **Create app** → elegí este repo y la rama (p. ej. `main`).
3. **Main file path:** `app.py`.
4. **App URL:** subdominio (`https://tu-nombre.streamlit.app`).

## Secrets (obligatorio)

En la app → **⚙ Settings** → **Secrets**, pegá un TOML con **exactamente** esta forma:

`SUPABASE_KEY` debe ser el JWT **service_role** (empieza con `eyJ`), de **Legacy API keys** en el panel de Supabase. No uses la clave nueva `sb_secret_...` con esta versión de la app.

```toml
[connections.supabase]
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...."

# Opcional: firma estable de la cookie de sesión (recomendado si rotás la API key)
# [auth]
# SESSION_SIGNING_KEY = "cadena-larga-aleatoria-solo-tuya"
```

- **URL y clave:** Supabase → **Project Settings** → **API** (Project URL + **service_role** en **Legacy API keys**, JWT `eyJ...`).
- Guardá y usá **Reboot** o **Redeploy** si la app ya existía.

## Python en Cloud

**`runtime.txt`** en la raíz fija la versión de Python para un build estable.

## Seguridad

- La **service_role** no respeta RLS: no la subas al repo ni la compartas. Si se filtró, rotala en Supabase.

## Actualizar

`git push` a la rama conectada o **Manage app → Reboot / Redeploy**.
