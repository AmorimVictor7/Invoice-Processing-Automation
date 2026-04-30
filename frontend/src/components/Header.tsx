"use client"; // precisa de hooks (usePathname, useTheme)

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, History, BarChart2, Sun, Moon } from "lucide-react";
import clsx from "clsx";
import { useTheme } from "./ThemeProvider";

export default function Header() {
  const path = usePathname();          // rota ativa — usada para realçar o link de navegação correto
  const { theme, toggle } = useTheme(); // tema atual e função para alternar claro/escuro

  return (
    // Header fixo no topo (sticky + z-30) para ficar visível durante o scroll
    <header className="sticky top-0 z-30 bg-white border-b border-gray-200 shadow-sm dark:bg-gray-800 dark:border-gray-700">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">

        {/* Logo e nome da aplicação */}
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-blue-600 shrink-0">
            <FileText size={18} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-900 leading-tight dark:text-gray-100">Invoice Processing</p>
            {/* Subtítulo oculto em mobile para economizar espaço */}
            <p className="text-xs text-gray-400 leading-tight dark:text-gray-500 hidden sm:block">Pecege — Automação Financeira</p>
          </div>
        </div>

        {/* Navegação principal + botão de tema */}
        <nav className="flex items-center gap-0.5 sm:gap-1">

          {/* Link "Processar" (página principal) — ativo quando path === "/" */}
          <Link
            href="/"
            className={clsx(
              "flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              path === "/"
                ? "bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400"    // estilo ativo
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-700" // estilo inativo
            )}
          >
            <FileText size={15} />
            <span className="hidden sm:inline">Processar</span>
          </Link>

          {/* Link "Histórico" */}
          <Link
            href="/history"
            className={clsx(
              "flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              path === "/history"
                ? "bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400"
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-700"
            )}
          >
            <History size={15} />
            <span className="hidden sm:inline">Histórico</span>
          </Link>

          {/* Link "Dashboard" */}
          <Link
            href="/dashboard"
            className={clsx(
              "flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              path === "/dashboard"
                ? "bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400"
                : "text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-700"
            )}
          >
            <BarChart2 size={15} />
            <span className="hidden sm:inline">Dashboard</span>
          </Link>

          {/* Botão de alternância claro/escuro — exibe ícone inverso ao tema atual */}
          <button
            onClick={toggle}
            className="ml-1 sm:ml-2 p-2 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-700 transition-colors"
            title={theme === "dark" ? "Modo claro" : "Modo escuro"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </nav>
      </div>
    </header>
  );
}