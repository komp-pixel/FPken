"""Tarjetas de cuentas / métodos de pago (layout tipo Binance P2P)."""

from __future__ import annotations

import html

import streamlit as st

from kf_constants import ACCOUNT_KIND_LABELS


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


def _sort_key(acc: dict) -> tuple:
    k = infer_account_kind(acc)
    inst = (acc.get("institution_kind") or acc.get("bank_name") or "").lower()
    if k == "app_pagos":
        sub = 0 if "zelle" in inst else 1 if "zinli" in inst else 9
    elif k == "banco":
        sub = 0 if _is_pago_movil(acc) else 1
    else:
        sub = 0
    kind_o = {"app_pagos": 0, "banco": 1, "wallet": 2}[k]
    return (kind_o, sub, str(acc.get("label") or "").lower())


_CARD_STYLE = """
<style>
.kf-pay-card-wrap .kf-pay-card {
    border: 1px solid rgba(49, 51, 63, 0.12);
    border-radius: 10px;
    padding: 1rem 1.1rem 1.1rem;
    margin-bottom: 0.85rem;
    background: linear-gradient(180deg, #fafbfc 0%, #f4f5f7 100%);
}
.kf-pay-card-wrap .kf-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.35rem 1rem;
    margin-bottom: 0.75rem;
    border-bottom: 1px solid rgba(49, 51, 63, 0.08);
    padding-bottom: 0.55rem;
}
.kf-pay-card-wrap .kf-title-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.kf-pay-card-wrap .kf-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    flex-shrink: 0;
}
.kf-pay-card-wrap .kf-meta {
    font-size: 0.8rem;
    color: rgba(49, 51, 63, 0.65);
    text-align: right;
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
    color: rgba(49, 51, 63, 0.55);
    margin-bottom: 0.2rem;
}
.kf-pay-card-wrap .kf-fld span {
    font-size: 0.95rem;
    color: #1a1c24;
    word-break: break-word;
}
.kf-pay-card-wrap.kf-interactive .kf-pay-card {
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
}
.kf-pay-card-wrap.kf-interactive .kf-pay-card:hover {
    box-shadow: 0 4px 16px rgba(59, 130, 246, 0.14);
    border-color: rgba(59, 130, 246, 0.35);
}
</style>
"""


def _card_html(acc: dict, kind: str) -> str:
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
    return f"""
<div class="kf-pay-card">
  <div class="kf-head">
    <div class="kf-title-row">
      <span class="kf-dot" style="background:{dot};"></span>
      <strong style="font-size:1.05rem;">{html.escape(title)}</strong>
    </div>
    <div class="kf-meta">{html.escape(str(subtitle))} · {html.escape(str(cur))} · {html.escape(kind_es)}</div>
  </div>
  <div class="kf-grid">{fields_html}</div>
</div>
"""


def _render_card(acc: dict, kind: str, *, interactive: bool = False) -> None:
    cls = "kf-pay-card-wrap kf-interactive" if interactive else "kf-pay-card-wrap"
    st.markdown(
        f'<div class="{cls}">{_card_html(acc, kind)}</div>',
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
) -> None:
    """Lista de cuentas como tarjetas horizontales (orden: apps → banco → wallet)."""
    if not accounts:
        st.info("Todavía no hay cuentas registradas.")
        return

    st.markdown(f"### {heading}")
    if caption:
        st.caption(caption)
    st.caption(
        "Orden: **Zelle → Zinli → otras apps → Pago Móvil → otros bancos → wallets**. "
        "Para **cédula / teléfono** en Pago Móvil usá **Nº cuenta** y **Routing** (teléfono) "
        "en el alta bancaria, o editá en **Cuentas**."
    )
    st.caption(
        "**Editar:** debajo de cada tarjeta hay un botón (Streamlit no puede hacer clic "
        "directamente sobre el HTML de la tarjeta)."
    )

    st.markdown(_CARD_STYLE, unsafe_allow_html=True)

    ordered = sorted(accounts, key=_sort_key)
    for acc in ordered:
        k = infer_account_kind(acc)
        _render_card(acc, k, interactive=True)
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
