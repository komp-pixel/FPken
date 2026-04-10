"""Tarjetas de cuentas / métodos de pago (layout tipo Binance P2P)."""

from __future__ import annotations

import html
from datetime import date
from decimal import Decimal

import streamlit as st

from kf_constants import ACCOUNT_KIND_LABELS
from kf_theme import is_dark_theme
from kf_theme_dark import DARK_KF_ACCOUNT_CARDS_CSS


def infer_account_kind(acc: dict) -> str:
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


def _is_pago_movil(acc: dict) -> bool:
    blob = (
        f"{acc.get('label', '')} {acc.get('bank_name', '')} "
        f"{acc.get('institution_kind', '')}"
    ).lower()
    return (
        "pago móvil" in blob
        or "pago movil" in blob
        or "pagomovil" in blob
        or "p.m." in blob
        or "pm " in blob
    )


def _card_title(acc: dict, kind: str) -> str:
    if kind == "app_pagos":
        return str(acc.get("institution_kind") or acc.get("bank_name") or "App de pago")
    if kind == "wallet":
        return str(acc.get("bank_name") or acc.get("institution_kind") or "Wallet")
    if _is_pago_movil(acc):
        return "Pago Móvil"
    return str(acc.get("bank_name") or acc.get("institution_kind") or "Cuenta bancaria")


def _dot_color(acc: dict, kind: str) -> str:
    inst = (acc.get("institution_kind") or acc.get("bank_name") or "").lower()
    if kind == "app_pagos":
        if "zelle" in inst:
            return "#8b5cf6"
        if "zinli" in inst:
            return "#a855f7"
        return "#c084fc"
    if kind == "banco":
        return "#3b82f6" if _is_pago_movil(acc) else "#64748b"
    return "#ea580c"


def _field_tuples(acc: dict, kind: str) -> list[tuple[str, str]]:
    """Pares (etiqueta, valor) para mostrar en la tarjeta."""
    h = lambda x: str(x).strip() if x is not None and str(x).strip() else "—"

    if kind == "app_pagos":
        inst = (acc.get("institution_kind") or "").lower()
        email = h(acc.get("zelle_email_or_phone"))
        nombre = h(acc.get("holder_name"))
        if "zelle" in inst:
            return [
                ("Email / Zelle", email),
                ("Nombre completo del titular", nombre),
            ]
        if "zinli" in inst:
            return [
                ("Correo electrónico", email),
                ("Nombre", nombre),
            ]
        return [
            ("App", h(acc.get("institution_kind") or acc.get("bank_name"))),
            ("Usuario / email / tel.", email),
            ("Titular", nombre),
        ]

    if kind == "wallet":
        out: list[tuple[str, str]] = [
            ("Exchange / red", h(acc.get("bank_name") or acc.get("institution_kind"))),
            ("UID del exchange", h(acc.get("exchange_uid"))),
            ("Pay ID", h(acc.get("pay_id"))),
            ("Red de depósito", h(acc.get("deposit_network"))),
            ("Dirección de depósito (on-chain)", h(acc.get("deposit_address"))),
            ("Memo / Tag", h(acc.get("deposit_memo"))),
            ("Referencia extra", h(acc.get("wallet_address"))),
            ("Titular", h(acc.get("holder_name"))),
        ]
        return [(a, b) for a, b in out if b != "—"]

    if _is_pago_movil(acc):
        return [
            ("Nombre completo del receptor", h(acc.get("holder_name"))),
            ("Número de cédula / ID", h(acc.get("account_number"))),
            ("Teléfono", h(acc.get("routing_or_swift"))),
            ("Banco", h(acc.get("bank_name") or acc.get("institution_kind"))),
        ]

    return [
        ("Banco", h(acc.get("bank_name") or acc.get("institution_kind"))),
        ("Titular", h(acc.get("holder_name"))),
        ("Nº cuenta / ref", h(acc.get("account_number"))),
        ("Routing / Swift", h(acc.get("routing_or_swift"))),
    ]


def _label_sort_key(acc: dict) -> tuple[str, str]:
    """Orden alfabético por nombre visible (label), desempate por id."""
    return (str(acc.get("label") or "").strip().lower(), str(acc.get("id") or ""))


_CARD_STYLE = """
<style>
.kf-pay-card-wrap .kf-pay-card {
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 1.05rem 1.15rem 1.15rem;
    margin-bottom: 0.9rem;
    background: #fff;
    box-shadow: 0 2px 14px rgba(15, 23, 42, 0.06), 0 1px 3px rgba(15, 23, 42, 0.04);
}
.kf-pay-card-wrap .kf-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.35rem 1rem;
    margin-bottom: 0.75rem;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 0.6rem;
}
.kf-pay-card-wrap .kf-title-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.kf-pay-card-wrap .kf-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
}
.kf-pay-card-wrap .kf-meta {
    font-size: 0.8rem;
    color: #475569;
    text-align: right;
    font-weight: 600;
}
.kf-pay-card-wrap .kf-balance-strip {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
    margin: 0 0 0.85rem 0;
    padding: 0.75rem 0.95rem;
    border-radius: 12px;
    background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
    border: 1px solid #bfdbfe;
}
.kf-pay-card-wrap .kf-balance-strip.kf-banco {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
    border: none;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.28);
}
.kf-pay-card-wrap .kf-balance-strip label {
    display: block;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 800;
    margin-bottom: 0.25rem;
    color: #1e293b;
}
.kf-pay-card-wrap .kf-balance-strip.kf-banco label {
    color: #ffffff !important;
    text-shadow: 0 1px 2px rgba(0,0,0,0.25);
}
.kf-pay-card-wrap .kf-balance-amt {
    font-size: 1.2rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: #0f172a;
}
.kf-pay-card-wrap .kf-balance-strip.kf-banco .kf-balance-amt {
    color: #fff !important;
}
.kf-pay-card-wrap .kf-bal-pos { color: #15803d !important; }
.kf-pay-card-wrap .kf-bal-neg { color: #b91c1c !important; }
.kf-pay-card-wrap .kf-balance-date {
    font-size: 0.82rem;
    color: #475569;
    font-weight: 700;
}
.kf-pay-card-wrap .kf-balance-strip.kf-banco .kf-balance-date {
    color: #ffffff !important;
    font-weight: 700;
    text-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
.kf-pay-card-wrap .kf-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.65rem 1.25rem;
}
.kf-pay-card-wrap .kf-fld label {
    display: block;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #64748b;
    margin-bottom: 0.2rem;
    font-weight: 700;
}
.kf-pay-card-wrap .kf-fld span {
    font-size: 0.95rem;
    color: #0f172a;
    word-break: break-word;
}
.kf-pay-card-wrap.kf-interactive .kf-pay-card {
    transition: box-shadow 0.15s ease, border-color 0.15s ease, transform 0.12s ease;
}
.kf-pay-card-wrap.kf-interactive .kf-pay-card:hover {
    box-shadow: 0 8px 28px rgba(37, 99, 235, 0.12);
    border-color: #93c5fd;
}
</style>
"""


def _card_html(
    acc: dict,
    kind: str,
    *,
    balance: Decimal | None = None,
    balance_as_of: date | None = None,
) -> str:
    title = _card_title(acc, kind)
    dot = _dot_color(acc, kind)
    subtitle = acc.get("label") or "—"
    cur = acc.get("currency") or "—"
    kind_es = ACCOUNT_KIND_LABELS.get(kind, kind)
    fields = _field_tuples(acc, kind)
    fields_html = "".join(
        f'<div class="kf-fld"><label>{html.escape(lab)}</label>'
        f"<span>{html.escape(str(val))}</span></div>"
        for lab, val in fields
    )

    balance_html = ""
    if balance is not None:
        cur_s = str(cur) if cur != "—" else ""
        amt = f"{float(balance):,.2f}"
        if cur_s:
            amt = f"{amt} {html.escape(cur_s)}"
        bal_cls = "kf-bal-pos" if balance >= 0 else "kf-bal-neg"
        strip_cls = "kf-balance-strip kf-banco" if kind == "banco" else "kf-balance-strip"
        amt_cls = "" if kind == "banco" else f" {bal_cls}"
        d_s = balance_as_of.isoformat() if balance_as_of else ""
        balance_html = f"""
  <div class="{strip_cls}">
    <div>
      <label>Saldo al día</label>
      <span class="kf-balance-amt{amt_cls}">{amt}</span>
    </div>
    <div class="kf-balance-date">{html.escape(d_s)}</div>
  </div>"""

    return f"""
<div class="kf-pay-card">
  <div class="kf-head">
    <div class="kf-title-row">
      <span class="kf-dot" style="background:{dot};"></span>
      <strong style="font-size:1.05rem;color:#0f172a;">{html.escape(title)}</strong>
    </div>
    <div class="kf-meta">{html.escape(str(subtitle))} · {html.escape(str(cur))} · {html.escape(kind_es)}</div>
  </div>
  {balance_html}
  <div class="kf-grid">{fields_html}</div>
</div>
"""


def _render_card(
    acc: dict,
    kind: str,
    *,
    interactive: bool = False,
    balance: Decimal | None = None,
    balance_as_of: date | None = None,
) -> None:
    cls = "kf-pay-card-wrap kf-interactive" if interactive else "kf-pay-card-wrap"
    st.markdown(
        f'<div class="{cls}">{_card_html(acc, kind, balance=balance, balance_as_of=balance_as_of)}</div>',
        unsafe_allow_html=True,
    )
    n = str(acc.get("notes") or "").strip()
    if n:
        st.caption(f"Notas: {n[:200]}{'…' if len(n) > 200 else ''}")


def render_payment_method_cards(
    accounts: list[dict],
    *,
    heading: str = "Mis cuentas y métodos de pago",
    caption: str | None = None,
    edit_select_state_key: str = "kf_accounts_edit_select",
    balances_by_account_id: dict[str, Decimal] | None = None,
    balance_as_of: date | None = None,
) -> None:
    """Lista de cuentas como tarjetas; orden alfabético por nombre (label)."""
    if not accounts:
        st.info("Todavía no hay cuentas registradas.")
        return

    st.markdown(
        f'<p class="lk-section" style="margin-top:0;">{html.escape(heading)}</p>',
        unsafe_allow_html=True,
    )
    if caption:
        st.caption(caption)
    st.caption(
        "Orden **alfabético** por el nombre de la cuenta (campo *label*). "
        "En **Pago Móvil**, cédula / teléfono: usá **Nº cuenta** y **Routing** en el alta bancaria."
    )
    st.caption(
        "**Editar:** debajo de cada tarjeta hay un botón (Streamlit no puede hacer clic "
        "directamente sobre el HTML de la tarjeta)."
    )

    st.markdown(_CARD_STYLE, unsafe_allow_html=True)
    if is_dark_theme():
        st.markdown(
            f"<style>{DARK_KF_ACCOUNT_CARDS_CSS}</style>",
            unsafe_allow_html=True,
        )

    ordered = sorted(accounts, key=_label_sort_key)
    for acc in ordered:
        k = infer_account_kind(acc)
        aid = str(acc.get("id") or "").strip()
        bal: Decimal | None = None
        if balances_by_account_id is not None and aid:
            bal = balances_by_account_id.get(aid)
        _render_card(
            acc,
            k,
            interactive=True,
            balance=bal,
            balance_as_of=balance_as_of,
        )
        aid = str(acc.get("id") or "").strip()
        if not aid:
            continue
        short = str(acc.get("label") or "Cuenta")[:42]
        if st.button(
            f"✏️ Editar · {short}",
            key=f"kf_card_edit_open_{aid}",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state[edit_select_state_key] = aid
            st.rerun()
