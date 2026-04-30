# Importa BaseModel (base de todos os modelos Pydantic) e Field (para configurar campos com defaults)
from pydantic import BaseModel, Field
# Optional = campo que pode ser None; Dict = dicionário; List = lista
from typing import Optional, Dict, List
# datetime importado mas não usado diretamente nos modelos (pode ser útil no futuro)
from datetime import datetime

# Representa uma nota fiscal extraída de um arquivo PDF/imagem.
# Todos os campos de negócio são Optional porque o OCR pode não conseguir extrair todos.
class InvoiceData(BaseModel):
    id: str                              # ID único gerado pelo backend para identificar a NF na sessão
    original_filename: str               # Nome do arquivo original enviado pelo usuário

    # --- Dados extraídos pelo OCR ---
    supplier: Optional[str] = None       # Nome do fornecedor
    invoice_number: Optional[str] = None # Número da nota fiscal
    issue_date: Optional[str] = None     # Data de emissão
    billing_period: Optional[str] = None # Período de competência cobrado
    description: Optional[str] = None   # Descrição do serviço ou produto
    currency: Optional[str] = None      # Moeda (BRL, USD, EUR...)
    subtotal: Optional[float] = None    # Valor antes de impostos e taxas
    taxes: Optional[float] = None       # Impostos (ISS, PIS, COFINS...)
    additional_fees: Optional[float] = None  # Taxas adicionais (frete, multa...)
    total_amount: Optional[float] = None     # Valor total da nota

    # --- Campos de controle financeiro ---
    cost_center: Optional[str] = None   # Centro de custo para contabilização
    observations: Optional[str] = None  # Observações livres

    # --- Conversão de moeda ---
    exchange_rate: Optional[float] = None    # Taxa de câmbio usada na conversão
    converted_amount: Optional[float] = None # Valor convertido para BRL

    # --- Metadados de processamento ---
    # confidence: dicionário campo→porcentagem indicando o quão seguro o OCR está de cada valor extraído
    confidence: Dict[str, float] = Field(default_factory=dict)
    ocr_method: Optional[str] = None    # Método de OCR usado (ex: "claude", "tesseract")
    processing_time: Optional[float] = None  # Tempo em segundos que levou para processar

    # --- Estado de revisão pelo usuário ---
    status: str = "pending"  # pending = aguardando revisão | confirmed = aprovada | skipped = ignorada
    is_duplicate: bool = False           # True se o sistema detectou que essa NF já foi enviada antes
    duplicate_of: Optional[str] = None  # ID da NF original caso seja duplicata


# Resposta que o backend envia depois que o usuário faz upload dos arquivos.
# Contém a lista de NFs já processadas prontas para revisão, mais erros que eventualmente ocorreram.
class UploadResponse(BaseModel):
    session_id: str                      # ID da sessão criada para esse lote de uploads
    invoices: List[InvoiceData]          # Lista de NFs extraídas com sucesso
    processing_errors: List[str] = Field(default_factory=list)  # Arquivos que falharam no processamento


# Payload que o frontend envia quando o usuário termina de revisar e clica em "Confirmar".
# Devolve a sessão e a lista de NFs com eventuais edições feitas pelo usuário na tela.
class ConfirmRequest(BaseModel):
    session_id: str          # Identifica o lote sendo confirmado
    invoices: List[InvoiceData]  # NFs com status atualizado (confirmed/skipped) e possíveis correções manuais


# Resposta do backend após gerar os arquivos de saída (Excel + ZIP com PDFs).
# O frontend usa download_url para oferecer o download ao usuário.
class ConfirmResponse(BaseModel):
    job_id: str              # ID do job de geração dos arquivos
    download_url: str        # URL para baixar o pacote ZIP
    excel_filename: str      # Nome do arquivo Excel gerado
    zip_filename: str        # Nome do arquivo ZIP com todos os anexos
    invoice_count: int       # Quantidade de NFs incluídas no pacote


# Representa uma entrada no histórico de lotes já processados.
# Permite que o usuário consulte processamentos anteriores e baixe novamente os arquivos.
class HistoryEntry(BaseModel):
    id: str                          # ID único do registro histórico
    processed_at: str                # Data/hora em que o lote foi processado (ISO 8601)
    invoice_count: int               # Quantidade de NFs nesse lote
    supplier_list: List[str]         # Lista de fornecedores presentes no lote
    total_amount_brl: Optional[float]  # Soma total das NFs em BRL (None se não convertível)
    excel_filename: str              # Nome do Excel gerado para esse lote
    zip_filename: str                # Nome do ZIP gerado para esse lote
    session_id: str                  # Referência à sessão original do upload
