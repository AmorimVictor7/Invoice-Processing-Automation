# Camada de acesso ao banco de dados SQLite.
# Todas as funções são assíncronas (aiosqlite) para não bloquear o loop de eventos do FastAPI.
# O banco armazena o histórico de lotes processados, incluindo o JSON completo das NFs.

import aiosqlite
import json
from pathlib import Path

# Caminho do arquivo .db na raiz do backend (invoice_history.db)
DB_PATH = Path(__file__).parent.parent / "invoice_history.db"


# Cria a tabela processing_history se ela ainda não existir.
# Chamado uma vez na inicialização do servidor (lifespan em main.py).
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS processing_history (
                id TEXT PRIMARY KEY,            -- job_id gerado no /confirm
                session_id TEXT NOT NULL,       -- ID da sessão de upload relacionada
                processed_at TEXT NOT NULL,     -- ISO 8601 de quando o pacote foi gerado
                invoice_count INTEGER NOT NULL, -- Quantidade de NFs no pacote
                supplier_list TEXT NOT NULL,    -- JSON array de strings com nomes dos fornecedores
                total_amount_brl REAL,          -- Soma em BRL (pode ser NULL se não houver conversão)
                excel_filename TEXT NOT NULL,   -- Nome do arquivo Excel gerado
                zip_filename TEXT NOT NULL,     -- Nome do arquivo ZIP gerado
                invoices_json TEXT NOT NULL     -- JSON completo de todas as NFs confirmadas
            )
        """)
        await db.commit()


# Salva um registro no histórico após o usuário confirmar o lote.
# supplier_list e invoices_json são serializados como JSON porque SQLite não tem tipo array/object nativo.
async def save_history(entry: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO processing_history
               (id, session_id, processed_at, invoice_count, supplier_list,
                total_amount_brl, excel_filename, zip_filename, invoices_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["id"],
                entry["session_id"],
                entry["processed_at"],
                entry["invoice_count"],
                json.dumps(entry["supplier_list"]),   # lista → string JSON
                entry.get("total_amount_brl"),
                entry["excel_filename"],
                entry["zip_filename"],
                json.dumps(entry["invoices_json"]),   # lista de dicts → string JSON
            ),
        )
        await db.commit()


# Lista os registros mais recentes com paginação (limit/offset).
# Desserializa supplier_list e invoices_json de volta para objetos Python antes de retornar.
async def get_history(limit: int = 50, offset: int = 0) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        # Row factory permite acessar colunas pelo nome (row["id"]) em vez de índice (row[0])
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM processing_history ORDER BY processed_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            entry = dict(row)
            entry["supplier_list"] = json.loads(entry["supplier_list"])   # string JSON → lista
            entry["invoices_json"] = json.loads(entry["invoices_json"])   # string JSON → lista de dicts
            result.append(entry)
        return result


# Remove um único registro pelo seu ID.
# Retorna True se encontrou e deletou, False se o ID não existia.
async def delete_history_entry(entry_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM processing_history WHERE id = ?", (entry_id,)
        )
        await db.commit()
        return cursor.rowcount > 0  # rowcount = 0 se nenhuma linha foi afetada


# Remove todos os registros da tabela de uma vez.
# Retorna o número de registros deletados.
async def delete_all_history() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM processing_history")
        await db.commit()
        return cursor.rowcount


# Verifica se já existe uma NF com o mesmo fornecedor + número de invoice no histórico.
# Usado para marcar NFs duplicadas antes de exibi-las ao usuário na tela de revisão.
# A busca é feita com LIKE no JSON serializado — funciona para maioria dos casos mas pode ter falsos positivos
# se o valor de uma NF contiver a substring de outra (limitação do LIKE no JSON).
async def check_duplicate(supplier: str, invoice_number: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM processing_history
               WHERE invoices_json LIKE ? AND invoices_json LIKE ?""",
            (
                f'%"invoice_number": "{invoice_number}"%',
                f'%"supplier": "{supplier}"%',
            ),
        )
        row = await cursor.fetchone()
        return row[0] > 0  # True = já processada antes (possível duplicata)