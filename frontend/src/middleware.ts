/**
 * Next.js Middleware — proteção de rotas.
 *
 * Regras:
 *   - /login → acessível sem autenticação
 *   - Todo o resto → requer cookie `access_token`
 *
 * O middleware apenas verifica a PRESENÇA do cookie (não verifica assinatura JWT,
 * pois o segredo fica somente no backend). Se o token estiver expirado, o primeiro
 * request autenticado retorna 401, o AuthContext chama /api/auth/refresh e retenta.
 */
import { type NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = new Set(["/login"]);

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Permite rotas públicas e assets Next.js sem verificação
  if (
    PUBLIC_PATHS.has(pathname) ||
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/favicon")
  ) {
    return NextResponse.next();
  }

  const hasToken = request.cookies.has("access_token");

  if (!hasToken) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);   // preserva destino para redirect pós-login
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Intercepta todas as rotas exceto:
     * - /api/* (Next.js API routes — não usadas aqui, mas por segurança)
     * - /_next/static, /_next/image
     * - /favicon.ico
     */
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
  ],
};
