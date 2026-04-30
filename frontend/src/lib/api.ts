// Camada de comunicação com a API do backend.
// Todas as funções são assíncronas e lançam Error com a mensagem do backend em caso de falha.
// BASE é lida da variável de ambiente NEXT_PUBLIC_API_URL — permite trocar a URL sem alterar código.

import type { ConfirmResponse, HistoryEntry, InvoiceData, UploadResponse } from "./types";

// URL base da API — em desenvolvimento aponta para http://localhost:8000/api
const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api";


// Envia arquivos para o backend processar via OCR.
// Usa FormData com múltiplos campos "files" (requisito do FastAPI para List[UploadFile]).
// Retorna a UploadResponse com session_id + lista de NFs extraídas.
export async function uploadInvoices(files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));

  const res = await fetch(`${BASE}/invoices/upload`, {
    method: "POST",
    body: form,
    // Não define Content-Type — o browser define automaticamente com o boundary correto para multipart
  });

  if (!res.ok) {
    // Tenta extrair a mensagem de erro do JSON do FastAPI (campo "detail"); fallback para statusText
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Erro no upload.");
  }
  return res.json();
}


// Envia as NFs revisadas pelo usuário para o backend gerar o Excel + ZIP.
// invoices já inclui as edições manuais e o status (confirmed/skipped) de cada NF.
// Retorna a ConfirmResponse com job_id e download_url.
export async function confirmInvoices(
  session_id: string,
  invoices: InvoiceData[]
): Promise<ConfirmResponse> {
  const res = await fetch(`${BASE}/invoices/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, invoices }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Erro ao confirmar invoices.");
  }
  return res.json();
}


// Busca a lista de processamentos anteriores para exibição no histórico.
// Retorna o array de entries (paginação padrão do backend: 50 mais recentes).
export async function fetchHistory(): Promise<HistoryEntry[]> {
  const res = await fetch(`${BASE}/history/`);
  if (!res.ok) throw new Error("Erro ao carregar histórico.");
  const data = await res.json();
  return data.entries; // o backend retorna { entries: [...], total: N }
}


// Remove um único registro do histórico pelo seu ID.
export async function deleteHistoryEntry(id: string): Promise<void> {
  const res = await fetch(`${BASE}/history/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erro ao excluir registro.");
}


// Remove todos os registros do histórico de uma vez.
export async function deleteAllHistory(): Promise<void> {
  const res = await fetch(`${BASE}/history/all`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erro ao limpar histórico.");
}