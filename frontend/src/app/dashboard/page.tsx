"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BarChart2,
  Loader2,
  AlertCircle,
  TrendingUp,
  Building2,
  FileText,
  DollarSign,
} from "lucide-react";
import Header from "@/components/Header";
import { fetchHistory } from "@/lib/api";
import type { HistoryEntry, InvoiceData } from "@/lib/types";

// Formatadores de exibição 

// Formata número como moeda BRL (ex: R$ 1.234,56)
function formatBRL(value: number) {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

// Versão abreviada para eixos de gráfico (ex: R$1,2M, R$500k)
function shortBRL(v: number): string {
  if (v >= 1_000_000) return `R$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `R$${(v / 1_000).toFixed(0)}k`;
  return `R$${v.toFixed(0)}`;
}

// Converte "2024-03" → "Mar/24" para os rótulos do eixo X do gráfico mensal
function fmtMonth(m: string): string {
  const [y, mo] = m.split("-");
  const names = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
  return `${names[parseInt(mo) - 1]}/${y.slice(2)}`;
}

//  Paletas de cores 

// Cores dos fornecedores no gráfico de barras (rotacionadas por índice)
const SUPPLIER_COLORS = [
  "bg-blue-500", "bg-violet-500", "bg-emerald-500", "bg-amber-500",
  "bg-rose-500", "bg-cyan-500", "bg-pink-500", "bg-orange-500",
];

// Cor fixa por moeda no gráfico de distribuição
const CURRENCY_COLORS: Record<string, string> = {
  USD: "bg-emerald-500",
  EUR: "bg-blue-500",
  GBP: "bg-violet-500",
  BRL: "bg-yellow-400",
  CAD: "bg-red-500",
  JPY: "bg-pink-500",
  CHF: "bg-teal-500",
  AUD: "bg-orange-500",
};

// Componentes internos 

// Card de KPI com ícone colorido, título, valor principal e subtítulo opcional
function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  accent: string; // classe Tailwind de cor de fundo do ícone (ex: "bg-blue-600")
}) {
  return (
    <div className="card p-4 sm:p-5 flex items-start gap-3 sm:gap-4">
      <div className={`w-9 h-9 sm:w-10 sm:h-10 rounded-xl flex items-center justify-center shrink-0 ${accent}`}>
        <Icon size={18} className="text-white" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">
          {label}
        </p>
        <p className="text-lg sm:text-2xl font-bold text-gray-900 dark:text-gray-100 mt-0.5 leading-tight tabular-nums break-all">
          {value}
        </p>
        {sub && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{sub}</p>
        )}
      </div>
    </div>
  );
}

// Gráfico de barras horizontais mostrando despesa total por fornecedor.
// A barra mais larga corresponde ao maior valor (100%); as demais são proporcionais.
function SupplierBars({
  data,
}: {
  data: Array<{ name: string; brl: number; count: number }>;
}) {
  const max = Math.max(...data.map((d) => d.brl), 1); // evita divisão por zero
  const total = data.reduce((s, d) => s + d.brl, 0);

  return (
    <div className="space-y-3.5">
      {data.map((d, i) => {
        const widthPct = (d.brl / max) * 100;            // largura proporcional ao maior valor
        const sharePct = total > 0 ? (d.brl / total) * 100 : 0; // participação percentual no total
        return (
          <div key={d.name} className="flex items-center gap-2 sm:gap-3">
            {/* Nome do fornecedor (truncado) */}
            <span className="w-20 sm:w-28 text-right text-xs sm:text-sm text-gray-600 dark:text-gray-400 truncate shrink-0 font-medium">
              {d.name}
            </span>
            {/* Barra de progresso */}
            <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-3 sm:h-4 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-700 ${SUPPLIER_COLORS[i % SUPPLIER_COLORS.length]}`}
                style={{ width: `${widthPct}%` }}
              />
            </div>
            {/* Valores numéricos à direita: percentual, valor BRL e quantidade de NFs */}
            <div className="flex items-center gap-1.5 sm:gap-3 shrink-0">
              <span className="text-xs text-gray-400 dark:text-gray-500 w-7 sm:w-8 text-right tabular-nums">
                {sharePct.toFixed(0)}%
              </span>
              <span className="text-xs sm:text-sm font-semibold text-gray-700 dark:text-gray-200 w-20 sm:w-28 text-right tabular-nums">
                {formatBRL(d.brl)}
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500 w-10 sm:w-16 hidden xs:block">
                {d.count} inv.
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Gráfico de linha SVG desenhado manualmente (sem biblioteca externa).
// Só é exibido quando há dados de 2 ou mais meses diferentes.
function MonthlyChart({ data }: { data: Array<{ month: string; total: number }> }) {
  if (data.length < 2) return null; // linha precisaria de pelo menos 2 pontos

  // Dimensões do SVG e padding interno para acomodar rótulos
  const W = 800, H = 200;
  const PAD = { top: 20, right: 20, bottom: 38, left: 72 };
  const iW = W - PAD.left - PAD.right;  // largura da área interna do gráfico
  const iH = H - PAD.top - PAD.bottom;
  const maxY = Math.max(...data.map((d) => d.total), 1) * 1.2; // 20% de margem acima do maior valor

  // Calcula as coordenadas SVG de cada ponto de dado
  const pts = data.map((d, i) => ({
    x: PAD.left + (i / (data.length - 1)) * iW, // distribuição uniforme no eixo X
    y: PAD.top + iH - (d.total / maxY) * iH,    // valor mapeado para coordenada Y (invertida)
  }));

  // Gera o atributo "d" de um path SVG com curvas de Bézier cúbicas para suavizar a linha
  function smoothD(points: { x: number; y: number }[]): string {
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const cx = (points[i].x + points[i + 1].x) / 2; // ponto de controle no meio horizontal
      d += ` C ${cx} ${points[i].y}, ${cx} ${points[i + 1].y}, ${points[i + 1].x} ${points[i + 1].y}`;
    }
    return d;
  }

  const linePath = smoothD(pts);
  // areaPath: linha + fecha a área abaixo com duas linhas horizontais para o gradiente de preenchimento
  const areaPath = `${linePath} L ${pts[pts.length - 1].x} ${PAD.top + iH} L ${pts[0].x} ${PAD.top + iH} Z`;
  const gridPcts = [0.25, 0.5, 0.75, 1.0]; // linhas de grade em 25%, 50%, 75% e 100% do maxY

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 220 }}>
      <defs>
        {/* Gradiente vertical para o preenchimento da área abaixo da linha */}
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.01" />
        </linearGradient>
      </defs>

      {/* Linhas de grade horizontais com rótulos de valor no eixo Y */}
      {gridPcts.map((pct, i) => {
        const gy = PAD.top + iH - pct * iH;
        return (
          <g key={i}>
            <line
              x1={PAD.left} y1={gy} x2={W - PAD.right} y2={gy}
              stroke="rgba(156,163,175,0.35)" strokeWidth="1" strokeDasharray="4 3"
            />
            <text x={PAD.left - 6} y={gy + 4} textAnchor="end" fontSize="10" fill="#9ca3af">
              {shortBRL(maxY * pct)}
            </text>
          </g>
        );
      })}

      {/* Área de preenchimento abaixo da linha */}
      <path d={areaPath} fill="url(#areaGrad)" />

      {/* Linha principal */}
      <path
        d={linePath}
        fill="none"
        stroke="#3b82f6"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Pontos nos vértices da linha */}
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="4" fill="#3b82f6" stroke="white" strokeWidth="2" />
      ))}

      {/* Rótulos do eixo X (mês/ano) */}
      {data.map((d, i) => (
        <text key={i} x={pts[i].x} y={H - 6} textAnchor="middle" fontSize="10" fill="#9ca3af">
          {fmtMonth(d.month)}
        </text>
      ))}
    </svg>
  );
}

//  Página principal 

export default function DashboardPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Busca o histórico completo ao montar a página
  useEffect(() => {
    fetchHistory()
      .then(setEntries)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Achata todas as NFs de todos os lotes em uma única lista para cálculos de dashboard
  const allInvoices: InvoiceData[] = useMemo(
    () => entries.flatMap((e) => e.invoices_json ?? []),
    [entries]
  );

  // Agrega despesa total (BRL) e contagem por fornecedor, ordenado do maior para o menor
  const bySupplier = useMemo(() => {
    const map = new Map<string, { brl: number; count: number }>();
    for (const inv of allInvoices) {
      if (!inv.supplier) continue;
      const cur = map.get(inv.supplier) ?? { brl: 0, count: 0 };
      map.set(inv.supplier, {
        brl: cur.brl + (inv.converted_amount ?? 0),
        count: cur.count + 1,
      });
    }
    return Array.from(map.entries())
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => b.brl - a.brl); // maior despesa primeiro
  }, [allInvoices]);

  // Agrega despesa total por mês (YYYY-MM), ordenado cronologicamente para o gráfico de linha
  const byMonth = useMemo(() => {
    const map = new Map<string, number>();
    for (const inv of allInvoices) {
      if (!inv.issue_date) continue;
      const m = inv.issue_date.slice(0, 7); // extrai "YYYY-MM" da data "YYYY-MM-DD"
      map.set(m, (map.get(m) ?? 0) + (inv.converted_amount ?? 0));
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b)) // ordem cronológica
      .map(([month, total]) => ({ month, total }));
  }, [allInvoices]);

  // Conta NFs por moeda para o gráfico de distribuição (barras de porcentagem)
  const byCurrency = useMemo(() => {
    const map = new Map<string, number>();
    for (const inv of allInvoices) {
      if (!inv.currency) continue;
      map.set(inv.currency, (map.get(inv.currency) ?? 0) + 1);
    }
    const total = allInvoices.filter((i) => i.currency).length;
    return Array.from(map.entries())
      .sort(([, a], [, b]) => b - a) // mais frequente primeiro
      .map(([currency, count]) => ({
        currency,
        count,
        pct: total > 0 ? (count / total) * 100 : 0, // percentual para a barra
      }));
  }, [allInvoices]);

  // KPIs do cabeçalho
  const totalBRL = useMemo(
    () => bySupplier.reduce((s, x) => s + x.brl, 0),
    [bySupplier]
  );
  const totalInvoices = allInvoices.length;
  const totalSuppliers = bySupplier.length;
  const avgPerInvoice = totalInvoices > 0 ? totalBRL / totalInvoices : 0;
  const isEmpty = !loading && !error && allInvoices.length === 0;

  return (
    <>
      <Header />
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* Título */}
        <div className="flex items-center gap-3">
          <BarChart2 size={22} className="text-blue-600 dark:text-blue-400" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              Dashboard de Despesas
            </h1>
            <p className="text-sm text-gray-500 mt-0.5 dark:text-gray-400">
              Visão consolidada por fornecedor.
            </p>
          </div>
        </div>

        {/* Estado: carregando */}
        {loading && (
          <div className="flex items-center gap-3 p-8 text-gray-500 dark:text-gray-400">
            <Loader2 className="animate-spin" size={20} />
            Carregando dados…
          </div>
        )}

        {/* Estado: erro ao buscar histórico */}
        {error && (
          <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 px-4 py-3 dark:bg-red-900/20 dark:border-red-700">
            <AlertCircle size={18} className="text-red-500 shrink-0 mt-0.5 dark:text-red-400" />
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Estado: histórico vazio (nenhum processamento ainda) */}
        {isEmpty && (
          <div className="card p-8 sm:p-12 flex flex-col items-center gap-3 text-center">
            <BarChart2 size={40} className="text-gray-300 dark:text-gray-600" />
            <p className="text-base font-semibold text-gray-500 dark:text-gray-400">
              Nenhum dado para exibir.
            </p>
            <p className="text-sm text-gray-400 dark:text-gray-500">
              Processe invoices na aba{" "}
              <span className="font-medium text-blue-600 dark:text-blue-400">Processar</span>{" "}
              para ver o dashboard.
            </p>
          </div>
        )}

        {/* Conteúdo principal — só exibido quando há dados */}
        {!loading && !error && !isEmpty && (
          <>
            {/* Linha de KPIs: 4 cards (2x2 no mobile, 1x4 no desktop) */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              <KpiCard icon={DollarSign} label="Total Gasto (BRL)" value={formatBRL(totalBRL)} accent="bg-blue-600" />
              <KpiCard
                icon={Building2}
                label="Fornecedores"
                value={String(totalSuppliers)}
                sub={`${entries.length} processamento${entries.length !== 1 ? "s" : ""}`}
                accent="bg-violet-600"
              />
              <KpiCard icon={FileText} label="Invoices" value={String(totalInvoices)} accent="bg-emerald-600" />
              <KpiCard icon={TrendingUp} label="Média por Invoice" value={formatBRL(avgPerInvoice)} accent="bg-amber-500" />
            </div>

            {/* Gráfico de fornecedores (2/3 da largura) + Distribuição por moeda (1/3) */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="card p-5 lg:col-span-2">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-5">
                  Despesas por Fornecedor
                </h2>
                {bySupplier.length > 0 ? (
                  <SupplierBars data={bySupplier} />
                ) : (
                  <p className="text-sm text-gray-400 dark:text-gray-500">Sem dados.</p>
                )}
              </div>

              <div className="card p-5">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-5">
                  Distribuição por Moeda
                </h2>
                <div className="space-y-4">
                  {byCurrency.map((c) => (
                    <div key={c.currency} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-gray-600 dark:text-gray-400">
                          {c.currency}
                        </span>
                        <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                          {c.count} inv. · {c.pct.toFixed(0)}%
                        </span>
                      </div>
                      {/* Barra de porcentagem colorida por moeda */}
                      <div className="h-2.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${CURRENCY_COLORS[c.currency] ?? "bg-gray-400"}`}
                          style={{ width: `${c.pct}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Gráfico de evolução mensal — só aparece quando há pelo menos 2 meses distintos */}
            {byMonth.length >= 2 && (
              <div className="card p-5">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-4">
                  Evolução Mensal (BRL)
                </h2>
                <MonthlyChart data={byMonth} />
              </div>
            )}
          </>
        )}
      </main>
    </>
  );
}