"use client";

import { useCallback, useRef, useState } from "react";
import { Upload, X, FileText, Image } from "lucide-react";
import clsx from "clsx";

interface Props {
  onUpload: (files: File[]) => void; // callback chamado quando o usuário clica em "Processar"
  disabled?: boolean;                // desabilita interação enquanto o upload está em andamento
}

const ACCEPTED = ".pdf,.png,.jpg,.jpeg"; // atributo "accept" do input file
const MAX_SIZE_MB = 20;                  // limite de tamanho por arquivo

// Ícone adaptado ao tipo de arquivo: PDF → vermelho, imagem → azul
function FileIcon({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileText size={16} className="text-red-500" />;
  return <Image size={16} className="text-blue-500" />;
}

export default function FileUpload({ onUpload, disabled }: Props) {
  const [dragging, setDragging] = useState(false);          // true quando o usuário está arrastando arquivo sobre a área
  const [selected, setSelected] = useState<File[]>([]);     // lista de arquivos selecionados (ainda não enviados)
  const [sizeError, setSizeError] = useState<string | null>(null); // erros de validação local
  const inputRef = useRef<HTMLInputElement>(null);           // ref para abrir o dialog de arquivo via click programático

  // Valida e adiciona novos arquivos à lista, evitando duplicatas pelo nome.
  // useCallback evita recriar a função em cada render (usada no onDrop que também é memoizado).
  const addFiles = useCallback((incoming: FileList | null) => {
    if (!incoming) return;
    setSizeError(null);
    const valid: File[] = [];
    const errors: string[] = [];

    Array.from(incoming).forEach((f) => {
      // Valida extensão
      const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
      if (!["pdf", "png", "jpg", "jpeg"].includes(ext)) {
        errors.push(`${f.name}: formato inválido`);
        return;
      }
      // Valida tamanho
      if (f.size > MAX_SIZE_MB * 1024 * 1024) {
        errors.push(`${f.name}: tamanho excede ${MAX_SIZE_MB} MB`);
        return;
      }
      valid.push(f);
    });

    if (errors.length) setSizeError(errors.join(" · "));

    // Merge com a lista atual, ignorando arquivos com o mesmo nome (evita duplicatas visíveis)
    setSelected((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...valid.filter((f) => !names.has(f.name))];
    });
  }, []);

  // Remove um arquivo da lista pelo nome
  const remove = (name: string) =>
    setSelected((prev) => prev.filter((f) => f.name !== name));

  // Lida com o evento de drop: cancela o comportamento padrão do browser (abrir o arquivo)
  // e delega para addFiles
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      addFiles(e.dataTransfer.files);
    },
    [addFiles]
  );

  // Dispara o callback onUpload passando a lista de arquivos selecionados
  const handleSubmit = () => {
    if (selected.length > 0) onUpload(selected);
  };

  // Formata tamanho de arquivo para exibição amigável (KB ou MB)
  const formatSize = (bytes: number) =>
    bytes < 1024 * 1024
      ? `${(bytes / 1024).toFixed(0)} KB`
      : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

  return (
    <div className="space-y-4">
      {/* Área de drop — muda visual quando o usuário arrasta arquivo sobre ela */}
      <div
        onClick={() => !disabled && inputRef.current?.click()} // click na área abre o dialog de arquivo
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={clsx(
          "relative flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-8 sm:p-12 cursor-pointer transition-all select-none",
          dragging
            ? "border-blue-500 bg-blue-50 scale-[1.01] dark:bg-blue-900/20"  // feedback visual ao arrastar
            : "border-gray-300 bg-white hover:border-blue-400 hover:bg-blue-50/40 dark:border-gray-600 dark:bg-gray-800 dark:hover:border-blue-500 dark:hover:bg-blue-900/10",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <div className="flex items-center justify-center w-14 h-14 rounded-full bg-blue-100 dark:bg-blue-900/40">
          <Upload size={26} className="text-blue-600 dark:text-blue-400" />
        </div>
        <div className="text-center">
          <p className="text-sm sm:text-base font-semibold text-gray-700 dark:text-gray-200 text-center">
            Arraste os invoices aqui ou{" "}
            <span className="text-blue-600 underline underline-offset-2 dark:text-blue-400">clique para selecionar</span>
          </p>
          <p className="text-sm text-gray-400 mt-1 dark:text-gray-500">PDF, PNG, JPG — até {MAX_SIZE_MB} MB por arquivo</p>
        </div>
        {/* Input file oculto — ativado programaticamente pelo click na área de drop */}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
          disabled={disabled}
        />
      </div>

      {/* Mensagens de erro de validação local (formato/tamanho) */}
      {sizeError && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 dark:text-red-400 dark:bg-red-900/20 dark:border-red-700">
          {sizeError}
        </p>
      )}

      {/* Lista de arquivos selecionados com botão de remoção individual */}
      {selected.length > 0 && (
        <ul className="space-y-2">
          {selected.map((file) => (
            <li
              key={file.name}
              className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-2.5 shadow-sm dark:border-gray-600 dark:bg-gray-700"
            >
              <FileIcon name={file.name} />
              <span className="flex-1 truncate text-sm text-gray-800 dark:text-gray-200">{file.name}</span>
              <span className="text-xs text-gray-400 shrink-0 dark:text-gray-500">{formatSize(file.size)}</span>
              {/* stopPropagation evita que o click no X abra o dialog de arquivo (propagaria para o pai) */}
              <button
                onClick={(e) => { e.stopPropagation(); remove(file.name); }}
                className="text-gray-400 hover:text-red-500 transition-colors dark:text-gray-500 dark:hover:text-red-400"
              >
                <X size={15} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Rodapé com contagem e botão de submit — aparece só quando há arquivos selecionados */}
      {selected.length > 0 && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {selected.length} arquivo{selected.length > 1 ? "s" : ""} selecionado{selected.length > 1 ? "s" : ""}
          </p>
          <button
            onClick={handleSubmit}
            disabled={disabled}
            className="btn-primary w-full sm:w-auto justify-center"
          >
            <Upload size={16} />
            Processar Invoices
          </button>
        </div>
      )}
    </div>
  );
}