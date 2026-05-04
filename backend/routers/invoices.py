# Roteador principal de invoices — expõe os três endpoints do fluxo de processamento:
#   POST /upload   → recebe PDFs/imagens, roda OCR e extrai campos, devolve NFs para revisão
#   POST /confirm  → recebe NFs revisadas, gera Excel + ZIP e salva no histórico
#   GET  /download/{job_id} → devolve o ZIP gerado para download
# Prefixo /api/invoices registrado em main.py.

from __future__ import annotations
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from db.database import check_duplicate, save_history
from models.invoice import ConfirmRequest, ConfirmResponse, InvoiceData, UploadResponse
from services.excel_service import generate_excel
from services.extractor_service import extract_all
from services.file_service import create_zip, organize_invoices
from services.ocr_service import extract_invoice_data

logger = logging.getLogger(__name__)
router = APIRouter()

# Diretório base onde os arquivos temporários de cada sessão ficam salvos.
# Pode ser sobrescrito via variável de ambiente TEMP_STORAGE_PATH.
TEMP_BASE = Path(os.getenv("TEMP_STORAGE_PATH", tempfile.gettempdir())) / "invoice_sessions"

# Formatos de arquivo aceitos no upload
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# Limite de tamanho por arquivo (20 MB em bytes)
MAX_FILE_SIZE = 20 * 1024 * 1024

# Dicionário em memória que mapeia session_id → dados da sessão (diretório de uploads e NFs processadas).
# Fica em RAM enquanto o servidor está rodando; reiniciar o servidor apaga as sessões.
_sessions: Dict[str, dict] = {}


def _session_dir(session_id: str) -> Path:
    """Retorna o caminho do diretório temporário de uma sessão específica."""
    return TEMP_BASE / session_id


# ─── POST /upload ──────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_invoices(files: List[UploadFile] = File(...)):
    """
    Recebe um ou mais arquivos (PDF/imagem), processa cada um com OCR e extração de campos,
    e devolve as NFs estruturadas junto com uma session_id para uso posterior no /confirm.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    # Cria uma sessão única para este lote de uploads
    session_id = str(uuid.uuid4())
    session_dir = _session_dir(session_id)
    uploads_dir = session_dir / "uploads"

    errors: List[str] = []    # arquivos que falharam (formato inválido, tamanho, erro no OCR)
    invoices: List[InvoiceData] = []

    for upload in files:
        # Valida a extensão do arquivo
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"{upload.filename}: formato não suportado ({ext}).")
            continue

        # Lê o conteúdo e valida o tamanho
        content = await upload.read()
        if len(content) > MAX_FILE_SIZE:
            errors.append(f"{upload.filename}: arquivo muito grande (máx 20 MB).")
            continue

        # Salva o arquivo original em: uploads/<invoice_id>/<nome_original>
        # Cada NF fica em seu próprio subdiretório para facilitar a organização posterior
        invoice_id = str(uuid.uuid4())
        file_dir = uploads_dir / invoice_id
        file_dir.mkdir(parents=True, exist_ok=True)
        (file_dir / upload.filename).write_bytes(content)

        # Executa OCR + extração de campos, medindo o tempo de processamento
        t0 = time.time()
        try:
            # Gemini retorna text + campos já estruturados (preextracted != None)
            # Demais provedores retornam apenas text e usam extractor_service para parsing
            text, method, preextracted = extract_invoice_data(content, upload.filename)
            extracted = preextracted or extract_all(text)
        except Exception as e:
            logger.exception("OCR failed for %s", upload.filename)
            errors.append(f"{upload.filename}: falha no OCR — {e}")
            continue
        elapsed = time.time() - t0

        data = extracted["data"]           # dict com os campos extraídos (supplier, total_amount, etc.)
        confidence = extracted["confidence"]  # dict campo→float com o score de confiança do OCR

        # Verifica se essa NF já foi processada antes (mesmo fornecedor + número)
        is_dup = False
        if data.get("invoice_number") and data.get("supplier"):
            is_dup = await check_duplicate(data["supplier"], data["invoice_number"])

        # Monta o objeto InvoiceData que será enviado ao frontend para revisão
        inv = InvoiceData(
            id=invoice_id,
            original_filename=upload.filename,
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

    # Persiste a sessão em memória para ser acessada posteriormente no /confirm
    _sessions[session_id] = {
        "uploads_dir": str(uploads_dir),
        "invoices": {inv.id: inv for inv in invoices},  # indexado por ID para busca rápida
    }

    return UploadResponse(
        session_id=session_id,
        invoices=invoices,
        processing_errors=errors,
    )


# ─── POST /confirm ─────────────────────────────────────────────────────────────

@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_invoices(body: ConfirmRequest):
    """
    Recebe a lista de NFs revisadas pelo usuário (com status confirmed/skipped e eventuais edições),
    filtra as NFs confirmadas, gera o Excel e o ZIP e salva o lote no histórico.
    """
    # Verifica se a sessão ainda existe em memória (pode ter expirado se o servidor reiniciou)
    session = _sessions.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada ou expirada.")

    # Descarta as NFs que o usuário marcou como "ignoradas"
    invoices = [inv for inv in body.invoices if inv.status != "skipped"]
    if not invoices:
        raise HTTPException(status_code=400, detail="Nenhuma invoice confirmada.")

    # Valida que todas as NFs confirmadas têm os campos obrigatórios preenchidos
    _required = ("supplier", "invoice_number", "issue_date", "total_amount", "currency")
    for inv in invoices:
        missing = [f for f in _required if not getattr(inv, f, None)]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Invoice '{inv.original_filename}': campos obrigatórios ausentes: {', '.join(missing)}",
            )

    # Prepara a estrutura de diretórios de saída da sessão
    job_id = str(uuid.uuid4())
    session_dir = _session_dir(body.session_id)
    output_dir = session_dir / "output"
    organized_dir = output_dir / "organized"  # PDFs renomeados e organizados em pastas por Ano/Mês/Fornecedor
    excel_dir = output_dir / "excel"          # arquivo .xlsx gerado

    excel_dir.mkdir(parents=True, exist_ok=True)
    organized_dir.mkdir(parents=True, exist_ok=True)

    # Nomeia os arquivos de saída com timestamp para evitar colisões
    date_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"Invoices_{date_tag}.xlsx"
    zip_filename = f"Pacote_Invoices_{date_tag}.zip"

    excel_path = str(excel_dir / excel_filename)
    zip_path = str(output_dir / zip_filename)

    try:
        # 1. Gera a planilha Excel com todas as NFs confirmadas
        generate_excel(invoices, excel_path)
        # 2. Copia e renomeia os PDFs originais na estrutura de pastas Ano/Mês/Fornecedor
        organize_invoices(invoices, session["uploads_dir"], str(organized_dir))
        # 3. Compacta tudo (Excel + PDFs organizados) em um único ZIP
        create_zip(str(organized_dir), excel_path, zip_path)
    except Exception as e:
        logger.exception("Package generation failed")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar pacote: {e}")

    # Atualiza a sessão em memória com os dados do pacote gerado (necessários no /download)
    _sessions[body.session_id]["job_id"] = job_id
    _sessions[body.session_id]["zip_path"] = zip_path
    _sessions[body.session_id]["excel_filename"] = excel_filename
    _sessions[body.session_id]["zip_filename"] = zip_filename

    # Salva o lote no banco SQLite para consulta futura no histórico
    await save_history(
        {
            "id": job_id,
            "session_id": body.session_id,
            "processed_at": datetime.now().isoformat(),
            "invoice_count": len(invoices),
            "supplier_list": list({inv.supplier or "—" for inv in invoices}),  # set para evitar duplicatas
            "total_amount_brl": sum(
                inv.converted_amount or 0
                for inv in invoices
                if inv.converted_amount
            ) or None,  # None se nenhuma NF tiver valor convertido
            "excel_filename": excel_filename,
            "zip_filename": zip_filename,
            "invoices_json": [inv.model_dump() for inv in invoices],  # serializa os objetos para JSON
        }
    )

    return ConfirmResponse(
        job_id=job_id,
        download_url=f"/api/invoices/download/{job_id}",
        excel_filename=excel_filename,
        zip_filename=zip_filename,
        invoice_count=len(invoices),
    )


# ─── GET /download/{job_id} ────────────────────────────────────────────────────

@router.get("/download/{job_id}")
async def download_package(job_id: str):
    """
    Devolve o arquivo ZIP gerado como download.
    Busca a sessão pelo job_id e serve o arquivo do sistema de arquivos temporário.
    """
    # Procura qual sessão gerou esse job_id (busca linear no dict em memória)
    session = next(
        (s for s in _sessions.values() if s.get("job_id") == job_id), None
    )
    if not session:
        raise HTTPException(status_code=404, detail="Pacote não encontrado.")

    zip_path = session.get("zip_path")
    if not zip_path or not Path(zip_path).exists():
        raise HTTPException(status_code=404, detail="Arquivo ZIP não encontrado.")

    # FileResponse transmite o arquivo em streaming com o Content-Disposition correto para download
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=session["zip_filename"],
    )