"""Resumen gerencial, análisis y exportación PDF."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client


def load_tx_date_range(
    sb: Client, account_ids: list[str], d0: date, d1: date
) -> list[dict[str, Any]]:
    if not account_ids:
        return []
    q = (
        sb.table("kf_transaction")
        .select("*")
        .in_("account_id", account_ids)
        .gte("tx_date", d0.isoformat())
        .lte("tx_date", d1.isoformat())
    )
    r = q.order("tx_date", desc=True).limit(8000).execute()
    return list(r.data or [])


def _acc_map(accounts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(a["id"]): a for a in accounts}


def _is_transfer_like_tx(t: dict[str, Any]) -> bool:
    gid = str(t.get("transfer_group_id") or "").strip()
    if gid:
        return True
    tag = str(t.get("transfer_tag") or "").strip().lower()
    return "traspaso" in tag


def _insights(df: pd.DataFrame, by_cur: dict[str, dict[str, float]]) -> list[str]:
    lines: list[str] = []
    if df.empty:
        lines.append("No hay movimientos en el rango y cuentas elegidas.")
        return lines
    d = df.copy()
    for col in ("category", "business", "fee_amount"):
        if col not in d.columns:
            d[col] = None
    eg = d[d["tx_type"] == "egreso"]
    ing = d[d["tx_type"] == "ingreso"]
    if not eg.empty and eg["category"].notna().any():
        top = (
            eg.dropna(subset=["category"])
            .groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(1)
        )
        if len(top):
            lines.append(
                f"Mayor rubro de gasto: **{top.index[0]}** "
                f"({float(top.iloc[0]):,.2f} en total en el período, todas las monedas mezcladas en cifra bruta)."
            )
    if not ing.empty and ing["business"].notna().any():
        topb = (
            ing.dropna(subset=["business"])
            .groupby("business")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(1)
        )
        if len(topb):
            lines.append(
                f"Principal fuente de ingreso registrada: **{topb.index[0]}**."
            )
    fees = d[d["fee_amount"].notna() & (pd.to_numeric(d["fee_amount"], errors="coerce") > 0)]
    if not fees.empty:
        lines.append(
            f"Hay **{len(fees)}** movimiento(s) con comisión registrada; revisá la tabla de detalle."
        )
    for cur, sums in sorted(by_cur.items()):
        net = sums.get("ing", 0) - sums.get("egr", 0)
        lines.append(
            f"**{cur}:** ingresos {sums.get('ing', 0):,.2f} · egresos {sums.get('egr', 0):,.2f} · neto flujo **{net:,.2f}**."
        )
    return lines


def _build_pdf_bytes(
    title: str,
    period: str,
    insights: list[str],
    summary_rows: list[list[str]],
    detail_head: list[str],
    detail_rows: list[list[str]],
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph(title.replace("&", "&amp;"), styles["Title"]))
    story.append(Paragraph(f"<i>{period}</i>", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Resumen ejecutivo</b>", styles["Heading2"]))
    for line in insights:
        safe = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace("**", "")
            .replace("*", "")
        )
        story.append(Paragraph(f"• {safe}", styles["Normal"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Totales por moneda</b>", styles["Heading2"]))
    t1 = Table([["Moneda", "Ingresos", "Egresos", "Neto flujo"]] + summary_rows)
    t1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ]
        )
    )
    story.append(t1)
    story.append(Spacer(1, 16))
    story.append(Paragraph("<b>Detalle de movimientos</b>", styles["Heading2"]))
    t2 = Table([detail_head] + detail_rows, repeatRows=1)
    t2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d2137")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.15, colors.grey),
            ]
        )
    )
    story.append(t2)
    doc.build(story)
    return buf.getvalue()


def render_reports_page(
    sb: Client,
    accounts: list[dict[str, Any]],
    umap: dict[str, str],
) -> None:
    st.subheader("Reportes inteligentes")
    st.caption("Resumen gerencial por rango de fechas y cuentas (USD, VES, USDT). Descargá PDF para imprimir.")

    if not accounts:
        st.warning("No hay cuentas.")
        return

    today = date.today()
    c1, c2, c3 = st.columns(3)
    with c1:
        d0 = st.date_input("Desde", value=today.replace(day=1), key="rep_d0")
    with c2:
        d1 = st.date_input("Hasta", value=today, key="rep_d1")
    with c3:
        opts = {str(a["id"]): f'{a.get("label")} ({a.get("currency", "?")})' for a in accounts}
        sel = st.multiselect(
            "Cuentas a incluir",
            options=list(opts.keys()),
            default=list(opts.keys()),
            format_func=lambda i: opts[i],
            key="rep_accs",
        )

    if not sel:
        st.info("Elegí al menos una cuenta.")
        return

    txs = load_tx_date_range(sb, sel, d0, d1)
    amap = _acc_map(accounts)

    exclude_transfers = st.checkbox(
        "Excluir traspasos del flujo (recomendado)",
        value=True,
        help="Mantiene el reporte como ingresos/egresos reales; los traspasos solo mueven dinero entre cuentas.",
        key="rep_ex_tr",
    )
    txs_use = [t for t in txs if not _is_transfer_like_tx(t)] if exclude_transfers else txs

    rows = []
    for t in txs_use:
        aid = str(t.get("account_id", ""))
        acc = amap.get(aid, {})
        cur = str(acc.get("currency", "USD"))
        rows.append(
            {
                "fecha": t.get("tx_date"),
                "cuenta": acc.get("label", aid[:8]),
                "moneda": cur,
                "tipo": t.get("tx_type"),
                "monto": float(t.get("amount") or 0),
                "descripcion": (t.get("description") or "")[:80],
                "rubro": t.get("category") or "",
                "negocio": t.get("business") or "",
                "comision": float(t["fee_amount"]) if t.get("fee_amount") else None,
                "etiqueta": t.get("transfer_tag") or "",
                "notas": (t.get("transaction_notes") or "")[:60],
            }
        )
    df = pd.DataFrame(rows)

    by_cur: dict[str, dict[str, float]] = defaultdict(lambda: {"ing": 0.0, "egr": 0.0})
    for t in txs_use:
        aid = str(t.get("account_id", ""))
        cur = str(amap.get(aid, {}).get("currency", "USD"))
        amt = float(t.get("amount") or 0)
        if t.get("tx_type") == "ingreso":
            by_cur[cur]["ing"] += amt
        else:
            by_cur[cur]["egr"] += amt

    st.markdown("---")
    st.markdown("### Resumen gerencial")
    for line in _insights(
        pd.DataFrame(
            [
                {
                    "tx_type": t.get("tx_type"),
                    "amount": t.get("amount"),
                    "category": t.get("category"),
                    "business": t.get("business"),
                    "fee_amount": t.get("fee_amount"),
                }
                for t in txs_use
            ]
        ),
        dict(by_cur),
    ):
        st.markdown(f"- {line}")

    sum_rows = []
    for cur, s in sorted(by_cur.items()):
        net = s["ing"] - s["egr"]
        sum_rows.append(
            [cur, f'{s["ing"]:,.2f}', f'{s["egr"]:,.2f}', f"{net:,.2f}"]
        )
    st.dataframe(
        pd.DataFrame(
            sum_rows, columns=["Moneda", "Ingresos", "Egresos", "Neto período"]
        ),
        use_container_width=True,
        hide_index=True,
    )

    if not df.empty:
        st.markdown("### Vista previa detalle")
        st.dataframe(df, use_container_width=True, hide_index=True)

    insight_lines = _insights(
        pd.DataFrame(
            [
                {
                    "tx_type": t.get("tx_type"),
                    "amount": t.get("amount"),
                    "category": t.get("category"),
                    "business": t.get("business"),
                    "fee_amount": t.get("fee_amount"),
                }
                for t in txs_use
            ]
        ),
        dict(by_cur),
    )
    detail_head = ["Fecha", "Cuenta", "Mon", "T", "Monto", "Descripción", "Rubro/Neg", "Com.", "Etiqueta"]
    detail_rows = []
    for t in txs_use:
        aid = str(t.get("account_id", ""))
        acc = amap.get(aid, {})
        cur = str(acc.get("currency", "?"))[:4]
        fee = t.get("fee_amount")
        fee_s = f"{float(fee):,.4f}" if fee is not None else ""
        detail_rows.append(
            [
                str(t.get("tx_date", ""))[:10],
                str(acc.get("label", ""))[:22],
                cur,
                (t.get("tx_type") or "")[:1].upper(),
                f'{float(t.get("amount") or 0):,.4f}',
                str(t.get("description", ""))[:35],
                str(t.get("category") or t.get("business") or "")[:18],
                fee_s,
                str(t.get("transfer_tag", ""))[:16],
            ]
        )

    try:
        pdf = _build_pdf_bytes(
            "Kenny Finanzas — Resumen gerencial",
            f"Período: {d0} a {d1}",
            insight_lines,
            sum_rows,
            detail_head,
            detail_rows[:400],
        )
        st.download_button(
            "Descargar PDF (imprimir)",
            data=pdf,
            file_name=f"kenny_finanzas_{d0}_{d1}.pdf",
            mime="application/pdf",
            type="primary",
        )
    except Exception as e:
        st.warning(f"No se pudo generar el PDF (¿instalaste reportlab?): {e}")
