# Serviço de organização e compactação dos arquivos de NF.
# Responsável por:
#   1. Renomear os PDFs originais com o padrão FORNECEDOR_NUMINVOICE_DATA_VALOR.ext
#   2. Organizar em uma hierarquia de pastas: Ano / Mês / Fornecedor
#   3. Compactar tudo (PDFs organizados + Excel) em um único arquivo ZIP

from __future__ import annotations
import os
import shutil
import zipfile
from pathlib import Path
from typing import List, Tuple

from models.invoice import InvoiceData

# Mapeamento de número do mês → nome da pasta (prefixo numérico garante ordenação correta no Explorer)
MONTH_NAMES_PT = {
    1: "01_Janeiro", 2: "02_Fevereiro", 3: "03_Março",
    4: "04_Abril", 5: "05_Maio", 6: "06_Junho",
    7: "07_Julho", 8: "08_Agosto", 9: "09_Setembro",
    10: "10_Outubro", 11: "11_Novembro", 12: "12_Dezembro",
}


def _safe_name(s: str) -> str:
    """Substitui caracteres inválidos em nomes de arquivo/pasta por underscore."""
    for ch in r'\/:*?"<>|':
        s = s.replace(ch, "_")
    return s.strip().strip(".")


def build_renamed_filename(inv: InvoiceData) -> str:
    """
    Constrói o nome padronizado do arquivo da NF.
    Formato: FORNECEDOR_NUMINVOICE_AAAAMMDD_VALORMoeda.ext
    Ex: GOOGLE_INV-001_20240315_250USD.pdf
    Valores ausentes são substituídos por placeholders (DESCONHECIDO, SEM_NUM, SEM_DATA).
    """
    supplier = _safe_name((inv.supplier or "DESCONHECIDO").upper().replace(" ", "_"))
    number = _safe_name((inv.invoice_number or "SEM_NUM").upper().replace(" ", "_"))
    date = (inv.issue_date or "SEM_DATA").replace("-", "")  # YYYYMMDD sem hífens
    amount = ""
    if inv.total_amount is not None:
        amount = f"_{inv.total_amount:.0f}{inv.currency or ''}"
    ext = Path(inv.original_filename).suffix.lower() or ".pdf"
    return f"{supplier}_{number}_{date}{amount}{ext}"


def _parse_date_parts(issue_date: str) -> Tuple[str, int]:
    """
    Extrai ano e mês de uma data no formato YYYY-MM-DD.
    Fallback para ano/mês atual se a data estiver ausente ou mal formatada.
    """
    try:
        parts = issue_date.split("-")
        return parts[0], int(parts[1])
    except Exception:
        from datetime import datetime
        now = datetime.now()
        return str(now.year), now.month


def organize_invoices(
    invoices: List[InvoiceData],
    uploads_dir: str,
    output_dir: str,
) -> List[Tuple[InvoiceData, str]]:
    """
    Copia os arquivos originais de cada NF para a estrutura de pastas:
      output_dir / Ano / MêsNome / FORNECEDOR / FORNECEDOR_NUM_DATA_VALOR.ext

    Exemplo:
      organized/2024/03_Março/GOOGLE/GOOGLE_INV-001_20240315_250USD.pdf

    Ignora silenciosamente NFs cujo arquivo original não for encontrado no uploads_dir.
    Retorna lista de (invoice, caminho_destino) para cada arquivo copiado com sucesso.
    """
    results = []
    for inv in invoices:
        # Caminho do arquivo original: uploads/<invoice_id>/<nome_original>
        src = Path(uploads_dir) / inv.id / inv.original_filename
        if not src.exists():
            continue  # arquivo pode ter sido deletado ou a sessão está inconsistente

        year, month = _parse_date_parts(inv.issue_date or "")
        month_folder = MONTH_NAMES_PT.get(month, f"{month:02d}")  # fallback para "MM" se mês inválido
        supplier_folder = _safe_name((inv.supplier or "DESCONHECIDO").replace(" ", "_").upper())

        # Cria a hierarquia completa de pastas (mkdir -p equivalente)
        dest_dir = Path(output_dir) / year / month_folder / supplier_folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        new_name = build_renamed_filename(inv)
        dest = dest_dir / new_name
        shutil.copy2(src, dest)  # copy2 preserva metadados (timestamps) do arquivo original
        results.append((inv, str(dest)))

    return results


def create_zip(output_dir: str, excel_path: str, zip_path: str) -> str:
    """
    Compacta o pacote final em um único ZIP com a seguinte estrutura interna:
      Invoices_YYYYMMDD_HHMMSS.xlsx          ← planilha na raiz
      invoices/Ano/Mês/Fornecedor/arquivo    ← PDFs organizados em subpasta "invoices/"

    ZIP_DEFLATED: compressão padrão (melhor compatibilidade com Windows Explorer).
    Exclui arquivos .zip que possam existir dentro do output_dir para evitar recursão.
    Retorna o caminho do ZIP criado.
    """
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Adiciona o Excel na raiz do ZIP
        zf.write(excel_path, arcname=Path(excel_path).name)
        # Percorre recursivamente a pasta de PDFs organizados
        output_root = Path(output_dir)
        for file_path in output_root.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() != ".zip":
                # arcname preserva o caminho relativo dentro do ZIP sob a pasta "invoices/"
                arcname = "invoices/" + str(file_path.relative_to(output_root))
                zf.write(file_path, arcname=arcname)
    return zip_path