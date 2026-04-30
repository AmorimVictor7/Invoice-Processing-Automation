"use client";

import { useEffect, useMemo, useState } from "react";
import { History, Loader2, AlertCircle, Building2, FileSpreadsheet, Trash2, Filter, X, Calendar, ChevronDown } from "lucide-react";
import Header from "@/components/Header";
import { fetchHistory, deleteHistoryEntry, deleteAllHistory } from "@/lib/api";
import type { HistoryEntry } from "@/lib/types";

// Formata uma string ISO 8601 para exibição no formato brasileiro (DD/MM/YYYY HH:MM)
function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso; // fallback: exibe a string original se o parse falhar
  }
}

// Formata valor como BRL ou exibe "—" se null (NFs sem conversão de moeda)
function formatBRL(value: number | null) {
  if (value == null) return "—";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);   // todos os registros do histórico
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null); // ID do registro sendo deletado (spinner)
  const [clearingAll, setClearingAll] = useState(false);         // true enquanto "Limpar tudo" está processando

  // Estado dos filtros do painel colapsável
  const [dateFrom, setDateFrom] = useState("");       // data de início (YYYY-MM-DD)
  const [dateTo, setDateTo] = useState("");           // data de fim (YYYY-MM-DD)
  const [supplierFilter, setSupplierFilter] = useState(""); // fornecedor selecionado
  const [filtersOpen, setFiltersOpen] = useState(false);    // painel de filtros expandido ou não

  // Busca o histórico ao montar a página
  useEffect(() => {
    fetchHistory()
      .then(setEntries)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Lista de fornecedores únicos de todos os registros — popula o select de filtro
  const allSuppliers = useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => e.supplier_list.forEach((s) => set.add(s)));
    return Array.from(set).sort();
  }, [entries]);

  // Filtra os registros com base nos critérios ativos (data de/até e fornecedor)
  const filteredEntries = useMemo(() => {
    return entries.filter((entry) => {
      const entryDate = entry.processed_at.slice(0, 10); // extrai só a data (YYYY-MM-DD)
      if (dateFrom && entryDate < dateFrom) return false;
      if (dateTo && entryDate > dateTo) return false;
      if (
        supplierFilter &&
        !entry.supplier_list.some((s) =>
          s.toLowerCase().includes(supplierFilter.toLowerCase())
        )
      )
        return false;
      return true;
    });
  }, [entries, dateFrom, dateTo, supplierFilter]);

  // true quando ao menos um filtro está ativo — exibe badge de contagem e botão "Limpar filtros"
  const hasFilters = dateFrom !== "" || dateTo !== "" || supplierFilter !== "";

  function clearFilters() {
    setDateFrom("");
    setDateTo("");
    setSupplierFilter("");
  }

  // Exclui um único registro após confirmação do usuário
  async function handleDeleteEntry(id: string) {
    if (!confirm("Excluir este registro do histórico?")) return;
    setDeletingId(id); // ativa o spinner no botão daquele registro
    try {
      await deleteHistoryEntry(id);
      setEntries((prev) => prev.filter((e) => e.id !== id)); // remove da lista local sem refetch
    } catch {
      alert("Erro ao excluir registro. Tente novamente.");
    } finally {
      setDeletingId(null);
    }
  }

  // Exclui todos os registros após confirmação com contagem explícita (evitar click acidental)
  async function handleClearAll() {
    if (
      !confirm(
        `Limpar todo o histórico? Esta ação não pode ser desfeita.\n\n${entries.length} registro(s) serão removidos.`
      )
    )
      return;
    setClearingAll(true);
    try {
      await deleteAllHistory();
      setEntries([]); // limpa a lista local sem refetch
    } catch {
      alert("Erro ao limpar histórico. Tente novamente.");
    } finally {
      setClearingAll(false);
    }
  }

  return (
    <>
      <Header />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* Cabeçalho com título e botão "Limpar tudo" (aparece só quando há registros) */}
        <div className="flex flex-wrap items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <History size={22} className="text-blue-600 dark:text-blue-400 shrink-0" />
            <div>
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
                Histórico de Processamentos
              </h1>
              <p className="text-sm text-gray-500 mt-0.5 dark:text-gray-400">
                Registros de todos os pacotes gerados.
              </p>
            </div>
          </div>

          {entries.length > 0 && (
            <button
              onClick={handleClearAll}
              disabled={clearingAll}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-red-600 border border-red-200 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:text-red-400 dark:border-red-700 dark:hover:bg-red-900/20"
            >
              {clearingAll ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Trash2 size={15} />
              )}
              Limpar tudo
            </button>
          )}
        </div>

        {/* Painel de filtros — colapsável, só aparece quando há registros carregados */}
        {!loading && !error && entries.length > 0 && (
          <div className="card overflow-hidden">
            {/* Cabeçalho clicável do painel — expande/colapsa os controles */}
            <button
              type="button"
              onClick={() => setFiltersOpen((v) => !v)}
              className="w-full flex items-center justify-between px-4 py-3 bg-gray-50/80 dark:bg-gray-700/40 hover:bg-gray-100/80 dark:hover:bg-gray-700/60 transition-colors"
            >
              <div className="flex items-center gap-2">
                <div className="flex items-center justify-center w-6 h-6 rounded-md bg-blue-100 dark:bg-blue-900/40">
                  <Filter size={13} className="text-blue-600 dark:text-blue-400" />
                </div>
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">Filtros</span>
                {/* Badge azul com contagem de filtros ativos */}
                {hasFilters && (
                  <span className="inline-flex items-center rounded-full bg-blue-600 text-white text-[10px] font-bold w-4 h-4 justify-center">
                    {[dateFrom, dateTo, supplierFilter].filter(Boolean).length}
                  </span>
                )}
              </div>
              {/* Seta que rotaciona 180° quando expandido */}
              <ChevronDown
                size={16}
                className={`text-gray-400 dark:text-gray-500 transition-transform duration-200 ${filtersOpen ? "rotate-180" : ""}`}
              />
            </button>

            {/* Controles de filtro — visíveis apenas quando o painel está expandido */}
            {filtersOpen && (
              <>
                <div className="flex flex-wrap gap-4 px-4 py-4 border-t border-gray-100 dark:border-gray-700">
                  {/* Filtro de período: dois inputs de data (de / até) */}
                  <div className="flex flex-col gap-1.5 min-w-[280px] flex-1">
                    <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                      <Calendar size={11} />
                      Período
                    </label>
                    <div className="flex items-center gap-2">
                      {/* max={dateTo} impede selecionar data de início depois do fim */}
                      <input
                        type="date"
                        value={dateFrom}
                        max={dateTo || undefined}
                        onChange={(e) => setDateFrom(e.target.value)}
                        className={`field-input text-sm flex-1 ${dateFrom ? "border-blue-400 dark:border-blue-500" : ""}`}
                      />
                      <span className="text-gray-300 dark:text-gray-600 shrink-0 text-sm">→</span>
                      {/* min={dateFrom} impede selecionar data de fim antes do início */}
                      <input
                        type="date"
                        value={dateTo}
                        min={dateFrom || undefined}
                        onChange={(e) => setDateTo(e.target.value)}
                        className={`field-input text-sm flex-1 ${dateTo ? "border-blue-400 dark:border-blue-500" : ""}`}
                      />
                    </div>
                  </div>

                  {/* Filtro de fornecedor: select populado com fornecedores únicos do histórico */}
                  <div className="flex flex-col gap-1.5 min-w-[200px]">
                    <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                      <Building2 size={11} />
                      Fornecedor
                    </label>
                    <div className="relative">
                      <select
                        value={supplierFilter}
                        onChange={(e) => setSupplierFilter(e.target.value)}
                        className={`field-input text-sm pr-8 appearance-none ${supplierFilter ? "border-blue-400 dark:border-blue-500" : ""}`}
                      >
                        <option value="">Todos os fornecedores</option>
                        {allSuppliers.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                      {/* Ícone de seta customizado para o select (appearance-none remove a seta nativa) */}
                      <ChevronDown
                        size={14}
                        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500"
                      />
                    </div>
                  </div>
                </div>

                {/* Rodapé do painel de filtros: contagem de resultados e botão limpar */}
                <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-700/20">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {hasFilters ? (
                      filteredEntries.length === entries.length ? (
                        <span>{entries.length} registro{entries.length !== 1 ? "s" : ""}</span>
                      ) : (
                        <>
                          <span className="font-semibold text-blue-600 dark:text-blue-400">{filteredEntries.length}</span>
                          {" de "}
                          {entries.length} registro{entries.length !== 1 ? "s" : ""} encontrado{filteredEntries.length !== 1 ? "s" : ""}
                        </>
                      )
                    ) : (
                      <span>{entries.length} registro{entries.length !== 1 ? "s" : ""} no total</span>
                    )}
                  </p>
                  {hasFilters && (
                    <button
                      onClick={clearFilters}
                      className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                    >
                      <X size={12} />
                      Limpar filtros
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* Estado: carregando */}
        {loading && (
          <div className="flex items-center gap-3 p-8 text-gray-500 dark:text-gray-400">
            <Loader2 className="animate-spin" size={20} />
            Carregando histórico…
          </div>
        )}

        {/* Estado: erro ao buscar */}
        {error && (
          <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 px-4 py-3 dark:bg-red-900/20 dark:border-red-700">
            <AlertCircle size={18} className="text-red-500 shrink-0 mt-0.5 dark:text-red-400" />
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Estado: histórico vazio (nunca processou nada) */}
        {!loading && !error && entries.length === 0 && (
          <div className="card p-8 sm:p-12 flex flex-col items-center gap-3 text-center">
            <FileSpreadsheet size={40} className="text-gray-300 dark:text-gray-600" />
            <p className="text-base font-semibold text-gray-500 dark:text-gray-400">
              Nenhum processamento registrado ainda.
            </p>
            <p className="text-sm text-gray-400 dark:text-gray-500">
              Processe invoices na aba{" "}
              <span className="font-medium text-blue-600 dark:text-blue-400">Processar</span> para
              ver o histórico aqui.
            </p>
          </div>
        )}

        {/* Estado: filtros ativos mas nenhum registro corresponde */}
        {!loading && !error && entries.length > 0 && filteredEntries.length === 0 && (
          <div className="card p-10 flex flex-col items-center gap-3 text-center">
            <Filter size={32} className="text-gray-300 dark:text-gray-600" />
            <p className="text-base font-semibold text-gray-500 dark:text-gray-400">
              Nenhum registro encontrado com os filtros aplicados.
            </p>
            <button
              onClick={clearFilters}
              className="text-sm text-blue-600 hover:underline dark:text-blue-400"
            >
              Limpar filtros
            </button>
          </div>
        )}

        {/* Tabela de registros filtrados */}
        {!loading && filteredEntries.length > 0 && (
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 dark:bg-gray-700/50 dark:border-gray-700">
                    <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide dark:text-gray-400">Data</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide dark:text-gray-400">Fornecedores</th>
                    <th className="text-center px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide dark:text-gray-400">Qtd</th>
                    <th className="text-right px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide dark:text-gray-400">Total (BRL)</th>
                    {/* Coluna "Arquivo Excel" oculta em telas pequenas */}
                    <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide dark:text-gray-400 hidden md:table-cell">Arquivo Excel</th>
                    {/* coluna vazia para o botão de deletar */}
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {filteredEntries.map((entry, i) => (
                    // Linhas alternadas com fundo levemente diferente (zebra)
                    <tr
                      key={entry.id}
                      className={
                        i % 2 === 0
                          ? "bg-white dark:bg-gray-800"
                          : "bg-gray-50/60 dark:bg-gray-700/30"
                      }
                    >
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap dark:text-gray-300 text-xs sm:text-sm">
                        {formatDate(entry.processed_at)}
                      </td>
                      {/* Tags de fornecedores — múltiplos por registro */}
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {entry.supplier_list.map((s) => (
                            <span
                              key={s}
                              className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5 text-xs text-blue-700 font-medium dark:bg-blue-900/30 dark:text-blue-400"
                            >
                              <Building2 size={10} />
                              {s}
                            </span>
                          ))}
                        </div>
                      </td>
                      {/* Bolinha com a quantidade de NFs do lote */}
                      <td className="px-4 py-3 text-center">
                        <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-gray-100 text-xs font-bold text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                          {entry.invoice_count}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-medium text-gray-800 whitespace-nowrap dark:text-gray-200 text-xs sm:text-sm">
                        {formatBRL(entry.total_amount_brl)}
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs truncate max-w-[200px] dark:text-gray-400 hidden md:table-cell">
                        {entry.excel_filename}
                      </td>
                      {/* Botão de deletar individual com spinner durante a operação */}
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleDeleteEntry(entry.id)}
                          disabled={deletingId === entry.id}
                          className="p-1.5 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors dark:text-gray-500 dark:hover:text-red-400 dark:hover:bg-red-900/20"
                          title="Excluir registro"
                        >
                          {deletingId === entry.id ? (
                            <Loader2 size={15} className="animate-spin" />
                          ) : (
                            <Trash2 size={15} />
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </>
  );
}