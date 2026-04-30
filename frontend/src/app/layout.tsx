// Layout raiz da aplicação Next.js — envolve todas as páginas.
// Define metadados globais (title, description), idioma e o ThemeProvider.

import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";

// Metadados exibidos na aba do navegador e usados por buscadores/Open Graph
export const metadata: Metadata = {
  title: "Invoice Processing Automation",
  description: "Automação de processamento de invoices internacionais — Pecege",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      {/*
        suppressHydrationWarning é necessário porque o script anti-FOUC abaixo
        pode modificar o DOM antes da hidratação do React, causando mismatch.
      */}
      <head>
        {/*
          Script anti-FOUC (Flash of Unstyled Content) para tema escuro.
          Executado de forma síncrona ANTES do React hidratar para evitar
          o piscar de tela claro→escuro ao carregar com preferência dark.
          Lê o localStorage e o prefers-color-scheme do sistema; se dark,
          adiciona a classe "dark" ao <html> imediatamente.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{const t=localStorage.getItem('theme');const p=window.matchMedia('(prefers-color-scheme: dark)').matches;if(t==='dark'||(t===null&&p))document.documentElement.classList.add('dark')}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased dark:bg-gray-900 dark:text-gray-100">
        {/* ThemeProvider disponibiliza o contexto de tema (light/dark) para todos os componentes */}
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}