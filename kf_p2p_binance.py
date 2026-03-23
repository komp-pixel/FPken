"""Referencia USDT/VES desde anuncios P2P públicos de Binance (sin API key)."""

from __future__ import annotations

import statistics
from typing import Any

import requests
import streamlit as st

BINANCE_P2P_SEARCH = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"


def _fetch_p2p_raw(trade_type: str, rows: int = 20) -> tuple[list[float], str | None]:
    """
    tradeType BUY  = querés comprar USDT → ves anuncios de quien vende (pagás VES por USDT).
    tradeType SELL = querés vender USDT → anuncios de quien compra (recibís VES por USDT).
    """
    payload: dict[str, Any] = {
        "asset": "USDT",
        "fiat": "VES",
        "merchantCheck": False,
        "page": 1,
        "payTypes": [],
        "publisherType": None,
        "rows": rows,
        "tradeType": trade_type,
    }
    try:
        r = requests.post(BINANCE_P2P_SEARCH, json=payload, timeout=18)
        r.raise_for_status()
        body = r.json()
    except requests.RequestException as e:
        return [], f"Red / Binance: {e}"
    except ValueError as e:
        return [], f"JSON inválido: {e}"

    if not body.get("success") and body.get("code") not in ("000000", 0, "0", None):
        return [], str(body.get("message") or body.get("code") or "Respuesta inesperada")

    data = body.get("data") or []
    prices: list[float] = []
    for item in data:
        adv = item.get("adv") or {}
        p = adv.get("price")
        if p is None:
            continue
        try:
            prices.append(float(p))
        except (TypeError, ValueError):
            continue
    if not prices:
        return [], "No se obtuvieron precios en la respuesta."
    return prices, None


@st.cache_data(ttl=50, show_spinner=False)
def cached_p2p_prices(trade_type: str) -> tuple[list[float], str | None]:
    return _fetch_p2p_raw(trade_type, rows=20)


def p2p_buy_sell_medians() -> tuple[float | None, float | None, str | None]:
    """Mediana de anuncios BUY y SELL; error si ambas fallan."""
    buy_p, err_b = cached_p2p_prices("BUY")
    sell_p, err_s = cached_p2p_prices("SELL")
    mb = statistics.median(buy_p) if buy_p else None
    ms = statistics.median(sell_p) if sell_p else None
    err = None
    if mb is None and ms is None:
        err = err_b or err_s
    return mb, ms, err


def render_usdt_ves_p2p_reference() -> None:
    """Bloque compacto para el dashboard."""
    st.markdown("#### USDT / VES — referencia P2P (Binance)")
    st.caption(
        "Promedio de los primeros anuncios públicos; **no** es cotización fija ni asesoría. "
        "Actualiza ~cada 50 s."
    )
    c1, c2, c3 = st.columns(3)
    buy_p, err_b = cached_p2p_prices("BUY")
    sell_p, err_s = cached_p2p_prices("SELL")

    def _stats(vals: list[float]) -> tuple[float, float, float] | None:
        if not vals:
            return None
        return (statistics.median(vals), min(vals), max(vals))

    sb = _stats(buy_p)
    ss = _stats(sell_p)

    with c1:
        if err_b or not sb:
            st.metric("Comprar USDT (pagás Bs)", "—", help="Anuncios de venta de USDT")
            if err_b:
                st.caption(f"Error: {err_b[:80]}")
        else:
            med, lo, hi = sb
            st.metric(
                "Comprar USDT (Bs × 1 USDT)",
                f"{med:,.2f}",
                delta=f"rango {lo:,.0f}–{hi:,.0f}",
                help="Mediana de los primeros anuncios (vos comprás USDT con bolívares).",
            )
    with c2:
        if err_s or not ss:
            st.metric("Vender USDT (recibís Bs)", "—", help="Anuncios de compra de USDT")
            if err_s:
                st.caption(f"Error: {err_s[:80]}")
        else:
            med, lo, hi = ss
            st.metric(
                "Vender USDT (Bs × 1 USDT)",
                f"{med:,.2f}",
                delta=f"rango {lo:,.0f}–{hi:,.0f}",
                help="Mediana de los primeros anuncios (vos vendés USDT por bolívares).",
            )
    with c3:
        if sb and ss:
            spread = sb[0] - ss[0]
            st.metric(
                "Brecha (compra − venta)",
                f"{spread:,.2f} Bs",
                help="Diferencia entre mediana compra y mediana venta en este snapshot.",
            )
        else:
            st.metric("Brecha", "—")

    if st.button("Actualizar cotización P2P ahora", key="btn_refresh_p2p"):
        cached_p2p_prices.clear()
        st.rerun()
