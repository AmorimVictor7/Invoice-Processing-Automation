"""
Dependências FastAPI para autenticação.
Injetadas nos routers via Depends(get_current_user).

Aceita autenticação via:
  1. Cookie httpOnly `access_token` (JWT) — fluxo do frontend
  2. Header `X-API-Key: ipa_<token>` — acesso programático
"""
import hashlib

from fastapi import Cookie, Depends, Header, HTTPException, status
import jwt

from db.database import get_api_key_by_hash, get_user_by_id, touch_api_key
from services.auth_service import decode_access_token


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_current_user(
    access_token: str = Cookie(None),
    x_api_key: str = Header(None, alias="X-API-Key"),
) -> dict:
    """
    Autentica via JWT cookie (frontend) ou X-API-Key header (programático).
    Retorna o dict do usuário autenticado ou levanta 401.
    """
    # ── Autenticação por API key ──────────────────────────────────────────────
    if x_api_key:
        if not x_api_key.startswith("ipa_"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida.")
        key_hash = _hash_api_key(x_api_key)
        record = await get_api_key_by_hash(key_hash)
        if not record:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida ou revogada.")
        user = await get_user_by_id(record["user_id"])
        if not user or not user["is_active"]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inativo.")
        await touch_api_key(key_hash)
        return user

    # ── Autenticação por JWT cookie ───────────────────────────────────────────
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado.")
    try:
        payload = decode_access_token(access_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    user = await get_user_by_id(payload["sub"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado ou inativo.")
    return user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    return current_user
