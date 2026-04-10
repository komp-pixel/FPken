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


def _is_transfer_like_df(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series([], dtype=bool)
    tg = (
        df.get("transfer_group_id")
        if "transfer_group_id" in df.columns
        else pd.Series([None] * len(df), index=df.index)
    )
    tag = (
        df.get("transfer_tag")
        if "transfer_tag" in df.columns
        else pd.Series([""] * len(df), index=df.index)
    )
    tag_s = tag.fillna("").astype(str).str.lower()
    tg_s = tg.fillna("").astype(str).str.strip()
    return (tg_s != "") | tag_s.str.contains("traspaso", na=False)


def txs_to_dataframe(txs: list[dict[str, Any]]) -> pd.DataFrame:
    if not txs:
        return pd.DataFrame(
            columns=[
                "tx_date",
                "tx_type",
                "amount",
                "description",
                "category",
                "business",
                "user_id",
                "transfer_tag",
                "transfer_group_id",
                "counterpart_account_id",
            ]
        )
    df = pd.DataFrame(txs)
    df["tx_date"] = pd.to_datetime(df["tx_date"], errors="coerce").dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    if "business" not in df.columns:
        df["business"] = None
    for col in ("transfer_tag", "transfer_group_id", "counterpart_account_id"):
        if col not in df.columns:
            df[col] = None
    return df


def render_finance_dashboard(
    txs: list[dict[str, Any]],
    opening_balance: Decimal,
    currency: str,
) -> None:
    df = txs_to_dataframe(txs)
    today = date.today()

    exclude_transfers = st.checkbox(
        "Excluir traspasos en Ingresos/Egresos (solo flujo real)",
        value=True,
        help=(
            "Los traspasos (egreso+ingreso enlazados) inflan ingresos/egresos del período pero no son "
            "dinero 'ganado/gastado'. El saldo proyectado se calcula con TODO."
        ),
        key="dash_ex_tr",
    )

    range_key = st.selectbox(
        "Vista rápida",
        [
            "Últimos 30 días",
            "Este mes",
            "Este año",
            "Últimos 12 meses",
            "Todo",
            "Personalizado (elegir fechas abajo)",
        ],
        index=0,
        key="dash_range",
    )
    if range_key == "Personalizado (elegir fechas abajo)":
        c0, c1 = st.columns(2)
        with c0:
            d0 = st.date_input("Desde", value=today - timedelta(days=89), key="dash_d0")
        with c1:
            d1 = st.date_input("Hasta", value=today, key="dash_d1")
    elif range_key == "Últimos 30 días":
        d0, d1 = today - timedelta(days=29), today
    elif range_key == "Este mes":
        d0, d1 = date(today.year, today.month, 1), today
    elif range_key == "Este año":
        d0, d1 = date(today.year, 1, 1), today
    elif range_key == "Últimos 12 meses":
        d0, d1 = today - timedelta(days=364), today
    else:
        d0, d1 = None, None

    mask = pd.Series(True, index=df.index) if len(df) else None
    if len(df) and mask is not None and d0 is not None and d1 is not None:
        mask = (df["tx_date"] >= d0) & (df["tx_date"] <= d1)
        dff = df.loc[mask].copy()
    else:
        dff = df.copy()

    if exclude_transfers and len(dff):
        _is_tr = _is_transfer_like_df(dff)
        dff_flow = dff.loc[~_is_tr].copy()
        dff_tr = dff.loc[_is_tr].copy()
    else:
        dff_flow = dff.copy()
        dff_tr = dff.iloc[0:0].copy()

    ing = dff_flow[dff_flow["tx_type"] == "ingreso"]["amount"].sum()
    egr = dff_flow[dff_flow["tx_type"] == "egreso"]["amount"].sum()
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

    if float(ing) > 0:
        st.caption(
            f"Relación período: los egresos representan el **{float(egr) / float(ing) * 100:.1f} %** de los ingresos "
            f"({currency}, sin traspasos si la casilla está activa)."
        )
    elif float(egr) > 0:
        st.caption("En el período hay egresos pero no ingresos registrados (en el flujo filtrado).")

    if exclude_transfers and len(dff_tr):
        tr_in = float(dff_tr[dff_tr["tx_type"] == "ingreso"]["amount"].sum())
        tr_out = float(dff_tr[dff_tr["tx_type"] == "egreso"]["amount"].sum())
        st.caption(
            f"Traspasos en el período (excluidos del flujo): entradas {tr_in:,.2f} · salidas {tr_out:,.2f} {currency}."
        )
    if len(df):
        first_m = date(today.year, today.month, 1)
        last_pm = first_m - timedelta(days=1)
        first_pm = date(last_pm.year, last_pm.month, 1)
        m_cur = (df["tx_date"] >= first_m) & (df["tx_date"] <= today)
        m_prv = (df["tx_date"] >= first_pm) & (df["tx_date"] <= last_pm)
        cur = df.loc[m_cur]
        prv = df.loc[m_prv]
        if exclude_transfers:
            cur = cur.loc[~_is_transfer_like_df(cur)]
            prv = prv.loc[~_is_transfer_like_df(prv)]
        ing_c = float(cur[cur["tx_type"] == "ingreso"]["amount"].sum())
        egr_c = float(cur[cur["tx_type"] == "egreso"]["amount"].sum())
        net_c = ing_c - egr_c
        ing_p = float(prv[prv["tx_type"] == "ingreso"]["amount"].sum())
        egr_p = float(prv[prv["tx_type"] == "egreso"]["amount"].sum())
        net_p = ing_p - egr_p

        def _pct_delta(new_v: float, old_v: float) -> str | None:
            if old_v == 0:
                return None
            return f"{((new_v - old_v) / abs(old_v) * 100):+.1f}% vs mes ant."

        st.markdown("##### Visión del dinero · mes en curso vs mes anterior")
        st.caption(
            f"Mes actual: {first_m.isoformat()} → {today.isoformat()} · "
            f"Mes anterior: {first_pm.isoformat()} → {last_pm.isoformat()} · moneda **{currency}**"
        )
        v1, v2, v3 = st.columns(3)
        with v1:
            st.metric(
                "Ingresos (mes actual)",
                f"{ing_c:,.2f}",
                delta=_pct_delta(ing_c, ing_p),
                help=f"Mes anterior: {ing_p:,.2f}",
            )
        with v2:
            st.metric(
                "Egresos (mes actual)",
                f"{egr_c:,.2f}",
                delta=_pct_delta(egr_c, egr_p),
                help=f"Mes anterior: {egr_p:,.2f}",
            )
        with v3:
            st.metric(
                "Neto (mes actual)",
                f"{net_c:,.2f}",
                delta=_pct_delta(net_c, net_p),
                help=f"Mes anterior: {net_p:,.2f}",
            )

    if dff_flow.empty:
        st.info("No hay movimientos en el período elegido.")
        return

    dff_flow = dff_flow.sort_values("tx_date")
    dff_flow["ing"] = dff_flow.apply(
        lambda r: float(r["amount"]) if r["tx_type"] == "ingreso" else 0.0, axis=1
    )
    dff_flow["egr"] = dff_flow.apply(
        lambda r: float(r["amount"]) if r["tx_type"] == "egreso" else 0.0, axis=1
    )

    daily = dff_flow.groupby("tx_date", as_index=False).agg(
        ingreso=("ing", "sum"), egreso=("egr", "sum")
    )
    daily["neto"] = daily["ingreso"] - daily["egreso"]

    dff_flow["ym"] = pd.to_datetime(dff_flow["tx_date"]).dt.to_period("M").astype(str)
    monthly = dff_flow.groupby("ym", as_index=False).agg(
        ingreso=("ing", "sum"), egreso=("egr", "sum")
    )
    monthly["neto"] = monthly["ingreso"] - monthly["egreso"]

    dff_flow["yr"] = pd.to_datetime(dff_flow["tx_date"]).dt.year.astype(str)
    yearly = dff_flow.groupby("yr", as_index=False).agg(
        ingreso=("ing", "sum"), egreso=("egr", "sum")
    )
    yearly["neto"] = yearly["ingreso"] - yearly["egreso"]

    tab_sum, tab_d, tab_m, tab_y, tab_neg, tab_cat = st.tabs(
        [
            "Resumen inteligente",
            "Diario",
            "Mensual",
            "Anual",
            "Ingresos por negocio",
            "Gastos por categoría",
        ]
    )

    layout = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,23,42,0.6)",
        font=dict(color="#e2e8f0"),
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    with tab_sum:
        st.caption(
            "Cuenta activa del lateral · mismos filtros de período y de traspasos que los gráficos de abajo. "
            "Los **% de peso** son sobre el total de ingresos o de egresos del período."
        )
        tot_mv = float(ing) + float(egr)
        if tot_mv <= 0:
            st.info("No hay ingresos ni egresos de flujo en este período para resumir.")
        else:
            fig_mix = go.Figure(
                data=[
                    go.Pie(
                        labels=["Ingresos", "Egresos"],
                        values=[float(ing), float(egr)],
                        hole=0.45,
                        marker=dict(colors=["#34d399", "#fb7185"]),
                        textinfo="label+percent",
                    )
                ]
            )
            fig_mix.update_layout(
                **layout,
                title="Proporción ingresos vs egresos (volumen movido en el período)",
                showlegend=True,
            )
            st.plotly_chart(fig_mix, use_container_width=True)
        if float(ing) > 0:
            st.metric(
                "Egresos como porcentaje de los ingresos",
                f"{float(egr) / float(ing) * 100:.1f} %",
                help="Si supera 100 %, gastaste más de lo que ingresó en el período.",
            )
        c_s1, c_s2 = st.columns(2)
        with c_s1:
            st.markdown("##### Ingresos por negocio (peso %)")
            ing_df2 = dff_flow[dff_flow["tx_type"] == "ingreso"].copy()
            ing_df2["business"] = ing_df2["business"].fillna("(sin negocio)")
            if ing_df2.empty:
                st.caption("Sin ingresos en el período.")
            else:
                agn2 = (
                    ing_df2.groupby("business", as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                t_ing = float(ing)
                agn2["pct"] = agn2["amount"] / t_ing * 100.0 if t_ing > 0 else 0.0
                agn2 = agn2.rename(
                    columns={
                        "business": "Negocio / fuente",
                        "amount": "Total",
                        "pct": "% del total ingresos",
                    }
                )
                st.dataframe(agn2, use_container_width=True, hide_index=True)
        with c_s2:
            st.markdown("##### Gastos por categoría (peso %)")
            cat_df2 = dff_flow[dff_flow["tx_type"] == "egreso"].copy()
            cat_df2["category"] = cat_df2["category"].fillna("(sin categoría)")
            if cat_df2.empty:
                st.caption("Sin egresos en el período.")
            else:
                agg2 = (
                    cat_df2.groupby("category", as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                t_eg = float(egr)
                agg2["pct"] = agg2["amount"] / t_eg * 100.0 if t_eg > 0 else 0.0
                agg2 = agg2.rename(
                    columns={
                        "category": "Categoría",
                        "amount": "Total",
                        "pct": "% del total egresos",
                    }
                )
                st.dataframe(agg2, use_container_width=True, hide_index=True)

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

    with tab_neg:
        ing_df = dff_flow[dff_flow["tx_type"] == "ingreso"].copy()
        ing_df["business"] = ing_df["business"].fillna("(sin negocio)")
        if ing_df.empty:
            st.caption("No hay ingresos en el período.")
        else:
            agn = (
                ing_df.groupby("business", as_index=False)["amount"]
                .sum()
                .sort_values("amount", ascending=False)
            )
            tot_n = float(agn["amount"].sum()) or 1.0
            agn["pct"] = agn["amount"] / tot_n * 100.0
            st.dataframe(
                agn.rename(
                    columns={
                        "business": "Negocio / fuente",
                        "amount": "Total",
                        "pct": "% del total ingresos",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
            fig_n = go.Figure(
                go.Bar(
                    x=agn["amount"],
                    y=agn["business"],
                    orientation="h",
                    marker=dict(color=agn["amount"], colorscale="Teal", showscale=False),
                )
            )
            fig_n.update_layout(
                **layout,
                title="Ingresos por negocio / fuente",
                xaxis_title=currency,
                yaxis_title="",
            )
            st.plotly_chart(fig_n, use_container_width=True)

    with tab_cat:
        cat_df = dff_flow[dff_flow["tx_type"] == "egreso"].copy()
        cat_df["category"] = cat_df["category"].fillna("(sin categoría)")
        if cat_df.empty:
            st.caption("No hay egresos en el período.")
        else:
            agg = cat_df.groupby("category", as_index=False)["amount"].sum().sort_values(
                "amount", ascending=False
            )
            tot_c = float(agg["amount"].sum()) or 1.0
            agg["pct"] = agg["amount"] / tot_c * 100.0
            st.dataframe(
                agg.rename(
                    columns={
                        "category": "Categoría",
                        "amount": "Total",
                        "pct": "% del total egresos",
                    }
                ),
                use_container_width=True,
                hide_index=True,
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
                title="Gastos por categoría (Casa, Carro, Hijos…)",
                xaxis_title=currency,
                yaxis_title="",
            )
            st.plotly_chart(fig_c, use_container_width=True)
