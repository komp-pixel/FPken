"""Tipo de cambio oficial BCV (referencia VES por USD) vía API pública."""

from __future__ import annotations

from typing import Any

import requests
import streamlit as st

BCV_OFICIAL_URL = "https://ve.dolarapi.com/v1/dolares/oficial"


def _parse_bcv_promedio(body: dict[str, Any]) -> float | None:
    p = body.get("promedio")
    if p is not None:
        try:
            return float(p)
        except (TypeError, ValueError):
            pass
    c, v = body.get("compra"), body.get("venta")
    try:
        if c is not None and v is not None:
            return (float(c) + float(v)) / 2.0
        if c is not None:
            return float(c)
        if v is not None:
            return float(v)
    except (TypeError, ValueError):
        pass
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def cached_bcv_ves_per_usd() -> tuple[float | None, str | None, str | None]:
    """
    Retorna (promedio Bs/USD, error, fecha_actualizacion ISO o None).
    """
    try:
        r = requests.get(BCV_OFICIAL_URL, timeout=18)
        r.raise_for_status()
        j = r.json()
    except requests.RequestException as e:
        return None, f"Red / API: {e}", None
    except ValueError as e:
        return None, f"JSON inválido: {e}", None

    rate = _parse_bcv_promedio(j)
    if rate is None:
        return None, "La respuesta no trae promedio ni compra/venta.", None
    fecha = j.get("fechaActualizacion")
    if fecha is not None:
        fecha = str(fecha)
    return rate, None, fecha


def render_bcv_reference() -> None:
    """Métrica compacta para dashboard o barra lateral."""
    rate, err, fecha = cached_bcv_ves_per_usd()
    if err:
        st.metric("BCV — USD oficial", "—", help="DolarAPI / fuente oficial")
        st.caption(f"No disponible: {err[:100]}")
        return
    hint = f"Bs por 1 USD (oficial). Actualización: {fecha or '—'}."
    st.metric("BCV — USD oficial (promedio)", f"{rate:,.4f} VES", help=hint)
    if fecha:
        st.caption(f"Última referencia API: {fecha}")

    if st.button("Actualizar BCV ahora", key="btn_refresh_bcv"):
        cached_bcv_ves_per_usd.clear()
        st.rerun()
