"""Conversión de saldos a VES según tasa elegida (BCV, P2P o manual)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from supabase import Client

from kf_bcv import cached_bcv_ves_per_usd
from kf_p2p_binance import p2p_buy_sell_medians


def to_ves(
    amount: Decimal,
    currency: str,
    ves_per_usd: Decimal,
    ves_per_usdt: Decimal,
) -> Decimal:
    c = (currency or "USD").strip().upper()
    if c == "VES":
        return amount
    if c == "USDT":
        return amount * ves_per_usdt
    return amount * ves_per_usd


def resolve_ves_rates(
    mode_key: str,
    manual_bs_per_unit: float | None,
) -> tuple[Decimal | None, Decimal | None, str]:
    """
    Devuelve (ves_per_usd, ves_per_usdt, etiqueta).
    Para USD y USDT se usa la misma tasa salvo que en el futuro se distingan.
    """
    if mode_key == "manual":
        if manual_bs_per_unit is None or manual_bs_per_unit <= 0:
            return None, None, "Definí un valor manual mayor que 0."
        d = Decimal(str(manual_bs_per_unit))
        return d, d, f"Manual: {float(d):,.4f} Bs × 1 USD/USDT"

    if mode_key == "bcv":
        r, err, _ = cached_bcv_ves_per_usd()
        if err or r is None:
            return None, None, err or "BCV no disponible."
        d = Decimal(str(r))
        return d, d, f"BCV oficial (promedio): {float(d):,.4f} Bs/USD"

    mb, ms, err = p2p_buy_sell_medians()
    if mode_key == "p2p_buy":
        if mb is None:
            return None, None, err or "P2P compra sin datos."
        d = Decimal(str(mb))
        return d, d, f"P2P Binance (comprar USDT, mediana): {float(d):,.2f} Bs/USDT"

    if mode_key == "p2p_sell":
        if ms is None:
            return None, None, err or "P2P venta sin datos."
        d = Decimal(str(ms))
        return d, d, f"P2P Binance (vender USDT, mediana): {float(d):,.2f} Bs/USDT"

    return None, None, "Modo de tasa desconocido."


def all_balances_native(
    sb: Client,
    accounts: list[dict[str, Any]],
    load_transactions_fn: Any,
    compute_balance_fn: Any,
) -> list[dict[str, Any]]:
    """Saldos calculados en la moneda nativa de cada cuenta (todas las cuentas)."""
    rows: list[dict[str, Any]] = []
    for a in accounts:
        aid = str(a["id"])
        txs = load_transactions_fn(sb, aid)
        bal = compute_balance_fn(a, txs)
        rows.append(
            {
                "Cuenta": a.get("label") or "—",
                "Moneda": str(a.get("currency", "USD")),
                "Saldo": float(bal),
            }
        )
    return rows


def all_balances_with_ves(
    sb: Client,
    accounts: list[dict[str, Any]],
    load_transactions_fn: Any,
    compute_balance_fn: Any,
    ves_per_usd: Decimal,
    ves_per_usdt: Decimal,
) -> tuple[list[dict[str, Any]], Decimal]:
    rows: list[dict[str, Any]] = []
    total = Decimal("0")
    for a in accounts:
        aid = str(a["id"])
        txs = load_transactions_fn(sb, aid)
        bal = compute_balance_fn(a, txs)
        cur = str(a.get("currency", "USD"))
        ves = to_ves(bal, cur, ves_per_usd, ves_per_usdt)
        total += ves
        rows.append(
            {
                "Cuenta": a.get("label") or "—",
                "Moneda": cur,
                "Saldo": float(bal),
                "≈ VES": float(ves),
            }
        )
    return rows, total
