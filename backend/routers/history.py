"""
Roteador de histórico — lista e exclui registros de processamentos anteriores.
Todos os endpoints exigem autenticação; cada usuário acessa apenas seu próprio histórico.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from db.database import delete_all_history, delete_history_entry, get_history, log_action
from deps.auth import get_current_user
from limiter import limiter

router = APIRouter()


@router.get("/")
@limiter.limit("60/minute")
async def list_history(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Retorna histórico paginado do usuário autenticado, do mais recente para o mais antigo."""
    entries = await get_history(limit=limit, offset=offset, user_id=current_user["id"])
    return {"entries": entries, "total": len(entries)}


@router.delete("/all")
@limiter.limit("5/minute")
async def clear_history(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Remove todos os registros do usuário autenticado. Ação irreversível."""
    deleted = await delete_all_history(user_id=current_user["id"])
    await log_action(
        "delete_all_history",
        user_id=current_user["id"],
        entity_type="history",
        details={"deleted_count": deleted},
    )
    return {"deleted": deleted}


@router.delete("/{entry_id}")
@limiter.limit("30/minute")
async def remove_history_entry(
    request: Request,
    entry_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove um único registro do histórico. Garante que pertence ao usuário autenticado."""
    found = await delete_history_entry(entry_id, user_id=current_user["id"])
    if not found:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    await log_action(
        "delete_history_entry",
        user_id=current_user["id"],
        entity_type="history",
        entity_id=entry_id,
    )
    return {"deleted": entry_id}
