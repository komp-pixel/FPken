"""
Kenny Finanzas — ingresos/egresos compartidos, login, tablero e importación Excel.
Supabase: schema.sql + patch_002 si la base ya existía sin usuarios.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client

from kf_auth import current_user, gate_auth, logout
from kf_dashboard import render_finance_dashboard


def get_supabase() -> Client:
    from supabase import create_client

    u = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
    k = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]
    return create_client(str(u), str(k))


def _dec(x: Any) -> Decimal:
    if x is None:
        return Decimal("0")
    return Decimal(str(x))


def load_accounts(sb: Client) -> list[dict[str, Any]]:
    r = sb.table("kf_account").select("*").order("created_at").execute()
    return list(r.data or [])


def load_transactions(sb: Client, account_id: str) -> list[dict[str, Any]]:
    r = (
        sb.table("kf_transaction")
        .select("*")
        .eq("account_id", account_id)
        .order("tx_date", desc=True)
        .order("created_at", desc=True)
        .limit(5000)
        .execute()
    )
    return list(r.data or [])


def load_user_map(sb: Client) -> dict[str, str]:
    r = sb.table("kf_users").select("id,display_name").execute()
    return {str(x["id"]): str(x.get("display_name") or "") for x in (r.data or [])}


def compute_balance(account: dict[str, Any], txs: list[dict[str, Any]]) -> Decimal:
    base = _dec(account.get("opening_balance"))
    for t in txs:
        amt = _dec(t.get("amount"))
        if t.get("tx_type") == "ingreso":
            base += amt
        else:
            base -= amt
    return base


def page_users_admin(sb: Client) -> None:
    st.subheader("Usuarios")
    st.caption("Solo administradores. Orlando y Kenny pueden tener cada uno su usuario.")
    with st.form("nu"):
        dn = st.text_input("Nombre para mostrar")
        un = st.text_input("Usuario (sin espacios)")
        adm = st.checkbox("Es administrador (puede crear más usuarios)", value=False)
        p1 = st.text_input("Contraseña", type="password")
        p2 = st.text_input("Repetir contraseña", type="password")
        if st.form_submit_button("Crear usuario"):
            if not dn.strip() or not un.strip():
                st.error("Completá nombre y usuario.")
            elif len(p1) < 8:
                st.error("Mínimo 8 caracteres en la contraseña.")
            elif p1 != p2:
                st.error("Las contraseñas no coinciden.")
            else:
                from kf_auth import _hash_password

                try:
                    sb.table("kf_users").insert(
                        {
                            "username": un.strip().lower(),
                            "display_name": dn.strip(),
                            "password_hash": _hash_password(p1),
                            "is_admin": adm,
                            "active": True,
                        }
                    ).execute()
                    st.success(f"Usuario «{un.strip().lower()}» creado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo crear (¿usuario duplicado?): {e}")


def import_excel_section(
    sb: Client, account_id: str, user_id: str, display_name: str
) -> None:
    st.subheader("Importar desde Excel")
    st.write(
        "Subí un `.xlsx` con tus columnas. Mapeá **fecha**, **monto** y **descripción**. "
        "Si tenés columna **tipo** (ingreso/egreso), usala; si no, los montos **negativos** serán egresos."
    )
    f = st.file_uploader("Archivo Excel (.xlsx)", type=["xlsx"])
    if not f:
        return
    try:
        raw = pd.read_excel(f, engine="openpyxl")
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        return
    if raw.empty:
        st.warning("El archivo está vacío.")
        return
    cols = list(raw.columns.astype(str))
    c1, c2, c3 = st.columns(3)
    with c1:
        col_fecha = st.selectbox("Columna fecha", ["—"] + cols, key="im_f")
    with c2:
        col_monto = st.selectbox("Columna monto", ["—"] + cols, key="im_m")
    with c3:
        col_desc = st.selectbox("Columna descripción", ["—"] + cols, key="im_d")
    col_tipo = st.selectbox(
        "Columna tipo (opcional: ingreso/egreso, I/E, +/−)", ["—"] + cols, key="im_t"
    )
    col_cat = st.selectbox("Columna categoría (opcional)", ["—"] + cols, key="im_c")

    if col_fecha == "—" or col_monto == "—" or col_desc == "—":
        st.info("Elegí las tres columnas obligatorias.")
        st.dataframe(raw.head(15), use_container_width=True)
        return

    work = pd.DataFrame(
        {
            "tx_date": pd.to_datetime(raw[col_fecha], errors="coerce").dt.date,
            "amount_raw": pd.to_numeric(raw[col_monto], errors="coerce"),
            "description": raw[col_desc].astype(str).fillna(""),
        }
    )
    if col_cat != "—":
        work["category"] = raw[col_cat].astype(str)
    else:
        work["category"] = None

    if col_tipo != "—":
        tlow = raw[col_tipo].astype(str).str.lower().str.strip()
        work["tx_type"] = tlow.map(
            lambda x: "ingreso"
            if x in ("ingreso", "i", "+", "in", "entrada", "credit", "crédito", "credito")
            else "egreso"
            if x in ("egreso", "e", "-", "out", "salida", "debit", "débito", "debito")
            else ""
        )
        amb = work["tx_type"] == ""
        if amb.any():
            work.loc[amb, "tx_type"] = work.loc[amb, "amount_raw"].apply(
                lambda v: "egreso" if v is not None and v < 0 else "ingreso"
            )
    else:
        work["tx_type"] = work["amount_raw"].apply(
            lambda v: "egreso" if v is not None and v < 0 else "ingreso"
        )

    work["amount"] = work["amount_raw"].abs()
    work = work.dropna(subset=["tx_date", "amount_raw"])
    work = work[work["amount"] > 0]

    st.write(f"Vista previa: **{len(work)}** filas listas para importar.")
    st.dataframe(work.head(20), use_container_width=True)

    if st.button("Confirmar importación a la cuenta actual", type="primary"):
        rows = []
        for _, row in work.iterrows():
            rows.append(
                {
                    "account_id": account_id,
                    "user_id": user_id,
                    "tx_type": row["tx_type"],
                    "amount": float(row["amount"]),
                    "tx_date": row["tx_date"].isoformat(),
                    "description": (row["description"] or "")[:500] or "(importado)",
                    "category": (str(row["category"]).strip() or None)
                    if row.get("category") is not None
                    and str(row.get("category")).strip()
                    else None,
                }
            )
        batch = 200
        for i in range(0, len(rows), batch):
            sb.table("kf_transaction").insert(rows[i : i + batch]).execute()
        st.success(f"Importadas {len(rows)} filas (registrado por {display_name}).")
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Kenny Finanzas", layout="wide")
    try:
        sb = get_supabase()
    except Exception as e:
        st.error("No se pudo conectar a Supabase. Revisá los secrets.")
        st.code(str(e))
        st.stop()

    user = gate_auth(sb)
    if not user:
        return

    with st.sidebar:
        st.markdown(f"**{user['display_name']}**  \n`{user['username']}`")
        if st.button("Cerrar sesión", use_container_width=True):
            logout()
            st.rerun()
        st.divider()

    try:
        accounts = load_accounts(sb)
    except Exception:
        st.error(
            "No se pudieron leer las cuentas. Revisá RLS / claves o ejecutá schema.sql + parches."
        )
        st.stop()

    if not accounts:
        st.title("Kenny Finanzas")
        st.subheader("Primera vez: crear la cuenta bancaria (BofA)")
        with st.form("new_account"):
            label = st.text_input("Nombre de la cuenta", value="BofA — Orlando Linares")
            bank = st.text_input("Banco", value="Bank of America")
            holder = st.text_input("Titular", value="Orlando Linares")
            opening = st.number_input(
                "Saldo inicial (desde tu Excel)",
                min_value=-1e12,
                value=0.0,
                step=0.01,
                format="%.2f",
            )
            ob_date = st.date_input("Fecha de ese saldo", value=date.today())
            notes = st.text_area("Notas (opcional)", height=68)
            if st.form_submit_button("Crear cuenta"):
                sb.table("kf_account").insert(
                    {
                        "label": label.strip() or "Cuenta",
                        "bank_name": bank.strip() or None,
                        "holder_name": holder.strip() or None,
                        "currency": "USD",
                        "opening_balance": float(opening),
                        "opening_balance_date": ob_date.isoformat(),
                        "notes": notes.strip() or None,
                    }
                ).execute()
                st.success("Cuenta creada.")
                st.rerun()
        st.stop()

    opts = {a["id"]: f'{a.get("label")} ({a.get("currency", "USD")})' for a in accounts}
    account_id = (
        list(opts.keys())[0]
        if len(accounts) == 1
        else st.sidebar.selectbox("Cuenta activa", options=list(opts.keys()), format_func=lambda i: opts[i])
    )
    acc = next(a for a in accounts if a["id"] == account_id)
    txs = load_transactions(sb, account_id)
    umap = load_user_map(sb)
    balance = compute_balance(acc, txs)

    nav = st.sidebar.radio(
        "Sección",
        ["Dashboard", "Movimientos", "Usuarios"],
        index=0,
    )
    if nav == "Usuarios" and not user.get("is_admin"):
        st.warning("No tenés permiso para administrar usuarios.")
        nav = "Dashboard"

    st.title("Kenny Finanzas")
    st.caption("Cuenta compartida · cada movimiento queda registrado con tu usuario")

    if nav == "Dashboard":
        render_finance_dashboard(
            txs,
            _dec(acc.get("opening_balance")),
            str(acc.get("currency", "USD")),
        )

    elif nav == "Movimientos":
        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo calculado", f"{balance:,.2f} {acc.get('currency', 'USD')}")
        c2.metric("Saldo inicial", f'{_dec(acc.get("opening_balance")):,.2f}')
        c3.metric("Movimientos", len(txs))

        t1, t2, t3 = st.tabs(["Registrar", "Saldo inicial", "Importar Excel"])

        with t1:
            with st.form("tx"):
                col_a, col_b = st.columns(2)
                with col_a:
                    tx_type = st.radio("Tipo", ["ingreso", "egreso"], horizontal=True)
                with col_b:
                    tx_date = st.date_input("Fecha", value=date.today())
                amount = st.number_input(
                    "Monto", min_value=0.01, value=10.0, step=0.01, format="%.2f"
                )
                description = st.text_input("Descripción")
                category = st.text_input("Categoría (opcional)")
                if st.form_submit_button("Guardar"):
                    sb.table("kf_transaction").insert(
                        {
                            "account_id": account_id,
                            "user_id": user["id"],
                            "tx_type": tx_type,
                            "amount": float(amount),
                            "tx_date": tx_date.isoformat(),
                            "description": description.strip() or "(sin descripción)",
                            "category": category.strip() or None,
                        }
                    ).execute()
                    st.success("Movimiento guardado.")
                    st.rerun()

        with t2:
            st.write(
                "Ajustá el saldo de corte si alineás con el Excel. Los movimientos cargados siguen aplicando."
            )
            with st.form("adj_opening"):
                new_open = st.number_input(
                    "Nuevo saldo inicial",
                    min_value=-1e12,
                    value=float(_dec(acc.get("opening_balance"))),
                    step=0.01,
                    format="%.2f",
                )
                _obd = acc.get("opening_balance_date")
                _obd_val = date.fromisoformat(str(_obd)[:10]) if _obd else date.today()
                new_date = st.date_input("Fecha de referencia", value=_obd_val)
                if st.form_submit_button("Actualizar"):
                    sb.table("kf_account").update(
                        {
                            "opening_balance": float(new_open),
                            "opening_balance_date": new_date.isoformat(),
                        }
                    ).eq("id", account_id).execute()
                    st.success("Actualizado.")
                    st.rerun()

        with t3:
            import_excel_section(sb, account_id, user["id"], user["display_name"])

        st.divider()
        st.subheader("Últimos movimientos")
        if not txs:
            st.write("Todavía no hay movimientos.")
        else:
            df = pd.DataFrame(txs)
            df["registró"] = df["user_id"].map(lambda x: umap.get(str(x), "—") if pd.notna(x) else "—")
            show = df[
                ["tx_date", "tx_type", "amount", "description", "category", "registró", "id"]
            ].copy()
            show["amount"] = show["amount"].apply(lambda x: f"{float(x):,.2f}")
            st.dataframe(show, use_container_width=True, hide_index=True)
            del_id = st.text_input("Eliminar por ID (uuid)", placeholder="…")
            if st.button("Eliminar") and del_id.strip():
                sb.table("kf_transaction").delete().eq("id", del_id.strip()).execute()
                st.success("Eliminado.")
                st.rerun()

    else:
        page_users_admin(sb)


if __name__ == "__main__":
    main()
