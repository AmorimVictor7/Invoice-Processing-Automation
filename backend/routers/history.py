# Roteador de histórico — expõe endpoints para listar e excluir registros de processamentos anteriores.
# Prefixo /api/history registrado em main.py.

from fastapi import APIRouter, HTTPException, Query
from db.database import delete_all_history, delete_history_entry, get_history

router = APIRouter()


@router.get(
    "/",
    responses={
        200: {"description": "Lista paginada de lotes processados, ordenada do mais recente para o mais antigo."},
    },
)
async def list_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    Retorna uma página de registros ordenados do mais recente para o mais antigo.
    `limit` e `offset` permitem paginação (mínimo 1, máximo 200 por página).

    **Cenários testados**

    | Cenário | Status | Teste |
    |---|---|---|
    | Histórico vazio | `200` (`entries: []`, `total: 0`) | `test_list_history_empty` |
    | Histórico após fluxo completo | `200` (entrada com dados do lote confirmado) | `test_fluxo_completo_popula_historico` |
    """
    entries = await get_history(limit=limit, offset=offset)
    # Retorna total como len(entries) — útil para o frontend saber se há mais páginas
    return {"entries": entries, "total": len(entries)}


@router.delete(
    "/all",
    responses={
        200: {"description": "Histórico limpo. Retorna `deleted` com a quantidade de registros removidos."},
    },
)
async def clear_history():
    """
    Apaga **todos** os registros do histórico. Ação irreversível.

    **Cenários testados**

    | Cenário | Status | Teste |
    |---|---|---|
    | Limpar histórico vazio | `200` (`deleted: 0`) | `test_delete_all_empty` |
    """
    deleted = await delete_all_history()
    return {"deleted": deleted}


@router.delete(
    "/{entry_id}",
    responses={
        200: {"description": "Registro removido. Retorna o `deleted` com o ID excluído."},
        404: {"description": "Registro não encontrado no banco."},
    },
)
async def remove_history_entry(entry_id: str):
    """
    Apaga um único registro pelo seu ID.

    **Cenários testados**

    | Cenário | Status | Teste |
    |---|---|---|
    | ID inexistente | `404` | `test_delete_entry_not_found` |
    """
    found = await delete_history_entry(entry_id)
    if not found:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    return {"deleted": entry_id}