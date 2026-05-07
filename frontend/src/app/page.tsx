"use client"; // componente client-side: usa hooks de estado e eventos do browser

import { useState } from "react";
import {
  Download,
  Loader2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  FileSpreadsheet,
} from "lucide-react";
import Header from "@/components/Header";
import FileUpload from "@/components/FileUpload";
import InvoiceCard from "@/components/InvoiceCard";
import { uploadInvoices, confirmInvoices } from "@/lib/api";
import type { AppState, ConfirmResponse, InvoiceData } from "@/lib/types";

export default function HomePage() {
  // Estado da máquina de estados do fluxo principal
  const [appState, setAppState] = useState<AppState>("idle");
  // ID da sessão retornado pelo backend após o upload — necessário para o /confirm
  const [sessionId, setSessionId] = useState("");
  // Lista de NFs retornada pelo OCR, mutável pelo usuário na tela de revisão
  const [invoices, setInvoices] = useState<InvoiceData[]>([]);
  // Erros de arquivos individuais que falharam no processamento (ex: formato inválido)
  const [errors, setErrors] = useState<string[]>([]);
  // Resultado do /confirm: contém download_url e nomes dos arquivos gerados
  const [result, setResult] = useState<ConfirmResponse | null>(null);
  // Erro global de operação (falha total no upload ou no confirm)
  const [globalError, setGlobalError] = useState<string | null>(null);


  // Chamado pelo componente FileUpload quando o usuário clica em "Processar Invoices".
  // Envia os arquivos ao backend e avança o estado para "reviewing".
  const handleUpload = async (files: File[]) => {
    setAppState("uploading");
    setGlobalError(null);
    setErrors([]);
    try {
      const res = await uploadInvoices(files);
      setSessionId(res.session_id);
      setInvoices(res.invoices);
      setErrors(res.processing_errors);
      setAppState("reviewing");
    } catch (e: unknown) {
      setGlobalError(e instanceof Error ? e.message : "Erro desconhecido.");
      setAppState("idle");
    }
  };

  // Atualiza uma NF específica na lista (chamado pelo InvoiceEditForm após edição de campo)
  const updateInvoice = (updated: InvoiceData) =>
    setInvoices((prev) => prev.map((inv) => (inv.id === updated.id ? updated : inv)));

  // Marca uma NF como "confirmed" (chamado pelo botão Confirmar do InvoiceCard)
  const confirmOne = (id: string) =>
    setInvoices((prev) =>
      prev.map((inv) => (inv.id === id ? { ...inv, status: "confirmed" } : inv))
    );

  // Marca uma NF como "skipped" — será excluída do pacote (chamado pelo botão Ignorar)
  const skipOne = (id: string) =>
    setInvoices((prev) =>
      prev.map((inv) => (inv.id === id ? { ...inv, status: "skipped" } : inv))
    );

  // Confirma todas as NFs que ainda não foram ignoradas de uma vez
  const confirmAll = () =>
    setInvoices((prev) =>
      prev.map((inv) =>
        inv.status !== "skipped" ? { ...inv, status: "confirmed" } : inv
      )
    );

  // true quando todas as NFs têm status definido (confirmed ou skipped) — habilita o botão "Gerar Pacote"
  const allConfirmedOrSkipped = invoices.every(
    (inv) => inv.status === "confirmed" || inv.status === "skipped"
  );
  const confirmedCount = invoices.filter((inv) => inv.status === "confirmed").length;


  // Envia as NFs confirmadas ao backend para gerar o Excel + ZIP.
  // Avança para "done" após sucesso, ou volta para "reviewing" se falhar.
  const handleGenerate = async () => {
    setAppState("confirming");
    setGlobalError(null);
    try {
      const res = await confirmInvoices(sessionId, invoices);
      setResult(res);
      setAppState("done");
    } catch (e: unknown) {
      setGlobalError(e instanceof Error ? e.message : "Erro ao gerar pacote.");
      setAppState("reviewing");
    }
  };

  // Reinicia todo o fluxo para o estado inicial (permite processar um novo lote)
  const reset = () => {
    setAppState("idle");
    setSessionId("");
    setInvoices([]);
    setErrors([]);
    setResult(null);
    setGlobalError(null);
  };

  return (
    <>
      <Header />

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Processar Invoices</h1>
          <p className="text-sm text-gray-500 mt-1 dark:text-gray-400">
            Faça upload dos invoices, revise os dados extraídos e gere o pacote para o financeiro.
          </p>
        </div>

        {/* Banner de erro global (falha no upload ou no confirm) */}
        {globalError && (
          <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 px-4 py-3 dark:bg-red-900/20 dark:border-red-700">
            <AlertCircle size={18} className="text-red-500 shrink-0 mt-0.5 dark:text-red-400" />
            <p className="text-sm text-red-700 dark:text-red-400">{globalError}</p>
          </div>
        )}

        {/* Lista de arquivos que falharam individualmente no OCR (não impede os demais) */}
        {errors.length > 0 && (() => {
          const quotaErrors = errors.filter(e => e.includes("Cota diária"));
          const otherErrors = errors.filter(e => !e.includes("Cota diária"));
          return (
            <>
              {quotaErrors.length > 0 && (
                <div className="rounded-xl bg-orange-50 border border-orange-200 px-4 py-3 dark:bg-orange-900/20 dark:border-orange-700">
                  <p className="text-sm font-semibold text-orange-700 mb-1 dark:text-orange-400">
                    Cota diária da API Gemini esgotada
                  </p>
                  <p className="text-xs text-orange-600 dark:text-orange-400">
                    Os arquivos não foram processados — tente novamente amanhã ou faça upgrade do plano.
                  </p>
                </div>
              )}
              {otherErrors.length > 0 && (
                <div className="rounded-xl bg-orange-50 border border-orange-200 px-4 py-3 dark:bg-orange-900/20 dark:border-orange-700">
                  <p className="text-sm font-semibold text-orange-700 mb-1 dark:text-orange-400">
                    Alguns arquivos não puderam ser processados:
                  </p>
                  <ul className="list-disc list-inside space-y-0.5">
                    {otherErrors.map((err, i) => (
                      <li key={i} className="text-xs text-orange-600 dark:text-orange-400">{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          );
        })()}

        {/* Estado idle: exibe a área de upload */}
        {appState === "idle" && (
          <div className="card p-6">
            <FileUpload onUpload={handleUpload} />
          </div>
        )}

        {/* Estado uploading: spinner enquanto o backend processa */}
        {appState === "uploading" && (
          <div className="card p-8 sm:p-12 flex flex-col items-center gap-4">
            <Loader2 size={40} className="text-blue-600 animate-spin" />
            <p className="text-base font-semibold text-gray-700 dark:text-gray-200">Processando invoices…</p>
            <p className="text-sm text-gray-400 dark:text-gray-500">Executando OCR e extraindo dados</p>
          </div>
        )}

        {/* Estados reviewing/confirming: exibe a lista de InvoiceCards para revisão */}
        {(appState === "reviewing" || appState === "confirming") && (
          <div className="space-y-4">
            {/* Barra de progresso: contagem de confirmadas + botões de ação rápida */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                <span className="font-semibold text-gray-900 dark:text-gray-100">{invoices.length}</span> invoice
                {invoices.length !== 1 ? "s" : ""} carregado{invoices.length !== 1 ? "s" : ""}.{" "}
                <span className="text-green-700 font-medium dark:text-green-400">{confirmedCount} confirmado{confirmedCount !== 1 ? "s" : ""}</span>
              </p>
              <div className="flex items-center gap-2">
                <button onClick={reset} className="btn-secondary text-xs py-1.5 px-3">
                  <RefreshCw size={13} />
                  Recomeçar
                </button>
                {/* "Confirmar Todos" só aparece enquanto houver NFs pendentes */}
                {!allConfirmedOrSkipped && (
                  <button onClick={confirmAll} className="btn-secondary text-xs py-1.5 px-3">
                    <CheckCircle2 size={13} />
                    Confirmar Todos
                  </button>
                )}
              </div>
            </div>

            {/* Lista de cards — um por NF */}
            <div className="space-y-3">
              {invoices.map((inv, i) => (
                <InvoiceCard
                  key={inv.id}
                  invoice={inv}
                  index={i}
                  onChange={updateInvoice}
                  onConfirm={confirmOne}
                  onSkip={skipOne}
                />
              ))}
            </div>

            {/* Rodapé com o botão "Gerar Pacote" — aparece assim que há ao menos 1 NF confirmada */}
            {confirmedCount > 0 && (
              <div className="card p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:border-blue-700">
                <div>
                  <p className="text-sm font-semibold text-blue-900 dark:text-blue-300">
                    {confirmedCount} invoice{confirmedCount !== 1 ? "s" : ""} pronto{confirmedCount !== 1 ? "s" : ""}
                  </p>
                  <p className="text-xs text-blue-600 dark:text-blue-400">
                    Gere a planilha Excel e o pacote ZIP para envio ao financeiro.
                  </p>
                </div>
                <button
                  onClick={handleGenerate}
                  disabled={appState === "confirming"} // desabilitado enquanto aguarda resposta
                  className="btn-primary w-full sm:w-auto justify-center shrink-0"
                >
                  {appState === "confirming" ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <FileSpreadsheet size={16} />
                  )}
                  {appState === "confirming" ? "Gerando…" : "Gerar Pacote"}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Estado done: exibe confirmação de sucesso e link de download */}
        {appState === "done" && result && (
          <div className="card p-6 sm:p-8 flex flex-col items-center gap-5 text-center">
            <div className="flex items-center justify-center w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/40">
              <CheckCircle2 size={32} className="text-green-600 dark:text-green-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Pacote gerado com sucesso!</h2>
              <p className="text-sm text-gray-500 mt-1 dark:text-gray-400">
                {result.invoice_count} invoice{result.invoice_count !== 1 ? "s" : ""} processado
                {result.invoice_count !== 1 ? "s" : ""} · {result.zip_filename}
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
              {/* Link de download direto — o atributo "download" sugere o nome do arquivo ao browser */}
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${result.download_url}`}
                download={result.zip_filename}
                className="btn-success justify-center"
              >
                <Download size={16} />
                Baixar Pacote ZIP
              </a>
              <button onClick={reset} className="btn-secondary justify-center">
                <RefreshCw size={16} />
                Processar Novos Invoices
              </button>
            </div>

            {/* Resumo do conteúdo do pacote gerado */}
            <div className="w-full rounded-lg bg-gray-50 border border-gray-200 p-4 text-left space-y-1 dark:bg-gray-700 dark:border-gray-600">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide dark:text-gray-400">O pacote contém</p>
              <p className="text-sm text-gray-700 dark:text-gray-200">📊 {result.excel_filename}</p>
              <p className="text-sm text-gray-700 dark:text-gray-200">
                📁 invoices/ — arquivos renomeados e organizados por Ano / Mês / Fornecedor
              </p>
            </div>
          </div>
        )}
      </main>
    </>
  );
}