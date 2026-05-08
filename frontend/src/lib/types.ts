// Tipos TypeScript compartilhados entre componentes e funções de API.
// Espelham exatamente os modelos Pydantic do backend (backend/models/invoice.py).


// ── Autenticação ──────────────────────────────────────────────────────────────

export interface User {
  id: string;
  name: string;
  email: string;
  role: "user" | "admin";
  last_login?: string | null;
  created_at?: string;
}

export interface AuthResponse {
  user: User;
}


// ── Invoice ───────────────────────────────────────────────────────────────────

// Representa uma nota fiscal — estrutura central da aplicação.
// null indica campo não extraído pelo OCR ou não preenchido pelo usuário.
export interface InvoiceData {
  id: string;                        // ID único da NF na sessão (gerado pelo backend)
  original_filename: string;         // Nome do arquivo original enviado

  // Campos extraídos pelo OCR
  supplier: string | null;
  invoice_number: string | null;
  issue_date: string | null;         // YYYY-MM-DD
  billing_period: string | null;
  description: string | null;
  currency: string | null;           // código ISO: USD, EUR, BRL...
  subtotal: number | null;
  taxes: number | null;
  additional_fees: number | null;
  total_amount: number | null;

  // Campos de controle financeiro (preenchidos pelo usuário na tela de revisão)
  cost_center: string | null;
  observations: string | null;
  exchange_rate: number | null;      // taxa de câmbio para conversão em BRL
  converted_amount: number | null;   // total_amount * exchange_rate

  // Metadados de processamento
  confidence: Record<string, number>; // campo → score de confiança (0.0–1.0)
  ocr_method: string | null;          // "pdfplumber" | "tesseract" | "google_vision" | "gemini"
  processing_time: number | null;     // segundos

  // Estado de revisão pelo usuário
  status: "pending" | "confirmed" | "skipped";
  is_duplicate: boolean;             // true se detectado como possível duplicata
  duplicate_of: string | null;       // ID da NF original, se duplicata
}


// ── API Responses ─────────────────────────────────────────────────────────────

// Resposta do POST /api/invoices/upload
export interface UploadResponse {
  session_id: string;                // ID da sessão para usar no /confirm
  invoices: InvoiceData[];           // NFs processadas com sucesso
  processing_errors: string[];       // mensagens de erro para arquivos que falharam
}


// Resposta do POST /api/invoices/confirm
export interface ConfirmResponse {
  job_id: string;                    // ID para buscar o pacote no /download/{job_id}
  download_url: string;              // caminho relativo para download do ZIP
  excel_filename: string;
  zip_filename: string;
  invoice_count: number;             // quantidade de NFs incluídas no pacote
}


// Entrada no histórico de processamentos anteriores
export interface HistoryEntry {
  id: string;                        // job_id do processamento
  session_id: string;
  processed_at: string;              // ISO 8601
  invoice_count: number;
  supplier_list: string[];           // fornecedores únicos do lote
  total_amount_brl: number | null;   // soma total em BRL (null se sem conversão)
  excel_filename: string;
  zip_filename: string;
  invoices_json?: InvoiceData[];     // opcional: NFs completas (usadas no dashboard)
}


// Estado global do fluxo principal da página de processamento
export type AppState =
  | "idle"        // aguardando upload
  | "uploading"   // enviando arquivos ao backend / aguardando OCR
  | "reviewing"   // usuário revisando as NFs extraídas
  | "confirming"  // aguardando geração do Excel + ZIP
  | "done";       // pacote gerado e pronto para download
