"""
Kenny Finanzas — ingresos/egresos compartidos, login, tablero e importación Excel.
Supabase: schema.sql + patch_002 si la base ya existía sin usuarios.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client

from kf_auth import gate_auth, logout
from kf_constants import (
    CURRENCIES,
    EXPENSE_CATEGORIES,
    INCOME_BUSINESSES,
    INSTITUTION_PRESETS,
    TRANSFER_TAGS,
)
from kf_dashboard import render_finance_dashboard
from kf_reports import render_reports_page


def _pick_list_value(selected: str, other_text: str) -> str | None:
    if selected == "Otro":
        return other_text.strip() or None
    return selected


def _amount_input_format(currency: str) -> tuple[float, str]:
    if currency == "USDT":
        return 0.000001, "%.6f"
    return 0.01, "%.2f"


def page_accounts(sb: Client, accounts: list[dict[str, Any]]) -> None:
    st.subheader("Cuentas, bancos y wallets")
    st.caption(
        "Registrá Banesco, Banca Amiga (VES), Binance (USDT), Zelle, etc. "
        "Datos sensibles: usá la app en cuenta personal y no subas capturas con claves."
    )
    for a in sorted(accounts, key=lambda x: str(x.get("label") or "")):
        cur = a.get("currency", "?")
        with st.expander(f"{a.get('label')} · {cur}", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Institución (tipo):** {a.get('institution_kind') or '—'}")
                st.markdown(f"**Banco (nombre):** {a.get('bank_name') or '—'}")
                st.markdown(f"**Nº cuenta / referencia:** `{a.get('account_number') or '—'}`")
                st.markdown(f"**Routing / Swift:** {a.get('routing_or_swift') or '—'}")
            with c2:
                st.markdown(f"**Titular:** {a.get('holder_name') or '—'}")
                st.markdown(f"**Zelle (email o tel):** {a.get('zelle_email_or_phone') or '—'}")
                w = a.get("wallet_address") or "—"
                st.markdown(f"**Wallet / UID Binance:** `{w}`")
            n = a.get("notes") or ""
            if n.strip():
                st.text_area("Notas (futuros, apalancamiento, recordatorios)", value=n, height=90, disabled=True)

    st.divider()
    with st.expander("Agregar cuenta nueva (VES, USDT, otra cuenta USD…)", expanded=False):
        with st.form("add_acc"):
            alabel = st.text_input("Nombre visible", placeholder="Banesco ahorro / Binance spot")
            cur = st.selectbox("Moneda de la cuenta", CURRENCIES)
            bank = st.text_input("Nombre banco o exchange", placeholder="Banesco / Binance")
            ikind = st.selectbox("Tipo de institución", INSTITUTION_PRESETS)
            iother = st.text_input("Si tipo = Otro, especificá")
            holder = st.text_input("Titular")
            acc_num = st.text_input("Número de cuenta / IBAN / ref (opcional)")
            rout = st.text_input("Routing, ABA o Swift (opcional)")
            zelle = st.text_input("Zelle: email o teléfono (opcional)")
            wallet = st.text_input("Dirección wallet USDT o UID de exchange (opcional)")
            anotes = st.text_area("Notas (futuros, estrategia, límites…)", height=72)
            op = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f")
            od = st.date_input("Fecha de ese saldo", value=date.today())
            if st.form_submit_button("Crear cuenta"):
                inst = _pick_list_value(ikind, iother) or ikind
                sb.table("kf_account").insert(
                    {
                        "label": alabel.strip() or "Cuenta",
                        "currency": cur,
                        "bank_name": bank.strip() or None,
                        "holder_name": holder.strip() or None,
                        "institution_kind": inst,
                        "account_number": acc_num.strip() or None,
                        "routing_or_swift": rout.strip() or None,
                        "zelle_email_or_phone": zelle.strip() or None,
                        "wallet_address": wallet.strip() or None,
                        "notes": anotes.strip() or None,
                        "opening_balance": float(op),
                        "opening_balance_date": od.isoformat(),
                    }
                ).execute()
                st.success("Cuenta creada. Elegila en la barra lateral como **Cuenta activa**.")
                st.rerun()

    st.subheader("Editar cuenta seleccionada")
    opts = {str(a["id"]): f'{a.get("label")} ({a.get("currency")})' for a in accounts}
    pick = st.selectbox("Cuenta a editar", options=list(opts.keys()), format_func=lambda i: opts[i])
    acc = next(x for x in accounts if str(x["id"]) == pick)
    with st.form("edit_acc"):
        elabel = st.text_input("Nombre visible", value=str(acc.get("label") or ""))
        ecur = st.selectbox("Moneda", CURRENCIES, index=max(0, CURRENCIES.index(acc["currency"])) if acc.get("currency") in CURRENCIES else 0)
        ebank = st.text_input("Banco o exchange", value=str(acc.get("bank_name") or ""))
        kinds = INSTITUTION_PRESETS
        ik0 = acc.get("institution_kind") or "Otro"
        ei_idx = kinds.index(ik0) if ik0 in kinds else 0
        ei = st.selectbox("Tipo institución", kinds, index=ei_idx)
        ei_other = st.text_input("Si Otro, especificá", value="" if ik0 in kinds else str(ik0))
        eholder = st.text_input("Titular", value=str(acc.get("holder_name") or ""))
        enum = st.text_input("Nº cuenta / ref", value=str(acc.get("account_number") or ""))
        erout = st.text_input("Routing / Swift", value=str(acc.get("routing_or_swift") or ""))
        ezelle = st.text_input("Zelle", value=str(acc.get("zelle_email_or_phone") or ""))
        ewallet = st.text_input("Wallet / UID", value=str(acc.get("wallet_address") or ""))
        enotes = st.text_area("Notas", value=str(acc.get("notes") or ""), height=80)
        if st.form_submit_button("Guardar cambios"):
            inst_e = _pick_list_value(ei, ei_other) or ei
            sb.table("kf_account").update(
                {
                    "label": elabel.strip() or "Cuenta",
                    "currency": ecur,
                    "bank_name": ebank.strip() or None,
                    "institution_kind": inst_e,
                    "holder_name": eholder.strip() or None,
                    "account_number": enum.strip() or None,
                    "routing_or_swift": erout.strip() or None,
                    "zelle_email_or_phone": ezelle.strip() or None,
                    "wallet_address": ewallet.strip() or None,
                    "notes": enotes.strip() or None,
                }
            ).eq("id", pick).execute()
            st.success("Cuenta actualizada.")
            st.rerun()


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


def _parse_money_cell(v: Any) -> float | None:
    """Acepta número de Excel o texto tipo '$ 1.032,46' / '3.669,60'."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and pd.isna(v):
            return None
        return float(v)
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "-", ""):
        return None
    s = re.sub(r"[\$€\s]", "", s, flags=re.I)
    if not s:
        return None
    try:
        x = float(s)
        return x
    except ValueError:
        pass
    lc, lp = s.rfind(","), s.rfind(".")
    if lc > lp:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _should_skip_row(desc: str, *, filter_noise: bool) -> bool:
    t = (desc or "").strip().lower()
    if not t:
        return True
    if not filter_noise:
        return False
    noise = (
        "total",
        "saldo al",
        "revisado",
        "total de kenny",
        "total de",
    )
    return any(n in t for n in noise)


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
        "Formato tipo **FECHA / DESCRIPCION / INGRESO / EGRESO** (BofA Kenny) o una sola columna de monto."
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

    mode = st.radio(
        "Formato del archivo",
        [
            "Dos columnas: Ingreso y Egreso (como tu Excel BofA)",
            "Una columna de monto (+ tipo o signo)",
        ],
        horizontal=False,
        key="im_mode",
    )
    dayfirst = st.checkbox(
        "Fechas con día primero (03-01-2026 = 3 ene)", value=True, key="im_df"
    )
    filter_noise = st.checkbox(
        "Omitir filas de totales / saldo / revisado", value=True, key="im_skip"
    )

    col_fecha = st.selectbox("Columna fecha", ["—"] + cols, key="im_f")
    col_desc = st.selectbox("Columna descripción", ["—"] + cols, key="im_d")

    work: pd.DataFrame | None = None

    if mode.startswith("Dos columnas"):
        col_in = st.selectbox("Columna INGRESO", ["—"] + cols, key="im_in")
        col_eg = st.selectbox("Columna EGRESO", ["—"] + cols, key="im_eg")
        col_cat = st.selectbox(
            "Columna rubro de gasto (opcional, egresos)", ["—"] + cols, key="im_c2"
        )
        col_biz = st.selectbox(
            "Columna negocio / fuente (opcional, ingresos)", ["—"] + cols, key="im_biz"
        )

        if col_fecha == "—" or col_desc == "—" or col_in == "—" or col_eg == "—":
            st.info("Elegí fecha, descripción, ingreso y egreso.")
            st.dataframe(raw.head(15), use_container_width=True)
            return

        dts = pd.to_datetime(raw[col_fecha], errors="coerce", dayfirst=dayfirst)
        out_rows: list[dict[str, Any]] = []
        for i in range(len(raw)):
            desc = str(raw.iloc[i][col_desc]).strip()
            if _should_skip_row(desc, filter_noise=filter_noise):
                continue
            td = dts.iloc[i]
            if pd.isna(td):
                continue
            txd = td.date()
            ing = _parse_money_cell(raw.iloc[i][col_in])
            egr = _parse_money_cell(raw.iloc[i][col_eg])
            cat_eg = None
            if col_cat != "—":
                c = raw.iloc[i][col_cat]
                if c is not None and str(c).strip():
                    cat_eg = str(c).strip()
            biz_in = None
            if col_biz != "—":
                b = raw.iloc[i][col_biz]
                if b is not None and str(b).strip():
                    biz_in = str(b).strip()
            if ing is not None and ing > 0:
                out_rows.append(
                    {
                        "tx_date": txd,
                        "tx_type": "ingreso",
                        "amount": ing,
                        "description": desc,
                        "category": None,
                        "business": biz_in,
                    }
                )
            if egr is not None and egr > 0:
                out_rows.append(
                    {
                        "tx_date": txd,
                        "tx_type": "egreso",
                        "amount": egr,
                        "description": desc,
                        "category": cat_eg,
                        "business": None,
                    }
                )
        work = pd.DataFrame(out_rows) if out_rows else pd.DataFrame()

    else:
        col_monto = st.selectbox("Columna monto", ["—"] + cols, key="im_m")
        col_tipo = st.selectbox(
            "Columna tipo (opcional)", ["—"] + cols, key="im_t"
        )
        col_cat = st.selectbox(
            "Columna rubro de gasto (opcional, egresos)", ["—"] + cols, key="im_c"
        )
        col_biz = st.selectbox(
            "Columna negocio / fuente (opcional, ingresos)", ["—"] + cols, key="im_biz1"
        )

        if col_fecha == "—" or col_monto == "—" or col_desc == "—":
            st.info("Elegí fecha, monto y descripción.")
            st.dataframe(raw.head(15), use_container_width=True)
            return

        dts = pd.to_datetime(raw[col_fecha], errors="coerce", dayfirst=dayfirst)
        descs = raw[col_desc].astype(str)
        amounts = [_parse_money_cell(x) for x in raw[col_monto]]

        tmp: list[dict[str, Any]] = []
        for i in range(len(raw)):
            desc = descs.iloc[i].strip()
            if _should_skip_row(desc, filter_noise=filter_noise):
                continue
            td = dts.iloc[i]
            if pd.isna(td):
                continue
            amt = amounts[i]
            if amt is None or amt == 0:
                continue
            tx_type = "ingreso"
            if col_tipo != "—":
                x = str(raw.iloc[i][col_tipo]).lower().strip()
                if x in ("egreso", "e", "-", "out", "salida", "débito", "debito"):
                    tx_type = "egreso"
                elif x in ("ingreso", "i", "+", "entrada", "crédito", "credito"):
                    tx_type = "ingreso"
                else:
                    tx_type = "egreso" if amt < 0 else "ingreso"
            else:
                tx_type = "egreso" if amt < 0 else "ingreso"
            cat = None
            if col_cat != "—" and tx_type == "egreso":
                c = raw.iloc[i][col_cat]
                if c is not None and str(c).strip():
                    cat = str(c).strip()
            biz = None
            if col_biz != "—" and tx_type == "ingreso":
                b = raw.iloc[i][col_biz]
                if b is not None and str(b).strip():
                    biz = str(b).strip()
            tmp.append(
                {
                    "tx_date": td.date(),
                    "tx_type": tx_type,
                    "amount": abs(float(amt)),
                    "description": desc,
                    "category": cat,
                    "business": biz,
                }
            )
        work = pd.DataFrame(tmp)

    if work is None or work.empty:
        st.warning("No quedaron filas para importar (revisá fechas, montos y filtros).")
        st.dataframe(raw.head(20), use_container_width=True)
        return

    if "business" not in work.columns:
        work["business"] = None

    st.write(f"Vista previa: **{len(work)}** movimientos listos.")
    st.dataframe(work.head(25), use_container_width=True)

    st.info(
        "**Saldo inicial:** si en el Excel el renglón «vienen» del 01/01/2026 es el arrastre del saldo, "
        "podés poner **saldo inicial** = 0 y dejar que importe esa fila, **o** poner saldo inicial = 1.032,46 "
        "al 31/12/2025 y **desmarcar** esa fila en Excel antes de exportar (para no duplicar)."
    )

    if st.button("Confirmar importación a la cuenta actual", type="primary"):
        rows = []
        for _, row in work.iterrows():
            tx_t = str(row["tx_type"])
            cat = (
                str(row["category"]).strip()
                if row.get("category") is not None
                and pd.notna(row.get("category"))
                and str(row.get("category")).strip()
                else None
            )
            bus = (
                str(row["business"]).strip()
                if row.get("business") is not None
                and pd.notna(row.get("business"))
                and str(row.get("business")).strip()
                else None
            )
            rows.append(
                {
                    "account_id": account_id,
                    "user_id": user_id,
                    "tx_type": tx_t,
                    "amount": float(row["amount"]),
                    "tx_date": row["tx_date"].isoformat(),
                    "description": (row["description"] or "")[:500] or "(importado)",
                    "category": cat if tx_t == "egreso" else None,
                    "business": bus if tx_t == "ingreso" else None,
                }
            )
        batch = 200
        try:
            for i in range(0, len(rows), batch):
                sb.table("kf_transaction").insert(rows[i : i + batch]).execute()
        except Exception as e:
            st.error(
                "Falló la importación. Si falta la columna `business` en Supabase, "
                "ejecutá `supabase/patch_003_business.sql`."
            )
            st.code(str(e))
        else:
            st.success(
                f"Importados {len(rows)} movimientos (registrado por {display_name})."
            )
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
        st.caption(
            "Pestañas: **Dashboard · Movimientos · Cuentas · Reportes · Usuarios** (área principal)."
        )

    try:
        accounts = load_accounts(sb)
    except Exception:
        st.error(
            "No se pudieron leer las cuentas. Revisá RLS / claves o ejecutá schema.sql + parches."
        )
        st.stop()

    if not accounts:
        st.title("Kenny Finanzas")
        st.success(
            "Usuario listo. **Ahora creá la cuenta del banco** (BofA) con el formulario de abajo; "
            "sin eso no hay Dashboard ni movimientos."
        )
        st.subheader("Primera cuenta (obligatorio para continuar)")
        with st.form("new_account"):
            label = st.text_input("Nombre de la cuenta", value="BofA — Orlando Linares")
            cur0 = st.selectbox("Moneda", CURRENCIES, index=0)
            bank = st.text_input("Banco / exchange", value="Bank of America")
            ikind = st.selectbox("Tipo", INSTITUTION_PRESETS, index=0)
            iother = st.text_input("Si tipo = Otro, especificá")
            holder = st.text_input("Titular", value="Orlando Linares")
            acc_num = st.text_input("Nº cuenta / ref (opcional)")
            rout = st.text_input("Routing / Swift (opcional)")
            zelle = st.text_input("Zelle email/tel (opcional)")
            wallet = st.text_input("Wallet USDT / UID (opcional)")
            opening = st.number_input(
                "Saldo inicial",
                min_value=-1e15,
                value=0.0,
                step=0.01,
                format="%.8f",
            )
            ob_date = st.date_input("Fecha de ese saldo", value=date.today())
            notes = st.text_area("Notas (opcional)", height=68)
            if st.form_submit_button("Crear cuenta"):
                inst = _pick_list_value(ikind, iother) or ikind
                sb.table("kf_account").insert(
                    {
                        "label": label.strip() or "Cuenta",
                        "bank_name": bank.strip() or None,
                        "holder_name": holder.strip() or None,
                        "currency": cur0,
                        "institution_kind": inst,
                        "account_number": acc_num.strip() or None,
                        "routing_or_swift": rout.strip() or None,
                        "zelle_email_or_phone": zelle.strip() or None,
                        "wallet_address": wallet.strip() or None,
                        "opening_balance": float(opening),
                        "opening_balance_date": ob_date.isoformat(),
                        "notes": notes.strip() or None,
                    }
                ).execute()
                st.success("Cuenta creada.")
                st.rerun()
        return

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

    st.title("Kenny Finanzas")
    st.caption("Cuenta compartida · cada movimiento queda registrado con tu usuario")

    tab_dash, tab_mov, tab_acc, tab_rep, tab_usr = st.tabs(
        ["Dashboard", "Movimientos", "Cuentas", "Reportes", "Usuarios"]
    )

    with tab_dash:
        try:
            render_finance_dashboard(
                txs,
                _dec(acc.get("opening_balance")),
                str(acc.get("currency", "USD")),
            )
        except Exception as e:
            st.error("El tablero falló al cargar. Probá recargar la página o revisá los datos.")
            st.code(str(e))

    with tab_mov:
        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo calculado", f"{balance:,.2f} {acc.get('currency', 'USD')}")
        c2.metric("Saldo inicial", f'{_dec(acc.get("opening_balance")):,.2f}')
        c3.metric("Movimientos", len(txs))

        t1, t2, t3 = st.tabs(["Registrar", "Saldo inicial", "Importar Excel"])

        with t1:
            acur = str(acc.get("currency", "USD"))
            step_f, fmt_f = _amount_input_format(acur)
            st.caption(f"Movimientos en **{acur}** para la cuenta activa (cambiala en la barra lateral).")
            with st.form("tx"):
                col_a, col_b = st.columns(2)
                with col_a:
                    tx_type = st.radio("Tipo", ["ingreso", "egreso"], horizontal=True)
                with col_b:
                    tx_date = st.date_input("Fecha", value=date.today())
                amount = st.number_input(
                    f"Monto principal ({acur})",
                    min_value=float(step_f),
                    value=10.0 if acur != "USDT" else 0.01,
                    step=float(step_f),
                    format=fmt_f,
                )
                description = st.text_input("Descripción / concepto")
                st.caption(
                    "**Ingreso:** elegí el negocio. **Egreso:** elegí el rubro del gasto (solo rellená el que corresponda)."
                )
                col_biz, col_cat = st.columns(2)
                with col_biz:
                    biz_sel = st.selectbox(
                        "Negocio (ingresos)",
                        INCOME_BUSINESSES,
                        index=0,
                        help="Movi Motors, delivery, Zemog…",
                    )
                    biz_other = st.text_input("Si negocio = Otro, escribí el nombre")
                with col_cat:
                    cat_sel = st.selectbox(
                        "Rubro del gasto (egresos)",
                        EXPENSE_CATEGORIES,
                        index=0,
                        help="Casa, carro, hijos…",
                    )
                    cat_other = st.text_input("Si rubro = Otro, escribí el nombre")
                tag_opts = ["(ninguna)"] + TRANSFER_TAGS
                tag_sel = st.selectbox("Etiqueta (ej. Zelle→Binance, futuros)", tag_opts)
                tag_other = st.text_input("Texto si usás etiqueta «Otro»")
                fee_amt = st.number_input(
                    "Comisión / fee del movimiento (opcional)",
                    min_value=0.0,
                    value=0.0,
                    step=float(step_f),
                    format=fmt_f,
                )
                fee_cur_opts = list(dict.fromkeys([acur, "USD", "USDT", "VES"]))
                fee_cur = st.selectbox("Moneda de la comisión", fee_cur_opts)
                tx_notes = st.text_area("Notas del movimiento (opcional)", height=60)
                if st.form_submit_button("Guardar"):
                    if tx_type == "ingreso":
                        business = _pick_list_value(biz_sel, biz_other)
                        category = None
                    else:
                        business = None
                        category = _pick_list_value(cat_sel, cat_other)
                    if tag_sel == "(ninguna)":
                        transfer_tag = None
                    elif tag_sel == "Otro":
                        transfer_tag = tag_other.strip() or None
                    else:
                        transfer_tag = tag_sel
                    row_ins: dict[str, Any] = {
                        "account_id": account_id,
                        "user_id": user["id"],
                        "tx_type": tx_type,
                        "amount": float(amount),
                        "tx_date": tx_date.isoformat(),
                        "description": description.strip() or "(sin descripción)",
                        "category": category,
                        "business": business,
                        "transfer_tag": transfer_tag,
                        "transaction_notes": tx_notes.strip() or None,
                    }
                    if fee_amt and float(fee_amt) > 0:
                        row_ins["fee_amount"] = float(fee_amt)
                        row_ins["fee_currency"] = fee_cur
                    try:
                        sb.table("kf_transaction").insert(row_ins).execute()
                    except Exception as e:
                        st.error(
                            "No se pudo guardar. Ejecutá en Supabase los parches: "
                            "`patch_003_business.sql` y `patch_004_accounts_reports.sql`."
                        )
                        st.code(str(e))
                    else:
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
            for col in ("business", "fee_amount", "transfer_tag", "transaction_notes"):
                if col not in df.columns:
                    df[col] = None
            show = df[
                [
                    "tx_date",
                    "tx_type",
                    "amount",
                    "fee_amount",
                    "business",
                    "category",
                    "transfer_tag",
                    "description",
                    "registró",
                    "id",
                ]
            ].copy()
            _prec = 6 if str(acc.get("currency")) == "USDT" else 2
            show["amount"] = show["amount"].apply(
                lambda x, p=_prec: f"{float(x):,.{p}f}"
            )
            show["fee_amount"] = show["fee_amount"].apply(
                lambda x: f"{float(x):,.6f}" if pd.notna(x) and x is not None and float(x) > 0 else "—"
            )
            st.dataframe(show, use_container_width=True, hide_index=True)
            del_id = st.text_input("Eliminar por ID (uuid)", placeholder="…")
            if st.button("Eliminar") and del_id.strip():
                sb.table("kf_transaction").delete().eq("id", del_id.strip()).execute()
                st.success("Eliminado.")
                st.rerun()

    with tab_acc:
        page_accounts(sb, accounts)

    with tab_rep:
        render_reports_page(sb, accounts, umap)

    with tab_usr:
        if user.get("is_admin"):
            page_users_admin(sb)
        else:
            st.info("Solo un administrador puede crear usuarios. Pedile acceso a quien creó el primer usuario.")


if __name__ == "__main__":
    main()
