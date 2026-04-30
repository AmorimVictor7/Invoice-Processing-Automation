"use client";

import clsx from "clsx";
import type { InvoiceData } from "@/lib/types";

// Moedas disponíveis no seletor de moeda
const CURRENCIES = ["USD", "EUR", "GBP", "BRL", "CAD", "AUD", "JPY", "CHF", "ARS", "MXN"];


// Props de um campo individual do formulário
interface FieldProps {
  label: string;
  field: keyof InvoiceData;                                   // nome do campo no objeto InvoiceData
  invoice: InvoiceData;
  onChange: (field: keyof InvoiceData, value: string | number | null) => void;
  type?: "text" | "number" | "date" | "textarea" | "select"; // tipo de input a renderizar
  options?: string[];   // opções para o select
  required?: boolean;   // exibe asterisco e mensagem de erro se vazio
  hint?: string;        // placeholder do input
}


// Bolinha colorida ao lado do label indicando o nível de confiança do OCR para aquele campo:
//   verde  = score ≥ 0.75 (alta confiança)
//   amarelo = score ≥ 0.45 (média)
//   vermelho = score < 0.45 (baixa — usuário deve verificar)
function ConfidenceDot({ score }: { score: number | undefined }) {
  if (score === undefined) return null;
  const color =
    score >= 0.75 ? "bg-green-400" : score >= 0.45 ? "bg-yellow-400" : "bg-red-400";
  const label =
    score >= 0.75 ? "Alta confiança" : score >= 0.45 ? "Confiança média" : "Baixa confiança";
  return (
    <span title={`${label} (${Math.round(score * 100)}%)`} className="inline-flex items-center gap-1 ml-1">
      <span className={clsx("inline-block w-2 h-2 rounded-full", color)} />
    </span>
  );
}


// Componente genérico de campo do formulário.
// Renderiza textarea, select ou input de acordo com o prop "type".
// Aplica classes CSS de erro quando campo obrigatório está vazio ou quando a confiança é baixa.
function Field({ label, field, invoice, onChange, type = "text", options, required, hint }: FieldProps) {
  const value = invoice[field] ?? "";
  const confidence = invoice.confidence[field as string];
  const isEmpty = value === "" || value === null || value === undefined;
  const isLowConf = confidence !== undefined && confidence < 0.5 && !isEmpty;
  const isMissingRequired = required && isEmpty;

  // Combina classes base do input com classes de estado (erro / baixa confiança)
  const inputClass = clsx(
    "field-input",
    isMissingRequired && "missing-required",              // borda vermelha
    isLowConf && !isMissingRequired && "low-confidence"   // borda amarela
  );

  return (
    <div>
      <label className="field-label">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
        <ConfidenceDot score={confidence} />
      </label>

      {/* Renderiza o tipo de input correto conforme a prop "type" */}
      {type === "textarea" ? (
        <textarea
          value={value as string}
          onChange={(e) => onChange(field, e.target.value)}
          rows={2}
          className={clsx(inputClass, "resize-none")}
          placeholder={hint}
        />
      ) : type === "select" ? (
        <select
          value={value as string}
          onChange={(e) => onChange(field, e.target.value)}
          className={inputClass}
        >
          <option value="">Selecione…</option>
          {options?.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      ) : (
        <input
          type={type}
          // Para campos numéricos, converte para string para o input mas mantém null quando vazio
          value={type === "number" ? (value === "" ? "" : String(value)) : (value as string)}
          onChange={(e) =>
            onChange(
              field,
              type === "number"
                ? e.target.value === "" ? null : parseFloat(e.target.value)
                : e.target.value
            )
          }
          className={inputClass}
          placeholder={hint}
          step={type === "number" ? "0.01" : undefined} // 2 casas decimais para valores monetários
          min={type === "number" ? "0" : undefined}     // valores negativos não fazem sentido para NF
        />
      )}

      {/* Mensagens de feedback abaixo do input */}
      {isMissingRequired && (
        <p className="text-xs text-red-500 mt-0.5 dark:text-red-400">Campo obrigatório</p>
      )}
      {isLowConf && !isMissingRequired && (
        <p className="text-xs text-yellow-600 mt-0.5 dark:text-yellow-400">Verifique este valor — confiança baixa</p>
      )}
    </div>
  );
}


interface Props {
  invoice: InvoiceData;
  onChange: (updated: InvoiceData) => void; // devolve o objeto inteiro atualizado para o InvoiceCard
}

export default function InvoiceEditForm({ invoice, onChange }: Props) {
  // Atualiza um campo e recalcula converted_amount automaticamente sempre que
  // total_amount ou exchange_rate mudam — evita que o usuário precise calcular manualmente
  const set = (field: keyof InvoiceData, value: string | number | null) => {
    const updated = { ...invoice, [field]: value };
    if (
      (field === "total_amount" || field === "exchange_rate") &&
      updated.total_amount != null &&
      updated.exchange_rate != null
    ) {
      updated.converted_amount = parseFloat(
        (updated.total_amount * updated.exchange_rate).toFixed(2)
      );
    }
    onChange(updated);
  };

  return (
    // Grid responsivo: 1 coluna no mobile, 2 no tablet, 3 no desktop
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {/* Campos obrigatórios (bloqueiam o botão Confirmar se vazios) */}
      <Field label="Fornecedor" field="supplier" invoice={invoice} onChange={set} required hint="Ex: Google LLC" />
      <Field label="Nº Invoice" field="invoice_number" invoice={invoice} onChange={set} required hint="Ex: INV-12345" />
      <Field label="Data de Emissão" field="issue_date" invoice={invoice} onChange={set} type="date" required />

      <Field label="Período de Cobrança" field="billing_period" invoice={invoice} onChange={set} hint="Ex: Abril/2026" />
      <Field label="Moeda" field="currency" invoice={invoice} onChange={set} type="select" options={CURRENCIES} required />
      <Field label="Valor Total" field="total_amount" invoice={invoice} onChange={set} type="number" required hint="Ex: 250.00" />

      {/* Campos opcionais */}
      <Field label="Subtotal" field="subtotal" invoice={invoice} onChange={set} type="number" hint="Opcional" />
      <Field label="Impostos / Taxas" field="taxes" invoice={invoice} onChange={set} type="number" hint="Opcional" />
      {/* Alterar cotação ou valor total recalcula converted_amount automaticamente (ver função set acima) */}
      <Field label="Cotação (R$)" field="exchange_rate" invoice={invoice} onChange={set} type="number" hint="Ex: 5.70" />

      <Field label="Valor Convertido (R$)" field="converted_amount" invoice={invoice} onChange={set} type="number" hint="Calculado automaticamente" />
      <Field label="Centro de Custo" field="cost_center" invoice={invoice} onChange={set} hint="Ex: TI / Marketing" />

      {/* Campos de texto longo ocupam toda a largura do grid */}
      <div className="sm:col-span-2 lg:col-span-3">
        <Field label="Descrição" field="description" invoice={invoice} onChange={set} type="textarea" hint="Descrição do serviço" />
      </div>
      <div className="sm:col-span-2 lg:col-span-3">
        <Field label="Observações" field="observations" invoice={invoice} onChange={set} type="textarea" hint="Notas adicionais" />
      </div>
    </div>
  );
}