"use client";

import { useState, useRef, useEffect, useLayoutEffect } from "react";

interface CurrencyInputProps {
  value: number | null | undefined;
  onChange: (value: number | null) => void;
  className?: string;
  placeholder?: string;
  readOnly?: boolean;
}

/**
 * Converte um inteiro de centavos para o formato monetário brasileiro.
 *   0       → "0,00"
 *   570     → "5,70"
 *   123456  → "1.234,56"
 */
function formatCents(cents: number): string {
  const str = String(cents).padStart(3, "0");
  const intPart = str.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decPart = str.slice(-2);
  return `${intPart || "0"},${decPart}`;
}

/**
 * Input de moeda com máscara dinâmica estilo Nubank.
 *
 * LÓGICA INTERNA
 * ─────────────
 * O valor é armazenado como uma string de dígitos inteiros que representam
 * centavos. Exemplo: "570" = R$ 5,70. Isso evita problemas de ponto flutuante
 * e simplifica a manipulação dígito a dígito.
 *
 * • Ao digitar: o novo dígito é acrescentado à direita da string de centavos.
 *   "57" + "0" → "570" → exibe "5,70"
 *
 * • Ao apagar: o último dígito é removido.
 *   "570" → "57" → exibe "0,57"
 *
 * • Para o pai: onChange recebe o valor em float (centavos / 100).
 *   Se o valor for zero, retorna null (campo "não preenchido").
 *
 * INTEGRAÇÃO NO FORMULÁRIO
 * ────────────────────────
 * <CurrencyInput
 *   value={invoice.exchange_rate}          // number | null
 *   onChange={(v) => set("exchange_rate", v)}
 *   className={inputClass}                 // reutiliza os estilos do Field
 * />
 */
export function CurrencyInput({ value, onChange, className, placeholder, readOnly }: CurrencyInputProps) {
  // Estado interno: string de dígitos sem formatação, ex: "570" = R$ 5,70
  const [rawDigits, setRawDigits] = useState<string>(() =>
    value == null || value === 0 ? "0" : String(Math.round(value * 100))
  );

  const inputRef = useRef<HTMLInputElement>(null);

  // Sincroniza quando o valor externo muda (ex: carregar dados de outra NF)
  // rawDigits é omitido das deps intencionalmente para não criar loop infinito:
  // onChange → parent atualiza value → useEffect → setRawDigits → onChange → ...
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const next = String(value == null ? 0 : Math.round(value * 100));
    if (next !== rawDigits) setRawDigits(next);
  }, [value]);

  // Após cada render, mantém o cursor no final enquanto o input estiver focado
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (el && document.activeElement === el) {
      el.selectionStart = el.value.length;
      el.selectionEnd = el.value.length;
    }
  });

  // Aplica a nova string de dígitos e notifica o pai com o float resultante
  function applyDigits(next: string) {
    setRawDigits(next);
    const cents = parseInt(next, 10);
    onChange(cents > 0 ? cents / 100 : null);
  }

  // Backspace/Delete removem o último dígito; outros caracteres não-numéricos são bloqueados
  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" || e.key === "Delete") {
      e.preventDefault();
      applyDigits(rawDigits.length <= 1 ? "0" : rawDigits.slice(0, -1));
      return;
    }
    if (e.key.length === 1 && !/^\d$/.test(e.key)) {
      e.preventDefault();
    }
  }

  // Fallback para mobile/IME: extrai apenas dígitos do que o browser renderizou
  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const digits = e.target.value.replace(/\D/g, "").replace(/^0+/, "").slice(0, 10) || "0";
    applyDigits(digits);
  }

  // Ao colar: extrai dígitos do texto colado (ex: "R$ 1.234,56" → "123456")
  function handlePaste(e: React.ClipboardEvent<HTMLInputElement>) {
    e.preventDefault();
    const digits =
      e.clipboardData.getData("text").replace(/\D/g, "").replace(/^0+/, "").slice(0, 10) || "0";
    applyDigits(digits);
  }

  function moveCursorToEnd() {
    const el = inputRef.current;
    if (el) {
      el.selectionStart = el.value.length;
      el.selectionEnd = el.value.length;
    }
  }

  return (
    <input
      ref={inputRef}
      type="text"
      inputMode={readOnly ? "none" : "numeric"}
      readOnly={readOnly}
      tabIndex={readOnly ? -1 : undefined}
      value={formatCents(parseInt(rawDigits, 10))}
      onChange={readOnly ? undefined : handleChange}
      onKeyDown={readOnly ? undefined : handleKeyDown}
      onPaste={readOnly ? undefined : handlePaste}
      onClick={readOnly ? undefined : moveCursorToEnd}
      onFocus={readOnly ? undefined : moveCursorToEnd}
      className={className}
      placeholder={placeholder}
    />
  );
}
