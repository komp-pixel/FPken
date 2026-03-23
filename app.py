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
    ACCOUNT_KIND_LABELS,
    CURRENCIES,
    EXPENSE_CATEGORIES,
    INCOME_BUSINESSES,
    INSTITUTION_APPS,
    INSTITUTION_BANKS,
    INSTITUTION_WALLET,
    TRANSFER_TAGS,
)
from kf_bcv import render_bcv_reference
from kf_dashboard import render_finance_dashboard
from kf_fx_convert import all_balances_with_ves, resolve_ves_rates, to_ves
from kf_p2p_binance import render_usdt_ves_p2p_reference
from kf_reports import render_reports_page


def _pick_list_value(selected: str, other_text: str) -> str | None:
    if selected == "Otro":
        return other_text.strip() or None
    return selected


_KF_ACCOUNT_CORE_FIELDS = frozenset(
    {
        "label",
        "currency",
        "bank_name",
        "holder_name",
        "opening_balance",
        "opening_balance_date",
        "notes",
    }
)


def kf_account_insert_flexible(sb: Client, row: dict[str, Any]) -> tuple[bool, str | None]:
    """Insert completo; si la BD no tiene patch_004, reintenta solo columnas base."""
    try:
        sb.table("kf_account").insert(row).execute()
        return True, None
    except Exception as e:
        first = str(e)
        core = {k: v for k, v in row.items() if k in _KF_ACCOUNT_CORE_FIELDS}
        try:
            sb.table("kf_account").insert(core).execute()
        except Exception as e2:
            return False, f"{first}\n---\n{str(e2)}"
        return True, (
            "Creado con datos mínimos. En Supabase ejecutá **`patch_004_accounts_reports.sql`** "
            "y **`patch_005_account_kind.sql`** para guardar también tipo (banco/wallet/app), "
            "nº de cuenta, Zelle, wallet y clasificación."
        )


def kf_account_update_flexible(sb: Client, acc_id: str, row: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        sb.table("kf_account").update(row).eq("id", acc_id).execute()
        return True, None
    except Exception as e:
        first = str(e)
        core = {k: v for k, v in row.items() if k in _KF_ACCOUNT_CORE_FIELDS}
        if not core:
            return False, first
        try:
            sb.table("kf_account").update(core).eq("id", acc_id).execute()
        except Exception as e2:
            return False, f"{first}\n---\n{str(e2)}"
        return True, (
            "Guardado parcial. Ejecutá **`patch_004`** y **`patch_005_account_kind.sql`** en Supabase."
        )


def _bootstrap_account_result(ok: bool, wmsg: str | None) -> None:
    if ok:
        if wmsg:
            st.warning(wmsg)
        else:
            st.success("Registro creado.")
        st.rerun()
    else:
        st.error("No se pudo crear.")
        st.code(wmsg or "")


def _amount_input_format(currency: str) -> tuple[float, str]:
    if currency == "USDT":
        return 0.000001, "%.6f"
    return 0.01, "%.2f"


def _infer_account_kind(acc: dict[str, Any]) -> str:
    k = acc.get("account_kind")
    if k in ("banco", "wallet", "app_pagos"):
        return str(k)
    ik = str(acc.get("institution_kind") or "").strip().lower()
    if any(x in ik for x in ("zinly", "zelle")):
        return "app_pagos"
    if any(x in ik for x in ("binance", "on-chain", "metamask", "wallet")):
        return "wallet"
    if acc.get("wallet_address") and not str(acc.get("account_number") or "").strip():
        return "wallet"
    if acc.get("zelle_email_or_phone") and not str(acc.get("account_number") or "").strip():
        return "app_pagos"
    return "banco"


def _nulls_for_kind(kind: str) -> dict[str, Any]:
    if kind == "banco":
        return {"wallet_address": None, "zelle_email_or_phone": None}
    if kind == "wallet":
        return {
            "account_number": None,
            "routing_or_swift": None,
            "zelle_email_or_phone": None,
        }
    if kind == "app_pagos":
        return {"wallet_address": None, "account_number": None, "routing_or_swift": None}
    return {}


def _render_account_detail(acc: dict[str, Any], kind: str) -> None:
    st.caption(f"Clasificación: **{ACCOUNT_KIND_LABELS.get(kind, kind)}**")
    if kind == "banco":
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Banco:** {acc.get('bank_name') or '—'}")
            st.markdown(f"**Institución:** {acc.get('institution_kind') or '—'}")
            st.markdown(f"**Nº cuenta / ref:** `{acc.get('account_number') or '—'}`")
            st.markdown(f"**Routing / Swift:** {acc.get('routing_or_swift') or '—'}")
        with c2:
            st.markdown(f"**Titular:** {acc.get('holder_name') or '—'}")
    elif kind == "wallet":
        st.markdown(f"**Exchange / red:** {acc.get('bank_name') or acc.get('institution_kind') or '—'}")
        st.markdown(f"**Dirección o UID:** `{acc.get('wallet_address') or '—'}`")
        st.markdown(f"**Titular:** {acc.get('holder_name') or '—'}")
    else:
        st.markdown(f"**App:** {acc.get('institution_kind') or acc.get('bank_name') or '—'}")
        st.markdown(f"**Usuario / email / tel.:** `{acc.get('zelle_email_or_phone') or '—'}`")
        st.markdown(f"**Titular:** {acc.get('holder_name') or '—'}")
    n = acc.get("notes") or ""
    if str(n).strip():
        st.text_area("Notas", value=str(n), height=72, disabled=True)


def page_accounts(sb: Client, accounts: list[dict[str, Any]]) -> None:
    st.subheader("Registros por tipo (separados)")
    st.caption(
        "**Banco** = cuenta en Banesco, BofA, Banca Amiga… "
        "**Wallet** = Binance / USDT / on-chain (sin número de cuenta bancario). "
        "**App** = Zinly, Zelle (pagos digitales; no es lo mismo que una cuenta corriente)."
    )
    st.info(
        "SQL en Supabase: **`patch_004_accounts_reports.sql`** y **`patch_005_account_kind.sql`**."
    )

    by_k: dict[str, list[dict[str, Any]]] = {"banco": [], "wallet": [], "app_pagos": []}
    for a in accounts:
        by_k[_infer_account_kind(a)].append(a)

    for kind, title in (
        ("banco", "Cuentas bancarias"),
        ("wallet", "Wallets y crypto"),
        ("app_pagos", "Apps de pago (Zinly, Zelle…)"),
    ):
        st.markdown(f"### {title}")
        if not by_k[kind]:
            st.write("Ningún registro aún.")
        for a in sorted(by_k[kind], key=lambda x: str(x.get("label") or "")):
            with st.expander(f"{a.get('label')} · {a.get('currency', '?')}", expanded=False):
                _render_account_detail(a, kind)

        if kind == "banco":
            with st.expander("Agregar cuenta **bancaria**", expanded=False):
                with st.form("add_banco"):
                    lb = st.text_input("Nombre (ej. Banesco ahorro)", key="ab_lb")
                    cur = st.selectbox("Moneda", CURRENCIES, index=0, key="ab_cur")
                    bn = st.text_input("Nombre del banco", key="ab_bn")
                    ik = st.selectbox("Institución", INSTITUTION_BANKS, key="ab_ik")
                    io = st.text_input("Si Otro, especificá", key="ab_io")
                    hol = st.text_input("Titular", key="ab_h")
                    an = st.text_input("Número de cuenta / IBAN", key="ab_an")
                    rt = st.text_input("Routing / ABA / Swift", key="ab_rt")
                    nt = st.text_area("Notas", height=60, key="ab_nt")
                    op = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f", key="ab_op")
                    od = st.date_input("Fecha saldo", value=date.today(), key="ab_od")
                    if st.form_submit_button("Crear banco"):
                        inst = _pick_list_value(ik, io) or ik
                        row = {
                            "account_kind": "banco",
                            "label": lb.strip() or "Cuenta bancaria",
                            "currency": cur,
                            "bank_name": bn.strip() or inst,
                            "institution_kind": inst,
                            "holder_name": hol.strip() or None,
                            "account_number": an.strip() or None,
                            "routing_or_swift": rt.strip() or None,
                            "notes": nt.strip() or None,
                            "opening_balance": float(op),
                            "opening_balance_date": od.isoformat(),
                            **_nulls_for_kind("banco"),
                        }
                        ok, wmsg = kf_account_insert_flexible(sb, row)
                        if ok:
                            if wmsg:
                                st.warning(wmsg)
                            else:
                                st.success("Cuenta bancaria creada.")
                            st.rerun()
                        else:
                            st.error("Error al crear.")
                            st.code(wmsg or "")
        elif kind == "wallet":
            with st.expander("Agregar **wallet / crypto**", expanded=False):
                with st.form("add_wallet"):
                    lb = st.text_input("Nombre (ej. Binance spot USDT)", key="aw_lb")
                    cur = st.selectbox("Moneda", CURRENCIES, index=CURRENCIES.index("USDT"), key="aw_cur")
                    ik = st.selectbox("Tipo", INSTITUTION_WALLET, key="aw_ik")
                    io = st.text_input("Si Otro, especificá", key="aw_io")
                    waddr = st.text_input("Dirección wallet o UID de la cuenta exchange *", key="aw_w")
                    hol = st.text_input("Titular (opcional)", key="aw_h")
                    nt = st.text_area("Notas (futuros, redes…)", height=60, key="aw_nt")
                    op = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f", key="aw_op")
                    od = st.date_input("Fecha saldo", value=date.today(), key="aw_od")
                    if st.form_submit_button("Crear wallet"):
                        inst = _pick_list_value(ik, io) or ik
                        row = {
                            "account_kind": "wallet",
                            "label": lb.strip() or "Wallet",
                            "currency": cur,
                            "bank_name": inst,
                            "institution_kind": inst,
                            "holder_name": hol.strip() or None,
                            "wallet_address": waddr.strip() or None,
                            "notes": nt.strip() or None,
                            "opening_balance": float(op),
                            "opening_balance_date": od.isoformat(),
                            **_nulls_for_kind("wallet"),
                        }
                        ok, wmsg = kf_account_insert_flexible(sb, row)
                        if ok:
                            if wmsg:
                                st.warning(wmsg)
                            else:
                                st.success("Wallet creada.")
                            st.rerun()
                        else:
                            st.error("Error al crear.")
                            st.code(wmsg or "")
        else:
            with st.expander("Agregar **app de pagos** (Zinly, Zelle…)", expanded=False):
                with st.form("add_app"):
                    lb = st.text_input("Nombre (ej. Zinly compras)", key="aa_lb")
                    cur = st.selectbox("Moneda", CURRENCIES, index=0, key="aa_cur")
                    ik = st.selectbox("App", INSTITUTION_APPS, key="aa_ik")
                    io = st.text_input("Si Otro, especificá", key="aa_io")
                    zid = st.text_input("Email, teléfono o usuario de la app *", key="aa_z")
                    hol = st.text_input("Titular (opcional)", key="aa_h")
                    nt = st.text_area("Notas", height=60, key="aa_nt")
                    op = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f", key="aa_op")
                    od = st.date_input("Fecha saldo", value=date.today(), key="aa_od")
                    if st.form_submit_button("Crear app"):
                        inst = _pick_list_value(ik, io) or ik
                        row = {
                            "account_kind": "app_pagos",
                            "label": lb.strip() or "App",
                            "currency": cur,
                            "bank_name": inst,
                            "institution_kind": inst,
                            "holder_name": hol.strip() or None,
                            "zelle_email_or_phone": zid.strip() or None,
                            "notes": nt.strip() or None,
                            "opening_balance": float(op),
                            "opening_balance_date": od.isoformat(),
                            **_nulls_for_kind("app_pagos"),
                        }
                        ok, wmsg = kf_account_insert_flexible(sb, row)
                        if ok:
                            if wmsg:
                                st.warning(wmsg)
                            else:
                                st.success("App registrada.")
                            st.rerun()
                        else:
                            st.error("Error al crear.")
                            st.code(wmsg or "")
        st.divider()

    st.subheader("Editar registro")
    opts = {
        str(a["id"]): f'[{ACCOUNT_KIND_LABELS.get(_infer_account_kind(a), "?")}] {a.get("label")} ({a.get("currency")})'
        for a in accounts
    }
    pick = st.selectbox("Elegir", options=list(opts.keys()), format_func=lambda i: opts[i])
    acc = next(x for x in accounts if str(x["id"]) == pick)
    kind0 = _infer_account_kind(acc)
    kind_labels = list(ACCOUNT_KIND_LABELS.keys())
    with st.form("edit_acc"):
        nk = st.selectbox(
            "Tipo de registro",
            kind_labels,
            index=kind_labels.index(kind0) if kind0 in kind_labels else 0,
            format_func=lambda k: ACCOUNT_KIND_LABELS[k],
        )
        elabel = st.text_input("Nombre visible", value=str(acc.get("label") or ""))
        ecur = st.selectbox(
            "Moneda",
            CURRENCIES,
            index=CURRENCIES.index(acc["currency"]) if acc.get("currency") in CURRENCIES else 0,
        )
        eholder = st.text_input("Titular", value=str(acc.get("holder_name") or ""))
        enotes = st.text_area("Notas", value=str(acc.get("notes") or ""), height=70)

        if nk == "banco":
            ebank = st.text_input("Nombre del banco", value=str(acc.get("bank_name") or ""))
            ik0 = acc.get("institution_kind") or "Otro"
            ei = st.selectbox(
                "Institución",
                INSTITUTION_BANKS,
                index=INSTITUTION_BANKS.index(ik0) if ik0 in INSTITUTION_BANKS else 0,
            )
            ei_other = st.text_input("Si Otro, especificá", value="" if ik0 in INSTITUTION_BANKS else ik0)
            enum = st.text_input("Nº cuenta / ref", value=str(acc.get("account_number") or ""))
            erout = st.text_input("Routing / Swift", value=str(acc.get("routing_or_swift") or ""))
        elif nk == "wallet":
            ebank = st.text_input("Exchange / red", value=str(acc.get("bank_name") or ""))
            ik0 = acc.get("institution_kind") or "Otro"
            ei = st.selectbox(
                "Tipo",
                INSTITUTION_WALLET,
                index=INSTITUTION_WALLET.index(ik0) if ik0 in INSTITUTION_WALLET else 0,
            )
            ei_other = st.text_input("Si Otro, especificá", value="" if ik0 in INSTITUTION_WALLET else ik0)
            ewallet = st.text_input("Wallet / UID", value=str(acc.get("wallet_address") or ""))
        else:
            ebank = st.text_input("App (nombre)", value=str(acc.get("bank_name") or ""))
            ik0 = acc.get("institution_kind") or "Otro"
            ei = st.selectbox(
                "App",
                INSTITUTION_APPS,
                index=INSTITUTION_APPS.index(ik0) if ik0 in INSTITUTION_APPS else 0,
            )
            ei_other = st.text_input("Si Otro, especificá", value="" if ik0 in INSTITUTION_APPS else ik0)
            ezelle = st.text_input(
                "Usuario / email / tel.",
                value=str(acc.get("zelle_email_or_phone") or ""),
            )

        if st.form_submit_button("Guardar"):
            inst_e = _pick_list_value(ei, ei_other) or ei
            base: dict[str, Any] = {
                "account_kind": nk,
                "label": elabel.strip() or "Cuenta",
                "currency": ecur,
                "holder_name": eholder.strip() or None,
                "notes": enotes.strip() or None,
                "institution_kind": inst_e,
                **_nulls_for_kind(nk),
            }
            if nk == "banco":
                base.update(
                    {
                        "bank_name": ebank.strip() or inst_e,
                        "account_number": enum.strip() or None,
                        "routing_or_swift": erout.strip() or None,
                    }
                )
            elif nk == "wallet":
                base.update(
                    {
                        "bank_name": ebank.strip() or inst_e,
                        "wallet_address": ewallet.strip() or None,
                    }
                )
            else:
                base.update(
                    {
                        "bank_name": ebank.strip() or inst_e,
                        "zelle_email_or_phone": ezelle.strip() or None,
                    }
                )
            ok, wmsg = kf_account_update_flexible(sb, pick, base)
            if ok:
                if wmsg:
                    st.warning(wmsg)
                else:
                    st.success("Actualizado.")
                st.rerun()
            else:
                st.error("No se pudo guardar.")
                st.code(wmsg or "")


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
        st.subheader("Primer registro (elegí una pestaña)")
        st.caption("Banco, wallet y app son formularios distintos — no mezcles datos.")
        tb, tw, ta = st.tabs(["Cuenta bancaria", "Wallet crypto", "App Zinly / Zelle"])
        with tb:
            with st.form("new_banco"):
                label = st.text_input("Nombre", value="BofA — Orlando Linares")
                cur0 = st.selectbox("Moneda", CURRENCIES, index=0)
                bank = st.text_input("Nombre del banco", value="Bank of America")
                ikind = st.selectbox("Institución", INSTITUTION_BANKS, index=0)
                iother = st.text_input("Si Otro, especificá")
                holder = st.text_input("Titular", value="Orlando Linares")
                acc_num = st.text_input("Nº cuenta / ref")
                rout = st.text_input("Routing / Swift (opcional)")
                opening = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f")
                ob_date = st.date_input("Fecha de ese saldo", value=date.today())
                notes = st.text_area("Notas", height=50)
                if st.form_submit_button("Crear banco"):
                    inst = _pick_list_value(ikind, iother) or ikind
                    ok, wmsg = kf_account_insert_flexible(
                        sb,
                        {
                            "account_kind": "banco",
                            "label": label.strip() or "Cuenta",
                            "currency": cur0,
                            "bank_name": bank.strip() or inst,
                            "institution_kind": inst,
                            "holder_name": holder.strip() or None,
                            "account_number": acc_num.strip() or None,
                            "routing_or_swift": rout.strip() or None,
                            "notes": notes.strip() or None,
                            "opening_balance": float(opening),
                            "opening_balance_date": ob_date.isoformat(),
                            **_nulls_for_kind("banco"),
                        },
                    )
                    _bootstrap_account_result(ok, wmsg)
        with tw:
            with st.form("new_wallet"):
                label = st.text_input("Nombre", value="Binance USDT")
                cur0 = st.selectbox("Moneda", CURRENCIES, index=CURRENCIES.index("USDT"))
                ikind = st.selectbox("Tipo", INSTITUTION_WALLET, index=0)
                iother = st.text_input("Si Otro, especificá")
                waddr = st.text_input("Wallet / UID *")
                holder = st.text_input("Titular (opcional)")
                opening = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f", key="nw_op")
                ob_date = st.date_input("Fecha saldo", value=date.today(), key="nw_od")
                notes = st.text_area("Notas", height=50, key="nw_nt")
                if st.form_submit_button("Crear wallet"):
                    inst = _pick_list_value(ikind, iother) or ikind
                    ok, wmsg = kf_account_insert_flexible(
                        sb,
                        {
                            "account_kind": "wallet",
                            "label": label.strip() or "Wallet",
                            "currency": cur0,
                            "bank_name": inst,
                            "institution_kind": inst,
                            "holder_name": holder.strip() or None,
                            "wallet_address": waddr.strip() or None,
                            "notes": notes.strip() or None,
                            "opening_balance": float(opening),
                            "opening_balance_date": ob_date.isoformat(),
                            **_nulls_for_kind("wallet"),
                        },
                    )
                    _bootstrap_account_result(ok, wmsg)
        with ta:
            with st.form("new_app"):
                label = st.text_input("Nombre", value="Zinly")
                cur0 = st.selectbox("Moneda", CURRENCIES, index=0, key="na_cur")
                ikind = st.selectbox("App", INSTITUTION_APPS, index=0)
                iother = st.text_input("Si Otro, especificá", key="na_io")
                zid = st.text_input("Email / tel / usuario *")
                holder = st.text_input("Titular (opcional)", key="na_h")
                opening = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f", key="na_op")
                ob_date = st.date_input("Fecha saldo", value=date.today(), key="na_od")
                notes = st.text_area("Notas", height=50, key="na_nt")
                if st.form_submit_button("Crear app"):
                    inst = _pick_list_value(ikind, iother) or ikind
                    ok, wmsg = kf_account_insert_flexible(
                        sb,
                        {
                            "account_kind": "app_pagos",
                            "label": label.strip() or "App",
                            "currency": cur0,
                            "bank_name": inst,
                            "institution_kind": inst,
                            "holder_name": holder.strip() or None,
                            "zelle_email_or_phone": zid.strip() or None,
                            "notes": notes.strip() or None,
                            "opening_balance": float(opening),
                            "opening_balance_date": ob_date.isoformat(),
                            **_nulls_for_kind("app_pagos"),
                        },
                    )
                    _bootstrap_account_result(ok, wmsg)
        return

    opts = {
        str(a["id"]): f'{a.get("label")} ({a.get("currency", "USD")}) · '
        f'{ACCOUNT_KIND_LABELS.get(_infer_account_kind(a), "?")}'
        for a in accounts
    }
    account_id = (
        list(opts.keys())[0]
        if len(accounts) == 1
        else st.sidebar.selectbox("Cuenta activa", options=list(opts.keys()), format_func=lambda i: opts[i])
    )

    st.sidebar.divider()
    st.sidebar.subheader("Tasa (bolívares)")
    _fx_choices: list[tuple[str, str]] = [
        ("BCV oficial (promedio)", "bcv"),
        ("P2P — comprar USDT (mediana)", "p2p_buy"),
        ("P2P — vender USDT (mediana)", "p2p_sell"),
        ("Manual: Bs × 1 USD o USDT", "manual"),
    ]
    _fx_labels = [t[0] for t in _fx_choices]
    _fx_pick = st.sidebar.selectbox(
        "Convertir USD / USDT a VES con",
        _fx_labels,
        key="kf_fx_mode_label",
        help="Una misma tasa aplica a USD y USDT como referencia; VES queda en Bs. "
        "El desglose por cuenta está en Dashboard.",
    )
    _fx_mode = dict(_fx_choices)[_fx_pick]
    _manual_bs: float | None = None
    if _fx_mode == "manual":
        _manual_bs = float(
            st.sidebar.number_input(
                "Bs por 1 USD o USDT",
                min_value=0.0001,
                value=400.0,
                format="%.4f",
                key="kf_fx_manual_bs",
            )
        )
    _ves_u, _ves_t, _fx_caption = resolve_ves_rates(_fx_mode, _manual_bs)
    st.sidebar.caption(_fx_caption)
    if _ves_u is None or _ves_t is None:
        st.sidebar.warning("No hay tasa válida; revisá la opción o la red.")
    else:
        st.sidebar.caption("Tabla de saldos en VES: **Dashboard**.")

    acc = next(a for a in accounts if str(a["id"]) == str(account_id))
    txs = load_transactions(sb, account_id)
    umap = load_user_map(sb)
    balance = compute_balance(acc, txs)

    st.title("Kenny Finanzas")
    st.caption("Cuenta compartida · cada movimiento queda registrado con tu usuario")

    tab_dash, tab_mov, tab_acc, tab_rep, tab_usr = st.tabs(
        ["Dashboard", "Movimientos", "Cuentas", "Reportes", "Usuarios"]
    )

    with tab_dash:
        st.markdown("### Cotizaciones (referencia)")
        _bcv_col, _p2p_intro = st.columns([1, 2])
        with _bcv_col:
            render_bcv_reference()
        with _p2p_intro:
            st.caption(
                "P2P: precios públicos en Binance; BCV: promedio oficial vía API pública. "
                "No son cotizaciones de contrato."
            )
        render_usdt_ves_p2p_reference()
        st.divider()
        st.markdown("### Patrimonio en bolívares (todas las cuentas)")
        st.caption(
            "Usa la tasa de la barra lateral. Activá el desglose solo si querés total y tabla "
            "(consulta movimientos de cada cuenta)."
        )
        _fx_detail = st.checkbox(
            "Mostrar desglose por cuenta y total ≈ VES",
            value=False,
            key="kf_fx_detail_all",
            help="Apagado por defecto: evita leer todas las cuentas en cada recarga.",
        )
        if _ves_u is not None and _ves_t is not None and _fx_detail:
            _rows, _tot = all_balances_with_ves(
                sb, accounts, load_transactions, compute_balance, _ves_u, _ves_t
            )
            st.metric("Total patrimonio ≈ VES", f"{float(_tot):,.2f}")
            st.dataframe(
                pd.DataFrame(_rows),
                use_container_width=True,
                hide_index=True,
            )
        elif _ves_u is not None and _ves_t is not None:
            st.info("Activá el desglose arriba para ver total y tabla por cuenta.")
        st.divider()
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
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Saldo calculado", f"{balance:,.2f} {acc.get('currency', 'USD')}")
        c2.metric("Saldo inicial", f'{_dec(acc.get("opening_balance")):,.2f}')
        c3.metric("Movimientos", len(txs))
        if _ves_u is not None and _ves_t is not None:
            _eq = to_ves(balance, str(acc.get("currency", "USD")), _ves_u, _ves_t)
            c4.metric(
                "Saldo ≈ VES",
                f"{_eq:,.2f}",
                help=f"Según tasa lateral: {_fx_caption[:120]}",
            )
        else:
            c4.metric("Saldo ≈ VES", "—", help="Elegí una tasa válida en la barra lateral.")

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
