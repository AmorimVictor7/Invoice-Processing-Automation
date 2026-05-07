import zipfile
from pathlib import Path


# ─── helpers ──────────────────────────────────────────────────────────────────

def _patch_file_services(monkeypatch):
    """Substitui os serviços de geração de arquivos por versões que não fazem I/O real."""
    import routers.invoices as inv

    monkeypatch.setattr(inv, "generate_excel", lambda invoices, path: Path(path).touch())
    monkeypatch.setattr(inv, "organize_invoices", lambda *a, **kw: None)

    def _fake_zip(organized_dir, excel_path, zip_path):
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("dummy.txt", "test content")

    monkeypatch.setattr(inv, "create_zip", _fake_zip)


async def _do_upload(client, monkeypatch, minimal_pdf, fake_ocr):
    """Faz upload de uma NF com OCR mockado. Retorna (session_id, invoice_dict)."""
    import routers.invoices as inv

    monkeypatch.setattr(inv, "extract_invoice_data", lambda content, fname: fake_ocr)

    r = await client.post(
        "/api/invoices/upload",
        files=[("files", ("invoice.pdf", minimal_pdf, "application/pdf"))],
    )
    assert r.status_code == 200
    data = r.json()
    return data["session_id"], data["invoices"][0]


# ─── upload ───────────────────────────────────────────────────────────────────

async def test_upload_formato_nao_suportado(client, minimal_pdf):
    r = await client.post(
        "/api/invoices/upload",
        files=[("files", ("documento.txt", b"hello", "text/plain"))],
    )
    assert r.status_code == 200
    data = r.json()
    assert data["invoices"] == []
    assert any("formato não suportado" in e for e in data["processing_errors"])


async def test_upload_sucesso(client, monkeypatch, minimal_pdf, fake_ocr):
    session_id, invoice = await _do_upload(client, monkeypatch, minimal_pdf, fake_ocr)

    assert session_id
    assert invoice["supplier"] == "ACME Corp"
    assert invoice["invoice_number"] == "INV-2024-001"
    assert invoice["total_amount"] == 1000.0
    assert invoice["currency"] == "USD"
    assert invoice["status"] == "pending"
    assert invoice["is_duplicate"] is False


# ─── confirm ──────────────────────────────────────────────────────────────────

async def test_confirm_sessao_nao_encontrada(client):
    r = await client.post(
        "/api/invoices/confirm",
        json={"session_id": "sessao-inexistente", "invoices": []},
    )
    assert r.status_code == 404


async def test_confirm_todas_ignoradas(client, monkeypatch, minimal_pdf, fake_ocr):
    session_id, invoice = await _do_upload(client, monkeypatch, minimal_pdf, fake_ocr)
    invoice["status"] = "skipped"

    r = await client.post(
        "/api/invoices/confirm",
        json={"session_id": session_id, "invoices": [invoice]},
    )
    assert r.status_code == 400


async def test_confirm_campo_obrigatorio_ausente(client, monkeypatch, minimal_pdf, fake_ocr):
    session_id, invoice = await _do_upload(client, monkeypatch, minimal_pdf, fake_ocr)
    invoice["status"] = "confirmed"
    invoice["supplier"] = None  # campo obrigatório removido

    r = await client.post(
        "/api/invoices/confirm",
        json={"session_id": session_id, "invoices": [invoice]},
    )
    assert r.status_code == 422


# ─── fluxo completo: upload → confirm → download ──────────────────────────────

async def test_fluxo_completo(client, monkeypatch, minimal_pdf, fake_ocr):
    _patch_file_services(monkeypatch)
    session_id, invoice = await _do_upload(client, monkeypatch, minimal_pdf, fake_ocr)

    invoice["status"] = "confirmed"
    r = await client.post(
        "/api/invoices/confirm",
        json={"session_id": session_id, "invoices": [invoice]},
    )
    assert r.status_code == 200
    confirm = r.json()
    assert "job_id" in confirm
    assert confirm["invoice_count"] == 1
    assert confirm["download_url"] == f"/api/invoices/download/{confirm['job_id']}"

    r = await client.get(f"/api/invoices/download/{confirm['job_id']}")
    assert r.status_code == 200
    assert "application/zip" in r.headers["content-type"]


async def test_fluxo_completo_popula_historico(client, monkeypatch, minimal_pdf, fake_ocr):
    _patch_file_services(monkeypatch)
    session_id, invoice = await _do_upload(client, monkeypatch, minimal_pdf, fake_ocr)

    invoice["status"] = "confirmed"
    await client.post(
        "/api/invoices/confirm",
        json={"session_id": session_id, "invoices": [invoice]},
    )

    r = await client.get("/api/history/")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["entries"][0]["invoice_count"] == 1
    assert "ACME Corp" in data["entries"][0]["supplier_list"]


# ─── download ─────────────────────────────────────────────────────────────────

async def test_download_nao_encontrado(client):
    r = await client.get("/api/invoices/download/job-inexistente")
    assert r.status_code == 404
