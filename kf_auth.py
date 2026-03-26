"""Login, cookie firmada y primer administrador — Kenny Finanzas."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import streamlit as st
from supabase import Client

from kf_config import resolve_supabase_credentials

KF_SESSION_COOKIE = "kf_fin_session"
SESSION_MAX_DAYS = 60


def _session_signing_key() -> bytes:
    try:
        auth = st.secrets.get("auth")
        if isinstance(auth, dict):
            sk = auth.get("SESSION_SIGNING_KEY")
            if sk:
                return str(sk).encode("utf-8")
    except Exception:
        pass
    _, k = resolve_supabase_credentials()
    if not k:
        raise RuntimeError("SUPABASE_KEY no configurada (secrets o entorno).")
    return hashlib.sha256((str(k) + "|kf_fin_session_v1").encode("utf-8")).digest()


def _encode_session_token(uid: str, sid: str, exp_unix: int) -> str:
    payload = {"v": 1, "uid": str(uid), "sid": str(sid), "exp": int(exp_unix)}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_session_signing_key(), body, hashlib.sha256).hexdigest()
    wrapped = json.dumps({"p": payload, "sig": sig}, separators=(",", ":"))
    return base64.urlsafe_b64encode(wrapped.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_session_token(token: str) -> dict[str, Any] | None:
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad)
        o = json.loads(raw.decode("utf-8"))
        p = o.get("p")
        sig = o.get("sig")
        if not isinstance(p, dict) or not isinstance(sig, str):
            return None
        body = json.dumps(p, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expect = hmac.new(_session_signing_key(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        if int(p.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return p
    except Exception:
        return None


def _cookie_manager():
    from extra_streamlit_components import CookieManager

    return CookieManager(key="kf_fin_cookie_mgr")


def safe_cookie_manager():
    try:
        return _cookie_manager() if cookie_support() else None
    except Exception:
        return None


def cookie_support() -> bool:
    try:
        import extra_streamlit_components  # noqa: F401

        return True
    except ImportError:
        return False


def _persist_session_cookie(cm: Any | None, row: dict[str, Any]) -> None:
    if cm is None:
        return
    uid = str(row["id"])
    sid = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    exp_unix = int(now.timestamp()) + SESSION_MAX_DAYS * 86400
    tok = _encode_session_token(uid, sid, exp_unix)
    expires_at = now + timedelta(days=SESSION_MAX_DAYS)
    cm.set(
        KF_SESSION_COOKIE,
        tok,
        key="kf_cookie_set",
        path="/",
        expires_at=expires_at,
        same_site="lax",
    )


def _clear_session_cookie(cm: Any | None) -> None:
    if cm is None:
        return
    try:
        cm.delete(KF_SESSION_COOKIE, key="kf_cookie_logout_del")
    except Exception:
        pass
    try:
        cm.set(
            KF_SESSION_COOKIE,
            "",
            key="kf_cookie_logout_set",
            path="/",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            same_site="lax",
        )
    except Exception:
        pass


def _restore_session_from_cookie(sb: Client, cm: Any | None) -> None:
    if cm is None or st.session_state.get("kf_uid"):
        return
    tok = cm.get(KF_SESSION_COOKIE)
    if not tok or not isinstance(tok, str):
        return
    payload = _decode_session_token(tok)
    if not payload:
        try:
            cm.delete(KF_SESSION_COOKIE, key="kf_cookie_del_bad")
        except Exception:
            pass
        return
    uid = str(payload.get("uid", "")).strip()
    if not uid:
        return
    r = (
        sb.table("kf_users")
        .select("id,username,display_name,is_admin,active")
        .eq("id", uid)
        .limit(1)
        .execute()
    )
    row = (r.data or [None])[0]
    if not row or row.get("active") is False:
        try:
            cm.delete(KF_SESSION_COOKIE, key="kf_cookie_del_inactive")
        except Exception:
            pass
        return
    st.session_state["kf_uid"] = str(row["id"])
    st.session_state["kf_username"] = str(row["username"])
    st.session_state["kf_display_name"] = str(row.get("display_name") or row["username"])
    st.session_state["kf_is_admin"] = bool(row.get("is_admin"))
    st.rerun()


def logout() -> None:
    for k in ("kf_uid", "kf_username", "kf_display_name", "kf_is_admin"):
        st.session_state.pop(k, None)
    st.session_state["kf_force_logout"] = True
    try:
        cm = safe_cookie_manager()
        _clear_session_cookie(cm)
    except Exception:
        pass


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _password_ok(plain: str, stored_hash: str) -> bool:
    h = (stored_hash or "").strip()
    if not h or not h.startswith("$2"):
        return False
    b = plain.encode("utf-8")
    try:
        if bcrypt.checkpw(b, h.encode("utf-8")):
            return True
    except Exception:
        pass
    if h.startswith("$2a$"):
        try:
            h2 = "$2b$" + h[4:]
            return bool(bcrypt.checkpw(b, h2.encode("utf-8")))
        except Exception:
            return False
    return False


def fetch_user_by_username(sb: Client, username: str) -> dict[str, Any] | None:
    u = username.strip().lower()
    r = sb.table("kf_users").select("*").eq("username", u).limit(1).execute()
    rows = r.data or []
    if rows:
        return rows[0]
    for row in (sb.table("kf_users").select("*").execute().data or []):
        if str(row.get("username", "")).strip().lower() == u:
            return row
    return None


def current_user() -> dict[str, Any] | None:
    uid = st.session_state.get("kf_uid")
    if not uid:
        return None
    return {
        "id": str(uid),
        "username": str(st.session_state.get("kf_username", "")),
        "display_name": str(st.session_state.get("kf_display_name", "")),
        "is_admin": bool(st.session_state.get("kf_is_admin")),
    }


def count_users(sb: Client) -> int:
    r = sb.table("kf_users").select("id").execute()
    return len(r.data or [])


def gate_auth(sb: Client) -> dict[str, Any] | None:
    """Devuelve el usuario logueado o detiene la app con login / bootstrap."""
    cm = safe_cookie_manager()
    if st.session_state.get("kf_force_logout"):
        for k in ("kf_uid", "kf_username", "kf_display_name", "kf_is_admin"):
            st.session_state.pop(k, None)
        _clear_session_cookie(cm)
    else:
        try:
            _restore_session_from_cookie(sb, cm)
        except Exception:
            pass

    u = current_user()
    if u:
        return u

    st.title("Kenny Finanzas")
    st.caption("Iniciá sesión para ver movimientos y el tablero.")

    try:
        n = count_users(sb)
    except Exception:
        st.error(
            "No existe la tabla de usuarios. En Supabase ejecutá `supabase/schema.sql` "
            "completo o `supabase/patch_002_users_auth.sql`."
        )
        st.stop()
        return None

    if n == 0:
        st.subheader("Primer acceso: crear administrador")
        st.write("Orlando o Kenny puede ser el primer usuario; después podrá crear al otro.")
        with st.form("bootstrap"):
            display_name = st.text_input("Nombre para mostrar", placeholder="Kenny")
            username = st.text_input("Usuario (sin espacios)", placeholder="kenny")
            p1 = st.text_input("Contraseña", type="password")
            p2 = st.text_input("Repetir contraseña", type="password")
            if st.form_submit_button("Crear administrador"):
                if not display_name.strip() or not username.strip():
                    st.error("Completá nombre y usuario.")
                elif len(p1) < 8:
                    st.error("La contraseña debe tener al menos 8 caracteres.")
                elif p1 != p2:
                    st.error("Las contraseñas no coinciden.")
                else:
                    sb.table("kf_users").insert(
                        {
                            "username": username.strip().lower(),
                            "display_name": display_name.strip(),
                            "password_hash": _hash_password(p1),
                            "is_admin": True,
                            "active": True,
                        }
                    ).execute()
                    row = fetch_user_by_username(sb, username)
                    if row:
                        st.session_state["kf_uid"] = str(row["id"])
                        st.session_state["kf_username"] = str(row["username"])
                        st.session_state["kf_display_name"] = str(row["display_name"])
                        st.session_state["kf_is_admin"] = True
                        st.session_state.pop("kf_force_logout", None)
                        _persist_session_cookie(cm, row)
                    st.success("Listo. Ya podés usar la app.")
                    st.rerun()
        st.stop()
        return None

    with st.form("login"):
        user = st.text_input("Usuario", autocomplete="username")
        pwd = st.text_input("Contraseña", type="password", autocomplete="current-password")
        if st.form_submit_button("Entrar"):
            row = fetch_user_by_username(sb, user)
            if not row or not row.get("active", True):
                st.error("Usuario o contraseña incorrectos.")
            elif not _password_ok(pwd, str(row.get("password_hash", ""))):
                st.error("Usuario o contraseña incorrectos.")
            else:
                st.session_state["kf_uid"] = str(row["id"])
                st.session_state["kf_username"] = str(row["username"])
                st.session_state["kf_display_name"] = str(row.get("display_name") or row["username"])
                st.session_state["kf_is_admin"] = bool(row.get("is_admin"))
                st.session_state.pop("kf_force_logout", None)
                _persist_session_cookie(cm, row)
                st.rerun()

    if not cookie_support():
        st.info(
            "Instalá `extra-streamlit-components` para que la sesión persista al refrescar la página."
        )

    st.stop()
    return None
