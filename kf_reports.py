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
    story.append(Spacer(1, 12))
    if transfer_head and transfer_rows:
        story.append(Paragraph("<b>Traspasos resumidos (origen → destino)</b>", styles["Heading2"]))
        story.append(
            Paragraph(
                "<i>Cada fila es una operación entre tus cuentas; no es gasto ni venta, solo cambio de caja.</i>",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 6))
        t_tr = Table([transfer_head] + transfer_rows[:200], repeatRows=1)
        t_tr.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14532d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.15, colors.grey),
                ]
            )
        )
        story.append(t_tr)
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
    story.append(Paragraph("<b>Detalle de movimientos (misma vista que en pantalla)</b>", styles["Heading2"]))
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

    with st.expander("Cómo leer este reporte (todo conectado)", expanded=True):
        st.markdown(
            """
            **1 — Flujo real** es lo que la app considera *dinero que entra o sale de verdad* (ventas, gastos, fees).
            Los **traspasos** (de una cuenta tuya a otra) **no** son ganancia ni gasto: solo cambiás de “caja”.

            **2 — Traspasos resumidos** agrupa cada operación como **Origen → Destino** para que veas el camino del dinero
            sin buscar fila por fila.

            **3 — Todo registrado por moneda** (solo si hay traspasos y tenés excluidos del flujo) suma **cada pierna**
            del movimiento: por eso ingresos y egresos se inflan respecto al flujo real; sirve para cruzar con extractos.

            El **detalle** al final es la misma grilla que respeta la casilla *Excluir traspasos*; el PDF incluye guía,
            traspasos resumidos y (cuando aplica) la tabla bruta.
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
        "Flujo real = ingresos y egresos sin contar traspasos entre cuentas propias (si la casilla está activa en la app).",
        "Traspaso = egreso en un origen e ingreso en un destino; el patrimonio total no cambia, solo la cuenta donde está el dinero.",
        "La tabla 'Todo registrado por moneda' suma cada pierna: si hubo traspasos, ingresos y egresos brutos serán mayores que el flujo real.",
    ]

    st.markdown("---")
    st.markdown("### 1. Flujo del período (para entender negocio)")
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

    st.markdown("### 2. Traspasos entre cuentas (origen → destino)")
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

    st.markdown("### 3. Todo registrado por moneda (incluye traspasos)")
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
                "rubro": t.get("category") or "",
                "negocio": t.get("business") or "",
                "comision": float(t["fee_amount"]) if t.get("fee_amount") else None,
                "etiqueta": t.get("transfer_tag") or "",
                "cuenta_relacionada": cuenta_rel,
                "notas": (t.get("transaction_notes") or "")[:60],
            }
        )
    df = pd.DataFrame(rows)

    st.markdown("### 4. Detalle línea a línea (respeta «Excluir traspasos»)")
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
    detail_rows = []
    for t in txs_use:
        aid = str(t.get("account_id", ""))
        acc = amap.get(aid, {})
        cur = str(acc.get("currency", "?"))[:4]
        fee = t.get("fee_amount")
        fee_s = f"{float(fee):,.4f}" if fee is not None else ""
        _cid = str(t.get("counterpart_account_id") or "").strip()
        _rel = (
            str(amap.get(_cid, {}).get("label", ""))[:18]
            if _cid
            else ""
        )
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

    try:
        pdf = _build_pdf_bytes(
            "Kenny Finanzas — Resumen gerencial",
            f"Período: {d0} a {d1}",
            guide_lines_pdf,
            flow_caption,
            insight_lines,
            sum_rows,
            detail_head,
            detail_rows[:400],
            transfer_head_pdf,
            transfer_rows_pdf,
            brute_rows_pdf,
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
