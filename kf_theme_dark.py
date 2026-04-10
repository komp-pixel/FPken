"""CSS para tema oscuro (importado por kf_theme)."""

# Tarjetas de pago / cuentas — sobreescribe kf_account_cards en oscuro
DARK_KF_ACCOUNT_CARDS_CSS = """
.kf-pay-card-wrap .kf-pay-card {
    background: #0f172a !important;
    border-color: #334155 !important;
    box-shadow: 0 2px 16px rgba(0, 0, 0, 0.35);
}
.kf-pay-card-wrap .kf-head {
    border-bottom-color: #334155 !important;
}
.kf-pay-card-wrap .kf-meta {
    color: #94a3b8 !important;
}
.kf-pay-card-wrap .kf-balance-strip {
    background: linear-gradient(135deg, #1e3a5f 0%, #1e293b 100%) !important;
    border-color: #3b82f6 !important;
}
.kf-pay-card-wrap .kf-balance-strip label {
    color: #e2e8f0 !important;
}
.kf-pay-card-wrap .kf-balance-amt {
    color: #f8fafc !important;
}
.kf-pay-card-wrap .kf-balance-date {
    color: #cbd5e1 !important;
}
.kf-pay-card-wrap .kf-balance-strip.kf-banco label,
.kf-pay-card-wrap .kf-balance-strip.kf-banco .kf-balance-date {
    color: #ffffff !important;
    text-shadow: 0 1px 3px rgba(0,0,0,0.4);
}
.kf-pay-card-wrap .kf-fld label {
    color: #94a3b8 !important;
}
.kf-pay-card-wrap .kf-fld span {
    color: #f1f5f9 !important;
}
.kf-pay-card-wrap .kf-title-row strong {
    color: #f8fafc !important;
}
"""

DARK_COMPONENT_CSS = """
/* Lukana oscuro — mismas piezas, colores invertidos */
.lk-canvas {
    background: linear-gradient(165deg, #1e293b 0%, #172033 50%, #0f172a 100%);
    border-radius: 20px;
    padding: 1.35rem 1.25rem 1.5rem;
    margin-bottom: 1.1rem;
    border: 1px solid #334155;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}
.lk-top {
    display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between;
    gap: 0.75rem; margin-bottom: 1.15rem;
}
.lk-brand { margin: 0; font-size: 1.55rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.035em; line-height: 1.15; }
.lk-brand em { font-style: normal; color: #60a5fa; }
.lk-subtitle { margin: 0.35rem 0 0 0; font-size: 0.88rem; color: #94a3b8; font-weight: 500; }
.lk-pill {
    display: inline-flex; align-items: center; height: 2rem; padding: 0 0.9rem;
    background: linear-gradient(135deg, #3b82f6, #2563eb); color: #fff !important;
    border-radius: 999px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.02em;
    box-shadow: 0 2px 12px rgba(37, 99, 235, 0.45);
}
.lk-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.85rem; }
@media (max-width: 950px) { .lk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.lk-stat {
    background: #0f172a;
    border-radius: 14px;
    padding: 1rem 1.05rem;
    min-height: 102px;
    border: 1px solid #334155;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
}
.lk-stat h4 {
    margin: 0; font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: #94a3b8;
}
.lk-stat .lk-val { margin: 0.45rem 0 0 0; font-size: 1.32rem; font-weight: 800; color: #f8fafc; line-height: 1.15; }
.lk-stat .lk-foot { margin: 0.35rem 0 0 0; font-size: 0.72rem; color: #94a3b8; font-weight: 500; }
.lk-stat-blue {
    background: linear-gradient(145deg, #2563eb 0%, #1d4ed8 100%);
    border: none;
    box-shadow: 0 6px 24px rgba(37, 99, 235, 0.45);
}
.lk-stat-blue h4 { color: rgba(255,255,255,0.9); }
.lk-stat-blue .lk-val { color: #fff !important; }
.lk-stat-blue .lk-foot { color: rgba(255,255,255,0.85); }
.lk-pos { color: #4ade80 !important; -webkit-text-fill-color: #4ade80 !important; }
.lk-neg { color: #f87171 !important; -webkit-text-fill-color: #f87171 !important; }
.lk-section {
    font-size: 1.02rem; font-weight: 800; color: #f1f5f9;
    margin: 1.15rem 0 0.5rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 3px solid #3b82f6;
    display: inline-block;
    letter-spacing: -0.02em;
}
.lk-hint { font-size: 0.82rem; color: #94a3b8; font-weight: 500; margin-top: 0.35rem; }
.lk-panel-h {
    margin: 0 0 0.5rem 0; font-size: 1.05rem; font-weight: 800; color: #f8fafc !important;
    letter-spacing: -0.02em; -webkit-text-fill-color: #f8fafc !important;
}
.lk-page-title { font-size: 1.75rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.03em; margin: 0 0 0.25rem 0; }
.lk-page-title em { font-style: normal; color: #60a5fa; }
.lk-balance-cards-wrap .lk-stat h4 { font-size: 0.78rem; line-height: 1.3; word-break: break-word; color: #94a3b8 !important; }
.lk-balance-cards-wrap .lk-stat .lk-val { font-size: 1.2rem; color: #f8fafc !important; }
section[data-testid="stMain"] .lk-stat-blue h4,
section[data-testid="stMain"] .lk-stat-blue .lk-val,
section[data-testid="stMain"] .lk-stat-blue .lk-foot {
    color: #ffffff !important; -webkit-text-fill-color: #ffffff !important;
}
section[data-testid="stMain"] .lk-stat-blue h4 { color: rgba(255,255,255,0.92) !important; }
section[data-testid="stMain"] .lk-stat-blue .lk-foot { color: rgba(255,255,255,0.88) !important; }
section[data-testid="stMain"] .lk-pill {
    color: #ffffff !important; -webkit-text-fill-color: #ffffff !important;
}
section[data-testid="stMain"] .lk-pos { color: #4ade80 !important; -webkit-text-fill-color: #4ade80 !important; }
section[data-testid="stMain"] .lk-neg { color: #f87171 !important; -webkit-text-fill-color: #f87171 !important; }
"""

DARK_GLOBAL_CHROME_CSS = """
.stApp {
    background: linear-gradient(165deg, #0f172a 0%, #1e1b2e 40%, #111827 100%) !important;
    color: #e2e8f0 !important;
}
.main .block-container {
    padding-top: 1.25rem;
    padding-bottom: 2rem;
    color-scheme: dark;
    color: #e2e8f0 !important;
    -webkit-text-fill-color: #e2e8f0 !important;
}
.main [data-testid="stCaption"],
.main [data-testid="stCaption"] p,
.main [data-testid="stCaption"] span,
section[data-testid="stMain"] [data-testid="stCaption"] {
    color: #cbd5e1 !important;
    opacity: 1 !important;
    font-weight: 500 !important;
    -webkit-text-fill-color: #cbd5e1 !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #020617 100%) !important;
    border-right: 1px solid #334155 !important;
    color: #e2e8f0 !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] [data-testid="stCaption"],
[data-testid="stSidebar"] [data-testid="stCaption"] p,
[data-testid="stSidebar"] [data-testid="stCaption"] span {
    color: #e2e8f0 !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #e2e8f0 !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] span {
    color: #f1f5f9 !important;
    opacity: 1 !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="input"] input,
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] * {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}
[data-testid="stSidebar"] details summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary span {
    color: #f1f5f9 !important;
}
[data-testid="stSidebar"] .stMarkdown a { color: #60a5fa !important; }
[data-testid="stSidebar"] button[kind="secondary"],
[data-testid="stSidebar"] [data-testid="baseButton-secondary"] {
    background-color: #1e293b !important;
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
    border: 1px solid #475569 !important;
}
[data-testid="stSidebar"] button[kind="secondary"] p,
[data-testid="stSidebar"] button[kind="secondary"] span,
[data-testid="stSidebar"] [data-testid="baseButton-secondary"] p,
[data-testid="stSidebar"] [data-testid="baseButton-secondary"] span {
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
}
[data-testid="stSidebar"] button[kind="primary"],
[data-testid="stSidebar"] [data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #3b82f6, #2563eb) !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
[data-testid="stSidebar"] button[kind="primary"] p,
[data-testid="stSidebar"] button[kind="primary"] span,
[data-testid="stSidebar"] [data-testid="baseButton-primary"] p,
[data-testid="stSidebar"] [data-testid="baseButton-primary"] span {
    color: #ffffff !important;
}
.main div[data-testid="stVerticalBlock"] > div > [data-testid="stElementContainer"] small {
    color: #94a3b8 !important;
}
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p,
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] li,
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] span {
    color: #f1f5f9 !important;
    opacity: 1 !important;
}
.main .block-container [data-testid="stMarkdownContainer"] p,
.main .block-container [data-testid="stMarkdownContainer"] li {
    color: #e2e8f0 !important;
}
.main .block-container [data-testid="stMarkdownContainer"] strong {
    color: #f8fafc !important;
}
/* Pestañas principales — más aire, texto grande, activa en cyan que resalta */
[data-testid="stTabs"] [data-baseweb="tab-list"],
.stTabs [data-baseweb="tab-list"] {
    gap: 0.65rem !important;
    row-gap: 0.5rem !important;
    background: linear-gradient(180deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.9) 100%) !important;
    border-radius: 14px !important;
    padding: 0.55rem 0.65rem !important;
    border: 1px solid #475569 !important;
    flex-wrap: wrap !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
}
[data-testid="stTabs"] [data-baseweb="tab"],
.stTabs [data-baseweb="tab"] {
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
    line-height: 1.35 !important;
    letter-spacing: 0.02em !important;
    padding: 0.5rem 1rem !important;
    min-height: 2.85rem !important;
    margin: 0 !important;
    color: #cbd5e1 !important;
    background-color: rgba(15, 23, 42, 0.75) !important;
    border: 1px solid #334155 !important;
    -webkit-text-fill-color: #cbd5e1 !important;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stTabs"] [data-baseweb="tab"] p,
[data-testid="stTabs"] [data-baseweb="tab"] span,
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span {
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    color: inherit !important;
    -webkit-text-fill-color: inherit !important;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover,
.stTabs [data-baseweb="tab"]:hover {
    color: #f1f5f9 !important;
    background-color: rgba(51, 65, 85, 0.95) !important;
    border-color: #64748b !important;
    -webkit-text-fill-color: #f1f5f9 !important;
}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"],
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #0f172a !important;
    background: linear-gradient(135deg, #22d3ee 0%, #38bdf8 45%, #818cf8 100%) !important;
    border-color: #67e8f9 !important;
    box-shadow: 0 0 0 1px rgba(103, 232, 249, 0.45), 0 6px 20px rgba(56, 189, 248, 0.28) !important;
    -webkit-text-fill-color: #0f172a !important;
}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] p,
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] span,
.stTabs [data-baseweb="tab"][aria-selected="true"] p,
.stTabs [data-baseweb="tab"][aria-selected="true"] span {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    font-weight: 800 !important;
}
/* Línea inferior por defecto de Base Web (evita doble “subrayado” con el pill) */
[data-testid="stTabs"] [data-baseweb="tab-border"],
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}
div[data-testid="stMetric"] {
    background: #0f172a !important;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 0.65rem 0.85rem;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    color: #f8fafc !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricValue"] *,
div[data-testid="stMetric"] [data-testid="stMarkdownContainer"] p {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}
div[data-testid="stMetric"] [data-testid="stMetricLabel"] p,
div[data-testid="stMetric"] [data-testid="stMetricLabel"] label,
div[data-testid="stMetric"] [data-testid="stMetricLabel"] span {
    color: #94a3b8 !important;
    font-weight: 600 !important;
}
.main div[data-testid="stMetric"] [data-testid="stMetricValue"],
.main div[data-testid="stMetric"] [data-testid="stMetricValue"] * {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}
.main [data-testid="stWidgetLabel"] p,
.main [data-testid="stWidgetLabel"] label {
    color: #e2e8f0 !important;
    font-weight: 600 !important;
}
.main [data-baseweb="select"] > div,
.main .stSelectbox [data-baseweb="select"] span {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}
div[data-testid="stAlert"] { border-radius: 12px; border-width: 1px; }
@media (max-width: 768px) {
    .block-container { padding-left: 0.85rem !important; padding-right: 0.85rem !important; }
}
div[data-testid="stVerticalBlock"] button { min-height: 2.75rem; }
section[data-testid="stMain"] h1, section[data-testid="stMain"] h2, section[data-testid="stMain"] h3,
section[data-testid="stMain"] h4, section[data-testid="stMain"] h5, section[data-testid="stMain"] h6,
section[data-testid="stMain"] .stMarkdown h1, section[data-testid="stMain"] .stMarkdown h2,
section[data-testid="stMain"] .stMarkdown h3, section[data-testid="stMain"] .stMarkdown h4,
section[data-testid="stMain"] .stMarkdown h5, section[data-testid="stMain"] .stMarkdown h6 {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}
[data-baseweb="tab-panel"] [data-testid="stCaption"],
[data-baseweb="tab-panel"] [data-testid="stCaption"] p,
[data-baseweb="tab-panel"] [data-testid="stCaption"] span,
[data-baseweb="tab-panel"] [data-testid="stMarkdownContainer"] p,
[data-baseweb="tab-panel"] [data-testid="stMarkdownContainer"] li,
[data-baseweb="tab-panel"] [data-testid="stMarkdownContainer"] span:not(a span) {
    color: #cbd5e1 !important;
    -webkit-text-fill-color: #cbd5e1 !important;
    opacity: 1 !important;
}
[data-baseweb="tab-panel"] [data-testid="stWidgetLabel"] p,
[data-baseweb="tab-panel"] [data-testid="stWidgetLabel"] label {
    color: #f1f5f9 !important;
}
[role="tabpanel"] [data-testid="stCaption"],
[role="tabpanel"] [data-testid="stCaption"] p,
[role="tabpanel"] [data-testid="stCaption"] span {
    color: #cbd5e1 !important;
    -webkit-text-fill-color: #cbd5e1 !important;
}
[data-testid="stExpander"] details summary,
[data-testid="stExpander"] details summary span,
[data-testid="stExpander"] summary {
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
}
[data-testid="stExpander"] [data-testid="stCaption"],
[data-testid="stExpander"] [data-testid="stCaption"] p,
[data-testid="stExpander"] [data-testid="stCaption"] span,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p,
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] li {
    color: #cbd5e1 !important;
    -webkit-text-fill-color: #cbd5e1 !important;
}
[data-testid="stExpander"] [data-testid="stWidgetLabel"] p,
[data-testid="stExpander"] label { color: #e2e8f0 !important; }
[data-testid="column"] [data-testid="stCaption"],
[data-testid="column"] [data-testid="stCaption"] p,
[data-testid="column"] [data-testid="stCaption"] span {
    color: #cbd5e1 !important;
    -webkit-text-fill-color: #cbd5e1 !important;
}
[data-testid="stDataFrame"] {
    background: #0f172a !important;
    border-radius: 12px;
    border: 1px solid #334155;
}
[data-testid="stDataFrame"] > div { background-color: #0f172a !important; }
section[data-testid="stMain"] .block-container {
    color: #e2e8f0 !important;
    -webkit-text-fill-color: #e2e8f0 !important;
}
section[data-testid="stMain"] .block-container [data-testid="stMarkdownContainer"] {
    color: #e2e8f0 !important;
    -webkit-text-fill-color: #e2e8f0 !important;
}
section[data-testid="stMain"] .block-container [data-testid="stCaption"],
section[data-testid="stMain"] .block-container [data-testid="stCaption"] p,
section[data-testid="stMain"] .block-container [data-testid="stCaption"] span {
    color: #cbd5e1 !important;
    -webkit-text-fill-color: #cbd5e1 !important;
}
section[data-testid="stMain"] .block-container [data-testid="stMarkdownContainer"] a,
section[data-testid="stMain"] .block-container a {
    color: #60a5fa !important;
    -webkit-text-fill-color: #60a5fa !important;
}
section[data-testid="stMain"] .block-container input,
section[data-testid="stMain"] .block-container textarea,
section[data-testid="stMain"] .block-container [data-baseweb="input"] input,
section[data-testid="stMain"] .block-container [data-baseweb="textarea"] textarea {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
    background-color: #1e293b !important;
}
section[data-testid="stMain"] button[kind="secondary"],
section[data-testid="stMain"] [data-testid="baseButton-secondary"] {
    background-color: #1e293b !important;
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
    border: 1px solid #475569 !important;
}
section[data-testid="stMain"] button[kind="secondary"] p,
section[data-testid="stMain"] button[kind="secondary"] span,
section[data-testid="stMain"] [data-testid="baseButton-secondary"] p,
section[data-testid="stMain"] [data-testid="baseButton-secondary"] span {
    color: #f1f5f9 !important;
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
}
"""
