"""
Kenny Finanzas — ingresos/egresos compartidos, login, tablero e importación Excel.
Supabase: schema.sql + patch_002 si la base ya existía sin usuarios.
"""

from __future__ import annotations

import re
import uuid
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client

from kf_account_cards import render_payment_method_cards
from kf_auth import gate_auth, logout
from kf_config import resolve_supabase_credentials
from kf_constants import (
    ACCOUNT_KIND_LABELS,
    CURRENCIES,
    EXPENSE_CATEGORIES,
    INCOME_BUSINESSES,
    INSTITUTION_APPS,
    INSTITUTION_BANKS,
    INSTITUTION_WALLET,
    TRANSFER_TAGS,
    WALLET_DEPOSIT_NETWORKS,
)
from kf_bcv import render_bcv_reference
from kf_dashboard import render_finance_dashboard
from kf_fx_convert import all_balances_native, all_balances_with_ves, resolve_ves_rates, to_ves
from kf_p2p_binance import render_usdt_ves_p2p_reference
from kf_reports import render_reports_page


def _pick_list_value(selected: str, other_text: str) -> str | None:
    if selected == "Otro":
        return other_text.strip() or None
    return selected


def _resolve_transfer_tag(tag_sel: str, tag_other: str) -> str | None:
    if tag_sel == "(ninguna)":
        return None
    if tag_sel == "Otro":
        return tag_other.strip() or None
    return tag_sel


def _split_list_or_other(raw: Any, choices: list[str]) -> tuple[str, str]:
    s = str(raw or "").strip()
    if not s:
        return choices[0], ""
    if s in choices:
        return s, ""
    return "Otro", s


def _transfer_tag_edit_defaults(raw: Any) -> tuple[str, str]:
    t = str(raw or "").strip()
    if not t:
        return "(ninguna)", ""
    if t in TRANSFER_TAGS:
        return t, ""
    return "Otro", t


def _tx_edit_row_label(t: dict[str, Any]) -> str:
    td = str(t.get("tx_date") or "")[:10]
    tt = str(t.get("tx_type") or "?")
    am = t.get("amount")
    de = (str(t.get("description") or "").replace("\n", " "))[:34]
    tid = str(t.get("id") or "")
    suf = f"{tid[:8]}…" if len(tid) >= 8 else tid
    return f"{td} · {tt} · {am} · {de} · id {suf}"


def _parse_tx_date_value(v: Any) -> date:
    if v is None:
        return date.today()
    return date.fromisoformat(str(v)[:10])


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
            "Creado con datos mínimos. En Supabase ejecutá **`patch_004_accounts_reports.sql`**, "
            "**`patch_005_account_kind.sql`** y **`patch_006_wallet_deposit.sql`** para guardar "
            "tipo, wallet extendida (UID, Pay ID, depósito on-chain) y clasificación."
        )


def kf_account_update_flexible(
    sb: Client, acc_id: str, row: dict[str, Any], owner_user_id: str | None = None
) -> tuple[bool, str | None]:
    try:
        q = sb.table("kf_account").update(row).eq("id", acc_id)
        if owner_user_id:
            q = q.eq("owner_user_id", str(owner_user_id))
        q.execute()
        return True, None
    except Exception as e:
        first = str(e)
        core = {k: v for k, v in row.items() if k in _KF_ACCOUNT_CORE_FIELDS}
        if not core:
            return False, first
        try:
            q2 = sb.table("kf_account").update(core).eq("id", acc_id)
            if owner_user_id:
                q2 = q2.eq("owner_user_id", str(owner_user_id))
            q2.execute()
        except Exception as e2:
            return False, f"{first}\n---\n{str(e2)}"
        return True, (
            "Guardado parcial. Ejecutá **`patch_004`**, **`patch_005_account_kind.sql`** y "
            "**`patch_006_wallet_deposit.sql`** en Supabase."
        )


def _account_owned_by_user(sb: Client, account_id: str, owner_user_id: str) -> bool:
    r = (
        sb.table("kf_account")
        .select("id")
        .eq("id", str(account_id))
        .eq("owner_user_id", str(owner_user_id))
        .limit(1)
        .execute()
    )
    return bool((r.data or []))


def kf_transaction_delete_secure(
    sb: Client, tx_id: str, owner_user_id: str
) -> tuple[bool, str | None]:
    tid = str(tx_id or "").strip()
    if not tid:
        return False, "Indicá un UUID."

    r = sb.table("kf_transaction").select("id,account_id,transfer_group_id").eq("id", tid).limit(1).execute()
    row = (r.data or [None])[0]
    if not row:
        return False, "No existe ese movimiento."

    acc_id = str(row.get("account_id") or "")
    if not _account_owned_by_user(sb, acc_id, owner_user_id):
        return False, "No podés borrar movimientos de otra persona."

    gid = str(row.get("transfer_group_id") or "").strip()
    if gid:
        r2 = sb.table("kf_transaction").select("id,account_id").eq("transfer_group_id", gid).limit(200).execute()
        rows = list(r2.data or [])
        if not rows:
            return False, "No se encontraron filas del grupo de traspaso."
        for rr in rows:
            aid = str(rr.get("account_id") or "")
            if not _account_owned_by_user(sb, aid, owner_user_id):
                return False, "Ese traspaso toca cuentas de otra persona; no se puede borrar desde este usuario."
        sb.table("kf_transaction").delete().eq("transfer_group_id", gid).execute()
        return True, "Traspaso eliminado (origen + destino)."

    sb.table("kf_transaction").delete().eq("id", tid).execute()
    return True, "Movimiento eliminado."


_TX_MIN_FIELDS = frozenset(
    {"account_id", "user_id", "tx_type", "amount", "tx_date", "description"}
)


def kf_transaction_insert_flexible(sb: Client, row: dict[str, Any]) -> tuple[bool, str | None]:
    """Inserta movimiento; sin patch_007 omite counterpart_account_id y transfer_group_id."""
    try:
        sb.table("kf_transaction").insert(row).execute()
        return True, None
    except Exception as e:
        first = str(e)
        core = {k: v for k, v in row.items() if k in _TX_MIN_FIELDS}
        for k in (
            "category",
            "business",
            "transaction_notes",
            "transfer_tag",
            "fee_amount",
            "fee_currency",
        ):
            if k in row and row[k] is not None:
                core[k] = row[k]
        try:
            sb.table("kf_transaction").insert(core).execute()
        except Exception as e2:
            return False, f"{first}\n---\n{str(e2)}"
        return True, (
            "Guardado sin enlace de traspaso. En Supabase ejecutá **`patch_007_transaction_counterpart.sql`**."
        )


def kf_transaction_update_flexible(sb: Client, tx_id: str, row: dict[str, Any]) -> tuple[bool, str | None]:
    """Actualiza kf_transaction; sin columnas de traspaso o metadatos reintenta con menos campos."""
    try:
        sb.table("kf_transaction").update(row).eq("id", tx_id).execute()
        return True, None
    except Exception as e:
        first = str(e)
    row2 = {k: v for k, v in row.items() if k not in ("counterpart_account_id", "transfer_group_id")}
    if row2 != row:
        try:
            sb.table("kf_transaction").update(row2).eq("id", tx_id).execute()
            return True, (
                "Movimiento actualizado; no se pudieron guardar columnas de enlace de traspaso. "
                "Si usás traspasos, ejecutá **`patch_007_transaction_counterpart.sql`**."
            )
        except Exception as e2:
            first = f"{first}\n---\n{str(e2)}"
    core_keys = (
        "account_id",
        "tx_type",
        "amount",
        "tx_date",
        "description",
        "category",
        "business",
        "transaction_notes",
        "transfer_tag",
        "fee_amount",
        "fee_currency",
    )
    core = {k: row2[k] for k in core_keys if k in row2}
    try:
        sb.table("kf_transaction").update(core).eq("id", tx_id).execute()
        return True, (
            "Se guardaron los datos principales; si categoría, comisión o notas no aplicaron, revisá la base."
        )
    except Exception as e3:
        return False, f"{first}\n---\n{str(e3)}"


def kf_transaction_delete_cascade(sb: Client, tx_id: str) -> tuple[bool, str | None, str]:
    """Elimina un movimiento por UUID. Si pertenece a un traspaso (`transfer_group_id`), borra ambas piernas."""
    tid = str(tx_id or "").strip()
    if not tid:
        return False, "Indicá un UUID.", ""
    try:
        r = (
            sb.table("kf_transaction")
            .select("id,transfer_group_id")
            .eq("id", tid)
            .limit(1)
            .execute()
        )
    except Exception as e:
        try:
            sb.table("kf_transaction").delete().eq("id", tid).execute()
            return True, None, "Movimiento eliminado (sin leer grupo de traspaso)."
        except Exception as e2:
            return False, f"{e}\n---\n{e2}", ""
    row = (r.data or [None])[0]
    if not row:
        return False, "No hay ningún movimiento con ese ID.", ""
    gid = row.get("transfer_group_id")
    if gid is not None and str(gid).strip():
        try:
            sb.table("kf_transaction").delete().eq("transfer_group_id", str(gid)).execute()
            return (
                True,
                None,
                "Traspaso eliminado: se quitaron **origen y destino**; los saldos vuelven como antes de ese traspaso.",
            )
        except Exception as e:
            return False, str(e), ""
    try:
        sb.table("kf_transaction").delete().eq("id", tid).execute()
        return True, None, "Movimiento eliminado."
    except Exception as e:
        return False, str(e), ""


def _traspaso_group_label(t: dict[str, Any], gid: str, opts: dict[str, str]) -> str:
    d = str(t.get("tx_date") or "")[:10]
    tt = str(t.get("tx_type") or "")
    amt = t.get("amount")
    de = (str(t.get("description") or "").replace("\n", " "))[:36]
    sa = str(t.get("account_id") or "")
    acc_l = str(opts.get(sa, "?"))[:30]
    return f"{d} · {tt} · {amt} {de}… · {acc_l} · grupo {str(gid)[:8]}…"


def _is_transfer_tx(t: dict[str, Any]) -> bool:
    gid = str(t.get("transfer_group_id") or "").strip()
    if gid:
        return True
    tag = str(t.get("transfer_tag") or "").strip().lower()
    return "traspaso" in tag


def _transfer_group_row(gid: str, rows: list[dict[str, Any]], opts: dict[str, str]) -> dict[str, Any]:
    out = next((r for r in rows if str(r.get("tx_type") or "") == "egreso"), None)
    inn = next((r for r in rows if str(r.get("tx_type") or "") == "ingreso"), None)
    ref = out or inn or rows[0]
    dt = str(ref.get("tx_date") or "")[:10]
    desc = str(ref.get("description") or "").replace("\n", " ")[:90]
    out_acc = str(opts.get(str(out.get("account_id")), "—")) if out else "—"
    in_acc = str(opts.get(str(inn.get("account_id")), "—")) if inn else "—"
    out_amt = float(out.get("amount") or 0) if out else 0.0
    in_amt = float(inn.get("amount") or 0) if inn else 0.0
    diff_amt = out_amt - in_amt
    return {
        "fecha": dt,
        "origen": out_acc,
        "egreso": out_amt if out else None,
        "destino": in_acc,
        "ingreso": in_amt if inn else None,
        "diferencia": diff_amt if (out or inn) else None,
        "descripcion": desc,
        "grupo": f"{gid[:8]}…" if len(gid) > 8 else gid,
        "group_id": gid,
    }


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


def _wallet_crypto_nulls() -> dict[str, Any]:
    return {
        "exchange_uid": None,
        "pay_id": None,
        "deposit_address": None,
        "deposit_network": None,
        "deposit_memo": None,
    }


def _nulls_for_kind(kind: str) -> dict[str, Any]:
    if kind == "banco":
        return {
            "wallet_address": None,
            "zelle_email_or_phone": None,
            **_wallet_crypto_nulls(),
        }
    if kind == "wallet":
        return {
            "account_number": None,
            "routing_or_swift": None,
            "zelle_email_or_phone": None,
        }
    if kind == "app_pagos":
        return {
            "wallet_address": None,
            "account_number": None,
            "routing_or_swift": None,
            **_wallet_crypto_nulls(),
        }
    return {}


def _deposit_network_value(selected: str) -> str | None:
    if not selected or selected.strip() == "—":
        return None
    return selected.strip() or None


def _wallet_row_dict(
    *,
    exchange_uid: str,
    pay_id: str,
    deposit_address: str,
    deposit_network_sel: str,
    deposit_memo: str,
    wallet_address_legacy: str,
) -> dict[str, Any]:
    return {
        "exchange_uid": exchange_uid.strip() or None,
        "pay_id": pay_id.strip() or None,
        "deposit_address": deposit_address.strip() or None,
        "deposit_network": _deposit_network_value(deposit_network_sel),
        "deposit_memo": deposit_memo.strip() or None,
        "wallet_address": wallet_address_legacy.strip() or None,
    }


def page_accounts(sb: Client, accounts: list[dict[str, Any]], user: dict[str, Any]) -> None:
    st.subheader("Cuentas y métodos de pago")
    st.caption(
        "**Banco** = Banesco, BofA, Banca Amiga, Pago Móvil… "
        "**Wallet** = Binance / USDT / on-chain. "
        "**App** = Zinly, Zelle."
    )
    st.info(
        "SQL en Supabase: **`patch_004`**, **`patch_005_account_kind.sql`**, "
        "**`patch_006_wallet_deposit.sql`** y **`patch_008_owner_user_scope.sql`**."
    )

    render_payment_method_cards(
        accounts,
        heading="Vista tarjeta (como métodos P2P)",
    )
    st.divider()

<<<<<<< Updated upstream
=======
    by_k: dict[str, list[dict[str, Any]]] = {"banco": [], "wallet": [], "app_pagos": []}
    for a in accounts:
        by_k[_infer_account_kind(a)].append(a)

    st.markdown("### Dar de alta por tipo")
    for kind, title in (
        ("banco", "Cuentas bancarias"),
        ("wallet", "Wallets y crypto"),
        ("app_pagos", "Apps de pago (Zinly, Zelle…)"),
    ):
        st.markdown(f"#### {title}")
        if not by_k[kind]:
            st.caption("Ningún registro de este tipo todavía.")

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
                            "owner_user_id": str(user["id"]),
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
                st.caption(
                    "En Binance: **UID** y **Pay ID** salen del perfil / Pay; la **dirección de depósito** "
                    "la copiás en Wallet → Depositar → moneda y **red** (TRC20, BEP20, etc.)."
                )
                with st.form("add_wallet"):
                    lb = st.text_input("Nombre (ej. Binance spot USDT)", key="aw_lb")
                    cur = st.selectbox("Moneda", CURRENCIES, index=CURRENCIES.index("USDT"), key="aw_cur")
                    ik = st.selectbox("Tipo", INSTITUTION_WALLET, key="aw_ik")
                    io = st.text_input("Si Otro, especificá", key="aw_io")
                    st.markdown("**Cuenta en el exchange**")
                    e_uid = st.text_input("UID del exchange (ej. Binance)", key="aw_euid")
                    pay_id = st.text_input("Pay ID (Binance Pay u otro)", key="aw_pay")
                    st.markdown("**Depósito on-chain** (para que te envíen desde fuera)")
                    dep_net = st.selectbox("Red de depósito", WALLET_DEPOSIT_NETWORKS, key="aw_depnet")
                    dep_addr = st.text_input("Dirección de depósito (esa moneda + red)", key="aw_depaddr")
                    dep_memo = st.text_input("Memo / Tag (si la red lo pide)", key="aw_depmemo")
                    waddr = st.text_input(
                        "Otra referencia (opcional, texto libre)",
                        key="aw_w",
                        help="Legado: podés dejar vacío si completaste UID / Pay / dirección arriba.",
                    )
                    hol = st.text_input("Titular (opcional)", key="aw_h")
                    nt = st.text_area("Notas (futuros, redes…)", height=60, key="aw_nt")
                    op = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f", key="aw_op")
                    od = st.date_input("Fecha saldo", value=date.today(), key="aw_od")
                    if st.form_submit_button("Crear wallet"):
                        inst = _pick_list_value(ik, io) or ik
                        row = {
                            "owner_user_id": str(user["id"]),
                            "account_kind": "wallet",
                            "label": lb.strip() or "Wallet",
                            "currency": cur,
                            "bank_name": inst,
                            "institution_kind": inst,
                            "holder_name": hol.strip() or None,
                            "notes": nt.strip() or None,
                            "opening_balance": float(op),
                            "opening_balance_date": od.isoformat(),
                            **_nulls_for_kind("wallet"),
                            **_wallet_row_dict(
                                exchange_uid=e_uid,
                                pay_id=pay_id,
                                deposit_address=dep_addr,
                                deposit_network_sel=str(dep_net),
                                deposit_memo=dep_memo,
                                wallet_address_legacy=waddr,
                            ),
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
                            "owner_user_id": str(user["id"]),
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

>>>>>>> Stashed changes
    st.subheader("Editar registro")
    opts = {
        str(a["id"]): f'[{ACCOUNT_KIND_LABELS.get(_infer_account_kind(a), "?")}] {a.get("label")} ({a.get("currency")})'
        for a in accounts
    }
    _KF_EDIT_SEL = "kf_accounts_edit_select"
    opts_keys = list(opts.keys())
    if _KF_EDIT_SEL not in st.session_state or st.session_state[_KF_EDIT_SEL] not in opts_keys:
        st.session_state[_KF_EDIT_SEL] = opts_keys[0]
    st.caption("Podés usar el desplegable o el botón **✏️ Editar** bajo cada tarjeta.")
    pick = st.selectbox(
        "Cuenta a editar",
        options=opts_keys,
        format_func=lambda i: opts[i],
        key=_KF_EDIT_SEL,
    )
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
            st.caption("UID / Pay / depósito: **`patch_006_wallet_deposit.sql`** en Supabase si falla al guardar.")
            e_exuid = st.text_input(
                "UID del exchange",
                value=str(acc.get("exchange_uid") or ""),
                key="edit_exuid",
            )
            e_pay = st.text_input(
                "Pay ID",
                value=str(acc.get("pay_id") or ""),
                key="edit_payid",
            )
            dn0 = acc.get("deposit_network") or "—"
            dn_idx = (
                WALLET_DEPOSIT_NETWORKS.index(dn0)
                if dn0 in WALLET_DEPOSIT_NETWORKS
                else 0
            )
            e_depnet = st.selectbox(
                "Red de depósito",
                WALLET_DEPOSIT_NETWORKS,
                index=dn_idx,
                key="edit_depnet",
            )
            e_depaddr = st.text_input(
                "Dirección de depósito on-chain",
                value=str(acc.get("deposit_address") or ""),
                key="edit_depaddr",
            )
            e_depmemo = st.text_input(
                "Memo / Tag",
                value=str(acc.get("deposit_memo") or ""),
                key="edit_depmemo",
            )
            ewallet = st.text_input(
                "Otra referencia (opcional)",
                value=str(acc.get("wallet_address") or ""),
                key="edit_wleg",
            )
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
                        **_wallet_row_dict(
                            exchange_uid=e_exuid,
                            pay_id=e_pay,
                            deposit_address=e_depaddr,
                            deposit_network_sel=str(e_depnet),
                            deposit_memo=e_depmemo,
                            wallet_address_legacy=ewallet,
                        ),
                    }
                )
            else:
                base.update(
                    {
                        "bank_name": ebank.strip() or inst_e,
                        "zelle_email_or_phone": ezelle.strip() or None,
                    }
                )
            ok, wmsg = kf_account_update_flexible(sb, pick, base, str(user["id"]))
            if ok:
                if wmsg:
                    st.warning(wmsg)
                else:
                    st.success("Actualizado.")
                st.rerun()
            else:
                st.error("No se pudo guardar.")
                st.code(wmsg or "")

    st.divider()


    by_k: dict[str, list[dict[str, Any]]] = {"banco": [], "wallet": [], "app_pagos": []}
    for a in accounts:
        by_k[_infer_account_kind(a)].append(a)

    st.markdown("### Dar de alta por tipo")
    for kind, title in (
        ("banco", "Cuentas bancarias"),
        ("wallet", "Wallets y crypto"),
        ("app_pagos", "Apps de pago (Zinly, Zelle…)"),
    ):
        st.markdown(f"#### {title}")
        if not by_k[kind]:
            st.caption("Ningún registro de este tipo todavía.")

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
                            "owner_user_id": str(user["id"]),
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
                st.caption(
                    "En Binance: **UID** y **Pay ID** salen del perfil / Pay; la **dirección de depósito** "
                    "la copiás en Wallet → Depositar → moneda y **red** (TRC20, BEP20, etc.)."
                )
                with st.form("add_wallet"):
                    lb = st.text_input("Nombre (ej. Binance spot USDT)", key="aw_lb")
                    cur = st.selectbox("Moneda", CURRENCIES, index=CURRENCIES.index("USDT"), key="aw_cur")
                    ik = st.selectbox("Tipo", INSTITUTION_WALLET, key="aw_ik")
                    io = st.text_input("Si Otro, especificá", key="aw_io")
                    st.markdown("**Cuenta en el exchange**")
                    e_uid = st.text_input("UID del exchange (ej. Binance)", key="aw_euid")
                    pay_id = st.text_input("Pay ID (Binance Pay u otro)", key="aw_pay")
                    st.markdown("**Depósito on-chain** (para que te envíen desde fuera)")
                    dep_net = st.selectbox("Red de depósito", WALLET_DEPOSIT_NETWORKS, key="aw_depnet")
                    dep_addr = st.text_input("Dirección de depósito (esa moneda + red)", key="aw_depaddr")
                    dep_memo = st.text_input("Memo / Tag (si la red lo pide)", key="aw_depmemo")
                    waddr = st.text_input(
                        "Otra referencia (opcional, texto libre)",
                        key="aw_w",
                        help="Legado: podés dejar vacío si completaste UID / Pay / dirección arriba.",
                    )
                    hol = st.text_input("Titular (opcional)", key="aw_h")
                    nt = st.text_area("Notas (futuros, redes…)", height=60, key="aw_nt")
                    op = st.number_input("Saldo inicial", min_value=-1e15, value=0.0, format="%.8f", key="aw_op")
                    od = st.date_input("Fecha saldo", value=date.today(), key="aw_od")
                    if st.form_submit_button("Crear wallet"):
                        inst = _pick_list_value(ik, io) or ik
                        row = {
                            "owner_user_id": str(user["id"]),
                            "account_kind": "wallet",
                            "label": lb.strip() or "Wallet",
                            "currency": cur,
                            "bank_name": inst,
                            "institution_kind": inst,
                            "holder_name": hol.strip() or None,
                            "notes": nt.strip() or None,
                            "opening_balance": float(op),
                            "opening_balance_date": od.isoformat(),
                            **_nulls_for_kind("wallet"),
                            **_wallet_row_dict(
                                exchange_uid=e_uid,
                                pay_id=pay_id,
                                deposit_address=dep_addr,
                                deposit_network_sel=str(dep_net),
                                deposit_memo=dep_memo,
                                wallet_address_legacy=waddr,
                            ),
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
                            "owner_user_id": str(user["id"]),
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



def _require_jwt_supabase_key(key: str) -> None:
    """supabase-py 2.8 solo acepta JWT (eyJ...); las claves nuevas sb_secret_ fallan al crear el cliente."""
    import re

    if re.match(
        r"^[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$",
        key,
    ):
        return
    if key.startswith("sb_secret_") or key.startswith("sb_publishable_"):
        raise RuntimeError(
            "La clave que pegaste es la **nueva** de Supabase (`sb_secret_...` / `sb_publishable_...`). "
            "Esta versión de la app usa `supabase-py` 2.8, que solo acepta la clave **JWT** (texto largo que empieza con **eyJ**).\n\n"
            "En Supabase: **Project Settings → API** → buscá **Legacy API keys** (o “anon” / “service_role”) "
            "y copiá **service_role** en `SUPABASE_KEY`. No la clave `sb_secret_`."
        )
    raise RuntimeError(
        "SUPABASE_KEY no tiene formato JWT (debería empezar con `eyJ`). "
        "Revisá que copiaste la clave **service_role** completa del apartado legacy en Project Settings → API."
    )


def get_supabase() -> Client:
    from supabase import create_client

    u, k = resolve_supabase_credentials()

    if not u or not k:
        raise RuntimeError(
            "Faltan SUPABASE_URL y/o SUPABASE_KEY.\n\n"
            "· Creá el archivo **`kenny finanzas/.streamlit/secrets.toml`** copiando "
            "`secrets.toml.example` y pegá la URL y la **service_role** del proyecto "
            "Supabase **solo de finanzas personales** (no el del ERP Movi).\n"
            "· Si corrés Streamlit desde la carpeta Movi, igualmente ese archivo debe existir "
            "junto a esta app (Streamlit lo busca en la carpeta del `app.py`).\n"
            "· En la nube: Streamlit Cloud → Settings → Secrets.\n"
            "· Opcional: variables de entorno SUPABASE_URL y SUPABASE_KEY."
        )

    if not u.startswith(("https://", "http://")):
        raise RuntimeError("SUPABASE_URL debe ser una URL (https://....supabase.co).")

    if "tu-proyecto" in u.lower() or "pega_aqui" in k.lower() or "pega_aqui" in u.lower():
        raise RuntimeError(
            "Seguís con los textos de ejemplo en secrets (TU-PROYECTO / pega_aqui…). "
            "Reemplazalos por la URL y la clave reales de Supabase → Project Settings → API."
        )

    _require_jwt_supabase_key(k)
    return create_client(u, k)


def _dec(x: Any) -> Decimal:
    if x is None:
        return Decimal("0")
    return Decimal(str(x))


def load_accounts(sb: Client, owner_user_id: str) -> list[dict[str, Any]]:
    try:
        r = (
            sb.table("kf_account")
            .select("*")
            .eq("owner_user_id", str(owner_user_id))
            .order("created_at")
            .execute()
        )
        return list(r.data or [])
    except Exception as e:
        # Compatibilidad temporal para bases que aun no ejecutaron patch_008.
        if "owner_user_id" in str(e):
            st.warning(
                "Tu base aun no tiene aislamiento multiusuario por propietario. "
                "Ejecuta **`supabase/patch_008_owner_user_scope.sql`**."
            )
            r = sb.table("kf_account").select("*").order("created_at").execute()
            return list(r.data or [])
        raise


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


def load_transactions_for_accounts(
    sb: Client, account_ids: list[str], limit: int = 12000
) -> list[dict[str, Any]]:
    if not account_ids:
        return []
    r = (
        sb.table("kf_transaction")
        .select("*")
        .in_("account_id", account_ids)
        .order("tx_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
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


def _inject_responsive_styles() -> None:
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.85rem !important;
                padding-right: 0.85rem !important;
            }
        }
        div[data-testid="stVerticalBlock"] button { min-height: 2.75rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _pick_account_id_sidebar(opts: dict[str, str]) -> str:
    keys = list(opts.keys())
    if not keys:
        return ""
    if len(keys) == 1:
        return keys[0]
    if (
        st.session_state.get("kf_sidebar_account") is None
        or st.session_state.get("kf_sidebar_account") not in opts
    ):
        st.session_state.kf_sidebar_account = keys[0]
    st.sidebar.caption("Atajos · misma lista que «Cuenta activa»")
    for row_start in range(0, len(keys), 2):
        c_a, c_b = st.sidebar.columns(2)
        with c_a:
            k = keys[row_start]
            lab = str(opts[k])
            short = (lab[:16] + "…") if len(lab) > 18 else lab
            if st.button(short, key=f"kf_accsh_{k}", use_container_width=True):
                st.session_state.kf_sidebar_account = k
                st.rerun()
        with c_b:
            if row_start + 1 < len(keys):
                k2 = keys[row_start + 1]
                lab2 = str(opts[k2])
                short2 = (lab2[:16] + "…") if len(lab2) > 18 else lab2
                if st.button(short2, key=f"kf_accsh_{k2}", use_container_width=True):
                    st.session_state.kf_sidebar_account = k2
                    st.rerun()
    return str(
        st.sidebar.selectbox(
            "Cuenta activa",
            options=keys,
            format_func=lambda x: opts[x],
            key="kf_sidebar_account",
        )
    )


def _safe_export_filename_part(s: str) -> str:
    t = re.sub(r"[^\w\-]+", "_", (s or "").strip(), flags=re.I).strip("_")
    return (t[:36] if t else "cuenta")


def _transactions_export_dataframe(
    txs: list[dict[str, Any]],
    umap: dict[str, str],
    opts: dict[str, str],
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for t in txs:
        td = t.get("tx_date")
        if td is None:
            continue
        try:
            d = date.fromisoformat(str(td)[:10])
        except ValueError:
            continue
        if d < date_from or d > date_to:
            continue
        cid = str(t.get("counterpart_account_id") or "").strip()
        contra = opts.get(cid, cid or "—")
        rows.append(
            {
                "fecha": d.isoformat(),
                "tipo": t.get("tx_type"),
                "monto": t.get("amount"),
                "comision": t.get("fee_amount"),
                "moneda_comision": t.get("fee_currency"),
                "negocio": t.get("business"),
                "rubro": t.get("category"),
                "etiqueta": t.get("transfer_tag"),
                "cuenta_relacionada": contra,
                "descripcion": t.get("description"),
                "notas": t.get("transaction_notes"),
                "registro_usuario": umap.get(str(t.get("user_id")), "—"),
                "id": str(t.get("id", "")),
            }
        )
    return pd.DataFrame(rows)


def _df_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Movimientos")
    return buf.getvalue()


def main() -> None:
    st.set_page_config(
        page_title="Kenny Finanzas",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    try:
        sb = get_supabase()
    except Exception as e:
        st.error("No se pudo iniciar el cliente de Supabase. Revisá URL, clave y Secrets.")
        st.markdown(str(e))
        st.caption(
            "Secrets: carpeta **`.streamlit/secrets.toml`** junto a `app.py`, o Streamlit Cloud → Settings → Secrets. "
            "La clave debe ser **service_role** en formato JWT (**eyJ...**), no `sb_secret_`. "
            "Guía: `DEPLOY_STREAMLIT_CLOUD.md`."
        )
        st.stop()

    user = gate_auth(sb)
    if not user:
        return

    _inject_responsive_styles()

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
        accounts = load_accounts(sb, str(user["id"]))
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
                            "owner_user_id": str(user["id"]),
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
                st.markdown("**Exchange**")
                nw_uid = st.text_input("UID (Binance)", key="nw_euid")
                nw_pay = st.text_input("Pay ID", key="nw_pay")
                st.markdown("**Depósito on-chain**")
                nw_net = st.selectbox("Red", WALLET_DEPOSIT_NETWORKS, key="nw_depnet")
                nw_dep = st.text_input("Dirección de depósito", key="nw_depaddr")
                nw_memo = st.text_input("Memo / Tag", key="nw_depmemo")
                waddr = st.text_input("Otra referencia (opcional)", key="nw_wleg")
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
                            "owner_user_id": str(user["id"]),
                            "label": label.strip() or "Wallet",
                            "currency": cur0,
                            "bank_name": inst,
                            "institution_kind": inst,
                            "holder_name": holder.strip() or None,
                            "notes": notes.strip() or None,
                            "opening_balance": float(opening),
                            "opening_balance_date": ob_date.isoformat(),
                            **_nulls_for_kind("wallet"),
                            **_wallet_row_dict(
                                exchange_uid=nw_uid,
                                pay_id=nw_pay,
                                deposit_address=nw_dep,
                                deposit_network_sel=str(nw_net),
                                deposit_memo=nw_memo,
                                wallet_address_legacy=waddr,
                            ),
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
                            "owner_user_id": str(user["id"]),
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
    account_id = _pick_account_id_sidebar(opts)

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
    st.caption("Espacio personal multiusuario · cada persona ve sus propias cuentas y movimientos")

    tab_dash, tab_mov, tab_acc, tab_rep, tab_usr = st.tabs(
        ["Dashboard", "Movimientos", "Cuentas", "Reportes", "Usuarios"]
    )

    with tab_dash:
        st.markdown("### Saldos por cuenta (todos tus bancos / cuentas)")
        st.caption(
            "Acá ves el **saldo calculado** de **cada** cuenta a la vez. Más abajo, los gráficos usan solo la **cuenta activa** del lateral."
        )
        try:
            _all_bal = all_balances_native(sb, accounts, load_transactions, compute_balance)
            st.dataframe(
                pd.DataFrame(_all_bal),
                use_container_width=True,
                hide_index=True,
            )
        except Exception as e:
            st.warning("No se pudieron cargar todos los saldos de una vez.")
            st.code(str(e))
        st.divider()
        st.markdown("### Gráficos (cuenta del lateral)")
        try:
            render_finance_dashboard(
                txs,
                _dec(acc.get("opening_balance")),
                str(acc.get("currency", "USD")),
            )
        except Exception as e:
            st.error("El tablero falló al cargar. Probá recargar la página o revisá los datos.")
            st.code(str(e))
        st.divider()
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
            _opt_keys = list(opts.keys())
            _def_acc_idx = (
                _opt_keys.index(str(account_id)) if str(account_id) in _opt_keys else 0
            )

            st.caption(
                "**Ingreso / egreso:** indicá en qué **cuenta** queda el movimiento (Zelle, BofA, Binance, bolívares…). "
                "No tenés que cambiar la cuenta del lateral solo para registrar; el listado de abajo sigue siendo la cuenta activa."
            )
            tab_in, tab_out, tab_tr = st.tabs(
                ["Ingreso (negocio u otros)", "Egreso (gastos)", "Traspaso entre cuentas"]
            )

            with tab_in:
                cta_in = st.selectbox(
                    "Cuenta que **recibió** este ingreso",
                    _opt_keys,
                    index=_def_acc_idx,
                    format_func=lambda i: opts[i],
                    key="kf_tx_in_account",
                )
                acc_in = next(a for a in accounts if str(a["id"]) == str(cta_in))
                _acur_in = str(acc_in.get("currency", "USD"))
                _step_in, _fmt_in = _amount_input_format(_acur_in)
                with st.form("tx_ingreso"):
                    tx_date = st.date_input("Fecha", value=date.today(), key="txin_d")
                    amount = st.number_input(
                        f"Monto ({_acur_in})",
                        min_value=float(_step_in),
                        value=10.0 if _acur_in != "USDT" else 0.01,
                        step=float(_step_in),
                        format=_fmt_in,
                        key="txin_amt",
                    )
                    description = st.text_input("Descripción / concepto", key="txin_desc")
                    biz_sel = st.selectbox(
                        "Negocio / fuente",
                        INCOME_BUSINESSES,
                        index=0,
                        key="txin_biz",
                    )
                    biz_other = st.text_input("Si negocio = Otro, nombre", key="txin_bio")
                    st.caption(
                        "**Etiqueta de tramo (abajo):** opcional; ej. «Zelle → Binance». "
                        "**No** es la cuenta: la cuenta del dinero es la que elegiste arriba (**Cuenta que recibió**)."
                    )
                    tag_opts = ["(ninguna)"] + TRANSFER_TAGS
                    tag_sel = st.selectbox(
                        "Etiqueta de tramo / motivo (opcional)",
                        tag_opts,
                        key="txin_tag",
                    )
                    tag_other = st.text_input("Texto si elegiste «Otro» en la etiqueta", key="txin_tgo")
                    fee_amt = st.number_input(
                        "Comisión / fee (opcional)",
                        min_value=0.0,
                        value=0.0,
                        step=float(_step_in),
                        format=_fmt_in,
                        key="txin_fee",
                    )
                    fee_cur_opts = list(dict.fromkeys([_acur_in, "USD", "USDT", "VES"]))
                    fee_cur = st.selectbox("Moneda de la comisión", fee_cur_opts, key="txin_fc")
                    tx_notes = st.text_area("Notas (opcional)", height=50, key="txin_nt")
                    if st.form_submit_button("Guardar ingreso"):
                        business = _pick_list_value(biz_sel, biz_other)
                        transfer_tag = _resolve_transfer_tag(tag_sel, tag_other)
                        row_ins: dict[str, Any] = {
                            "account_id": str(cta_in),
                            "user_id": user["id"],
                            "tx_type": "ingreso",
                            "amount": float(amount),
                            "tx_date": tx_date.isoformat(),
                            "description": description.strip() or "(sin descripción)",
                            "category": None,
                            "business": business,
                            "transfer_tag": transfer_tag,
                            "transaction_notes": tx_notes.strip() or None,
                        }
                        if fee_amt and float(fee_amt) > 0:
                            row_ins["fee_amount"] = float(fee_amt)
                            row_ins["fee_currency"] = fee_cur
                        ok_tx, wmsg_tx = kf_transaction_insert_flexible(sb, row_ins)
                        if ok_tx:
                            if wmsg_tx:
                                st.warning(wmsg_tx)
                            else:
                                st.success("Ingreso guardado.")
                            st.rerun()
                        else:
                            st.error("No se pudo guardar.")
                            st.code(wmsg_tx or "")

            with tab_out:
                cta_out = st.selectbox(
                    "Cuenta de la que **sale** este gasto",
                    _opt_keys,
                    index=_def_acc_idx,
                    format_func=lambda i: opts[i],
                    key="kf_tx_out_account",
                )
                acc_out = next(a for a in accounts if str(a["id"]) == str(cta_out))
                _acur_out = str(acc_out.get("currency", "USD"))
                _step_out, _fmt_out = _amount_input_format(_acur_out)
                with st.form("tx_egreso"):
                    tx_date = st.date_input("Fecha", value=date.today(), key="txout_d")
                    amount = st.number_input(
                        f"Monto ({_acur_out})",
                        min_value=float(_step_out),
                        value=10.0 if _acur_out != "USDT" else 0.01,
                        step=float(_step_out),
                        format=_fmt_out,
                        key="txout_amt",
                    )
                    description = st.text_input("Descripción / concepto", key="txout_desc")
                    cat_sel = st.selectbox(
                        "Rubro del gasto",
                        EXPENSE_CATEGORIES,
                        index=0,
                        key="txout_cat",
                    )
                    cat_other = st.text_input("Si rubro = Otro, nombre", key="txout_cao")
                    st.caption(
                        "**Etiqueta de tramo (abajo):** opcional. "
                        "La **cuenta** del gasto es la que elegiste arriba (**Cuenta de la que sale**)."
                    )
                    tag_opts2 = ["(ninguna)"] + TRANSFER_TAGS
                    tag_sel2 = st.selectbox(
                        "Etiqueta de tramo / motivo (opcional)",
                        tag_opts2,
                        key="txout_tag",
                    )
                    tag_other2 = st.text_input("Texto si elegiste «Otro» en la etiqueta", key="txout_tgo")
                    fee_amt2 = st.number_input(
                        "Comisión / fee (opcional)",
                        min_value=0.0,
                        value=0.0,
                        step=float(_step_out),
                        format=_fmt_out,
                        key="txout_fee",
                    )
                    fee_cur_opts2 = list(dict.fromkeys([_acur_out, "USD", "USDT", "VES"]))
                    fee_cur2 = st.selectbox("Moneda de la comisión", fee_cur_opts2, key="txout_fc")
                    tx_notes2 = st.text_area("Notas (opcional)", height=50, key="txout_nt")
                    if st.form_submit_button("Guardar egreso"):
                        category = _pick_list_value(cat_sel, cat_other)
                        transfer_tag = _resolve_transfer_tag(tag_sel2, tag_other2)
                        row_ins = {
                            "account_id": str(cta_out),
                            "user_id": user["id"],
                            "tx_type": "egreso",
                            "amount": float(amount),
                            "tx_date": tx_date.isoformat(),
                            "description": description.strip() or "(sin descripción)",
                            "category": category,
                            "business": None,
                            "transfer_tag": transfer_tag,
                            "transaction_notes": tx_notes2.strip() or None,
                        }
                        if fee_amt2 and float(fee_amt2) > 0:
                            row_ins["fee_amount"] = float(fee_amt2)
                            row_ins["fee_currency"] = fee_cur2
                        ok_tx, wmsg_tx = kf_transaction_insert_flexible(sb, row_ins)
                        if ok_tx:
                            if wmsg_tx:
                                st.warning(wmsg_tx)
                            else:
                                st.success("Egreso guardado.")
                            st.rerun()
                        else:
                            st.error("No se pudo guardar.")
                            st.code(wmsg_tx or "")

            with tab_tr:
                st.caption(
                    "Genera **dos movimientos**: egreso en el origen e ingreso en el destino (ej. Zelle USD → Binance USDT por P2P). "
                    "Si las monedas son distintas, podés usar **Tasa P2P** (ej. Bs por USDT) para calcular lo que entra en el banco en bolívares. "
                    "Los saldos de cada cuenta se actualizan solos."
                )
                _to_idx_tr = 1 if len(_opt_keys) > 1 else 0
                with st.form("tx_traspaso"):
                    fc1, fc2 = st.columns(2)
                    with fc1:
                        fid = st.selectbox(
                            "Origen (egreso)",
                            _opt_keys,
                            index=0,
                            format_func=lambda i: opts[i],
                            key="kf_tr_from",
                        )
                    with fc2:
                        tid = st.selectbox(
                            "Destino (ingreso)",
                            _opt_keys,
                            index=_to_idx_tr,
                            format_func=lambda i: opts[i],
                            key="kf_tr_to",
                        )
                    tx_date_tr = st.date_input("Fecha", value=date.today(), key="txtr_d")
                    desc_tr = st.text_input("Descripción (ej. P2P Zelle → Binance)", key="txtr_desc")
                    acc_fr = next(a for a in accounts if str(a["id"]) == str(fid))
                    acc_to = next(a for a in accounts if str(a["id"]) == str(tid))
                    cur_fr = str(acc_fr.get("currency", "USD"))
                    cur_to = str(acc_to.get("currency", "USD"))
                    st.caption(f"Moneda origen **{cur_fr}** → Moneda destino **{cur_to}**")
                    if cur_fr == cur_to:
                        m_rec = st.number_input(
                            f"Monto que **entra** en destino ({cur_to})",
                            min_value=0.00000001,
                            value=10.0 if cur_to != "USDT" else 0.01,
                            step=_amount_input_format(cur_to)[0],
                            format=_amount_input_format(cur_to)[1],
                            key="txtr_rec",
                        )
                        m_fee = st.number_input(
                            f"Comisión / diferencia (sale del origen, {cur_fr}; no suma al destino)",
                            min_value=0.0,
                            value=0.0,
                            step=_amount_input_format(cur_fr)[0],
                            format=_amount_input_format(cur_fr)[1],
                            key="txtr_fee",
                        )
                        m_send = float(m_rec) + float(m_fee)
                    else:
                        tr_cross_mode = st.radio(
                            "Cómo definir el monto en destino (moneda distinta)",
                            [
                                "Manual — cargo lo que sale y lo que entra",
                                "Tasa P2P / cambio — calculo lo que entra en destino",
                            ],
                            key="txtr_xmode",
                            horizontal=True,
                        )
                        m_send = float(
                            st.number_input(
                                f"Monto que **sale** del origen ({cur_fr}) — incluí fees del camino si querés",
                                min_value=0.00000001,
                                value=10.0 if cur_fr != "USDT" else 0.01,
                                step=_amount_input_format(cur_fr)[0],
                                format=_amount_input_format(cur_fr)[1],
                                key="txtr_send",
                            )
                        )
                        if tr_cross_mode.startswith("Manual"):
                            m_rec = float(
                                st.number_input(
                                    f"Monto que **entra** al destino ({cur_to})",
                                    min_value=0.00000001,
                                    value=10.0 if cur_to != "USDT" else 0.01,
                                    step=_amount_input_format(cur_to)[0],
                                    format=_amount_input_format(cur_to)[1],
                                    key="txtr_recv",
                                )
                            )
                        else:
                            st.caption(
                                f"**Tasa** = cuántos **{cur_to}** recibís por **cada 1 {cur_fr}** que sale del origen. "
                                f"Ej.: vendés **USDT** y cobrás en **bolívares**: si en Binance P2P cerraste a **350 Bs por USDT**, "
                                f"poné **350** abajo. El banco/cuenta en **{cur_to}** se acredita con el resultado."
                            )
                            _r_step, _r_fmt = (
                                (0.000001, "%.6f")
                                if cur_to == "USDT"
                                else (0.01, "%.2f")
                            )
                            _r_default = (
                                350.0
                                if cur_fr == "USDT" and cur_to == "VES"
                                else (0.0001 if cur_to == "USDT" else 1.0)
                            )
                            rate = float(
                                st.number_input(
                                    f"{cur_to} por cada 1 {cur_fr} (precio al que vendiste / compraste)",
                                    min_value=float(_r_step),
                                    value=float(_r_default),
                                    step=float(_r_step),
                                    format=_r_fmt,
                                    key="txtr_rate",
                                )
                            )
                            m_rec = m_send * rate
                            _mr = f"{m_rec:,.6f}" if cur_to == "USDT" else f"{m_rec:,.2f}"
                            st.success(
                                f"En **{acc_to.get('label') or 'destino'}** entrará **{_mr} {cur_to}** "
                                f"(= {m_send:g} {cur_fr} × {rate:g})."
                            )
                    tx_notes_tr = st.text_area("Notas (opcional)", height=40, key="txtr_nt")
                    if st.form_submit_button("Registrar traspaso"):
                        if str(fid) == str(tid):
                            st.error("Origen y destino no pueden ser la misma cuenta.")
                        else:
                            gid = str(uuid.uuid4())
                            lbl_f = str(acc_fr.get("label") or "Origen")
                            lbl_t = str(acc_to.get("label") or "Destino")
                            base_desc = (desc_tr.strip() or "Traspaso interno")[:200]
                            row_out: dict[str, Any] = {
                                "account_id": str(fid),
                                "user_id": user["id"],
                                "tx_type": "egreso",
                                "amount": float(m_send),
                                "tx_date": tx_date_tr.isoformat(),
                                "description": f"{base_desc} → {lbl_t}",
                                "category": None,
                                "business": None,
                                "transfer_tag": "Traspaso interno",
                                "transaction_notes": tx_notes_tr.strip() or None,
                                "counterpart_account_id": str(tid),
                                "transfer_group_id": gid,
                            }
                            row_in: dict[str, Any] = {
                                "account_id": str(tid),
                                "user_id": user["id"],
                                "tx_type": "ingreso",
                                "amount": float(m_rec),
                                "tx_date": tx_date_tr.isoformat(),
                                "description": f"{base_desc} ← {lbl_f}",
                                "category": None,
                                "business": None,
                                "transfer_tag": "Traspaso interno",
                                "transaction_notes": tx_notes_tr.strip() or None,
                                "counterpart_account_id": str(fid),
                                "transfer_group_id": gid,
                            }
                            ok1, w1 = kf_transaction_insert_flexible(sb, row_out)
                            if not ok1:
                                st.error("No se pudo registrar el egreso de origen.")
                                st.code(w1 or "")
                            else:
                                ok2, w2 = kf_transaction_insert_flexible(sb, row_in)
                                if not ok2:
                                    st.error(
                                        "Se guardó el egreso pero falló el ingreso en destino. "
                                        "Revisá movimientos en la cuenta origen y corregí a mano si hace falta."
                                    )
                                    st.code(w2 or "")
                                else:
                                    if w1 or w2:
                                        st.warning(
                                            (w1 or "")
                                            + ("\n" if w1 and w2 else "")
                                            + (w2 or "")
                                        )
                                    st.success("Traspaso registrado (egreso + ingreso).")
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
                    ).eq("id", account_id).eq("owner_user_id", str(user["id"])).execute()
                    st.success("Actualizado.")
                    st.rerun()

        with t3:
            import_excel_section(sb, account_id, user["id"], user["display_name"])

        _today_x = date.today()
        with st.expander("Exportar Excel · cuenta activa del lateral", expanded=False):
            st.caption(
                "Movimientos de la **cuenta del lateral**, entre las fechas que elijas. "
                "Los montos van en bruto (número), listos para Excel."
            )
            ex_a, ex_b = st.columns(2)
            with ex_a:
                ex_from = st.date_input(
                    "Desde",
                    value=_today_x - timedelta(days=365),
                    key="kf_xlsx_from",
                )
            with ex_b:
                ex_to = st.date_input("Hasta", value=_today_x, key="kf_xlsx_to")
            ex_df = _transactions_export_dataframe(txs, umap, opts, ex_from, ex_to)
            st.caption(f"Filas en el archivo: **{len(ex_df)}**.")
            if ex_df.empty:
                st.info("No hay movimientos en ese rango para esta cuenta.")
            else:
                _xfn = (
                    f"kenny_movimientos_{_safe_export_filename_part(str(acc.get('label')))}_"
                    f"{ex_from}_{ex_to}.xlsx"
                )
                st.download_button(
                    "Descargar .xlsx",
                    data=_df_to_xlsx_bytes(ex_df),
                    file_name=_xfn,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="kf_xlsx_dl",
                    use_container_width=True,
                )

        st.divider()
        st.subheader("Traspasos registrados")
        st.caption(
            "Esta tabla muestra **solo traspasos** (grupo origen + destino), en **todas** tus cuentas. "
            "Usala para detectar duplicados o errores y luego borrarlos por grupo."
        )
        _all_ids = list(opts.keys())
        _all_txs = load_transactions_for_accounts(sb, _all_ids, limit=16000)
        _all_transfer_txs = [t for t in _all_txs if _is_transfer_tx(t)]
        _by_gid_all: dict[str, list[dict[str, Any]]] = {}
        for _t in _all_transfer_txs:
            _g = str(_t.get("transfer_group_id") or "").strip()
            if not _g:
                continue
            _by_gid_all.setdefault(_g, []).append(_t)
        _group_rows = [
            _transfer_group_row(_g, _rows, opts) for _g, _rows in _by_gid_all.items() if _rows
        ]
        if _group_rows:
            _df_tr = pd.DataFrame(_group_rows).sort_values("fecha", ascending=False)
            _df_show = _df_tr[
                [
                    "fecha",
                    "origen",
                    "egreso",
                    "destino",
                    "ingreso",
                    "diferencia",
                    "descripcion",
                    "grupo",
                ]
            ].copy()
            _df_show["egreso"] = _df_show["egreso"].map(
                lambda x: "—" if pd.isna(x) else f"{float(x):,.4f}"
            )
            _df_show["ingreso"] = _df_show["ingreso"].map(
                lambda x: "—" if pd.isna(x) else f"{float(x):,.4f}"
            )
            _df_show["diferencia"] = _df_show["diferencia"].map(
                lambda x: "—" if pd.isna(x) else f"{float(x):+,.4f}"
            )
            st.dataframe(_df_show, use_container_width=True, hide_index=True)
        else:
            st.info("No se encontraron traspasos enlazados con `transfer_group_id`.")

        _orphans = [
            _t for _t in _all_transfer_txs if not str(_t.get("transfer_group_id") or "").strip()
        ]
        if _orphans:
            st.warning(
                f"Hay **{len(_orphans)}** movimiento(s) marcados como traspaso **sin grupo**. "
                "Esos no aparecen en la tabla de arriba; podés borrarlos por UUID."
            )

        st.subheader("Últimos movimientos (cuenta activa)")
        st.caption(
            f"Aquí sí se listan solo los movimientos de la **cuenta activa**: "
            f"**{acc.get('label', '—')}**."
        )
        if not txs:
            st.write("Todavía no hay movimientos.")
        else:
            df = pd.DataFrame(txs)
            df["registró"] = df["user_id"].map(lambda x: umap.get(str(x), "—") if pd.notna(x) else "—")
            for col in (
                "business",
                "fee_amount",
                "transfer_tag",
                "transaction_notes",
                "counterpart_account_id",
                "transfer_group_id",
            ):
                if col not in df.columns:
                    df[col] = None

            def _contra_label(cid: Any) -> str:
                if cid is None or (isinstance(cid, float) and pd.isna(cid)):
                    return "—"
                s = str(cid).strip()
                if not s:
                    return "—"
                return str(opts.get(s, s))[:55]

            df["cuenta_relacionada"] = df["counterpart_account_id"].map(_contra_label)

            def _gid_short_cell(x: Any) -> str:
                if x is None or (isinstance(x, float) and pd.isna(x)):
                    return "—"
                s = str(x).strip()
                if not s:
                    return "—"
                return f"{s[:8]}…" if len(s) > 8 else s

            df["grupo_traspaso"] = df["transfer_group_id"].map(_gid_short_cell)
            show = df[
                [
                    "tx_date",
                    "tx_type",
                    "amount",
                    "fee_amount",
                    "business",
                    "category",
                    "transfer_tag",
                    "grupo_traspaso",
                    "cuenta_relacionada",
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
<<<<<<< Updated upstream

            _opt_keys_ed = list(opts.keys())
            with st.expander("Editar movimiento", expanded=False):
                st.caption(
                    "Corregí cuenta, tipo, fecha, monto, descripción, rubro/negocio, etiqueta, comisión o notas. "
                    "Quién **registró** no cambia. En **Reportes** podés ver varias cuentas; acá elegí **la cuenta** "
                    "donde quedó guardado el movimiento (ej. Zinli si lo cargaste ahí)."
                )
                _def_ed_idx = (
                    _opt_keys_ed.index(str(account_id))
                    if str(account_id) in _opt_keys_ed
                    else 0
                )
                _edit_acc = st.selectbox(
                    "Cuenta del movimiento a editar",
                    _opt_keys_ed,
                    index=_def_ed_idx,
                    format_func=lambda x: opts[x],
                    key="kf_tx_edit_account_filter",
                )
                txs_edit = load_transactions(sb, str(_edit_acc))
                if not txs_edit:
                    st.info("No hay movimientos en esa cuenta.")
                else:
                    _pick_ix = st.selectbox(
                        "Elegí el movimiento",
                        options=list(range(len(txs_edit))),
                        format_func=lambda i: _tx_edit_row_label(txs_edit[i]),
                        key=f"kf_tx_edit_pick_{_edit_acc}",
                    )
                    sel_tx = txs_edit[_pick_ix]
                    _tid = str(sel_tx.get("id") or "").strip()
                    if sel_tx.get("transfer_group_id") or sel_tx.get("counterpart_account_id"):
                        st.warning(
                            "Este registro está **vinculado a un traspaso** (u otra cuenta). "
                            "Si cambiás el monto o la fecha, revisá también el movimiento en la otra cuenta."
                        )
                    _acc_idx = (
                        _opt_keys_ed.index(str(sel_tx.get("account_id")))
                        if str(sel_tx.get("account_id") or "") in _opt_keys_ed
                        else 0
                    )
                    _tt_idx = 0 if str(sel_tx.get("tx_type")) == "ingreso" else 1
                    _biz_sel, _biz_other = _split_list_or_other(sel_tx.get("business"), INCOME_BUSINESSES)
                    _biz_ix = (
                        INCOME_BUSINESSES.index(_biz_sel) if _biz_sel in INCOME_BUSINESSES else INCOME_BUSINESSES.index("Otro")
                    )
                    _cat_sel, _cat_other = _split_list_or_other(sel_tx.get("category"), EXPENSE_CATEGORIES)
                    _cat_ix = (
                        EXPENSE_CATEGORIES.index(_cat_sel)
                        if _cat_sel in EXPENSE_CATEGORIES
                        else EXPENSE_CATEGORIES.index("Otro")
                    )
                    _tag_opts_ed = ["(ninguna)"] + TRANSFER_TAGS
                    _tg_sel, _tg_other = _transfer_tag_edit_defaults(sel_tx.get("transfer_tag"))
                    _tg_ix = _tag_opts_ed.index(_tg_sel) if _tg_sel in _tag_opts_ed else 0
                    _fee_raw = sel_tx.get("fee_amount")
                    try:
                        _fee_val = float(_fee_raw) if _fee_raw is not None and str(_fee_raw) != "" else 0.0
                    except (TypeError, ValueError):
                        _fee_val = 0.0
                    if pd.isna(_fee_raw):
                        _fee_val = 0.0

                    with st.form(f"kf_tx_edit_{_tid}"):
                        cta_ed = st.selectbox(
                            "Cuenta",
                            _opt_keys_ed,
                            index=_acc_idx,
                            format_func=lambda i: opts[i],
                        )
                        acc_ed = next(a for a in accounts if str(a["id"]) == str(cta_ed))
                        _acur_ed = str(acc_ed.get("currency", "USD"))
                        _step_ed, _fmt_ed = _amount_input_format(_acur_ed)
                        tx_type_ed = st.radio(
                            "Tipo",
                            ["ingreso", "egreso"],
                            index=_tt_idx,
                            horizontal=True,
                        )
                        tx_date_ed = st.date_input(
                            "Fecha",
                            value=_parse_tx_date_value(sel_tx.get("tx_date")),
                        )
                        amt_ed = st.number_input(
                            f"Monto ({_acur_ed})",
                            min_value=float(_step_ed),
                            value=float(sel_tx.get("amount") or 0),
                            step=float(_step_ed),
                            format=_fmt_ed,
                        )
                        desc_ed = st.text_input(
                            "Descripción / concepto",
                            value=str(sel_tx.get("description") or ""),
                        )
                        st.caption("**Ingreso:** negocio. **Egreso:** rubro (solo aplica el que corresponda al tipo).")
                        cb1, cb2 = st.columns(2)
                        with cb1:
                            biz_sel_ed = st.selectbox(
                                "Negocio / fuente",
                                INCOME_BUSINESSES,
                                index=_biz_ix,
                            )
                            biz_other_ed = st.text_input("Si negocio = Otro", value=_biz_other)
                        with cb2:
                            cat_sel_ed = st.selectbox(
                                "Rubro del gasto",
                                EXPENSE_CATEGORIES,
                                index=_cat_ix,
                            )
                            cat_other_ed = st.text_input("Si rubro = Otro", value=_cat_other)
                        st.caption(
                            "**Etiqueta:** tramo / motivo opcional; **no** reemplaza la cuenta elegida arriba."
                        )
                        tag_sel_ed = st.selectbox(
                            "Etiqueta de tramo / motivo (opcional)",
                            _tag_opts_ed,
                            index=_tg_ix,
                        )
                        tag_other_ed = st.text_input(
                            "Texto si elegiste «Otro» en la etiqueta",
                            value=_tg_other,
                        )
                        fee_amt_ed = st.number_input(
                            "Comisión / fee (opcional)",
                            min_value=0.0,
                            value=float(_fee_val),
                            step=float(_step_ed),
                            format=_fmt_ed,
                        )
                        _fee_cur_opts_ed = list(dict.fromkeys([_acur_ed, "USD", "USDT", "VES"]))
                        _fc_def = str(sel_tx.get("fee_currency") or _acur_ed)
                        _fc_ix = (
                            _fee_cur_opts_ed.index(_fc_def) if _fc_def in _fee_cur_opts_ed else 0
                        )
                        fee_cur_ed = st.selectbox("Moneda de la comisión", _fee_cur_opts_ed, index=_fc_ix)
                        notes_ed = st.text_area(
                            "Notas (opcional)",
                            value=str(sel_tx.get("transaction_notes") or ""),
                            height=60,
                        )
                        if st.form_submit_button("Guardar cambios"):
                            business_ed: str | None
                            category_ed: str | None
                            if tx_type_ed == "ingreso":
                                business_ed = _pick_list_value(biz_sel_ed, biz_other_ed)
                                category_ed = None
                            else:
                                business_ed = None
                                category_ed = _pick_list_value(cat_sel_ed, cat_other_ed)
                            transfer_tag_ed = _resolve_transfer_tag(tag_sel_ed, tag_other_ed)
                            upd: dict[str, Any] = {
                                "account_id": str(cta_ed),
                                "tx_type": tx_type_ed,
                                "amount": float(amt_ed),
                                "tx_date": tx_date_ed.isoformat(),
                                "description": desc_ed.strip() or "(sin descripción)",
                                "category": category_ed,
                                "business": business_ed,
                                "transfer_tag": transfer_tag_ed,
                                "transaction_notes": notes_ed.strip() or None,
                            }
                            if fee_amt_ed and float(fee_amt_ed) > 0:
                                upd["fee_amount"] = float(fee_amt_ed)
                                upd["fee_currency"] = fee_cur_ed
                            else:
                                upd["fee_amount"] = None
                                upd["fee_currency"] = None
                            if sel_tx.get("counterpart_account_id"):
                                upd["counterpart_account_id"] = str(sel_tx.get("counterpart_account_id"))
                            if sel_tx.get("transfer_group_id"):
                                upd["transfer_group_id"] = str(sel_tx.get("transfer_group_id"))
                            ok_ed, wmsg_ed = kf_transaction_update_flexible(sb, _tid, upd)
                            if ok_ed:
                                if wmsg_ed:
                                    st.warning(wmsg_ed)
                                else:
                                    st.success("Movimiento actualizado.")
                                st.rerun()
                            else:
                                st.error("No se pudo guardar.")
                                st.code(wmsg_ed or "")

            st.markdown("##### Borrar movimientos")
            st.caption(
                "Si borrás un **traspaso** por UUID, se eliminan **las dos piernas** (egreso e ingreso) y los saldos se corrigen. "
                "Traspasos viejos sin `transfer_group_id` en la base hay que borrar **cada pierna** con su UUID (o ejecutá el parche SQL de traspasos)."
            )
            _by_gid: dict[str, dict[str, Any]] = {}
            for _g, _rows in _by_gid_all.items():
                if _rows:
                    _by_gid[_g] = _rows[0]
            if _by_gid:
                with st.expander("Eliminar traspaso equivocado (todas las cuentas)", expanded=True):
                    st.caption(
                        "Aparecen traspasos de **todas las cuentas**. "
                        "Al confirmar se borra **todo el par** en todas las cuentas."
                    )
                    _glist = list(_by_gid.keys())
                    _pick_g = st.selectbox(
                        "Elegí el traspaso a borrar",
                        options=_glist,
                        format_func=lambda x: _traspaso_group_label(_by_gid[x], x, opts),
                        key="kf_del_traspaso_pick",
                    )
                    if st.button("Eliminar este traspaso completo", type="primary", key="kf_del_traspaso_btn"):
                        try:
                            sb.table("kf_transaction").delete().eq("transfer_group_id", str(_pick_g)).execute()
                            st.success(
                                "Traspaso eliminado (origen + destino). Revisá saldos en **ambas** cuentas."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error("No se pudo borrar.")
                            st.code(str(e))
            else:
                if _orphans:
                    st.warning(
                        f"Hay **{len(_orphans)}** movimiento(s) marcados como traspaso "
                        "pero **sin `transfer_group_id`** en la base: **no** entran en la lista de borrado por grupo. "
                        "Usá **Eliminar por UUID** en cada pierna o ejecutá en Supabase "
                        "**`patch_007_transaction_counterpart.sql`** para que los traspasos nuevos queden enlazados."
                    )
            del_id = st.text_input("O eliminar por ID (uuid de cualquier pierna)", placeholder="…", key="kf_del_uuid")
            if st.button("Eliminar por UUID", key="kf_del_uuid_btn"):
                ok_d, err_d, msg_d = kf_transaction_delete_cascade(sb, del_id)
                if ok_d:
                    st.success(msg_d)
                    st.rerun()
                else:
                    st.error(err_d or "No se pudo eliminar.")
=======
            del_id = st.text_input("Eliminar por ID (uuid)", placeholder="…")
            if st.button("Eliminar") and del_id.strip():
                ok_del, msg_del = kf_transaction_delete_secure(sb, del_id, str(user["id"]))
                if ok_del:
                    st.success(msg_del or "Eliminado.")
                    st.rerun()
                else:
                    st.error(msg_del or "No se pudo eliminar.")
>>>>>>> Stashed changes

    with tab_acc:
        page_accounts(sb, accounts, user)

    with tab_rep:
        render_reports_page(sb, accounts, umap)

    with tab_usr:
        if user.get("is_admin"):
            page_users_admin(sb)
        else:
            st.info("Solo un administrador puede crear usuarios. Pedile acceso a quien creó el primer usuario.")


if __name__ == "__main__":
    main()
