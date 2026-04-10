"""Tablero: tendencias, metas de ahorro, presupuestos y cumplimiento."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from supabase import Client

from kf_constants import EXPENSE_CATEGORIES
from kf_goals import (
    clear_savings_goal,
    delete_category_budget,
    load_category_budgets,
    load_emergency_fund,
    load_savings_goal,
    goals_tables_missing_message,
    upsert_category_budget,
    upsert_emergency_fund,
    upsert_savings_goal,
    ym_from_date,
)


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


def _bounds_for_goal_month(ym_str: str, today_d: date) -> tuple[date, date]:
    y, m = map(int, ym_str.split("-"))
    start = date(y, m, 1)
    if m == 12:
        end_m = date(y, 12, 31)
    else:
        end_m = date(y, m + 1, 1) - timedelta(days=1)
    if y == today_d.year and m == today_d.month:
        end = today_d
    else:
        end = end_m
    return start, end


def _recent_month_keys(n: int, anchor: date) -> list[str]:
    y, m = anchor.year, anchor.month
    out: list[str] = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    return out


def _budget_status_emoji(pct: float) -> str:
    if pct < 0.8:
        return "🟢"
    if pct <= 1.0:
        return "🟡"
    return "🔴"


def render_finance_dashboard(
    txs: list[dict[str, Any]],
    opening_balance: Decimal,
    currency: str,
    *,
    sb: Client | None = None,
    user_id: str | None = None,
    account_id: str | None = None,
    account_label: str = "",
    accounts: list[dict[str, Any]] | None = None,
) -> None:
    df = txs_to_dataframe(txs)
    today = date.today()
    ym_cur = ym_from_date(today)

    st.markdown(
        """
        <style>
        .kf-hero {
            background: linear-gradient(125deg, #0c1929 0%, #1e3a5f 40%, #0f766e 100%);
            border-radius: 16px; padding: 1.25rem 1.5rem; margin-bottom: 1rem;
            border: 1px solid rgba(56, 189, 248, 0.2);
            box-shadow: 0 12px 40px rgba(0,0,0,0.35);
        }
        .kf-hero h2 { margin: 0; color: #f0f9ff; font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; }
        .kf-hero p { margin: 0.4rem 0 0 0; color: #94a3b8; font-size: 0.9rem; }
        .kf-hero .kf-pill {
            display: inline-block; margin-top: 0.5rem; padding: 0.2rem 0.65rem;
            background: rgba(56, 189, 248, 0.15); color: #7dd3fc; border-radius: 999px;
            font-size: 0.75rem; font-weight: 600;
        }
        .kf-card {
            background: linear-gradient(160deg, rgba(30, 58, 95, 0.95) 0%, rgba(13, 33, 55, 0.98) 100%);
            border: 1px solid rgba(56, 189, 248, 0.22); border-radius: 14px; padding: 1rem 1.15rem;
            margin-bottom: 0.5rem; box-shadow: 0 8px 28px rgba(0,0,0,0.32);
            min-height: 108px;
        }
        .kf-card h4 { margin: 0; color: #7dd3fc; font-size: 0.78rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
        .kf-card p { margin: 0.4rem 0 0 0; font-size: 1.45rem; font-weight: 700; color: #f8fafc; line-height: 1.2; }
        .kf-card .kf-sub { font-size: 0.72rem; color: #94a3b8; margin-top: 0.35rem; font-weight: 400; }
        .kf-net-pos { color: #4ade80 !important; } .kf-net-neg { color: #fb7185 !important; }
        .kf-section-title { color: #e2e8f0; font-size: 1.05rem; font-weight: 600; margin: 1rem 0 0.5rem 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )

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

    _lbl = account_label or "Cuenta activa"
    st.markdown(
        f'<div class="kf-hero"><h2>Tablero financiero</h2><p>{_lbl}</p>'
        f'<span class="kf-pill">Moneda · {currency}</span></div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="kf-card"><h4>↑ Ingresos</h4><p>{float(ing):,.2f} {currency}</p>'
            f'<div class="kf-sub">En el período filtrado</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="kf-card"><h4>↓ Egresos</h4><p>{float(egr):,.2f} {currency}</p>'
            f'<div class="kf-sub">Flujo real</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        cls = "kf-net-pos" if net >= 0 else "kf-net-neg"
        st.markdown(
            f'<div class="kf-card"><h4>◆ Neto</h4><p class="{cls}">{net:,.2f} {currency}</p>'
            f'<div class="kf-sub">Ingresos − egresos</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        bal = float(opening_balance) + float(
            df[df["tx_type"] == "ingreso"]["amount"].sum()
            - df[df["tx_type"] == "egreso"]["amount"].sum()
        )
        st.markdown(
            f'<div class="kf-card"><h4>Saldo proyectado</h4><p>{bal:,.2f} {currency}</p>'
            f'<div class="kf-sub">Saldo inicial + movimientos</div></div>',
            unsafe_allow_html=True,
        )

    if float(ing) > 0:
        st.caption(
            f"En el período: egresos = **{float(egr) / float(ing) * 100:.1f} %** de los ingresos ({currency})."
        )
    elif float(egr) > 0:
        st.caption("En el período hay egresos pero no ingresos en el flujo filtrado.")

    if exclude_transfers and len(dff_tr):
        tr_in = float(dff_tr[dff_tr["tx_type"] == "ingreso"]["amount"].sum())
        tr_out = float(dff_tr[dff_tr["tx_type"] == "egreso"]["amount"].sum())
        st.caption(
            f"Traspasos excluidos del flujo: movimientos **{tr_in:,.2f}** in / **{tr_out:,.2f}** out {currency}."
        )

    ing_c = egr_c = net_c = 0.0
    spent_by_cat: dict[str, float] = {}
    first_m = date(today.year, today.month, 1)
    last_pm = first_m - timedelta(days=1)
    first_pm = date(last_pm.year, last_pm.month, 1)

    if len(df):
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

        ce = cur[cur["tx_type"] == "egreso"]
        if len(ce):
            spent_by_cat = (
                ce.groupby(ce["category"].fillna("(sin categoría)"))["amount"]
                .sum()
                .to_dict()
            )

        def _pct_delta(new_v: float, old_v: float) -> str | None:
            if old_v == 0:
                return None
            return f"{((new_v - old_v) / abs(old_v) * 100):+.1f}% vs mes ant."

        st.markdown('<p class="kf-section-title">Mes en curso vs anterior</p>', unsafe_allow_html=True)
        st.caption(
            f"{first_m.isoformat()} → {today.isoformat()} · comparado con "
            f"{first_pm.isoformat()} → {last_pm.isoformat()}"
        )
        v1, v2, v3 = st.columns(3)
        with v1:
            st.metric(
                "Ingresos (mes)",
                f"{ing_c:,.2f}",
                delta=_pct_delta(ing_c, ing_p),
                help=f"Anterior: {ing_p:,.2f} {currency}",
            )
        with v2:
            st.metric(
                "Egresos (mes)",
                f"{egr_c:,.2f}",
                delta=_pct_delta(egr_c, egr_p),
                help=f"Anterior: {egr_p:,.2f} {currency}",
            )
        with v3:
            st.metric(
                "Ahorro / neto (mes)",
                f"{net_c:,.2f}",
                delta=_pct_delta(net_c, net_p),
                help=f"Anterior: {net_p:,.2f} {currency}",
            )

    st.divider()
    st.markdown('<p class="kf-section-title">Metas y cumplimiento (mes calendario)</p>', unsafe_allow_html=True)
    st.caption(
        "Aplica a la **cuenta del lateral** y su moneda. Ejecutá **`patch_009_goals_budgets.sql`** en Supabase si no cargan las metas."
    )

    budgets: list[dict[str, Any]] = []
    sg: dict[str, Any] | None = None
    emg: dict[str, Any] | None = None
    goal_ym = ym_cur
    target_save: float | None = None

    if sb and user_id and accounts is not None:
        goal_ym = st.selectbox(
            "Mes de las metas",
            options=_recent_month_keys(6, today),
            index=0,
            key="dash_goal_ym",
        )

        sg = load_savings_goal(sb, user_id, goal_ym, currency)
        budgets = load_category_budgets(sb, user_id, goal_ym, currency)
        emg = load_emergency_fund(sb, user_id)
        em_acc = str(emg.get("account_id") or "") if emg else ""
        em_tgt = float(emg.get("target_amount") or 0) if emg else 0.0

        g0, g1 = _bounds_for_goal_month(goal_ym, today)
        mg = (df["tx_date"] >= g0) & (df["tx_date"] <= g1)
        dfg = df.loc[mg] if len(df) else df.iloc[0:0]
        if exclude_transfers and len(dfg):
            dfg = dfg.loc[~_is_transfer_like_df(dfg)]
        ing_g = float(dfg[dfg["tx_type"] == "ingreso"]["amount"].sum())
        egr_g = float(dfg[dfg["tx_type"] == "egreso"]["amount"].sum())
        net_g = ing_g - egr_g
        spent_goal_cat: dict[str, float] = {}
        ce_g = dfg[dfg["tx_type"] == "egreso"]
        if len(ce_g):
            spent_goal_cat = (
                ce_g.groupby(ce_g["category"].fillna("(sin categoría)"))["amount"]
                .sum()
                .to_dict()
            )

        if sg:
            if sg.get("goal_mode") == "percent_income" and ing_g > 0:
                target_save = ing_g * (float(sg.get("target_numeric") or 0) / 100.0)
            elif sg.get("goal_mode") == "fixed_amount":
                target_save = float(sg.get("target_numeric") or 0)

        colg1, colg2 = st.columns(2)
        with colg1:
            st.markdown("##### Meta de ahorro")
            if target_save and target_save > 0:
                prog = max(0.0, min(1.0, net_g / target_save)) if target_save else 0.0
                st.progress(prog)
                st.caption(
                    f"Mes **{goal_ym}** · ahorro **{net_g:,.2f}** {currency} · objetivo **{target_save:,.2f}** "
                    f"({'≥ meta ✓' if net_g >= target_save else 'por debajo'})"
                )
            elif sg:
                st.caption("Meta definida pero sin ingresos este mes para calcular % (o revisá el modo).")
            else:
                st.caption("Sin meta configurada para este mes/moneda.")

        with colg2:
            st.markdown("##### Fondo de emergencia")
            if em_acc and em_tgt > 0 and str(account_id) == em_acc:
                prog_e = max(0.0, min(1.0, bal / em_tgt))
                st.progress(prog_e)
                st.caption(
                    f"Saldo actual **{bal:,.2f}** · objetivo **{em_tgt:,.2f}** {currency} "
                    f"({prog_e * 100:.0f} %)"
                )
            elif em_acc and em_tgt > 0:
                st.caption(
                    "La meta de emergencia está en **otra cuenta**. Abrí esa cuenta en el lateral para ver el progreso aquí."
                )
            else:
                st.caption("Sin fondo de emergencia configurado.")

        if budgets:
            st.markdown(f"##### Presupuesto por rubro (mes {goal_ym})")
            for b in budgets:
                cat = str(b.get("category", ""))
                lim = float(b.get("budget_limit") or 0)
                spent = float(spent_goal_cat.get(cat, 0) or 0)
                pct = (spent / lim) if lim > 0 else 0.0
                emj = _budget_status_emoji(pct)
                st.progress(min(1.0, pct))
                st.caption(f"{emj} **{cat}** · gastado **{spent:,.2f}** / **{lim:,.2f}** {currency} ({pct * 100:.0f} % del tope)")

        with st.expander("Configurar metas, presupuestos y emergencia", expanded=False):
            st.caption(f"Usuario actual · moneda **{currency}** · mes **{goal_ym}** (alineá con el selector de arriba).")
            with st.form("dash_save_goal"):
                mode = st.radio(
                    "Tipo de meta de ahorro",
                    ["Monto fijo a ahorrar este mes", "Porcentaje de los ingresos del mes"],
                    horizontal=True,
                )
                val = st.number_input(
                    "Valor (monto en moneda de la cuenta, o % si elegiste porcentaje)",
                    min_value=0.0,
                    value=float(sg.get("target_numeric") or 0) if sg else 0.0,
                    step=1.0,
                )
                if st.form_submit_button("Guardar meta"):
                    if val <= 0:
                        ok, err = clear_savings_goal(sb, user_id, goal_ym, currency)
                    else:
                        gm = "fixed_amount" if mode.startswith("Monto") else "percent_income"
                        ok, err = upsert_savings_goal(sb, user_id, goal_ym, currency, gm, val)
                    if ok:
                        st.success("Meta actualizada.")
                        st.rerun()
                    else:
                        st.error(goals_tables_missing_message(err or ""))

            with st.form("dash_clear_goal"):
                st.caption("Quitar solo la meta de ahorro de este mes/moneda.")
                if st.form_submit_button("Quitar meta de ahorro"):
                    ok, err = clear_savings_goal(sb, user_id, goal_ym, currency)
                    if ok:
                        st.success("Meta eliminada.")
                        st.rerun()
                    else:
                        st.error(err or "")

            st.markdown("**Fondo de emergencia** (una cuenta + saldo objetivo)")
            acc_opts = {str(a["id"]): f'{a.get("label")} ({a.get("currency", "?")})' for a in accounts}
            _acc_keys = list(acc_opts.keys())
            _em_idx = 0
            if em_acc in acc_opts:
                _em_idx = _acc_keys.index(em_acc) + 1
            with st.form("dash_emg"):
                pick = st.selectbox(
                    "Cuenta del colchón",
                    [""] + _acc_keys,
                    format_func=lambda x: "—" if not x else acc_opts[x],
                    index=_em_idx,
                )
                tgt = st.number_input(
                    "Saldo objetivo",
                    min_value=0.0,
                    value=em_tgt if em_tgt > 0 else 0.0,
                    step=100.0,
                )
                if st.form_submit_button("Guardar emergencia"):
                    ok, err = upsert_emergency_fund(sb, user_id, pick or None, tgt if tgt > 0 else None)
                    if ok:
                        st.success("Guardado.")
                        st.rerun()
                    else:
                        st.error(goals_tables_missing_message(err or ""))

            st.markdown("**Tope por rubro** (egresos del mes, sin traspasos)")
            bc = st.selectbox("Rubro", EXPENSE_CATEGORIES, key="dash_bcat")
            with st.form("dash_budget_row"):
                blim = st.number_input("Límite mensual", min_value=0.0, value=0.0, step=10.0)
                if st.form_submit_button("Guardar / actualizar tope"):
                    ok, err = upsert_category_budget(sb, user_id, goal_ym, currency, bc, blim)
                    if ok:
                        st.success("Presupuesto guardado.")
                        st.rerun()
                    else:
                        st.error(goals_tables_missing_message(err or ""))

            if budgets:
                st.caption("Eliminar un tope guardado:")
                for b in budgets:
                    bid = str(b.get("id", ""))
                    if bid and st.button(f"Borrar {b.get('category')}", key=f"delbud_{bid}"):
                        ok, err = delete_category_budget(sb, bid)
                        if ok:
                            st.rerun()
                        else:
                            st.error(err or "")
    else:
        st.info("Iniciá sesión y cargá cuentas para usar metas y presupuestos.")

    st.divider()

    if dff_flow.empty:
        st.info("No hay movimientos de flujo en el período elegido para graficar.")
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

    tab_met, tab_sum, tab_d, tab_m, tab_y, tab_neg, tab_cat = st.tabs(
        [
            "Cumplimiento",
            "Resumen",
            "Diario",
            "Mensual",
            "Anual",
            "Ingresos",
            "Gastos",
        ]
    )

    layout = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,23,42,0.55)",
        font=dict(color="#e2e8f0"),
        margin=dict(l=40, r=20, t=48, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    with tab_met:
        st.caption(
            f"Mes de metas seleccionado arriba (**{goal_ym}**) · cuenta lateral · gastos sin traspasos."
        )
        if budgets and sb and user_id:
            g0, g1 = _bounds_for_goal_month(goal_ym, today)
            mg = (df["tx_date"] >= g0) & (df["tx_date"] <= g1)
            dfg = df.loc[mg] if len(df) else df.iloc[0:0]
            if exclude_transfers and len(dfg):
                dfg = dfg.loc[~_is_transfer_like_df(dfg)]
            sg_spent: dict[str, float] = {}
            ce_g = dfg[dfg["tx_type"] == "egreso"]
            if len(ce_g):
                sg_spent = (
                    ce_g.groupby(ce_g["category"].fillna("(sin categoría)"))["amount"]
                    .sum()
                    .to_dict()
                )
            cats = [str(b.get("category")) for b in budgets]
            lims = [float(b.get("budget_limit") or 0) for b in budgets]
            sps = [float(sg_spent.get(c, 0) or 0) for c in cats]
            fig_b = go.Figure()
            fig_b.add_trace(
                go.Bar(name="Gastado", y=cats, x=sps, orientation="h", marker_color="#fb7185")
            )
            fig_b.add_trace(
                go.Bar(name="Tope", y=cats, x=lims, orientation="h", marker_color="rgba(56,189,248,0.35)")
            )
            fig_b.update_layout(
                **layout,
                title="Presupuesto vs gastado (mes en curso)",
                barmode="group",
                xaxis_title=currency,
            )
            st.plotly_chart(fig_b, use_container_width=True)
        else:
            st.caption("Definí topes por rubro en **Configurar metas** para ver este gráfico.")
        if target_save and target_save > 0 and sb and user_id:
            g0, g1 = _bounds_for_goal_month(goal_ym, today)
            mg = (df["tx_date"] >= g0) & (df["tx_date"] <= g1)
            dfg = df.loc[mg] if len(df) else df.iloc[0:0]
            if exclude_transfers and len(dfg):
                dfg = dfg.loc[~_is_transfer_like_df(dfg)]
            net_tab = float(
                dfg[dfg["tx_type"] == "ingreso"]["amount"].sum()
                - dfg[dfg["tx_type"] == "egreso"]["amount"].sum()
            )
            fig_g = go.Figure(
                go.Bar(
                    x=["Ahorro del mes", "Meta"],
                    y=[max(0, net_tab), target_save],
                    marker_color=["#34d399", "#38bdf8"],
                )
            )
            fig_g.update_layout(
                **layout, title=f"Ahorro vs meta ({goal_ym})", yaxis_title=currency
            )
            st.plotly_chart(fig_g, use_container_width=True)

    with tab_sum:
        st.caption("Período seleccionado arriba · peso % sobre totales de ingreso o egreso.")
        tot_mv = float(ing) + float(egr)
        if tot_mv <= 0:
            st.info("No hay ingresos ni egresos de flujo en este período.")
        else:
            fig_mix = go.Figure(
                data=[
                    go.Pie(
                        labels=["Ingresos", "Egresos"],
                        values=[float(ing), float(egr)],
                        hole=0.5,
                        marker=dict(colors=["#34d399", "#fb7185"], line=dict(color="#0f172a", width=2)),
                        textinfo="label+percent",
                    )
                ]
            )
            fig_mix.update_layout(
                **layout,
                title="Ingresos vs egresos (volumen del período)",
                showlegend=True,
            )
            st.plotly_chart(fig_mix, use_container_width=True)
        if float(ing) > 0:
            st.metric(
                "Egresos / ingresos",
                f"{float(egr) / float(ing) * 100:.1f} %",
                help="Si supera 100 %, gastaste más de lo ingresado en el período.",
            )
        c_s1, c_s2 = st.columns(2)
        with c_s1:
            st.markdown("##### Ingresos por negocio")
            ing_df2 = dff_flow[dff_flow["tx_type"] == "ingreso"].copy()
            ing_df2["business"] = ing_df2["business"].fillna("(sin negocio)")
            if ing_df2.empty:
                st.caption("Sin ingresos.")
            else:
                agn2 = (
                    ing_df2.groupby("business", as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                t_ing = float(ing)
                agn2["pct"] = agn2["amount"] / t_ing * 100.0 if t_ing > 0 else 0.0
                st.dataframe(
                    agn2.rename(
                        columns={
                            "business": "Negocio / fuente",
                            "amount": "Total",
                            "pct": "% del total",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
        with c_s2:
            st.markdown("##### Gastos por categoría")
            cat_df2 = dff_flow[dff_flow["tx_type"] == "egreso"].copy()
            cat_df2["category"] = cat_df2["category"].fillna("(sin categoría)")
            if cat_df2.empty:
                st.caption("Sin egresos.")
            else:
                agg2 = (
                    cat_df2.groupby("category", as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                t_eg = float(egr)
                agg2["pct"] = agg2["amount"] / t_eg * 100.0 if t_eg > 0 else 0.0
                st.dataframe(
                    agg2.rename(
                        columns={
                            "category": "Categoría",
                            "amount": "Total",
                            "pct": "% del total",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
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
                name="Neto acumulado",
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
        fig_m.update_layout(**layout, title="Por mes", barmode="group")
        st.plotly_chart(fig_m, use_container_width=True)

    with tab_y:
        fig_y = go.Figure(
            data=[
                go.Bar(name="Ingresos", x=yearly["yr"], y=yearly["ingreso"], marker_color="#22c55e"),
                go.Bar(name="Egresos", x=yearly["yr"], y=yearly["egreso"], marker_color="#ef4444"),
            ]
        )
        fig_y.update_layout(**layout, title="Por año", barmode="group")
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
                        "pct": "% del total",
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
                title="Ingresos por negocio",
                xaxis_title=currency,
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
                        "pct": "% del total",
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
                title="Gastos por categoría",
                xaxis_title=currency,
            )
            st.plotly_chart(fig_c, use_container_width=True)
