# Roteador de histórico — expõe endpoints para listar e excluir registros de processamentos anteriores.
# Prefixo /api/history registrado em main.py.

from fastapi import APIRouter, HTTPException, Query
from db.database import delete_all_history, delete_history_entry, get_history

router = APIRouter()


# GET /api/history/?limit=50&offset=0
# Retorna uma página de registros ordenados do mais recente para o mais antigo.
# limit e offset permitem paginação (ge/le validam limites aceitáveis).
@router.get("/")
async def list_history(
    limit: int = Query(default=50, ge=1, le=200),   # mínimo 1, máximo 200 por página
    offset: int = Query(default=0, ge=0),           # deslocamento (0 = começa do início)
):
    entries = await get_history(limit=limit, offset=offset)
    # Retorna total como len(entries) — útil para o frontend saber se há mais páginas
    return {"entries": entries, "total": len(entries)}


# DELETE /api/history/all
# Apaga todos os registros do histórico. Ação irreversível.
# Retorna quantos registros foram deletados.
@router.delete("/all")
async def clear_history():
    deleted = await delete_all_history()
    return {"deleted": deleted}


# DELETE /api/history/{entry_id}
# Apaga um único registro pelo seu ID.
# Retorna 404 se o ID não for encontrado no banco.
@router.delete("/{entry_id}")
async def remove_history_entry(entry_id: str):
    found = await delete_history_entry(entry_id)
    if not found:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    return {"deleted": entry_id}