"""
Roteador de autenticação.
Todos os tokens trafegam exclusivamente via cookies httpOnly — nunca no body.

Endpoints:
  POST /api/auth/register  → cria conta e já autentica
  POST /api/auth/login     → autentica usuário existente
  POST /api/auth/refresh   → renova access token via refresh token (rotação)
  POST /api/auth/logout    → revoga refresh token e limpa cookies
  GET  /api/auth/me        → retorna dados do usuário autenticado
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

from db.database import (
    create_api_key,
    create_refresh_token,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_valid_refresh_token,
    list_api_keys,
    log_action,
    revoke_api_key,
    revoke_refresh_token,
    update_last_login,
)
from deps.auth import get_current_user
import hashlib
import secrets

from services.auth_service import (
    REFRESH_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token_value,
    hash_password,
    hash_refresh_token,
    verify_password,
    ACCESS_EXPIRE_MINUTES,
)

router = APIRouter()

ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
_IS_PROD = os.getenv("APP_ENV", "development") == "production"


# ── helpers ───────────────────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, access_token: str, refresh_value: str) -> None:
    """Define os dois cookies httpOnly na resposta."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=_IS_PROD,
        samesite="strict",
        max_age=ACCESS_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_value,
        httponly=True,
        secure=_IS_PROD,
        samesite="strict",
        max_age=REFRESH_EXPIRE_DAYS * 86400,
        path="/api/auth",   # restrito ao endpoint de refresh
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth")


def _user_payload(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
    }


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host


# ── schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request, response: Response):
    if not ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="Registro de novos usuários está desabilitado.")

    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Senha deve ter no mínimo 8 caracteres.")

    if await get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await create_user({
        "id": user_id,
        "name": body.name.strip(),
        "email": body.email,
        "password_hash": hash_password(body.password),
        "role": "user",
        "is_active": 1,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
    })

    access_token = create_access_token(user_id, body.email, "user")
    refresh_value = create_refresh_token_value()

    await create_refresh_token({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "token_hash": hash_refresh_token(refresh_value),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS)).isoformat(),
        "revoked": 0,
        "created_at": now,
    })

    _set_auth_cookies(response, access_token, refresh_value)
    await log_action("register", user_id=user_id, entity_type="user", entity_id=user_id,
                     ip_address=_client_ip(request))

    return {"user": {"id": user_id, "name": body.name.strip(), "email": body.email, "role": "user"}}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    user = await get_user_by_email(body.email)

    # Tempo constante para evitar timing attacks (mesmo quando usuário não existe)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Conta desativada. Contate o administrador.")

    access_token = create_access_token(user["id"], user["email"], user["role"])
    refresh_value = create_refresh_token_value()
    now = datetime.now(timezone.utc).isoformat()

    await create_refresh_token({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "token_hash": hash_refresh_token(refresh_value),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS)).isoformat(),
        "revoked": 0,
        "created_at": now,
    })
    await update_last_login(user["id"], now)

    _set_auth_cookies(response, access_token, refresh_value)
    await log_action("login", user_id=user["id"], entity_type="user", entity_id=user["id"],
                     ip_address=_client_ip(request))

    return {"user": _user_payload(user)}


@router.post("/refresh")
async def refresh(request: Request, response: Response, refresh_token: str = Cookie(None)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token ausente.")

    token_hash = hash_refresh_token(refresh_token)
    record = await get_valid_refresh_token(token_hash)

    if not record:
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado.")

    # Rotação: invalida o token atual antes de emitir um novo
    await revoke_refresh_token(token_hash)

    user = await get_user_by_id(record["user_id"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Usuário inativo.")

    access_token = create_access_token(user["id"], user["email"], user["role"])
    new_refresh_value = create_refresh_token_value()
    now = datetime.now(timezone.utc).isoformat()

    await create_refresh_token({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "token_hash": hash_refresh_token(new_refresh_value),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS)).isoformat(),
        "revoked": 0,
        "created_at": now,
    })

    _set_auth_cookies(response, access_token, new_refresh_value)
    return {"user": _user_payload(user)}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    refresh_token: str = Cookie(None),
    current_user: dict = Depends(get_current_user),
):
    if refresh_token:
        await revoke_refresh_token(hash_refresh_token(refresh_token))

    _clear_auth_cookies(response)
    await log_action("logout", user_id=current_user["id"], entity_type="user",
                     entity_id=current_user["id"], ip_address=_client_ip(request))
    return {"message": "Logout realizado com sucesso."}


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "user": {
            **_user_payload(current_user),
            "last_login": current_user.get("last_login"),
            "created_at": current_user.get("created_at"),
        }
    }


# ── API Keys ──────────────────────────────────────────────────────────────────

class ApiKeyCreateRequest(BaseModel):
    name: str


def _generate_api_key() -> str:
    return "ipa_" + secrets.token_urlsafe(48)


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/api-keys", status_code=201)
async def create_api_key_endpoint(
    body: ApiKeyCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Cria uma nova API key para o usuário autenticado.
    A chave é exibida UMA ÚNICA VEZ — apenas o hash é armazenado.
    """
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Nome da API key é obrigatório.")

    raw_key = _generate_api_key()
    now = datetime.now(timezone.utc).isoformat()

    await create_api_key({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "name": body.name.strip(),
        "key_hash": _hash_api_key(raw_key),
        "created_at": now,
    })

    await log_action(
        "api_key_created",
        user_id=current_user["id"],
        entity_type="api_key",
        details={"name": body.name.strip()},
        ip_address=_client_ip(request),
    )

    return {
        "key": raw_key,
        "name": body.name.strip(),
        "created_at": now,
        "warning": "Guarde esta chave agora — ela não será exibida novamente.",
    }


@router.get("/api-keys")
async def list_api_keys_endpoint(current_user: dict = Depends(get_current_user)):
    """Lista todas as API keys do usuário (sem exibir o valor da chave)."""
    keys = await list_api_keys(current_user["id"])
    return {"api_keys": keys}


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key_endpoint(
    key_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Revoga uma API key. Ação irreversível."""
    revoked = await revoke_api_key(key_id, current_user["id"])
    if not revoked:
        raise HTTPException(status_code=404, detail="API key não encontrada.")
    await log_action(
        "api_key_revoked",
        user_id=current_user["id"],
        entity_type="api_key",
        entity_id=key_id,
        ip_address=_client_ip(request),
    )
