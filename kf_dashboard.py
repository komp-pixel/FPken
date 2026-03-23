"""Tablero: tendencias diarias, mensuales y anuales."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _dec(x: Any) -> Decimal:
    if x is None:
        return Decimal("0")
    return Decimal(str(x))


def txs_to_dataframe(txs: list[dict[str, Any]]) -> pd.DataFrame:
    if not txs:
        return pd.DataFrame(
            columns=["tx_date", "tx_type", "amount", "description", "category", "user_id"]
        )
    df = pd.DataFrame(txs)
    df["tx_date"] = pd.to_datetime(df["tx_date"], errors="coerce").dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df


def render_finance_dashboard(
    txs: list[dict[str, Any]],
    opening_balance: Decimal,
    currency: str,
) -> None:
    df = txs_to_dataframe(txs)
    today = date.today()
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        range_key = st.selectbox(
            "Vista rápida",
            ["Últimos 30 días", "Este mes", "Este año", "Últimos 12 meses", "Todo"],
            index=0,
            key="dash_range",
        )
    with col_f2:
        custom = st.date_input(
            "O filtrá fechas (opcional)",
            value=(today - timedelta(days=89), today),
            key="dash_custom_range",
        )

    if range_key == "Últimos 30 días":
        d0, d1 = today - timedelta(days=29), today
    elif range_key == "Este mes":
        d0, d1 = date(today.year, today.month, 1), today
    elif range_key == "Este año":
        d0, d1 = date(today.year, 1, 1), today
    elif range_key == "Últimos 12 meses":
        d0, d1 = today - timedelta(days=364), today
    else:
        d0, d1 = None, None

    if isinstance(custom, tuple) and len(custom) == 2:
        c0, c1 = custom[0], custom[1]
        if c0 and c1:
            d0, d1 = c0, c1

    mask = pd.Series(True, index=df.index) if len(df) else None
    if len(df) and mask is not None and d0 is not None and d1 is not None:
        mask = (df["tx_date"] >= d0) & (df["tx_date"] <= d1)
        dff = df.loc[mask].copy()
    else:
        dff = df.copy()

    ing = dff[dff["tx_type"] == "ingreso"]["amount"].sum()
    egr = dff[dff["tx_type"] == "egreso"]["amount"].sum()
    net = float(ing) - float(egr)

    st.markdown(
        """
        <style>
        .kf-card { background: linear-gradient(135deg, #1e3a5f 0%, #0d2137 100%);
        border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 14px; padding: 1rem 1.25rem;
        margin-bottom: 0.5rem; box-shadow: 0 8px 32px rgba(0,0,0,0.35); }
        .kf-card h4 { margin: 0; color: #7dd3fc; font-size: 0.85rem; font-weight: 600; letter-spacing: .04em; }
        .kf-card p { margin: 0.35rem 0 0 0; font-size: 1.65rem; font-weight: 700; color: #f0f9ff; }
        .kf-net-pos { color: #4ade80 !important; } .kf-net-neg { color: #fb7185 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="kf-card"><h4>INGRESOS (período)</h4><p>{ing:,.2f} {currency}</p></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="kf-card"><h4>EGRESOS (período)</h4><p>{egr:,.2f} {currency}</p></div>',
            unsafe_allow_html=True,
        )
    with c3:
        cls = "kf-net-pos" if net >= 0 else "kf-net-neg"
        st.markdown(
            f'<div class="kf-card"><h4>NETO (período)</h4><p class="{cls}">{net:,.2f} {currency}</p></div>',
            unsafe_allow_html=True,
        )
    with c4:
        bal = float(opening_balance) + float(
            df[df["tx_type"] == "ingreso"]["amount"].sum()
            - df[df["tx_type"] == "egreso"]["amount"].sum()
        )
        st.markdown(
            f'<div class="kf-card"><h4>SALDO PROYECTADO</h4><p>{bal:,.2f} {currency}</p></div>',
            unsafe_allow_html=True,
        )

    if dff.empty:
        st.info("No hay movimientos en el período elegido.")
        return

    dff = dff.sort_values("tx_date")
    dff["ing"] = dff.apply(lambda r: float(r["amount"]) if r["tx_type"] == "ingreso" else 0.0, axis=1)
    dff["egr"] = dff.apply(lambda r: float(r["amount"]) if r["tx_type"] == "egreso" else 0.0, axis=1)

    daily = dff.groupby("tx_date", as_index=False).agg(ingreso=("ing", "sum"), egreso=("egr", "sum"))
    daily["neto"] = daily["ingreso"] - daily["egreso"]

    dff["ym"] = pd.to_datetime(dff["tx_date"]).dt.to_period("M").astype(str)
    monthly = dff.groupby("ym", as_index=False).agg(ingreso=("ing", "sum"), egreso=("egr", "sum"))
    monthly["neto"] = monthly["ingreso"] - monthly["egreso"]

    dff["yr"] = pd.to_datetime(dff["tx_date"]).dt.year.astype(str)
    yearly = dff.groupby("yr", as_index=False).agg(ingreso=("ing", "sum"), egreso=("egr", "sum"))
    yearly["neto"] = yearly["ingreso"] - yearly["egreso"]

    tab_d, tab_m, tab_y, tab_cat = st.tabs(
        ["Diario", "Mensual", "Anual", "Por categoría"]
    )

    layout = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,23,42,0.6)",
        font=dict(color="#e2e8f0"),
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    with tab_d:
        fig_d = go.Figure()
        fig_d.add_trace(
            go.Bar(x=daily["tx_date"], y=daily["ingreso"], name="Ingresos", marker_color="#34d399")
        )
        fig_d.add_trace(
            go.Bar(x=daily["tx_date"], y=daily["egreso"], name="Egresos", marker_color="#fb7185")
        )
        fig_d.update_layout(
            **layout,
            title="Flujo por día",
            barmode="group",
            xaxis_title="Fecha",
            yaxis_title=currency,
        )
        st.plotly_chart(fig_d, use_container_width=True)

        fig_line = go.Figure()
        fig_line.add_trace(
            go.Scatter(
                x=daily["tx_date"],
                y=daily["neto"].cumsum(),
                fill="tozeroy",
                name="Neto acumulado (período filtrado)",
                line=dict(color="#38bdf8", width=2),
            )
        )
        fig_line.update_layout(**layout, title="Neto acumulado en el período", yaxis_title=currency)
        st.plotly_chart(fig_line, use_container_width=True)

    with tab_m:
        fig_m = go.Figure()
        fig_m.add_trace(
            go.Bar(x=monthly["ym"], y=monthly["ingreso"], name="Ingresos", marker_color="#4ade80")
        )
        fig_m.add_trace(
            go.Bar(x=monthly["ym"], y=monthly["egreso"], name="Egresos", marker_color="#f87171")
        )
        fig_m.update_layout(**layout, title="Ingresos vs egresos por mes", barmode="group")
        st.plotly_chart(fig_m, use_container_width=True)

    with tab_y:
        fig_y = go.Figure(
            data=[
                go.Bar(name="Ingresos", x=yearly["yr"], y=yearly["ingreso"], marker_color="#22c55e"),
                go.Bar(name="Egresos", x=yearly["yr"], y=yearly["egreso"], marker_color="#ef4444"),
            ]
        )
        fig_y.update_layout(**layout, title="Totales por año", barmode="group")
        st.plotly_chart(fig_y, use_container_width=True)

    with tab_cat:
        cat_df = dff[dff["tx_type"] == "egreso"].copy()
        cat_df["category"] = cat_df["category"].fillna("(sin categoría)")
        if cat_df.empty:
            st.caption("No hay egresos con categoría en el período.")
        else:
            agg = cat_df.groupby("category", as_index=False)["amount"].sum().sort_values(
                "amount", ascending=False
            )
            fig_c = go.Figure(
                go.Bar(
                    x=agg["amount"],
                    y=agg["category"],
                    orientation="h",
                    marker=dict(color=agg["amount"], colorscale="Reds", showscale=False),
                )
            )
            fig_c.update_layout(
                **layout,
                title="Egresos por categoría",
                xaxis_title=currency,
                yaxis_title="",
            )
            st.plotly_chart(fig_c, use_container_width=True)
