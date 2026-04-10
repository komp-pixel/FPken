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


def _disp_str(v: Any) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    if not s or s.lower() == "none":
        return ""
    return s


def _is_transfer_like_tx(t: dict[str, Any]) -> bool:
    gid = str(t.get("transfer_group_id") or "").strip()
    if gid:
        return True
    tag = str(t.get("transfer_tag") or "").strip().lower()
    return "traspaso" in tag


def _by_cur_from_txs(
    txs: list[dict[str, Any]], amap: dict[str, dict[str, Any]]
) -> dict[str, dict[str, float]]:
    by_cur: dict[str, dict[str, float]] = defaultdict(lambda: {"ing": 0.0, "egr": 0.0})
    for t in txs:
        aid = str(t.get("account_id", ""))
        cur = str(amap.get(aid, {}).get("currency", "USD"))
        amt = float(t.get("amount") or 0)
        if t.get("tx_type") == "ingreso":
            by_cur[cur]["ing"] += amt
        else:
            by_cur[cur]["egr"] += amt
    return dict(by_cur)


def _transfer_legs_list(
    txs_tr: list[dict[str, Any]], amap: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cada fila = un movimiento de traspaso (egreso o ingreso), ordenado por fecha."""
    rows: list[dict[str, Any]] = []
    for t in sorted(txs_tr, key=lambda x: str(x.get("tx_date") or ""), reverse=True):
        aid = str(t.get("account_id", ""))
        acc = amap.get(aid, {})
        gid = str(t.get("transfer_group_id") or "").strip()
        cid = str(t.get("counterpart_account_id") or "").strip()
        contra = (
            str(amap.get(cid, {}).get("label", "")) if cid else ""
        )
        rows.append(
            {
                "fecha": t.get("tx_date"),
                "cuenta": acc.get("label", aid[:8]),
                "tipo": t.get("tx_type"),
                "monto": float(t.get("amount") or 0),
                "moneda": acc.get("currency", "?"),
                "descripcion": (t.get("description") or "")[:80],
                "etiqueta": _disp_str(t.get("transfer_tag")),
                "id_grupo": (gid[:10] + "…") if len(gid) > 10 else gid,
                "cuenta_relacionada": contra,
            }
        )
    return rows


def _transfer_operation_rows(
    txs_tr: list[dict[str, Any]], amap: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filas de traspasos enlazados por grupo vs movimientos sueltos (sin grupo)."""
    by_gid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    loose: list[dict[str, Any]] = []
    for t in txs_tr:
        gid = str(t.get("transfer_group_id") or "").strip()
        if gid:
            by_gid[gid].append(t)
        else:
            loose.append(t)

    paired: list[dict[str, Any]] = []
    for gid, group in sorted(by_gid.items(), key=lambda x: x[0]):
        eg = next((x for x in group if str(x.get("tx_type")) == "egreso"), None)
        ing = next((x for x in group if str(x.get("tx_type")) == "ingreso"), None)
        if not eg and not ing:
            continue
        a_eg = amap.get(str(eg.get("account_id", ""))) if eg else None
        a_in = amap.get(str(ing.get("account_id", ""))) if ing else None
        desc = ""
        if eg:
            desc = str(eg.get("description") or "")
        if ing and not desc:
            desc = str(ing.get("description") or "")
        paired.append(
            {
                "grupo": gid[:8] + "…" if len(gid) >= 8 else gid,
                "fecha": (eg or ing or {}).get("tx_date"),
                "desde": (a_eg.get("label") if a_eg else "—") if eg else "—",
                "sale": float(eg.get("amount") or 0) if eg else 0.0,
                "mon_sale": (a_eg.get("currency") if a_eg else "?") if eg else "—",
                "hacia": (a_in.get("label") if a_in else "—") if ing else "—",
                "entra": float(ing.get("amount") or 0) if ing else 0.0,
                "mon_entra": (a_in.get("currency") if a_in else "?") if ing else "—",
                "descripcion": desc[:70],
            }
        )
    return paired, loose


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


def _pdf_safe_line(line: str) -> str:
    return (
        line.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace("**", "")
        .replace("*", "")
    )


def _analyze_flow_by_currency(
    txs: list[dict[str, Any]], amap: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Por moneda de la cuenta: totales, % gasto/ingreso, peso de rubros y de negocios."""
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ing": 0.0, "egr": 0.0, "ing_items": [], "egr_items": []}
    )
    for t in txs:
        aid = str(t.get("account_id", ""))
        cur = str(amap.get(aid, {}).get("currency", "USD"))
        amt = float(t.get("amount") or 0)
        if str(t.get("tx_type")) == "ingreso":
            buckets[cur]["ing"] += amt
            buckets[cur]["ing_items"].append(t)
        else:
            buckets[cur]["egr"] += amt
            buckets[cur]["egr_items"].append(t)

    out: list[dict[str, Any]] = []
    for cur in sorted(buckets.keys()):
        b = buckets[cur]
        ing, egr = float(b["ing"]), float(b["egr"])
        pct_gasto = (egr / ing * 100.0) if ing > 0 else None

        rub: dict[str, float] = defaultdict(float)
        for t in b["egr_items"]:
            k = str(t.get("category") or "").strip() or "(sin categoría)"
            rub[k] += float(t.get("amount") or 0)
        rub_rows = [
            {"rubro": name, "total": val, "pct": (val / egr * 100.0) if egr > 0 else 0.0}
            for name, val in sorted(rub.items(), key=lambda x: -x[1])
        ]

        bus: dict[str, float] = defaultdict(float)
        for t in b["ing_items"]:
            k = str(t.get("business") or "").strip() or "(sin negocio)"
            bus[k] += float(t.get("amount") or 0)
        bus_rows = [
            {"negocio": name, "total": val, "pct": (val / ing * 100.0) if ing > 0 else 0.0}
            for name, val in sorted(bus.items(), key=lambda x: -x[1])
        ]

        out.append(
            {
                "currency": cur,
                "ing": ing,
                "egr": egr,
                "net": ing - egr,
                "pct_gasto_sobre_ingreso": pct_gasto,
                "rubros": rub_rows,
                "negocios": bus_rows,
            }
        )
    return out


def _build_pdf_bytes(
    title: str,
    period: str,
    guide_lines: list[str],
    flow_caption: str,
    insights: list[str],
    summary_rows: list[list[str]],
    detail_head: list[str],
    detail_rows: list[list[str]],
    transfer_head: list[str] | None = None,
    transfer_rows: list[list[str]] | None = None,
    brute_rows: list[list[str]] | None = None,
    analysis_by_currency: list[dict[str, Any]] | None = None,
    transfer_legs_head: list[str] | None = None,
    transfer_legs_rows: list[list[str]] | None = None,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # Carta US apaisada (~792×612 pt); márgenes 0,5" para que al imprimir en Letter no se corte el ancho útil.
    _m = 0.5 * inch
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        rightMargin=_m,
        leftMargin=_m,
        topMargin=_m,
        bottomMargin=_m,
    )
    _page_w = landscape(letter)[0]
    _usable_w = _page_w - 2 * _m
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph(title.replace("&", "&amp;"), styles["Title"]))
    story.append(Paragraph(f"<i>{period}</i>", styles["Normal"]))
    story.append(Spacer(1, 12))
    if guide_lines:
        story.append(Paragraph("<b>Guía de lectura</b>", styles["Heading2"]))
        for line in guide_lines:
            story.append(Paragraph(f"• {_pdf_safe_line(line)}", styles["Normal"]))
            story.append(Spacer(1, 3))
        story.append(Spacer(1, 8))
    story.append(Paragraph("<b>Resumen ejecutivo</b>", styles["Heading2"]))
    for line in insights:
        story.append(Paragraph(f"• {_pdf_safe_line(line)}", styles["Normal"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>Flujo por moneda (tabla siguiente)</b>", styles["Heading2"]))
    story.append(Paragraph(f"<i>{_pdf_safe_line(flow_caption)}</i>", styles["Normal"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Totales por moneda — flujo mostrado</b>", styles["Heading2"]))
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
    story.append(Spacer(1, 10))
    if analysis_by_currency:
        story.append(Paragraph("<b>Análisis por moneda (peso de rubros y negocios)</b>", styles["Heading2"]))
        story.append(
            Paragraph(
                "<i>% gasto = egresos ÷ ingresos del período en esa moneda. Los porcentajes de rubro son sobre el total "
                "de egresos; los de negocio sobre el total de ingresos.</i>",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 6))
        for block in analysis_by_currency:
            cur = str(block.get("currency", "?"))
            ing = float(block.get("ing") or 0)
            egr = float(block.get("egr") or 0)
            net = float(block.get("net") or 0)
            pg = block.get("pct_gasto_sobre_ingreso")
            pg_s = f"{pg:.1f} %" if pg is not None else "n/d (sin ingresos)"
            story.append(Paragraph(f"<b>Moneda {cur}</b> — Ingresos {ing:,.2f} · Egresos {egr:,.2f} · Neto {net:,.2f} · Gasto/ingreso {pg_s}", styles["Normal"]))
            story.append(Spacer(1, 4))
            sum_a = Table(
                [
                    ["Concepto", "Valor"],
                    ["Total ingresos", f"{ing:,.2f} {cur}"],
                    ["Total egresos", f"{egr:,.2f} {cur}"],
                    ["Neto flujo", f"{net:,.2f} {cur}"],
                    ["Gastos como % de ingresos", pg_s],
                ]
            )
            sum_a.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(sum_a)
            story.append(Spacer(1, 6))
            rubs = block.get("rubros") or []
            if rubs:
                story.append(Paragraph("<b>Egresos por rubro</b>", styles["Heading2"]))
                rr = [["Rubro", "Total", "% del total egresos"]]
                for r in rubs[:50]:
                    rr.append(
                        [
                            _pdf_safe_line(str(r.get("rubro", "")))[:32],
                            f'{float(r.get("total") or 0):,.2f}',
                            f'{float(r.get("pct") or 0):.1f} %',
                        ]
                    )
                trb = Table(rr, colWidths=[200, 80, 100])
                trb.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7f1d1d")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("FONTSIZE", (0, 0), (-1, -1), 7),
                            ("GRID", (0, 0), (-1, -1), 0.15, colors.grey),
                        ]
                    )
                )
                story.append(trb)
                story.append(Spacer(1, 6))
            negs = block.get("negocios") or []
            if negs:
                story.append(Paragraph("<b>Ingresos por negocio / fuente</b>", styles["Heading2"]))
                nr = [["Negocio / fuente", "Total", "% del total ingresos"]]
                for r in negs[:50]:
                    nr.append(
                        [
                            _pdf_safe_line(str(r.get("negocio", "")))[:32],
                            f'{float(r.get("total") or 0):,.2f}',
                            f'{float(r.get("pct") or 0):.1f} %',
                        ]
                    )
                tnb = Table(nr, colWidths=[200, 80, 100])
                tnb.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#134e4a")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("FONTSIZE", (0, 0), (-1, -1), 7),
                            ("GRID", (0, 0), (-1, -1), 0.15, colors.grey),
                        ]
                    )
                )
                story.append(tnb)
                story.append(Spacer(1, 8))
    story.append(Spacer(1, 6))
    if transfer_head and transfer_rows:
        story.append(Paragraph("<b>Traspasos resumidos (origen → destino)</b>", styles["Heading2"]))
        story.append(
            Paragraph(
                "<i>Cada fila es una operación entre tus cuentas; no es gasto ni venta, solo cambio de caja.</i>",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 6))
        tr_w = [52, 72, 58, 28, 72, 58, 28, 118]
        t_tr = Table([transfer_head] + transfer_rows[:500], repeatRows=1, colWidths=tr_w)
        t_tr.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14532d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTSIZE", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.12, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(t_tr)
        story.append(Spacer(1, 12))
    if transfer_legs_head and transfer_legs_rows:
        story.append(Paragraph("<b>Todas las piernas de traspaso (cada movimiento)</b>", styles["Heading2"]))
        story.append(
            Paragraph(
                "<i>Listado completo de egresos e ingresos que forman traspasos en el período.</i>",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 6))
        _lw = int(_usable_w)
        leg_w = [
            int(_lw * 0.067),
            int(_lw * 0.14),
            int(_lw * 0.028),
            int(_lw * 0.065),
            int(_lw * 0.038),
            int(_lw * 0.36),
            int(_lw * 0.075),
            _lw
            - int(_lw * 0.067)
            - int(_lw * 0.14)
            - int(_lw * 0.028)
            - int(_lw * 0.065)
            - int(_lw * 0.038)
            - int(_lw * 0.36)
            - int(_lw * 0.075),
        ]
        t_legs = Table([transfer_legs_head] + transfer_legs_rows[:800], repeatRows=1, colWidths=leg_w)
        t_legs.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#166534")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTSIZE", (0, 0), (-1, -1), 5),
                    ("GRID", (0, 0), (-1, -1), 0.1, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(t_legs)
        story.append(Spacer(1, 12))
    if brute_rows:
        story.append(Paragraph("<b>Todo registrado por moneda (incluye traspasos)</b>", styles["Heading2"]))
        story.append(
            Paragraph(
                "<i>Suma cada pierna de traspaso: ingresos y egresos se inflan; útil para cruzar con extractos.</i>",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 6))
        t_b = Table([["Moneda", "Ingresos", "Egresos", "Neto"]] + brute_rows)
        t_b.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#422006")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fff7ed")]),
                ]
            )
        )
        story.append(t_b)
        story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "<b>Detalle de movimientos (flujo; carta apaisada, columnas ajustadas al ancho útil)</b>",
            styles["Heading2"],
        )
    )
    _uw = int(_usable_w)
    detail_col_w = [
        int(_uw * 0.061),
        int(_uw * 0.1),
        int(_uw * 0.034),
        int(_uw * 0.028),
        int(_uw * 0.07),
        int(_uw * 0.33),
        int(_uw * 0.08),
        int(_uw * 0.042),
        int(_uw * 0.05),
        _uw
        - int(_uw * 0.061)
        - int(_uw * 0.1)
        - int(_uw * 0.034)
        - int(_uw * 0.028)
        - int(_uw * 0.07)
        - int(_uw * 0.33)
        - int(_uw * 0.08)
        - int(_uw * 0.042)
        - int(_uw * 0.05),
    ]
    t2 = Table([detail_head] + detail_rows, repeatRows=1, colWidths=detail_col_w)
    t2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d2137")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.1, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1),
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
    st.markdown(
        '<p class="lk-section" style="margin-top:0;">Reportes inteligentes</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Resumen por rango y cuentas. El PDF se genera en **carta US apaisada (Letter landscape)** con tablas "
        "ajustadas al ancho útil para imprimir sin cortes."
    )

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

    with st.expander("Cómo leer este reporte (todo conectado)", expanded=True):
        st.markdown(
            """
            **1 — Flujo real** es lo que la app considera *dinero que entra o sale de verdad* (ventas, gastos, fees).
            Los **traspasos** (de una cuenta tuya a otra) **no** son ganancia ni gasto: solo cambiás de “caja”.

            **2 — Traspasos resumidos** (origen → destino) y **2b** el **listado de todas las piernas** (cada egreso/ingreso).

            **3 — Todo registrado por moneda** (solo si hay traspasos y tenés excluidos del flujo) suma **cada pierna**
            del movimiento: por eso ingresos y egresos se inflan respecto al flujo real; sirve para cruzar con extractos.

            **1.5** solo **egresos por rubro**; **1.6** solo **ingresos por negocio** (más claros por separado).

            El **detalle** al final va agrupado (ingresos, luego egresos por rubro). El **PDF** es **carta US apaisada**,
            columnas calculadas al ancho útil para que no se corten al imprimir en Letter.
            """
        )

    exclude_transfers = st.checkbox(
        "Excluir traspasos del flujo (recomendado)",
        value=True,
        help="Mantiene el reporte como ingresos/egresos reales; los traspasos solo mueven dinero entre cuentas.",
        key="rep_ex_tr",
    )

    txs_transfer_like = [t for t in txs if _is_transfer_like_tx(t)]
    txs_use = [t for t in txs if not _is_transfer_like_tx(t)] if exclude_transfers else txs
    paired_tr, loose_tr = _transfer_operation_rows(txs_transfer_like, amap)
    paired_tr.sort(key=lambda r: str(r.get("fecha") or ""), reverse=True)

    by_cur = _by_cur_from_txs(txs_use, amap)
    by_cur_all = _by_cur_from_txs(txs, amap)

    def _insight_df(tlist: list[dict[str, Any]]) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "tx_type": t.get("tx_type"),
                    "amount": t.get("amount"),
                    "category": t.get("category"),
                    "business": t.get("business"),
                    "fee_amount": t.get("fee_amount"),
                }
                for t in tlist
            ]
        )

    insight_lines = _insights(_insight_df(txs_use), dict(by_cur))

    flow_caption = (
        "Solo ingresos y egresos que no son traspasos entre tus cuentas (recomendado para ver negocio)."
        if exclude_transfers
        else "Incluye traspasos: los totales mezclan flujo real con movimientos entre cuentas."
    )

    guide_lines_pdf = [
        "PDF en tamaño carta US (Letter) apaisado, márgenes 1/2 pulgada; tablas con anchos proporcionales al ancho útil para evitar cortes.",
        "Flujo real = ingresos y egresos sin contar traspasos entre cuentas propias (si la casilla está activa en la app).",
        "Traspaso = egreso en un origen e ingreso en un destino; el patrimonio total no cambia, solo la cuenta donde está el dinero.",
        "Incluye resumen por rubro, por negocio, traspasos resumidos y listado completo de piernas de traspaso.",
    ]

    st.markdown("---")
    st.markdown(
        '<p class="lk-section" style="margin-top:0;">1. Flujo del período (para entender negocio)</p>',
        unsafe_allow_html=True,
    )
    st.caption(flow_caption)
    if exclude_transfers and txs_transfer_like:
        st.caption(
            f"Ocultos del flujo y del detalle siguiente: **{len(txs_transfer_like)}** movimiento(s) de traspaso "
            "(se listan en la sección 2)."
        )
    if not txs:
        st.warning("No hay movimientos en el rango y cuentas elegidas.")
    for line in insight_lines:
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

    analysis = _analyze_flow_by_currency(txs_use, amap) if txs_use else []
    st.markdown(
        '<p class="lk-section">1.5 Resumen de EGRESOS por rubro (por moneda)</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Solo gastos clasificados por **rubro**. **% del total egresos** = peso de cada rubro dentro de todo lo gastado "
        "en esa moneda en el período."
    )
    if not analysis:
        st.caption("Sin movimientos de flujo en el período para analizar.")
    else:
        for blk in analysis:
            cur = blk["currency"]
            egr = blk["egr"]
            dr = blk.get("rubros") or []
            st.markdown(f"**Moneda {cur}** — total egresos en flujo **{egr:,.2f}**")
            if dr:
                st.dataframe(
                    pd.DataFrame(dr).rename(
                        columns={"rubro": "Rubro", "total": "Total", "pct": "% del total egresos"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Sin egresos con rubro en esta moneda.")

    st.markdown(
        '<p class="lk-section">1.6 Resumen de INGRESOS por negocio / fuente (por moneda)</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Solo entradas clasificadas por **negocio o fuente**. **% del total ingresos** = participación de cada una "
        "dentro de todo lo ingresado en esa moneda."
    )
    if analysis:
        for blk in analysis:
            cur = blk["currency"]
            ing = blk["ing"]
            dn = blk.get("negocios") or []
            st.markdown(f"**Moneda {cur}** — total ingresos en flujo **{ing:,.2f}**")
            if dn:
                st.dataframe(
                    pd.DataFrame(dn).rename(
                        columns={
                            "negocio": "Negocio / fuente",
                            "total": "Total",
                            "pct": "% del total ingresos",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Sin ingresos con negocio en esta moneda.")

    st.markdown(
        '<p class="lk-section">2. Traspasos entre cuentas (origen → destino)</p>',
        unsafe_allow_html=True,
    )
    if not txs_transfer_like:
        st.caption("En este período no hay movimientos marcados como traspaso en las cuentas seleccionadas.")
    else:
        st.caption(
            "Cada fila es **una** operación entre tus cuentas. Se enlaza por grupo en base de datos cuando usaste "
            "«Traspaso entre cuentas» en Movimientos."
        )
        if paired_tr:
            df_p = pd.DataFrame(paired_tr)
            df_p = df_p.rename(
                columns={
                    "grupo": "id_grupo",
                    "fecha": "fecha",
                    "desde": "cuenta_origen",
                    "sale": "egresa",
                    "mon_sale": "mon_origen",
                    "hacia": "cuenta_destino",
                    "entra": "ingresa",
                    "mon_entra": "mon_destino",
                    "descripcion": "descripcion",
                }
            )
            st.dataframe(df_p, use_container_width=True, hide_index=True)
        if loose_tr:
            st.caption(
                "Movimientos con etiqueta de traspaso **sin** `transfer_group_id` (datos viejos o creados fuera del "
                "formulario de traspaso). Revisalos en Movimientos o aplicá el parche SQL de contrapartes."
            )
            loose_rows = []
            for t in loose_tr:
                aid = str(t.get("account_id", ""))
                acc = amap.get(aid, {})
                loose_rows.append(
                    {
                        "fecha": t.get("tx_date"),
                        "cuenta": acc.get("label", aid[:8]),
                        "tipo": t.get("tx_type"),
                        "monto": float(t.get("amount") or 0),
                        "moneda": acc.get("currency", "?"),
                        "etiqueta": t.get("transfer_tag") or "",
                        "descripcion": (t.get("description") or "")[:60],
                    }
                )
            st.dataframe(pd.DataFrame(loose_rows), use_container_width=True, hide_index=True)

    st.markdown(
        '<p class="lk-section">2b. Todas las piernas de traspaso (listado completo)</p>',
        unsafe_allow_html=True,
    )
    if not txs_transfer_like:
        st.caption("No hay traspasos en el período.")
    else:
        st.caption(
            f"**{len(txs_transfer_like)}** movimiento(s): cada fila es un egreso o ingreso que forma parte de un traspaso. "
            "Así ves todo lo que entró y salió entre cuentas, además del resumen 2."
        )
        st.dataframe(
            pd.DataFrame(_transfer_legs_list(txs_transfer_like, amap)),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown(
        '<p class="lk-section">3. Todo registrado por moneda (incluye traspasos)</p>',
        unsafe_allow_html=True,
    )
    if exclude_transfers and txs_transfer_like:
        st.caption(
            "Aquí se cuentan **todas** las piernas de cada movimiento. Un traspaso suma a la vez un ingreso y un egreso; "
            "por eso no coincide con la sección 1. Útil para validar contra bancos o wallets."
        )
        brute_rows_ui = []
        for cur, s in sorted(by_cur_all.items()):
            net = s["ing"] - s["egr"]
            brute_rows_ui.append(
                {
                    "moneda": cur,
                    "ingresos": s["ing"],
                    "egresos": s["egr"],
                    "neto": net,
                }
            )
        st.dataframe(pd.DataFrame(brute_rows_ui), use_container_width=True, hide_index=True)
    elif txs_transfer_like and not exclude_transfers:
        st.caption("Tenés los traspasos incluidos en el flujo: la sección 1 ya es el total bruto por moneda.")
    else:
        st.caption("No hay traspasos en el período; la sección 1 ya representa todo lo registrado.")

    rows = []
    for t in txs_use:
        aid = str(t.get("account_id", ""))
        acc = amap.get(aid, {})
        cur = str(acc.get("currency", "USD"))
        cid = str(t.get("counterpart_account_id") or "").strip()
        cuenta_rel = (
            str(amap.get(cid, {}).get("label", cid[:8] + "…"))
            if cid
            else ""
        )
        rows.append(
            {
                "fecha": t.get("tx_date"),
                "cuenta": acc.get("label", aid[:8]),
                "moneda": cur,
                "tipo": t.get("tx_type"),
                "monto": float(t.get("amount") or 0),
                "descripcion": (t.get("description") or "")[:80],
                "rubro": _disp_str(t.get("category")),
                "negocio": _disp_str(t.get("business")),
                "comision": float(t["fee_amount"]) if t.get("fee_amount") else None,
                "etiqueta": _disp_str(t.get("transfer_tag")),
                "cuenta_relacionada": cuenta_rel,
                "notas": (t.get("transaction_notes") or "")[:60],
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df_ing = df[df["tipo"] == "ingreso"].sort_values(
            by=["negocio", "fecha"], ascending=[True, False], na_position="last"
        )
        df_eg = df[df["tipo"] == "egreso"].sort_values(
            by=["rubro", "fecha"], ascending=[True, False], na_position="last"
        )
        df = pd.concat([df_ing, df_eg], ignore_index=True)
        df["fecha"] = df["fecha"].dt.date

    st.markdown(
        '<p class="lk-section">4. Detalle agrupado (ingresos arriba, egresos abajo; orden por rubro/negocio y fecha)</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Tip: al **imprimir** esta pantalla con el navegador (Ctrl+P), elegí **horizontal** y márgenes normales. "
        "El **PDF** de abajo es **carta US apaisada** (Letter landscape), columnas proporcionales al ancho útil."
    )
    st.markdown(
        """
        <style>
        @media print {
          @page { size: letter landscape; margin: 10mm; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if df.empty:
        st.caption("Nada que mostrar con los filtros actuales.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
    detail_head = [
        "Fecha",
        "Cuenta",
        "Mon",
        "T",
        "Monto",
        "Descripción",
        "Rubro/Neg",
        "Com.",
        "Etiqueta",
        "Relacionada",
    ]
    detail_rows_pdf: list[list[str]] = []
    txs_ing = [t for t in txs_use if str(t.get("tx_type")) == "ingreso"]
    txs_ing = sorted(txs_ing, key=lambda t: str(t.get("tx_date") or ""), reverse=True)
    txs_ing = sorted(
        txs_ing,
        key=lambda t: (_disp_str(t.get("business")) or "zzz").lower(),
    )
    txs_eg = [t for t in txs_use if str(t.get("tx_type")) == "egreso"]
    txs_eg = sorted(txs_eg, key=lambda t: str(t.get("tx_date") or ""), reverse=True)
    txs_eg = sorted(
        txs_eg,
        key=lambda t: (_disp_str(t.get("category")) or "zzz").lower(),
    )

    for t in txs_ing + txs_eg:
        aid = str(t.get("account_id", ""))
        acc = amap.get(aid, {})
        cur = str(acc.get("currency", "?"))[:4]
        fee = t.get("fee_amount")
        fee_s = f"{float(fee):,.2f}" if fee is not None else ""
        _cid = str(t.get("counterpart_account_id") or "").strip()
        _rel = (
            str(amap.get(_cid, {}).get("label", ""))[:14]
            if _cid
            else ""
        )
        rub_neg = _disp_str(t.get("category")) or _disp_str(t.get("business")) or ""
        detail_rows_pdf.append(
            [
                str(t.get("tx_date", ""))[:10],
                str(acc.get("label", ""))[:16],
                cur,
                (t.get("tx_type") or "")[:1].upper(),
                f'{float(t.get("amount") or 0):,.2f}',
                str(t.get("description", ""))[:36],
                rub_neg[:18],
                fee_s,
                _disp_str(t.get("transfer_tag"))[:12],
                _rel,
            ]
        )

    transfer_head_pdf: list[str] | None = None
    transfer_rows_pdf: list[list[str]] | None = None
    if txs_transfer_like:
        transfer_head_pdf = [
            "Fecha",
            "Origen",
            "Egresa",
            "M",
            "Destino",
            "Ingresa",
            "M",
            "Nota",
        ]
        transfer_rows_pdf = []
        for p in paired_tr:
            transfer_rows_pdf.append(
                [
                    str(p.get("fecha", ""))[:10],
                    str(p.get("desde", ""))[:16],
                    f'{float(p.get("sale") or 0):,.4f}',
                    str(p.get("mon_sale", ""))[:4],
                    str(p.get("hacia", ""))[:16],
                    f'{float(p.get("entra") or 0):,.4f}',
                    str(p.get("mon_entra", ""))[:4],
                    str(p.get("descripcion", ""))[:26],
                ]
            )
        for t in loose_tr:
            aid = str(t.get("account_id", ""))
            acc = amap.get(aid, {})
            is_eg = str(t.get("tx_type")) == "egreso"
            transfer_rows_pdf.append(
                [
                    str(t.get("tx_date", ""))[:10],
                    str(acc.get("label", ""))[:14] if is_eg else "—",
                    f'{float(t.get("amount") or 0):,.4f}' if is_eg else "—",
                    str(acc.get("currency", "?"))[:4],
                    str(acc.get("label", ""))[:14] if not is_eg else "—",
                    f'{float(t.get("amount") or 0):,.4f}' if not is_eg else "—",
                    str(acc.get("currency", "?"))[:4],
                    f'sin grupo · {str(t.get("transfer_tag") or "")[:12]}',
                ]
            )

    brute_rows_pdf: list[list[str]] | None = None
    if exclude_transfers and txs_transfer_like:
        brute_rows_pdf = []
        for cur, s in sorted(by_cur_all.items()):
            net = s["ing"] - s["egr"]
            brute_rows_pdf.append(
                [cur, f'{s["ing"]:,.2f}', f'{s["egr"]:,.2f}', f"{net:,.2f}"]
            )

    transfer_legs_head_pdf: list[str] | None = None
    transfer_legs_rows_pdf: list[list[str]] | None = None
    if txs_transfer_like:
        transfer_legs_head_pdf = [
            "Fecha",
            "Cuenta",
            "T",
            "Monto",
            "M",
            "Descripción",
            "Grupo",
            "Contra",
        ]
        transfer_legs_rows_pdf = []
        for row in _transfer_legs_list(txs_transfer_like, amap):
            transfer_legs_rows_pdf.append(
                [
                    str(row.get("fecha", ""))[:10],
                    str(row.get("cuenta", ""))[:18],
                    (str(row.get("tipo", ""))[:1] or "?").upper(),
                    f'{float(row.get("monto") or 0):,.2f}',
                    str(row.get("moneda", ""))[:4],
                    str(row.get("descripcion", ""))[:40],
                    str(row.get("id_grupo", ""))[:12],
                    str(row.get("cuenta_relacionada", ""))[:18],
                ]
            )

    try:
        pdf = _build_pdf_bytes(
            "Kenny Finanzas — Resumen gerencial",
            f"Período: {d0} a {d1}",
            guide_lines_pdf,
            flow_caption,
            insight_lines,
            sum_rows,
            detail_head,
            detail_rows_pdf[:500],
            transfer_head_pdf,
            transfer_rows_pdf,
            brute_rows_pdf,
            analysis_by_currency=analysis if analysis else None,
            transfer_legs_head=transfer_legs_head_pdf,
            transfer_legs_rows=transfer_legs_rows_pdf,
        )
        st.download_button(
            "Descargar PDF (carta apaisada)",
            data=pdf,
            file_name=f"kenny_finanzas_{d0}_{d1}.pdf",
            mime="application/pdf",
            type="primary",
        )
        st.caption("En el visor de PDF / impresora, elegí **Letter** u **carta** y **horizontal** si hace falta.")
    except Exception as e:
        st.warning(f"No se pudo generar el PDF (¿instalaste reportlab?): {e}")
