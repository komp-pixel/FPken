"""Credenciales Supabase: secrets.toml o variables de entorno."""

from __future__ import annotations

import os
from typing import Tuple

import streamlit as st


def resolve_supabase_credentials() -> Tuple[str, str]:
    u, k = "", ""
    try:
        sec = st.secrets["connections"]["supabase"]
        u = str(sec.get("SUPABASE_URL", "")).strip().strip('"').strip("'")
        k = str(sec.get("SUPABASE_KEY", "")).strip().strip('"').strip("'")
    except (KeyError, TypeError):
        pass

    if not u or not k:
        u = (os.environ.get("SUPABASE_URL") or "").strip()
        k = (
            os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or ""
        ).strip()

    return u, k
