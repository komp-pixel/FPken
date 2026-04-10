"""Tablero: tendencias, metas de ahorro, presupuestos y cumplimiento."""

from __future__ import annotations

import html
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from supabase import Client

from kf_constants import EXPENSE_CATEGORIES
from kf_theme import is_dark_theme
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


def _chart_bounds(
    d0: date | None,
    d1: date | None,
    dff_flow: pd.DataFrame,
    df: pd.DataFrame,
) -> tuple[date | None, date | None]:
    """Rango de fechas para rellenar meses/años (incluso con ceros)."""
    if d0 is not None and d1 is not None:
        return d0, d1
    if len(dff_flow):
        return (
            pd.Timestamp(dff_flow["tx_date"].min()).date(),
            pd.Timestamp(dff_flow["tx_date"].max()).date(),
        )
    if len(df):
        return (
            pd.Timestamp(df["tx_date"].min()).date(),
            pd.Timestamp(df["tx_date"].max()).date(),
        )
    return None, None


def _expand_monthly_table(
    monthly: pd.DataFrame,
    cb0: date,
    cb1: date,
) -> pd.DataFrame:
    """Todos los meses calendario entre cb0 y cb1 con ingreso/egreso (0 si no hubo flujo)."""
    p0 = pd.Timestamp(cb0).to_period("M")
    p1 = pd.Timestamp(cb1).to_period("M")
    pr = pd.period_range(p0, p1, freq="M")
    full = pd.DataFrame({"ym": pr.astype(str)})
    if len(monthly) and "ym" in monthly.columns:
        cols = [c for c in ("ym", "ingreso", "egreso") if c in monthly.columns]
        full = full.merge(monthly[cols], on="ym", how="left")
    if "ingreso" not in full.columns:
        full["ingreso"] = 0.0
        full["egreso"] = 0.0
    full["ingreso"] = full["ingreso"].fillna(0.0)
    full["egreso"] = full["egreso"].fillna(0.0)
    full["neto"] = full["ingreso"] - full["egreso"]
    _meses = (
        "ene",
        "feb",
        "mar",
        "abr",
        "may",
        "jun",
        "jul",
        "ago",
        "sep",
        "oct",
        "nov",
        "dic",
    )

    def _lbl(ym: str) -> str:
        try:
            y, m = ym.split("-")
            return f"{_meses[int(m) - 1]} {y}"
        except (ValueError, IndexError):
            return ym

    full["Mes"] = full["ym"].map(_lbl)
    return full


def _expand_yearly_table(
    yearly: pd.DataFrame,
    cb0: date,
    cb1: date,
) -> pd.DataFrame:
    years = [str(y) for y in range(cb0.year, cb1.year + 1)]
    full = pd.DataFrame({"yr": years})
    if len(yearly) and "yr" in yearly.columns:
        cols = [c for c in ("yr", "ingreso", "egreso") if c in yearly.columns]
        full = full.merge(yearly[cols], on="yr", how="left")
    if "ingreso" not in full.columns:
        full["ingreso"] = 0.0
        full["egreso"] = 0.0
    full["ingreso"] = full["ingreso"].fillna(0.0)
    full["egreso"] = full["egreso"].fillna(0.0)
    full["neto"] = full["ingreso"] - full["egreso"]
    return full


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
    bal = float(opening_balance) + float(
        df[df["tx_type"] == "ingreso"]["amount"].sum()
        - df[df["tx_type"] == "egreso"]["amount"].sum()
    )
    _net_cls = "lk-pos" if net >= 0 else "lk-neg"
    st.markdown(
        f'<div class="lk-canvas">'
        f'<div class="lk-top">'
        f'<div><p class="lk-brand">Kenny <em>Finanzas</em></p>'
        f'<p class="lk-subtitle">{_lbl}</p></div>'
        f'<span class="lk-pill">{currency}</span></div>'
        f'<div class="lk-grid">'
        f'<div class="lk-stat"><h4>Ingresos</h4>'
        f'<p class="lk-val">{float(ing):,.2f} {currency}</p>'
        f'<p class="lk-foot">Período seleccionado</p></div>'
        f'<div class="lk-stat"><h4>Egresos</h4>'
        f'<p class="lk-val">{float(egr):,.2f} {currency}</p>'
        f'<p class="lk-foot">Flujo real</p></div>'
        f'<div class="lk-stat"><h4>Neto</h4>'
        f'<p class="lk-val {_net_cls}">{net:,.2f} {currency}</p>'
        f'<p class="lk-foot">Ingresos − egresos</p></div>'
        f'<div class="lk-stat lk-stat-blue"><h4>Saldo proyectado</h4>'
        f'<p class="lk-val">{bal:,.2f} {currency}</p>'
        f'<p class="lk-foot">Saldo inicial + movimientos</p></div>'
        f"</div></div>",
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

        def _month_compare_foot(new_v: float, old_v: float) -> str:
            """HTML pie de tarjeta: % vs mes ant. + referencia (texto oscuro vía lk-*)."""
            cur_e = html.escape(str(currency))
            d = _pct_delta(new_v, old_v)
            if d is None:
                return (
                    f'<p class="lk-foot">Mes anterior: {old_v:,.2f} {cur_e} '
                    f"(sin % de cambio)</p>"
                )
            cls = "lk-pos" if d.startswith("+") else "lk-neg"
            return (
                f'<p class="lk-foot {cls}" style="font-weight:700;">{html.escape(d)}</p>'
                f'<p class="lk-foot">Ant.: {old_v:,.2f} {cur_e}</p>'
            )

        st.markdown(
            '<p class="lk-section">Mes en curso vs mes anterior</p>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"{first_m.isoformat()} → {today.isoformat()} · comparado con "
            f"{first_pm.isoformat()} → {last_pm.isoformat()}"
        )
        cur_e = html.escape(str(currency))
        _net_cls = "lk-pos" if net_c >= 0 else "lk-neg"
        st.markdown(
            f'<div class="lk-grid" style="margin-top:0.65rem;">'
            f'<div class="lk-stat"><h4>Ingresos (mes)</h4>'
            f'<p class="lk-val">{ing_c:,.2f} {cur_e}</p>'
            f"{_month_compare_foot(ing_c, ing_p)}</div>"
            f'<div class="lk-stat"><h4>Egresos (mes)</h4>'
            f'<p class="lk-val">{egr_c:,.2f} {cur_e}</p>'
            f"{_month_compare_foot(egr_c, egr_p)}</div>"
            f'<div class="lk-stat"><h4>Ahorro / neto (mes)</h4>'
            f'<p class="lk-val {_net_cls}">{net_c:,.2f} {cur_e}</p>'
            f"{_month_compare_foot(net_c, net_p)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown(
        '<p class="lk-section">Metas y cumplimiento</p>'
        '<p class="lk-hint">Mes calendario · misma moneda que la cuenta del lateral</p>',
        unsafe_allow_html=True,
    )
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
            st.markdown(
                '<p class="lk-panel-h">Meta de ahorro</p>',
                unsafe_allow_html=True,
            )
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
            st.markdown(
                '<p class="lk-panel-h">Fondo de emergencia</p>',
                unsafe_allow_html=True,
            )
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
            st.markdown(
                f'<p class="lk-panel-h">Presupuesto por rubro (mes {html.escape(goal_ym)})</p>',
                unsafe_allow_html=True,
            )
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

    cb0, cb1 = _chart_bounds(d0, d1, dff_flow, df)
    if cb0 is None or cb1 is None:
        st.info("No hay movimientos registrados en esta cuenta para graficar.")
        return

    if dff_flow.empty:
        st.caption(
            "**Sin ingresos ni egresos de flujo** en el período (puede ser que solo registraste **traspasos** "
            "con «excluir traspasos» activo, o que no hubo movimientos). "
            "Igual ves **cada mes del rango** con **0** para ubicarte en el calendario."
        )

    if len(dff_flow):
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
    else:
        daily = pd.DataFrame(columns=["tx_date", "ingreso", "egreso", "neto"])
        monthly = pd.DataFrame(columns=["ym", "ingreso", "egreso", "neto"])
        yearly = pd.DataFrame(columns=["yr", "ingreso", "egreso", "neto"])

    monthly_full = _expand_monthly_table(monthly, cb0, cb1)
    yearly_full = _expand_yearly_table(yearly, cb0, cb1)

    tab_met, tab_sum, tab_d, tab_m, tab_y, tab_neg, tab_cat = st.tabs(
        [
            "🎯 Cumplimiento",
            "📎 Resumen",
            "📅 Diario",
            "🗓 Mensual",
            "📆 Anual",
            "🔺 Ingresos",
            "🔻 Gastos",
        ]
    )

    if is_dark_theme():
        layout = dict(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#1e293b",
            font=dict(color="#e2e8f0", family="system-ui, -apple-system, sans-serif", size=13),
            margin=dict(l=48, r=28, t=52, b=44),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        _axis_style = dict(gridcolor="#334155", linecolor="#475569", showgrid=True)
    else:
        layout = dict(
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#f8fafc",
            font=dict(color="#334155", family="system-ui, -apple-system, sans-serif", size=13),
            margin=dict(l=48, r=28, t=52, b=44),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        _axis_style = dict(gridcolor="#e2e8f0", linecolor="#cbd5e1", showgrid=True)

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
                go.Bar(name="Gastado", y=cats, x=sps, orientation="h", marker_color="#f97316")
            )
            fig_b.add_trace(
                go.Bar(name="Tope", y=cats, x=lims, orientation="h", marker_color="#93c5fd")
            )
            fig_b.update_layout(
                **layout,
                title="Presupuesto vs gastado",
                barmode="group",
                xaxis=dict(title=currency, **_axis_style),
                yaxis=dict(**_axis_style),
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
                    marker_color=["#22c55e", "#2563eb"],
                )
            )
            fig_g.update_layout(
                **layout,
                title=f"Ahorro vs meta ({goal_ym})",
                xaxis=dict(**_axis_style),
                yaxis=dict(title=currency, **_axis_style),
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
                        marker=dict(colors=["#22c55e", "#f97316"], line=dict(color="#fff", width=2)),
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
            st.markdown(
                '<p class="lk-panel-h">Ingresos por negocio</p>',
                unsafe_allow_html=True,
            )
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
            st.markdown(
                '<p class="lk-panel-h">Gastos por categoría</p>',
                unsafe_allow_html=True,
            )
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
        if len(daily):
            fig_d = go.Figure()
            fig_d.add_trace(
                go.Bar(
                    x=daily["tx_date"],
                    y=daily["ingreso"],
                    name="Ingresos",
                    marker_color="#22c55e",
                )
            )
            fig_d.add_trace(
                go.Bar(
                    x=daily["tx_date"],
                    y=daily["egreso"],
                    name="Egresos",
                    marker_color="#f97316",
                )
            )
            fig_d.update_layout(
                **layout,
                title="Flujo por día",
                barmode="group",
                xaxis=dict(title="Fecha", **_axis_style),
                yaxis=dict(title=currency, **_axis_style),
            )
            st.plotly_chart(fig_d, use_container_width=True)

            fig_line = go.Figure()
            fig_line.add_trace(
                go.Scatter(
                    x=daily["tx_date"],
                    y=daily["neto"].cumsum(),
                    fill="tozeroy",
                    name="Neto acumulado",
                    line=dict(color="#2563eb", width=2),
                    fillcolor="rgba(37, 99, 235, 0.12)",
                )
            )
            fig_line.update_layout(
                **layout,
                title="Neto acumulado en el período",
                xaxis=dict(**_axis_style),
                yaxis=dict(title=currency, **_axis_style),
            )
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info(
                "No hay **flujo diario** que mostrar (sin ingresos/egresos en el período, o solo traspasos excluidos). "
                f"Probá el tab **Mensual**: ahí figuran los meses **{cb0}** → **{cb1}** aunque estén en cero."
            )

    with tab_m:
        st.caption(
            f"Rango del gráfico: **{cb0}** → **{cb1}** · moneda **{currency}** · "
            "cada barra es un **mes calendario** (meses sin movimientos = **0**)."
        )
        fig_m = go.Figure()
        fig_m.add_trace(
            go.Bar(
                x=monthly_full["Mes"],
                y=monthly_full["ingreso"],
                name="Ingresos",
                marker_color="#22c55e",
            )
        )
        fig_m.add_trace(
            go.Bar(
                x=monthly_full["Mes"],
                y=monthly_full["egreso"],
                name="Egresos",
                marker_color="#f97316",
            )
        )
        fig_m.update_layout(
            **layout,
            title="Por mes (desglose completo del período)",
            barmode="group",
            xaxis=dict(**_axis_style),
            yaxis=dict(title=currency, **_axis_style),
        )
        st.plotly_chart(fig_m, use_container_width=True)
        st.markdown("**Tabla mes a mes** (mismos totales que las barras)")
        st.dataframe(
            monthly_full.rename(
                columns={
                    "ym": "Año-mes",
                    "Mes": "Mes",
                    "ingreso": "Ingresos",
                    "egreso": "Egresos",
                    "neto": "Neto",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    with tab_y:
        st.caption(
            f"Años que cruzan **{cb0}** → **{cb1}** (si solo cae un año, verás una sola barra)."
        )
        fig_y = go.Figure(
            data=[
                go.Bar(
                    name="Ingresos",
                    x=yearly_full["yr"],
                    y=yearly_full["ingreso"],
                    marker_color="#22c55e",
                ),
                go.Bar(
                    name="Egresos",
                    x=yearly_full["yr"],
                    y=yearly_full["egreso"],
                    marker_color="#ef4444",
                ),
            ]
        )
        fig_y.update_layout(
            **layout,
            title="Por año",
            barmode="group",
            xaxis=dict(**_axis_style),
            yaxis=dict(title=currency, **_axis_style),
        )
        st.plotly_chart(fig_y, use_container_width=True)
        st.dataframe(
            yearly_full.rename(
                columns={
                    "yr": "Año",
                    "ingreso": "Ingresos",
                    "egreso": "Egresos",
                    "neto": "Neto",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

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
                xaxis=dict(title=currency, **_axis_style),
                yaxis=dict(**_axis_style),
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
                xaxis=dict(title=currency, **_axis_style),
                yaxis=dict(**_axis_style),
            )
            st.plotly_chart(fig_c, use_container_width=True)


def txs_to_dataframe_with_accounts(
    txs: list[dict[str, Any]], accounts: list[dict[str, Any]]
) -> pd.DataFrame:
    """Mismo esquema que txs_to_dataframe + cuenta y moneda de cada movimiento."""
    amap = {str(a["id"]): a for a in accounts}
    df = txs_to_dataframe(txs)
    if df.empty or not txs:
        return df
    acc_ids: list[str] = []
    labels: list[str] = []
    curs: list[str] = []
    for t in txs:
        aid = str(t.get("account_id") or "")
        acc_ids.append(aid)
        a = amap.get(aid, {})
        labels.append(str(a.get("label") or "—"))
        curs.append(str(a.get("currency") or "?"))
    out = df.copy()
    out["account_id"] = acc_ids
    out["account_label"] = labels
    out["currency"] = curs
    return out


def _traspaso_pairs_for_panorama(dff_tr: pd.DataFrame) -> pd.DataFrame:
    """Tabla legible origen → destino; `dff_tr` ya filtrada a movimientos tipo traspaso."""
    if dff_tr.empty:
        return pd.DataFrame(
            columns=[
                "Fecha",
                "Origen",
                "M. origen",
                "Sale",
                "Destino",
                "M. destino",
                "Entra",
                "Descripción",
                "Nota",
            ]
        )
    rows: list[dict[str, Any]] = []
    dc = dff_tr.copy()
    dc["_gid"] = dc["transfer_group_id"].fillna("").astype(str).str.strip()
    paired = dc[dc["_gid"] != ""]
    for _gid, g in paired.groupby("_gid", sort=False):
        g = g.sort_values("tx_date")
        dt = g["tx_date"].min()
        eg = g[g["tx_type"] == "egreso"]
        inn = g[g["tx_type"] == "ingreso"]
        o_lab = str(eg.iloc[0]["account_label"]) if len(eg) else "—"
        o_cur = str(eg.iloc[0]["currency"]) if len(eg) else "—"
        d_lab = str(inn.iloc[0]["account_label"]) if len(inn) else "—"
        d_cur = str(inn.iloc[0]["currency"]) if len(inn) else "—"
        a_out = float(eg.iloc[0]["amount"]) if len(eg) else float("nan")
        a_in = float(inn.iloc[0]["amount"]) if len(inn) else float("nan")
        d1 = str(eg.iloc[0].get("description") or "") if len(eg) else ""
        d2 = str(inn.iloc[0].get("description") or "") if len(inn) else ""
        desc = (d1 or d2)[:140]
        rows.append(
            {
                "Fecha": dt,
                "Origen": o_lab,
                "M. origen": o_cur,
                "Sale": a_out,
                "Destino": d_lab,
                "M. destino": d_cur,
                "Entra": a_in,
                "Descripción": desc,
                "Nota": "",
            }
        )
    orphans = dc[dc["_gid"] == ""]
    for _, r in orphans.iterrows():
        tt = str(r.get("tx_type") or "")
        rows.append(
            {
                "Fecha": r["tx_date"],
                "Origen": str(r["account_label"]) if tt == "egreso" else "—",
                "M. origen": str(r["currency"]) if tt == "egreso" else "—",
                "Sale": float(r["amount"]) if tt == "egreso" else float("nan"),
                "Destino": str(r["account_label"]) if tt == "ingreso" else "—",
                "M. destino": str(r["currency"]) if tt == "ingreso" else "—",
                "Entra": float(r["amount"]) if tt == "ingreso" else float("nan"),
                "Descripción": str(r.get("description") or "")[:140],
                "Nota": "Sin ID de grupo (una pierna)",
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("Fecha", ascending=False).reset_index(drop=True)


def render_global_accounts_panorama(
    sb: Client,
    accounts: list[dict[str, Any]],
    load_transactions_for_accounts_fn: Any,
) -> None:
    """
    Panorama por moneda: ingresos **negocio → cuenta**, egresos **cuenta → rubro**;
    traspasos en bloque aparte; resumen por cuenta opcional.
    """
    st.markdown(
        '<p class="lk-section" style="margin-top:0;">🌎 Panorama de todas las cuentas</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "**Entradas:** de qué negocio cae el dinero y **en qué cuenta**. "
        "**Salidas:** de qué cuenta sale y **en qué rubro** gastás. "
        "Los **traspasos** van aparte (no mezclarlos con negocio/gasto real)."
    )
    today = date.today()
    exclude_transfers = st.checkbox(
        "Excluir traspasos del análisis de ingresos/egresos (recomendado)",
        value=True,
        key="gpan_ex_tr",
        help="Si está marcado, las tablas de negocio y rubro no cuentan movimientos entre tus cuentas.",
    )
    show_pct = st.checkbox(
        "Mostrar porcentajes en las tablas",
        value=False,
        key="gpan_show_pct",
    )
    range_key = st.selectbox(
        "Período del panorama",
        [
            "Últimos 30 días",
            "Este mes",
            "Este año",
            "Últimos 12 meses",
            "Todo",
            "Personalizado",
        ],
        index=0,
        key="gpan_range",
    )
    if range_key == "Personalizado":
        c0, c1 = st.columns(2)
        with c0:
            d0 = st.date_input("Desde", value=today - timedelta(days=29), key="gpan_d0")
        with c1:
            d1 = st.date_input("Hasta", value=today, key="gpan_d1")
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

    ids = [str(a["id"]) for a in accounts]
    if not ids:
        st.info("No hay cuentas cargadas.")
        return
    try:
        all_txs = load_transactions_for_accounts_fn(sb, ids)
    except Exception as e:
        st.warning("No se pudieron cargar los movimientos de todas las cuentas.")
        st.caption(str(e)[:200])
        return

    df = txs_to_dataframe_with_accounts(all_txs, accounts)
    if len(df) and d0 is not None and d1 is not None:
        dff = df.loc[(df["tx_date"] >= d0) & (df["tx_date"] <= d1)].copy()
    else:
        dff = df.copy()

    if exclude_transfers and len(dff):
        _tr = _is_transfer_like_df(dff)
        dff_flow = dff.loc[~_tr].copy()
    else:
        dff_flow = dff.copy()

    if dff.empty:
        st.info("No hay movimientos en el período seleccionado.")
        return

    if dff_flow.empty:
        st.info(
            "No hay **ingresos ni egresos “reales”** en este período "
            "(solo traspasos entre cuentas, o nada). Revisá la sección **Traspasos** abajo."
        )
    else:
        currencies = sorted(
            {str(c) for c in dff_flow["currency"].dropna().unique() if str(c).strip()},
            key=lambda x: (x != "USD", x != "USDT", x),
        )
        for cur in currencies:
            sub = dff_flow[dff_flow["currency"] == cur]
            if sub.empty:
                continue
            ing = sub[sub["tx_type"] == "ingreso"]["amount"].sum()
            egr = sub[sub["tx_type"] == "egreso"]["amount"].sum()
            net = float(ing) - float(egr)
            st.markdown(
                f'<p class="lk-panel-h">Moneda {html.escape(cur)}</p>',
                unsafe_allow_html=True,
            )
            m1, m2, m3 = st.columns(3)
            m1.metric("Ingresos (sin traspasos)", f"{float(ing):,.2f}")
            m2.metric("Egresos (sin traspasos)", f"{float(egr):,.2f}")
            m3.metric("Neto", f"{net:,.2f}")

            st.markdown("**Entradas** — negocio / fuente → **cuenta donde cae el dinero**")
            ing_df = sub[sub["tx_type"] == "ingreso"].copy()
            ing_df["business"] = ing_df["business"].fillna("(sin negocio)")
            if ing_df.empty:
                st.caption("Sin ingresos en esta moneda en el período.")
            else:
                agn = (
                    ing_df.groupby(["business", "account_label"], as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                agn = agn.rename(
                    columns={
                        "business": "Negocio / fuente",
                        "account_label": "Cuenta donde entra",
                        "amount": f"Total ({cur})",
                    }
                )
                if show_pct:
                    tot_i = float(ing_df["amount"].sum()) or 1.0
                    agn["% del total ingresos"] = (agn[f"Total ({cur})"] / tot_i * 100.0).map(
                        lambda x: f"{x:.1f} %"
                    )
                st.dataframe(agn, use_container_width=True, hide_index=True)

            st.markdown("**Salidas** — **cuenta de la que sale** → rubro / en qué gastás")
            eg_df = sub[sub["tx_type"] == "egreso"].copy()
            eg_df["category"] = eg_df["category"].fillna("(sin categoría)")
            if eg_df.empty:
                st.caption("Sin egresos en esta moneda en el período.")
            else:
                agc = (
                    eg_df.groupby(["account_label", "category"], as_index=False)["amount"]
                    .sum()
                    .sort_values("amount", ascending=False)
                )
                agc = agc.rename(
                    columns={
                        "account_label": "Cuenta de la que sale",
                        "category": "Rubro / gasto",
                        "amount": f"Total ({cur})",
                    }
                )
                if show_pct:
                    tot_e = float(eg_df["amount"].sum()) or 1.0
                    agc["% del total egresos"] = (agc[f"Total ({cur})"] / tot_e * 100.0).map(
                        lambda x: f"{x:.1f} %"
                    )
                st.dataframe(agc, use_container_width=True, hide_index=True)

            with st.expander(f"📎 Resumen por cuenta · {cur} (opcional)", expanded=False):
                st.caption("Mismos totales que arriba, solo agrupados por cuenta.")
                rows_pa: list[dict[str, Any]] = []
                for lab in sorted(sub["account_label"].unique(), key=str):
                    s2 = sub[sub["account_label"] == lab]
                    i2 = float(s2[s2["tx_type"] == "ingreso"]["amount"].sum())
                    e2 = float(s2[s2["tx_type"] == "egreso"]["amount"].sum())
                    rows_pa.append(
                        {
                            "Cuenta": lab,
                            "Ingresos": i2,
                            "Egresos": e2,
                            "Neto": i2 - e2,
                        }
                    )
                st.dataframe(
                    pd.DataFrame(rows_pa),
                    use_container_width=True,
                    hide_index=True,
                )
            st.divider()

    tr_all = dff.loc[_is_transfer_like_df(dff)].copy()
    if tr_all.empty:
        st.caption("No hay movimientos marcados como traspaso en este período.")
    else:
        ttab = _traspaso_pairs_for_panorama(tr_all)
        with st.expander(
            f"🔄 Traspasos en el período · {len(ttab)} fila(s)",
            expanded=False,
        ):
            st.caption(
                "Cambios de **caja entre tus cuentas** (misma moneda o cruzada). "
                "No son ingreso de negocio ni gasto con rubro."
            )
            if ttab.empty:
                st.write("—")
            else:
                disp = ttab.copy()
                for col in ("Sale", "Entra"):
                    if col in disp.columns:
                        disp[col] = disp[col].apply(
                            lambda x: f"{float(x):,.2f}" if pd.notna(x) else "—"
                        )
                st.dataframe(disp, use_container_width=True, hide_index=True)
