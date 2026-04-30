"use client"; // usa hooks e acesso ao DOM (localStorage, classList) — deve ser client component

import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";

// Contexto global de tema — expõe o tema atual e a função de alternância para qualquer componente
const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
  theme: "light",
  toggle: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light"); // estado inicial "light" até o efeito rodar

  useEffect(() => {
    // Sincroniza o estado React com o que o script anti-FOUC de layout.tsx já aplicou no DOM.
    // O script pode ter adicionado a classe "dark" antes da hidratação, então lemos ela aqui
    // para que o estado do React reflita a preferência real do usuário.
    const isDark = document.documentElement.classList.contains("dark");
    setTheme(isDark ? "dark" : "light");
  }, []); // roda apenas uma vez na montagem

  const toggle = () => {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    localStorage.setItem("theme", next);  // persiste a preferência para o próximo carregamento
    // Adiciona/remove a classe "dark" no <html> — o Tailwind usa essa classe para aplicar estilos dark:
    document.documentElement.classList.toggle("dark", next === "dark");
  };

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

// Hook de conveniência — qualquer componente que precise do tema usa: const { theme, toggle } = useTheme()
export function useTheme() {
  return useContext(ThemeContext);
}