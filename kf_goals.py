"""Metas de ahorro, presupuestos por rubro y fondo de emergencia (Supabase)."""

from __future__ import annotations

from datetime import date
from typing import Any

from supabase import Client


def ym_from_date(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def load_savings_goal(
    sb: Client, user_id: str, ym: str, currency: str
) -> dict[str, Any] | None:
    try:
        r = (
            sb.table("kf_savings_goal_month")
            .select("*")
            .eq("user_id", str(user_id))
            .eq("ym", ym)
            .eq("currency", currency)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None
    except Exception:
        return None


def upsert_savings_goal(
    sb: Client,
    user_id: str,
    ym: str,
    currency: str,
    goal_mode: str,
    target_numeric: float,
) -> tuple[bool, str | None]:
    try:
        uid = str(user_id)
        sb.table("kf_savings_goal_month").delete().eq("user_id", uid).eq("ym", ym).eq(
            "currency", currency
        ).execute()
        if float(target_numeric) <= 0:
            return True, None
        row = {
            "user_id": uid,
            "ym": ym,
            "currency": currency,
            "goal_mode": goal_mode,
            "target_numeric": float(target_numeric),
        }
        sb.table("kf_savings_goal_month").insert(row).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def clear_savings_goal(sb: Client, user_id: str, ym: str, currency: str) -> tuple[bool, str | None]:
    try:
        sb.table("kf_savings_goal_month").delete().eq("user_id", str(user_id)).eq("ym", ym).eq(
            "currency", currency
        ).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def load_category_budgets(
    sb: Client, user_id: str, ym: str, currency: str
) -> list[dict[str, Any]]:
    try:
        r = (
            sb.table("kf_category_budget_month")
            .select("category,budget_limit,id")
            .eq("user_id", str(user_id))
            .eq("ym", ym)
            .eq("currency", currency)
            .execute()
        )
        return list(r.data or [])
    except Exception:
        return []


def upsert_category_budget(
    sb: Client,
    user_id: str,
    ym: str,
    currency: str,
    category: str,
    budget_limit: float,
) -> tuple[bool, str | None]:
    try:
        uid = str(user_id)
        cat = category.strip()
        sb.table("kf_category_budget_month").delete().eq("user_id", uid).eq("ym", ym).eq(
            "currency", currency
        ).eq("category", cat).execute()
        if float(budget_limit) <= 0:
            return True, None
        row = {
            "user_id": uid,
            "ym": ym,
            "currency": currency,
            "category": cat,
            "budget_limit": float(budget_limit),
        }
        sb.table("kf_category_budget_month").insert(row).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def delete_category_budget(sb: Client, budget_id: str) -> tuple[bool, str | None]:
    try:
        sb.table("kf_category_budget_month").delete().eq("id", budget_id).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def load_emergency_fund(sb: Client, user_id: str) -> dict[str, Any] | None:
    try:
        r = (
            sb.table("kf_emergency_fund_target")
            .select("*")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return dict(rows[0]) if rows else None
    except Exception:
        return None


def upsert_emergency_fund(
    sb: Client, user_id: str, account_id: str | None, target_amount: float | None
) -> tuple[bool, str | None]:
    try:
        uid = str(user_id)
        sb.table("kf_emergency_fund_target").delete().eq("user_id", uid).execute()
        if not account_id or target_amount is None or float(target_amount) <= 0:
            return True, None
        row: dict[str, Any] = {
            "user_id": uid,
            "account_id": str(account_id),
            "target_amount": float(target_amount),
        }
        sb.table("kf_emergency_fund_target").insert(row).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def goals_tables_missing_message(exc: str) -> str:
    if "kf_savings_goal_month" in exc or "does not exist" in exc.lower():
        return (
            "Faltan las tablas de metas. En Supabase ejecutá **`supabase/patch_009_goals_budgets.sql`**."
        )
    return exc
