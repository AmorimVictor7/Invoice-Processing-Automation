/**
 * Camada de comunicação com a API do backend.
 *
 * Todos os requests incluem `credentials: "include"` para enviar os cookies
 * httpOnly de autenticação automaticamente.
 *
 * Interceptor 401:
 *   1. Tenta renovar o access token via POST /api/auth/refresh
 *   2. Se bem-sucedido, repete o request original
 *   3. Se falhar, redireciona para /login
 */
import type {
  AuthResponse,
  ConfirmResponse,
  HistoryEntry,
  InvoiceData,
  UploadResponse,
  User,
} from "./types";

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api";

// ── Interceptor central ───────────────────────────────────────────────────────

let _isRefreshing = false;
let _refreshPromise: Promise<boolean> | null = null;

async function _tryRefresh(): Promise<boolean> {
  if (_isRefreshing && _refreshPromise) return _refreshPromise;
  _isRefreshing = true;
  _refreshPromise = fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      _isRefreshing = false;
      _refreshPromise = null;
    });
  return _refreshPromise;
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const opts: RequestInit = { ...init, credentials: "include" };
  const res = await fetch(url, opts);

  if (res.status === 401) {
    const refreshed = await _tryRefresh();
    if (!refreshed) {
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
      throw new Error("Sessão expirada.");
    }
    const retry = await fetch(url, opts);
    if (!retry.ok) {
      const err = await retry.json().catch(() => ({ detail: retry.statusText }));
      throw new Error(err.detail || "Erro na requisição.");
    }
    return retry.json() as Promise<T>;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Erro na requisição.");
  }
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
// Endpoints de auth usam fetch direto (sem interceptor de redirect)
// para evitar loop infinito na verificação inicial de sessão.

export async function apiLogin(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Credenciais inválidas.");
  }
  return res.json();
}

export async function apiRegister(
  name: string,
  email: string,
  password: string
): Promise<AuthResponse> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Erro ao criar conta.");
  }
  return res.json();
}

export async function apiLogout(): Promise<void> {
  await fetch(`${BASE}/auth/logout`, { method: "POST", credentials: "include" });
}

export async function apiGetMe(): Promise<{ user: User }> {
  // Sem interceptor: se não autenticado, simplesmente lança erro (AuthContext trata como user=null)
  const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

// ── Invoices ──────────────────────────────────────────────────────────────────

export async function uploadInvoices(files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  return request<UploadResponse>(`${BASE}/invoices/upload`, {
    method: "POST",
    body: form,
    // Sem Content-Type — browser define o boundary correto para multipart
  });
}

export async function confirmInvoices(
  session_id: string,
  invoices: InvoiceData[]
): Promise<ConfirmResponse> {
  return request<ConfirmResponse>(`${BASE}/invoices/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, invoices }),
  });
}

// ── History ───────────────────────────────────────────────────────────────────

export async function fetchHistory(): Promise<HistoryEntry[]> {
  const data = await request<{ entries: HistoryEntry[]; total: number }>(
    `${BASE}/history/`
  );
  return data.entries;
}

export async function deleteHistoryEntry(id: string): Promise<void> {
  await request(`${BASE}/history/${id}`, { method: "DELETE" });
}

export async function deleteAllHistory(): Promise<void> {
  await request(`${BASE}/history/all`, { method: "DELETE" });
}
