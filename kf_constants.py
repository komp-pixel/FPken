"""Origen de ingresos (negocios), cuentas por tipo (banco / wallet / app) y categorías."""

INCOME_BUSINESSES: list[str] = [
    "Movi Motors",
    "Cuentas Delivery",
    "Asistente Zemog",
    "Otro",
]

CURRENCIES: list[str] = ["USD", "VES", "USDT"]

# Cuentas bancarias tradicionales (Banesco, BofA, Banca Amiga) — sin wallet ni apps.
INSTITUTION_BANKS: list[str] = [
    "Bank of America",
    "Banesco",
    "Banca Amiga",
    "Otro",
]

# Solo crypto / exchange (Binance, on-chain, etc.)
INSTITUTION_WALLET: list[str] = [
    "Binance",
    "On-chain / otra wallet",
    "Otro",
]

# Red de depósito on-chain (texto libre si elegís "Otro" en formularios que lo permitan)
WALLET_DEPOSIT_NETWORKS: list[str] = [
    "—",
    "TRC20",
    "BEP20 (BSC)",
    "ERC20",
    "Arbitrum One",
    "Optimism",
    "Polygon",
    "Otro / varias (ver notas)",
]

# Zinly, Zelle y similares (pagos digitales; no es cuenta corriente ni wallet on-chain)
INSTITUTION_APPS: list[str] = [
    "Zinly",
    "Zelle",
    "Otro",
]

# Compatibilidad con datos viejos o edición genérica
INSTITUTION_PRESETS: list[str] = (
    INSTITUTION_BANKS[:-1] + INSTITUTION_WALLET[:-1] + INSTITUTION_APPS
)

TRANSFER_TAGS: list[str] = [
    "Zelle → Binance / comisión",
    "Zinly / compras electrónicas",
    "P2P bolívares",
    "Futuros / inversión",
    "Entre mis cuentas",
    "Otro",
]

EXPENSE_CATEGORIES: list[str] = [
    "Casa",
    "Carro",
    "Hijos",
    "Salud",
    "Educación",
    "Comida",
    "Servicios",
    "Compras electrónicas / online",
    "Impuestos / banco",
    "Ocio / viajes",
    "Otro",
]

ACCOUNT_KIND_LABELS: dict[str, str] = {
    "banco": "Cuenta bancaria",
    "wallet": "Wallet / crypto",
    "app_pagos": "App de pagos",
}
