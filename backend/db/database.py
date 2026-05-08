"""
Camada de acesso ao banco SQLite via aiosqlite.

Tabelas:
  users               — contas de usuário
  refresh_tokens      — tokens de refresh (somente hash armazenado)
  processing_history  — lotes de invoices processados
  invoices            — invoices normalizadas (índices para duplicate check)
  audit_logs          — log de auditoria de ações críticas
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).parent.parent / "invoice_history.db"


# ── inicialização ─────────────────────────────────────────────────────────────

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                email       TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role        TEXT NOT NULL DEFAULT 'user',
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                last_login  TEXT
            );

            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL REFERENCES users(id),
                token_hash  TEXT NOT NULL UNIQUE,
                expires_at  TEXT NOT NULL,
                revoked     INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rt_hash ON refresh_tokens(token_hash);
            CREATE INDEX IF NOT EXISTS idx_rt_user ON refresh_tokens(user_id);

            CREATE TABLE IF NOT EXISTS processing_history (
                id              TEXT PRIMARY KEY,
                session_id      TEXT NOT NULL,
                processed_at    TEXT NOT NULL,
                invoice_count   INTEGER NOT NULL,
                supplier_list   TEXT NOT NULL,
                total_amount_brl REAL,
                excel_filename  TEXT NOT NULL,
                zip_filename    TEXT NOT NULL,
                invoices_json   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id              TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL REFERENCES users(id),
                session_id      TEXT,
                job_id          TEXT,
                supplier        TEXT,
                invoice_number  TEXT,
                issue_date      TEXT,
                currency        TEXT,
                total_amount    REAL,
                status          TEXT NOT NULL DEFAULT 'confirmed',
                original_filename TEXT,
                created_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_inv_dup ON invoices(user_id, supplier, invoice_number);
            CREATE INDEX IF NOT EXISTS idx_inv_user ON invoices(user_id);

            CREATE TABLE IF NOT EXISTS audit_logs (
                id          TEXT PRIMARY KEY,
                user_id     TEXT REFERENCES users(id),
                action      TEXT NOT NULL,
                entity_type TEXT,
                entity_id   TEXT,
                details     TEXT,
                ip_address  TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_al_user ON audit_logs(user_id);

            CREATE TABLE IF NOT EXISTS api_keys (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL REFERENCES users(id),
                name        TEXT NOT NULL,
                key_hash    TEXT NOT NULL UNIQUE,
                is_active   INTEGER NOT NULL DEFAULT 1,
                last_used_at TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ak_hash ON api_keys(key_hash);
            CREATE INDEX IF NOT EXISTS idx_ak_user ON api_keys(user_id);
        """)
        await db.commit()

    # Migração: adiciona user_id a processing_history se já existia sem ela
    added = await _maybe_add_column("processing_history", "user_id", "TEXT")
    if added:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ph_user ON processing_history(user_id)"
            )
            await db.commit()


async def _maybe_add_column(table: str, column: str, col_type: str) -> bool:
    """Adiciona coluna se não existir. Retorna True se adicionou, False se já existia."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in await cursor.fetchall()]
        if column not in cols:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            await db.commit()
            logger.info("Coluna '%s' adicionada em '%s'", column, table)
            return True
        return False


# ── users ─────────────────────────────────────────────────────────────────────

async def create_user(user: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users
               (id, name, email, password_hash, role, is_active, created_at, updated_at, last_login)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"], user["name"], user["email"], user["password_hash"],
                user.get("role", "user"), user.get("is_active", 1),
                user["created_at"], user["updated_at"], user.get("last_login"),
            ),
        )
        await db.commit()


async def get_user_by_email(email: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_by_id(user_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_last_login(user_id: str, timestamp: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_login = ? WHERE id = ?", (timestamp, user_id)
        )
        await db.commit()


# ── refresh_tokens ────────────────────────────────────────────────────────────

async def create_refresh_token(record: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, revoked, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                record["id"], record["user_id"], record["token_hash"],
                record["expires_at"], record.get("revoked", 0), record["created_at"],
            ),
        )
        await db.commit()


async def get_valid_refresh_token(token_hash: str) -> Optional[dict]:
    """Retorna o registro se o token existe, não está revogado e não expirou."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM refresh_tokens
               WHERE token_hash = ? AND revoked = 0 AND expires_at > ?""",
            (token_hash, now),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def revoke_refresh_token(token_hash: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?", (token_hash,)
        )
        await db.commit()


async def revoke_all_user_tokens(user_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()


# ── processing_history ────────────────────────────────────────────────────────

async def save_history(entry: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO processing_history
               (id, session_id, user_id, processed_at, invoice_count,
                supplier_list, total_amount_brl, excel_filename, zip_filename, invoices_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["id"],
                entry["session_id"],
                entry.get("user_id"),
                entry["processed_at"],
                entry["invoice_count"],
                json.dumps(entry["supplier_list"]),
                entry.get("total_amount_brl"),
                entry["excel_filename"],
                entry["zip_filename"],
                json.dumps(entry["invoices_json"]),
            ),
        )
        await db.commit()


async def get_history(limit: int = 50, offset: int = 0, user_id: Optional[str] = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            cursor = await db.execute(
                """SELECT * FROM processing_history
                   WHERE user_id = ?
                   ORDER BY processed_at DESC LIMIT ? OFFSET ?""",
                (user_id, limit, offset),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM processing_history ORDER BY processed_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            entry = dict(row)
            entry["supplier_list"] = json.loads(entry["supplier_list"])
            entry["invoices_json"] = json.loads(entry["invoices_json"])
            result.append(entry)
        return result


async def delete_history_entry(entry_id: str, user_id: Optional[str] = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id:
            cursor = await db.execute(
                "DELETE FROM processing_history WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            )
        else:
            cursor = await db.execute(
                "DELETE FROM processing_history WHERE id = ?", (entry_id,)
            )
        await db.commit()
        return cursor.rowcount > 0


async def delete_all_history(user_id: Optional[str] = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id:
            cursor = await db.execute(
                "DELETE FROM processing_history WHERE user_id = ?", (user_id,)
            )
        else:
            cursor = await db.execute("DELETE FROM processing_history")
        await db.commit()
        return cursor.rowcount


# ── invoices (normalized) ─────────────────────────────────────────────────────

async def save_invoices_batch(invoices: list[dict]) -> None:
    """Persiste invoices na tabela normalizada para duplicate check indexado."""
    if not invoices:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO invoices
               (id, user_id, session_id, job_id, supplier, invoice_number,
                issue_date, currency, total_amount, status, original_filename, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    inv["id"], inv["user_id"], inv.get("session_id"),
                    inv.get("job_id"), inv.get("supplier"), inv.get("invoice_number"),
                    inv.get("issue_date"), inv.get("currency"), inv.get("total_amount"),
                    inv.get("status", "confirmed"), inv.get("original_filename"),
                    inv.get("created_at", datetime.now(timezone.utc).isoformat()),
                )
                for inv in invoices
            ],
        )
        await db.commit()


async def check_duplicate(supplier: str, invoice_number: str, user_id: str) -> bool:
    """
    Verifica duplicata por índice em colunas reais (sem LIKE em JSON).
    A comparação é case-insensitive e trimmed.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM invoices
               WHERE user_id = ?
                 AND LOWER(TRIM(supplier)) = LOWER(TRIM(?))
                 AND LOWER(TRIM(invoice_number)) = LOWER(TRIM(?))""",
            (user_id, supplier, invoice_number),
        )
        row = await cursor.fetchone()
        return row[0] > 0


# ── audit_logs ────────────────────────────────────────────────────────────────

async def log_action(
    action: str,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    import uuid
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO audit_logs
               (id, user_id, action, entity_type, entity_id, details, ip_address, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), user_id, action, entity_type, entity_id,
                json.dumps(details) if details else None,
                ip_address,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db.commit()


# ── api_keys ──────────────────────────────────────────────────────────────────

async def create_api_key(record: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO api_keys (id, user_id, name, key_hash, is_active, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (record["id"], record["user_id"], record["name"], record["key_hash"], record["created_at"]),
        )
        await db.commit()


async def get_api_key_by_hash(key_hash: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1",
            (key_hash,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_api_keys(user_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, is_active, last_used_at, created_at FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def revoke_api_key(key_id: str, user_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ? AND user_id = ?",
            (key_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def touch_api_key(key_hash: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE key_hash = ?",
            (datetime.now(timezone.utc).isoformat(), key_hash),
        )
        await db.commit()
