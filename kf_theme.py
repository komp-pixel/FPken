"""Estilos globales tipo Lukana: lienzo claro, acento azul, tarjetas y tipografía."""

from __future__ import annotations

import streamlit as st

# Componentes reutilizables (dashboard, métricas HTML, etc.)
LUKANA_COMPONENT_CSS = """
/* Panel / KPIs */
.lk-canvas {
    background: linear-gradient(165deg, #eef2f9 0%, #e2e8f0 45%, #dce4f0 100%);
    border-radius: 20px;
    padding: 1.35rem 1.25rem 1.5rem;
    margin-bottom: 1.1rem;
    border: 1px solid #cbd5e1;
    box-shadow: 0 4px 24px rgba(15, 23, 42, 0.06);
}
.lk-top {
    display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between;
    gap: 0.75rem; margin-bottom: 1.15rem;
}
.lk-brand { margin: 0; font-size: 1.55rem; font-weight: 800; color: #0f172a; letter-spacing: -0.035em; line-height: 1.15; }
.lk-brand em { font-style: normal; color: #2563eb; }
.lk-subtitle { margin: 0.35rem 0 0 0; font-size: 0.88rem; color: #334155; font-weight: 600; }
.lk-pill {
    display: inline-flex; align-items: center; height: 2rem; padding: 0 0.9rem;
    background: linear-gradient(135deg, #2563eb, #1d4ed8); color: #fff !important;
    border-radius: 999px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.02em;
    box-shadow: 0 2px 8px rgba(37, 99, 235, 0.35);
}
.lk-grid {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.85rem;
}
@media (max-width: 950px) {
    .lk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.lk-stat {
    background: #fff;
    border-radius: 14px;
    padding: 1rem 1.05rem;
    min-height: 102px;
    border: 1px solid #f1f5f9;
    box-shadow: 0 2px 12px rgba(15, 23, 42, 0.05), 0 1px 2px rgba(15, 23, 42, 0.04);
}
.lk-stat h4 {
    margin: 0; font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: #475569;
}
.lk-stat .lk-val { margin: 0.45rem 0 0 0; font-size: 1.32rem; font-weight: 800; color: #0f172a; line-height: 1.15; }
.lk-stat .lk-foot { margin: 0.35rem 0 0 0; font-size: 0.72rem; color: #64748b; font-weight: 600; }
.lk-stat-blue {
    background: linear-gradient(145deg, #2563eb 0%, #1e40af 100%);
    border: none;
    box-shadow: 0 6px 20px rgba(37, 99, 235, 0.35);
}
.lk-stat-blue h4 { color: rgba(255,255,255,0.88); }
.lk-stat-blue .lk-val { color: #fff !important; }
.lk-stat-blue .lk-foot { color: rgba(255,255,255,0.82); }
.lk-pos { color: #16a34a !important; }
.lk-neg { color: #dc2626 !important; }
.lk-section {
    font-size: 1.02rem; font-weight: 800; color: #0f172a;
    margin: 1.15rem 0 0.5rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 3px solid #2563eb;
    display: inline-block;
    letter-spacing: -0.02em;
}
.lk-hint { font-size: 0.82rem; color: #334155; font-weight: 500; margin-top: 0.35rem; }
.lk-page-title {
    font-size: 1.75rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.03em;
    margin: 0 0 0.25rem 0;
}
.lk-page-title em { font-style: normal; color: #2563eb; }
"""

LUKANA_GLOBAL_CHROME_CSS = """
/* App: lienzo general */
.stApp {
    background: linear-gradient(165deg, #eef2f9 0%, #e8edf5 35%, #f8fafc 100%) !important;
}
.main .block-container {
    padding-top: 1.25rem;
    padding-bottom: 2rem;
}
/* Sidebar: fondo claro + texto siempre legible (Streamlit suele poner gris muy claro) */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #e8eef8 0%, #dce4f0 100%) !important;
    border-right: 1px solid #cbd5e1 !important;
    color: #0f172a !important;
}
/* Texto generado por st.markdown / st.caption en el lateral */
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] [data-testid="stCaption"],
[data-testid="stSidebar"] [data-testid="stCaption"] p,
[data-testid="stSidebar"] [data-testid="stCaption"] span {
    color: #0f172a !important;
    opacity: 1 !important;
}
[data-testid="stSidebar"] [data-testid="stCaption"] {
    font-weight: 600 !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] label {
    color: #0f172a !important;
}
[data-testid="stSidebar"] .stMarkdown a {
    color: #1d4ed8 !important;
    font-weight: 600;
}
/* Área principal: captions y ayudas */
.main [data-testid="stCaption"],
.main [data-testid="stCaption"] p,
.main [data-testid="stCaption"] span,
section[data-testid="stMain"] [data-testid="stCaption"] {
    color: #334155 !important;
    opacity: 1 !important;
    font-weight: 500 !important;
}
/* st.caption a veces sin testid según versión */
.main div[data-testid="stVerticalBlock"] > div > [data-testid="stElementContainer"] small {
    color: #475569 !important;
    opacity: 1 !important;
}
/* Alertas info/success: cuerpo del mensaje más oscuro */
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p,
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] li,
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] span {
    color: #0f172a !important;
    opacity: 1 !important;
}
/* Markdown normal en el cuerpo (evita gris demasiado claro del tema) */
.main .block-container [data-testid="stMarkdownContainer"] p,
.main .block-container [data-testid="stMarkdownContainer"] li {
    color: #1e293b !important;
}
.main .block-container [data-testid="stMarkdownContainer"] strong {
    color: #0f172a !important;
}
/* Pestañas principales */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.35rem;
    background-color: rgba(255, 255, 255, 0.65);
    border-radius: 12px;
    padding: 0.35rem 0.5rem;
    border: 1px solid #e2e8f0;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-weight: 600;
}
/* Métricas tipo tarjeta */
div[data-testid="stMetric"] {
    background: #fff;
    border: 1px solid #f1f5f9;
    border-radius: 14px;
    padding: 0.65rem 0.85rem;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
}
/* Alertas más suaves */
div[data-testid="stAlert"] {
    border-radius: 12px;
    border-width: 1px;
}
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
    }
}
div[data-testid="stVerticalBlock"] button { min-height: 2.75rem; }
"""


def inject_lukana_theme() -> None:
    """Inyecta CSS global una vez por página (llamar tras set_page_config / login)."""
    st.markdown(
        f"<style>{LUKANA_GLOBAL_CHROME_CSS}\n{LUKANA_COMPONENT_CSS}</style>",
        unsafe_allow_html=True,
    )
