"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  FileText,
} from "lucide-react";
import clsx from "clsx";
import type { InvoiceData } from "@/lib/types";
import InvoiceEditForm from "./InvoiceEditForm";

interface Props {
  invoice: InvoiceData;
  index: number;
  onChange: (updated: InvoiceData) => void; // callback quando o usuário edita um campo
  onConfirm: (id: string) => void;          // callback para marcar como "confirmed"
  onSkip: (id: string) => void;             // callback para marcar como "skipped"
}

// Badge colorido exibido no cabeçalho do card indicando o estado atual da NF.
// Prioridade: duplicata > confirmado > ignorado > pendente
function StatusBadge({ status, isDuplicate }: { status: string; isDuplicate: boolean }) {
  if (isDuplicate)
    return <span className="badge-duplicate flex items-center gap-1"><AlertTriangle size={12} /> Duplicado</span>;
  if (status === "confirmed")
    return <span className="badge-confirmed flex items-center gap-1"><CheckCircle2 size={12} /> Confirmado</span>;
  if (status === "skipped")
    return <span className="badge-skipped flex items-center gap-1"><XCircle size={12} /> Ignorado</span>;
  return <span className="badge-pending flex items-center gap-1"><Clock size={12} /> Pendente</span>;
}

// Retorna true se algum campo obrigatório está faltando — bloqueia o botão "Confirmar"
function missingRequired(inv: InvoiceData): boolean {
  return (
    !inv.supplier ||
    !inv.invoice_number ||
    !inv.issue_date ||
    inv.total_amount == null ||
    !inv.currency
  );
}

export default function InvoiceCard({ invoice, onChange, onConfirm, onSkip }: Props) {
  // Controla se o formulário de edição está expandido ou colapsado
  const [expanded, setExpanded] = useState(true);

  const hasMissing = missingRequired(invoice);
  const isConfirmed = invoice.status === "confirmed";
  const isSkipped = invoice.status === "skipped";

  return (
    <div
      className={clsx(
        "card transition-all",
        isConfirmed && "ring-2 ring-green-400",         // borda verde quando confirmada
        isSkipped && "opacity-60",                       // opacidade reduzida quando ignorada
        invoice.is_duplicate && "ring-2 ring-orange-400" // borda laranja quando suspeita de duplicata
      )}
    >
      {/* Cabeçalho clicável — expande/colapsa o formulário de edição */}
      <div
        className="flex items-center gap-2 sm:gap-3 px-4 sm:px-5 py-3 sm:py-4 cursor-pointer select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-100 shrink-0 dark:bg-blue-900/40">
          <FileText size={15} className="text-blue-600 dark:text-blue-400" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Título: nome do fornecedor se extraído, senão nome do arquivo */}
            <p className="text-sm font-semibold text-gray-900 truncate dark:text-gray-100">
              {invoice.supplier || invoice.original_filename}
            </p>
            <StatusBadge status={invoice.status} isDuplicate={invoice.is_duplicate} />
            {/* Aviso de campos incompletos — só aparece se NF não foi ignorada */}
            {hasMissing && invoice.status !== "skipped" && (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/40 dark:text-red-400">
                <AlertTriangle size={10} /> Campos incompletos
              </span>
            )}
          </div>
          {/* Linha de resumo: nome do arquivo, número, valor + moeda, tempo de OCR */}
          <p className="text-xs text-gray-400 mt-0.5 truncate dark:text-gray-500">
            {invoice.original_filename}
            {invoice.invoice_number && ` · ${invoice.invoice_number}`}
            {invoice.total_amount != null && invoice.currency
              && ` · ${invoice.total_amount.toLocaleString("pt-BR", { minimumFractionDigits: 2 })} ${invoice.currency}`}
            {invoice.processing_time != null && ` · ${invoice.processing_time}s`}
          </p>
        </div>

        {/* Ícone de chevron indica o estado expandido/colapsado */}
        <div className="shrink-0 text-gray-400 dark:text-gray-500">
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>
      </div>

      {/* Aviso de duplicata — exibido independente do estado expandido */}
      {invoice.is_duplicate && (
        <div className="mx-5 mb-3 flex items-start gap-2 rounded-lg bg-orange-50 border border-orange-200 px-3 py-2 dark:bg-orange-900/20 dark:border-orange-700">
          <AlertTriangle size={14} className="text-orange-600 mt-0.5 shrink-0 dark:text-orange-400" />
          <p className="text-xs text-orange-700 dark:text-orange-400">
            Este invoice pode ser duplicado — verifique antes de confirmar.
          </p>
        </div>
      )}

      {/* Formulário de edição — visível apenas quando expandido e não ignorado */}
      {expanded && !isSkipped && (
        <div className="border-t border-gray-100 px-4 sm:px-5 py-4 dark:border-gray-700">
          {/* InvoiceEditForm renderiza todos os campos editáveis da NF */}
          <InvoiceEditForm invoice={invoice} onChange={onChange} />

          {/* Rodapé com ações: Ignorar (esquerda) e Confirmar (direita) */}
          <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-between gap-2 mt-5 pt-4 border-t border-gray-100 dark:border-gray-700">
            <button
              onClick={() => onSkip(invoice.id)}
              disabled={isConfirmed} // não pode ignorar uma NF já confirmada
              className="btn-danger justify-center"
            >
              <XCircle size={15} />
              Ignorar
            </button>

            <button
              onClick={() => onConfirm(invoice.id)}
              disabled={isConfirmed || hasMissing} // bloqueado se campos obrigatórios faltam
              title={hasMissing ? "Preencha os campos obrigatórios antes de confirmar" : undefined}
              className={clsx(
                "justify-center",
                isConfirmed ? "btn-secondary cursor-default" : "btn-success",
                hasMissing && "opacity-50 cursor-not-allowed"
              )}
            >
              <CheckCircle2 size={15} />
              {isConfirmed ? "Confirmado" : "Confirmar"}
            </button>
          </div>
        </div>
      )}

      {/* Quando ignorada, exibe apenas um link "Desfazer" para restaurar para pending */}
      {isSkipped && (
        <div className="border-t border-gray-100 px-5 py-3 flex justify-end dark:border-gray-700">
          <button
            onClick={() => onChange({ ...invoice, status: "pending" })}
            className="text-xs text-blue-600 hover:underline dark:text-blue-400"
          >
            Desfazer
          </button>
        </div>
      )}
    </div>
  );
}