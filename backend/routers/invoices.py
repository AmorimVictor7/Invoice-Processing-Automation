"""
Roteador principal de invoices — expõe os três endpoints do fluxo de processamento.

Segurança:
  - Autenticação JWT obrigatória em todos os endpoints (Depends(get_current_user))
  - Validação de MIME type via magic bytes (filetype)
  - Nome de arquivo sanitizado (Path.name) para evitar path traversal
  - Tamanho lido com limite antes de carregar tudo em RAM
  - OCR executado em thread pool (run_in_executor) — não bloqueia o event loop

Sessões:
  - Gerenciadas pelo SessionService (Redis ou memória com fallback)
  - Isoladas por user_id — usuário acessa apenas suas próprias sessões
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import filetype
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from db.database import check_duplicate, log_action, save_history, save_invoices_batch
from deps.auth import get_current_user
from limiter import limiter
from models.invoice import ConfirmRequest, ConfirmResponse, InvoiceData, UploadResponse
from services.excel_service import generate_excel
from services.extractor_service import extract_all
from services.file_service import create_zip, organize_invoices
from services.ocr_service import extract_invoice_data
from services.session_service import SessionState, session_service

logger = logging.getLogger(__name__)
router = APIRouter()

TEMP_BASE = Path(os.getenv("TEMP_STORAGE_PATH", tempfile.gettempdir())) / "invoice_sessions"
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
ALLOWED_MIMES = {"application/pdf", "image/png", "image/jpeg"}
MAX_FILE_SIZE = 20 * 1024 * 1024   # 20 MB
MAX_FILES_PER_BATCH = 50


def _session_dir(session_id: str) -> Path:
    return TEMP_BASE / session_id


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    return fwd.split(",")[0].strip() if fwd else (request.client.host or "unknown")


# ── POST /upload ──────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
@limiter.limit("20/minute")
async def upload_invoices(
    request: Request,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Recebe arquivos (PDF/imagem), valida, executa OCR em thread pool e retorna NFs estruturadas.
    Cria uma sessão isolada por usuário no SessionService.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {MAX_FILES_PER_BATCH} arquivos por envio.",
        )

    session_id = str(uuid.uuid4())
    uploads_dir = _session_dir(session_id) / "uploads"

    errors: List[str] = []
    invoices: List[InvoiceData] = []
    loop = asyncio.get_event_loop()

    for upload in files:
        # ── Validação de extensão ───────────────────────────────────────────
        safe_name = Path(upload.filename or "file").name   # path traversal fix
        ext = Path(safe_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"{safe_name}: formato não suportado ({ext}).")
            continue

        # ── Leitura com limite (evita carregar arquivo gigante em RAM) ──────
        content = await upload.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            errors.append(f"{safe_name}: arquivo muito grande (máx 20 MB).")
            continue

        # ── Validação de MIME type por magic bytes ──────────────────────────
        kind = filetype.guess(content[:512])
        if kind is None or kind.mime not in ALLOWED_MIMES:
            detected = kind.mime if kind else "desconhecido"
            errors.append(f"{safe_name}: tipo de arquivo inválido ({detected}).")
            continue

        # ── Persistência do arquivo original ───────────────────────────────
        invoice_id = str(uuid.uuid4())
        file_dir = uploads_dir / invoice_id
        file_dir.mkdir(parents=True, exist_ok=True)
        (file_dir / safe_name).write_bytes(content)

        # ── OCR em thread pool (não bloqueia event loop) ────────────────────
        t0 = time.time()
        try:
            text, method, preextracted = await loop.run_in_executor(
                None, extract_invoice_data, content, safe_name
            )
            extracted = preextracted or await loop.run_in_executor(None, extract_all, text)
        except Exception as exc:
            logger.exception("OCR falhou para %s", safe_name)
            err_str = str(exc)
            if any(k in err_str for k in ("429", "quota", "RESOURCE_EXHAUSTED")):
                msg = "Cota da API Gemini esgotada. Tente mais tarde ou use outro provider."
            elif "circuit" in err_str.lower():
                msg = "Serviço OCR temporariamente indisponível (muitas falhas). Usando fallback."
            else:
                msg = f"falha no OCR — {exc}"
            errors.append(f"{safe_name}: {msg}")
            continue

        elapsed = time.time() - t0
        data = extracted["data"]
        confidence = extracted["confidence"]

        # ── Verificação de duplicata por índice normalizado ─────────────────
        is_dup = False
        if data.get("invoice_number") and data.get("supplier"):
            is_dup = await check_duplicate(
                data["supplier"], data["invoice_number"], current_user["id"]
            )

        inv = InvoiceData(
            id=invoice_id,
            original_filename=safe_name,
            supplier=data.get("supplier"),
            invoice_number=data.get("invoice_number"),
            issue_date=data.get("issue_date"),
            billing_period=data.get("billing_period"),
            description=data.get("description"),
            currency=data.get("currency"),
            subtotal=data.get("subtotal"),
            taxes=data.get("taxes"),
            total_amount=data.get("total_amount"),
            confidence=confidence,
            ocr_method=method,
            processing_time=round(elapsed, 2),
            is_duplicate=is_dup,
        )
        invoices.append(inv)

    # ── Persiste sessão no SessionService ───────────────────────────────────
    await session_service.create(session_id, {
        "session_id": session_id,
        "user_id": current_user["id"],
        "uploads_dir": str(uploads_dir),
        "status": SessionState.REVIEW_PENDING,
        "invoices": {inv.id: inv.model_dump() for inv in invoices},
    })

    await log_action(
        "upload",
        user_id=current_user["id"],
        entity_type="session",
        entity_id=session_id,
        details={"file_count": len(files), "success": len(invoices), "errors": len(errors)},
        ip_address=_client_ip(request),
    )

    return UploadResponse(
        session_id=session_id,
        invoices=invoices,
        processing_errors=errors,
    )


# ── POST /confirm ─────────────────────────────────────────────────────────────

@router.post("/confirm", response_model=ConfirmResponse)
@limiter.limit("30/minute")
async def confirm_invoices(
    request: Request,
    body: ConfirmRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Recebe NFs revisadas, valida campos obrigatórios, gera Excel + ZIP e salva no histórico.
    Só permite confirmação de sessões pertencentes ao usuário autenticado.
    """
    session = await session_service.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada ou expirada.")

    # Isolamento: usuário só acessa suas próprias sessões
    if session.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Acesso negado a esta sessão.")

    # Impede múltiplos confirms na mesma sessão
    if session.get("status") in (SessionState.CONFIRMED, SessionState.EXPORTED):
        raise HTTPException(status_code=409, detail="Esta sessão já foi confirmada.")

    invoices = [inv for inv in body.invoices if inv.status != "skipped"]
    if not invoices:
        raise HTTPException(status_code=400, detail="Nenhuma invoice confirmada.")

    _required = ("supplier", "invoice_number", "issue_date", "total_amount", "currency")
    for inv in invoices:
        missing = [f for f in _required if not getattr(inv, f, None)]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Invoice '{inv.original_filename}': campos obrigatórios ausentes: {', '.join(missing)}",
            )

    await session_service.set_state(body.session_id, SessionState.CONFIRMED)

    job_id = str(uuid.uuid4())
    session_dir = _session_dir(body.session_id)
    output_dir = session_dir / "output"
    organized_dir = output_dir / "organized"
    excel_dir = output_dir / "excel"

    excel_dir.mkdir(parents=True, exist_ok=True)
    organized_dir.mkdir(parents=True, exist_ok=True)

    date_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"Invoices_{date_tag}.xlsx"
    zip_filename = f"Pacote_Invoices_{date_tag}.zip"
    excel_path = str(excel_dir / excel_filename)
    zip_path = str(output_dir / zip_filename)

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, generate_excel, invoices, excel_path)
        await loop.run_in_executor(
            None, organize_invoices, invoices, session["uploads_dir"], str(organized_dir)
        )
        await loop.run_in_executor(None, create_zip, str(organized_dir), excel_path, zip_path)
    except Exception as exc:
        logger.exception("Falha na geração do pacote para sessão %s", body.session_id)
        await session_service.set_state(body.session_id, SessionState.FAILED)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar pacote: {exc}")

    # Atualiza sessão e registra índice job_id → session_id
    session.update({
        "job_id": job_id,
        "zip_path": zip_path,
        "excel_filename": excel_filename,
        "zip_filename": zip_filename,
        "status": SessionState.EXPORTED,
    })
    await session_service.update(body.session_id, session)
    await session_service.register_job(job_id, body.session_id)

    now = datetime.now(timezone.utc).isoformat()

    # Persiste no histórico
    await save_history({
        "id": job_id,
        "session_id": body.session_id,
        "user_id": current_user["id"],
        "processed_at": now,
        "invoice_count": len(invoices),
        "supplier_list": list({inv.supplier or "—" for inv in invoices}),
        "total_amount_brl": sum(
            inv.converted_amount or 0 for inv in invoices if inv.converted_amount
        ) or None,
        "excel_filename": excel_filename,
        "zip_filename": zip_filename,
        "invoices_json": [inv.model_dump() for inv in invoices],
    })

    # Persiste invoices normalizadas para duplicate check indexado
    await save_invoices_batch([
        {
            "id": inv.id,
            "user_id": current_user["id"],
            "session_id": body.session_id,
            "job_id": job_id,
            "supplier": inv.supplier,
            "invoice_number": inv.invoice_number,
            "issue_date": inv.issue_date,
            "currency": inv.currency,
            "total_amount": inv.total_amount,
            "status": "confirmed",
            "original_filename": inv.original_filename,
            "created_at": now,
        }
        for inv in invoices
    ])

    await log_action(
        "confirm",
        user_id=current_user["id"],
        entity_type="session",
        entity_id=body.session_id,
        details={"job_id": job_id, "invoice_count": len(invoices)},
        ip_address=_client_ip(request),
    )

    return ConfirmResponse(
        job_id=job_id,
        download_url=f"/api/invoices/download/{job_id}",
        excel_filename=excel_filename,
        zip_filename=zip_filename,
        invoice_count=len(invoices),
    )


# ── GET /download/{job_id} ────────────────────────────────────────────────────

@router.get("/download/{job_id}")
async def download_package(
    job_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Download do ZIP gerado. Verificação O(1) via índice job→session no SessionService.
    Garante que o usuário só baixa seus próprios pacotes.
    """
    session = await session_service.get_by_job_id(job_id)
    if not session:
        raise HTTPException(status_code=404, detail="Pacote não encontrado.")

    if session.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Acesso negado a este pacote.")

    zip_path = session.get("zip_path")
    if not zip_path or not Path(zip_path).exists():
        raise HTTPException(status_code=404, detail="Arquivo ZIP não encontrado.")

    await log_action(
        "download",
        user_id=current_user["id"],
        entity_type="job",
        entity_id=job_id,
        ip_address=_client_ip(request),
    )

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=session["zip_filename"],
    )
