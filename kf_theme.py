"""Estilos globales tipo Lukana: tema claro (por defecto) y tema oscuro opcional.

- **Claro:** texto oscuro sobre lienzo claro (ver comentarios en CSS).
- **Oscuro:** `kf_theme_dark.py` + selector en el lateral (`render_theme_picker_sidebar`).
"""

from __future__ import annotations

import streamlit as st

from kf_theme_dark import DARK_COMPONENT_CSS, DARK_GLOBAL_CHROME_CSS

KF_THEME_KEY = "kf_ui_theme"
THEME_LIGHT = "light"
THEME_DARK = "dark"


def is_dark_theme() -> bool:
    return str(st.session_state.get(KF_THEME_KEY, THEME_LIGHT)).lower() == THEME_DARK


def render_theme_picker_sidebar() -> None:
    """Selector Claro / Oscuro; debe llamarse dentro de `st.sidebar`."""
    st.session_state.setdefault(KF_THEME_KEY, THEME_LIGHT)
    cur = st.session_state[KF_THEME_KEY]
    opts = ("Claro", "Oscuro")
    choice = st.radio(
        "Tema visual",
        opts,
        index=1 if cur == THEME_DARK else 0,
        horizontal=True,
        key="kf_theme_radio_sidebar",
    )
    want = THEME_DARK if choice == "Oscuro" else THEME_LIGHT
    if want != st.session_state[KF_THEME_KEY]:
        st.session_state[KF_THEME_KEY] = want
        st.rerun()

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
.lk-subtitle { margin: 0.35rem 0 0 0; font-size: 0.88rem; color: #1e293b; font-weight: 600; }
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
.lk-stat .lk-foot { margin: 0.35rem 0 0 0; font-size: 0.72rem; color: #475569; font-weight: 600; }
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
.lk-hint { font-size: 0.82rem; color: #1e293b; font-weight: 600; margin-top: 0.35rem; }
/* Subtítulos dentro del dashboard (metas, etc.) — nunca color tema claro */
.lk-panel-h {
    margin: 0 0 0.5rem 0;
    font-size: 1.05rem;
    font-weight: 800;
    color: #0f172a !important;
    letter-spacing: -0.02em;
    -webkit-text-fill-color: #0f172a !important;
}
.lk-page-title {
    font-size: 1.75rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.03em;
    margin: 0 0 0.25rem 0;
}
.lk-page-title em { font-style: normal; color: #2563eb; }
/* Grilla de saldos en dashboard (cuentas × tarjetas) */
.lk-balance-cards-wrap .lk-stat {
    min-height: 0;
    text-align: left;
}
.lk-balance-cards-wrap .lk-stat h4 {
    font-size: 0.78rem;
    line-height: 1.3;
    word-break: break-word;
    color: #334155 !important;
}
.lk-balance-cards-wrap .lk-stat .lk-val {
    font-size: 1.2rem;
}

/* Excepciones con mayor especificidad que la regla global del main (texto claro sobre azul) */
section[data-testid="stMain"] .lk-stat-blue h4 {
    color: rgba(255, 255, 255, 0.92) !important;
    -webkit-text-fill-color: rgba(255, 255, 255, 0.92) !important;
}
section[data-testid="stMain"] .lk-stat-blue .lk-val {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
section[data-testid="stMain"] .lk-stat-blue .lk-foot {
    color: rgba(255, 255, 255, 0.9) !important;
    -webkit-text-fill-color: rgba(255, 255, 255, 0.9) !important;
}
section[data-testid="stMain"] .lk-pill {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
section[data-testid="stMain"] .lk-pos {
    color: #15803d !important;
    -webkit-text-fill-color: #15803d !important;
}
section[data-testid="stMain"] .lk-neg {
    color: #b91c1c !important;
    -webkit-text-fill-color: #b91c1c !important;
}
"""

LUKANA_GLOBAL_CHROME_CSS = """
/* App: lienzo general */
.stApp {
    background: linear-gradient(165deg, #eef2f9 0%, #e8edf5 35%, #f8fafc 100%) !important;
}
.main .block-container {
    padding-top: 1.25rem;
    padding-bottom: 2rem;
    color-scheme: light;
    color: #1e293b !important;
    -webkit-text-fill-color: #1e293b !important;
}
/* Subtítulo bajo el título principal: bien oscuro */
.main [data-testid="stCaption"],
.main [data-testid="stCaption"] p,
.main [data-testid="stCaption"] span,
section[data-testid="stMain"] [data-testid="stCaption"] {
    color: #0f172a !important;
    opacity: 1 !important;
    font-weight: 600 !important;
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
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] span {
    color: #0f172a !important;
    opacity: 1 !important;
}
/* Selectores / desplegables en el lateral (texto a menudo gris claro) */
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="input"] input,
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] * {
    color: #0f172a !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #0f172a !important;
}
[data-testid="stSidebar"] details summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary span {
    color: #0f172a !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}
[data-testid="stSidebar"] .stMarkdown a {
    color: #1d4ed8 !important;
    font-weight: 600;
}
/* Botones lateral: secondary = tarjeta blanca + texto oscuro; primary = azul + blanco */
[data-testid="stSidebar"] button[kind="secondary"],
[data-testid="stSidebar"] [data-testid="baseButton-secondary"] {
    background-color: #ffffff !important;
    background-image: none !important;
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    border: 1px solid #94a3b8 !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] button[kind="secondary"] p,
[data-testid="stSidebar"] button[kind="secondary"] span,
[data-testid="stSidebar"] [data-testid="baseButton-secondary"] p,
[data-testid="stSidebar"] [data-testid="baseButton-secondary"] span {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
}
[data-testid="stSidebar"] button[kind="primary"],
[data-testid="stSidebar"] [data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
    background-image: none !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    border: none !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] button[kind="primary"] p,
[data-testid="stSidebar"] button[kind="primary"] span,
[data-testid="stSidebar"] [data-testid="baseButton-primary"] p,
[data-testid="stSidebar"] [data-testid="baseButton-primary"] span {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
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
/* Métricas tipo tarjeta + valor SIEMPRE oscuro (Streamlit a veces deja el número casi blanco) */
div[data-testid="stMetric"] {
    background: #fff !important;
    border: 1px solid #f1f5f9;
    border-radius: 14px;
    padding: 0.65rem 0.85rem;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    color: #0f172a !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricValue"] *,
div[data-testid="stMetric"] [data-testid="stMarkdownContainer"] p {
    color: #0f172a !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #0f172a !important;
}
div[data-testid="stMetric"] [data-testid="stMetricLabel"] p,
div[data-testid="stMetric"] [data-testid="stMetricLabel"] label,
div[data-testid="stMetric"] [data-testid="stMetricLabel"] span {
    color: #334155 !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}
/* Delta: mantener verde / rojo del tema */
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    opacity: 1 !important;
}
div[data-testid="stMetric"] [data-testid="stMetricDelta"] svg {
    opacity: 1 !important;
}
/* Área principal: mismos fixes para métricas fuera de columnas raras */
.main div[data-testid="stMetric"] [data-testid="stMetricValue"],
.main div[data-testid="stMetric"] [data-testid="stMetricValue"] * {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
}
/* Selectores y widgets en el cuerpo (ej. «Vista rápida» en dashboard) */
.main [data-testid="stWidgetLabel"] p,
.main [data-testid="stWidgetLabel"] label {
    color: #1e293b !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}
.main [data-baseweb="select"] > div,
.main .stSelectbox [data-baseweb="select"] span {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
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
/* Encabezados markdown Streamlit (##### etc.): forzar oscuro en el cuerpo principal */
section[data-testid="stMain"] h1,
section[data-testid="stMain"] h2,
section[data-testid="stMain"] h3,
section[data-testid="stMain"] h4,
section[data-testid="stMain"] h5,
section[data-testid="stMain"] h6,
section[data-testid="stMain"] .stMarkdown h1,
section[data-testid="stMain"] .stMarkdown h2,
section[data-testid="stMain"] .stMarkdown h3,
section[data-testid="stMain"] .stMarkdown h4,
section[data-testid="stMain"] .stMarkdown h5,
section[data-testid="stMain"] .stMarkdown h6 {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    opacity: 1 !important;
}
/* Contenido dentro de pestañas (Cumplimiento, Gastos…): captions y texto gris ilegible → oscuro */
[data-baseweb="tab-panel"] [data-testid="stCaption"],
[data-baseweb="tab-panel"] [data-testid="stCaption"] p,
[data-baseweb="tab-panel"] [data-testid="stCaption"] span,
[data-baseweb="tab-panel"] [data-testid="stMarkdownContainer"] p,
[data-baseweb="tab-panel"] [data-testid="stMarkdownContainer"] li,
[data-baseweb="tab-panel"] [data-testid="stMarkdownContainer"] span:not(a span) {
    color: #1e293b !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #1e293b !important;
    font-weight: 500 !important;
}
[data-baseweb="tab-panel"] [data-testid="stWidgetLabel"] p,
[data-baseweb="tab-panel"] [data-testid="stWidgetLabel"] label {
    color: #0f172a !important;
    opacity: 1 !important;
}
/* Variante DOM de pestañas (Streamlit / Base Web) */
[role="tabpanel"] [data-testid="stCaption"],
[role="tabpanel"] [data-testid="stCaption"] p,
[role="tabpanel"] [data-testid="stCaption"] span {
    color: #1e293b !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #1e293b !important;
    font-weight: 600 !important;
}
/* Expander «Configurar metas…»: título y texto interior */
[data-testid="stExpander"] details summary,
[data-testid="stExpander"] details summary span,
[data-testid="stExpander"] summary {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}
[data-testid="stExpander"] [data-testid="stCaption"],
[data-testid="stExpander"] [data-testid="stCaption"] p,
[data-testid="stExpander"] [data-testid="stCaption"] span,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] li {
    color: #334155 !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #334155 !important;
}
[data-testid="stExpander"] [data-testid="stWidgetLabel"] p,
[data-testid="stExpander"] label {
    color: #0f172a !important;
}
/* Columnas (metas / dos columnas): captions legibles */
[data-testid="column"] [data-testid="stCaption"],
[data-testid="column"] [data-testid="stCaption"] p,
[data-testid="column"] [data-testid="stCaption"] span {
    color: #334155 !important;
    font-weight: 600 !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #334155 !important;
}
/* Tablas interactivas: pedir tema claro al navegador y fondo blanco en el contenedor */
[data-testid="stDataFrame"] {
    background: #ffffff !important;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
}
[data-testid="stDataFrame"] > div {
    background-color: #ffffff !important;
}

/* =============================================================================
   Tema claro obligatorio: copia oscura en main (Streamlit a veces inyecta gris/blanco).
   Va al final del bloque global; las clases .lk-*/.kf-* en LUKANA_COMPONENT_CSS
   pueden sumar !important para excepciones (azul, pill, etc.).
   ============================================================================= */
section[data-testid="stMain"] .block-container {
    color: #1e293b !important;
    -webkit-text-fill-color: #1e293b !important;
}
/* Markdown Streamlit: color base oscuro (hereda; no listar `p` sueltos: rompería .lk-stat-blue) */
section[data-testid="stMain"] .block-container [data-testid="stMarkdownContainer"] {
    color: #1e293b !important;
    -webkit-text-fill-color: #1e293b !important;
}
section[data-testid="stMain"] .block-container [data-testid="stCaption"],
section[data-testid="stMain"] .block-container [data-testid="stCaption"] p,
section[data-testid="stMain"] .block-container [data-testid="stCaption"] span {
    color: #1e293b !important;
    -webkit-text-fill-color: #1e293b !important;
    opacity: 1 !important;
}
section[data-testid="stMain"] .block-container [data-testid="stMarkdownContainer"] a,
section[data-testid="stMain"] .block-container a {
    color: #1d4ed8 !important;
    -webkit-text-fill-color: #1d4ed8 !important;
    font-weight: 600 !important;
}
section[data-testid="stMain"] .block-container input,
section[data-testid="stMain"] .block-container textarea,
section[data-testid="stMain"] .block-container [data-baseweb="input"] input,
section[data-testid="stMain"] .block-container [data-baseweb="textarea"] textarea {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
}
/* Botones en el cuerpo: secondary = blanco + texto oscuro (igual que sidebar) */
section[data-testid="stMain"] button[kind="secondary"],
section[data-testid="stMain"] [data-testid="baseButton-secondary"] {
    background-color: #ffffff !important;
    background-image: none !important;
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    border: 1px solid #94a3b8 !important;
    font-weight: 600 !important;
}
section[data-testid="stMain"] button[kind="secondary"] p,
section[data-testid="stMain"] button[kind="secondary"] span,
section[data-testid="stMain"] [data-testid="baseButton-secondary"] p,
section[data-testid="stMain"] [data-testid="baseButton-secondary"] span {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
}
section[data-testid="stMain"] button[kind="primary"],
section[data-testid="stMain"] [data-testid="baseButton-primary"] {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
section[data-testid="stMain"] button[kind="primary"] p,
section[data-testid="stMain"] button[kind="primary"] span,
section[data-testid="stMain"] [data-testid="baseButton-primary"] p,
section[data-testid="stMain"] [data-testid="baseButton-primary"] span {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
"""


def inject_lukana_theme() -> None:
    """Inyecta CSS según `st.session_state[kf_ui_theme]` (default claro)."""
    st.session_state.setdefault(KF_THEME_KEY, THEME_LIGHT)
    if is_dark_theme():
        bundle = f"{DARK_GLOBAL_CHROME_CSS}\n{DARK_COMPONENT_CSS}"
    else:
        bundle = f"{LUKANA_GLOBAL_CHROME_CSS}\n{LUKANA_COMPONENT_CSS}"
    st.markdown(f"<style>{bundle}</style>", unsafe_allow_html=True)
