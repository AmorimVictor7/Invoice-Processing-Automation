"""
Serviço de sessões com Redis (primário) e memória RAM (fallback).

Estados formais de uma sessão:
  uploaded       → arquivos recebidos, OCR em andamento
  review_pending → OCR concluído, aguardando revisão do usuário
  confirmed      → usuário confirmou, geração do pacote em andamento
  exported       → pacote ZIP gerado e disponível para download
  failed         → erro irrecuperável durante processamento
  expired        → TTL expirado ou sessão inválida
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "7200"))


class SessionState:
    UPLOADED = "uploaded"
    REVIEW_PENDING = "review_pending"
    CONFIRMED = "confirmed"
    EXPORTED = "exported"
    FAILED = "failed"
    EXPIRED = "expired"


class SessionService:
    def __init__(self):
        self._redis = None
        self._mem: dict[str, dict] = {}
        self._job_index: dict[str, str] = {}  # job_id → session_id (fallback only)

    async def init(self) -> None:
        if not REDIS_URL:
            logger.warning("REDIS_URL não configurado — sessões em memória RAM (não persistem entre restarts)")
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await self._redis.ping()
            logger.info("SessionService: Redis conectado em %s", REDIS_URL)
        except Exception as exc:
            logger.warning("Redis indisponível (%s) — usando fallback em memória", exc)
            self._redis = None

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    # ── chaves Redis ──────────────────────────────────────────────────────────

    @staticmethod
    def _skey(session_id: str) -> str:
        return f"session:{session_id}"

    @staticmethod
    def _jkey(job_id: str) -> str:
        return f"job:{job_id}"

    # ── operações básicas ─────────────────────────────────────────────────────

    async def create(self, session_id: str, data: dict) -> None:
        payload = json.dumps(data, default=str)
        if self._redis:
            await self._redis.setex(self._skey(session_id), SESSION_TTL, payload)
        else:
            self._mem[session_id] = data

    async def get(self, session_id: str) -> Optional[dict]:
        if self._redis:
            raw = await self._redis.get(self._skey(session_id))
            return json.loads(raw) if raw else None
        return self._mem.get(session_id)

    async def update(self, session_id: str, data: dict) -> None:
        payload = json.dumps(data, default=str)
        if self._redis:
            await self._redis.setex(self._skey(session_id), SESSION_TTL, payload)
        else:
            self._mem[session_id] = data

    async def set_state(self, session_id: str, state: str) -> None:
        session = await self.get(session_id)
        if session is not None:
            session["status"] = state
            await self.update(session_id, session)

    async def delete(self, session_id: str) -> None:
        if self._redis:
            await self._redis.delete(self._skey(session_id))
        else:
            self._mem.pop(session_id, None)

    # ── índice job_id → session ───────────────────────────────────────────────

    async def register_job(self, job_id: str, session_id: str) -> None:
        """Cria um índice para que /download encontre a sessão via job_id em O(1)."""
        if self._redis:
            await self._redis.setex(self._jkey(job_id), SESSION_TTL, session_id)
        else:
            self._job_index[job_id] = session_id

    async def get_by_job_id(self, job_id: str) -> Optional[dict]:
        if self._redis:
            session_id = await self._redis.get(self._jkey(job_id))
            if not session_id:
                return None
            return await self.get(session_id)
        session_id = self._job_index.get(job_id)
        if not session_id:
            return None
        return self._mem.get(session_id)

    # ── limpeza periódica (memória apenas) ───────────────────────────────────

    def cleanup_memory(self) -> int:
        """Remove entradas sem job_id do fallback em memória. Redis usa TTL automático."""
        if self._redis:
            return 0
        before = len(self._mem)
        self._mem = {k: v for k, v in self._mem.items() if v.get("status") != SessionState.EXPIRED}
        return before - len(self._mem)


session_service = SessionService()
