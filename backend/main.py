# Módulo de entrada do servidor FastAPI.
# Configura o app, CORS e registra os roteadores de invoices e histórico.

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db
from routers import history, invoices

# Carrega as variáveis de ambiente do arquivo .env (ANTHROPIC_KEY, FRONTEND_URL, etc.)
load_dotenv()

# Configura o logger global: exibe timestamp, nível (INFO/WARNING/ERROR) e módulo de origem
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# URL do frontend — usada para liberar CORS; padrão localhost em desenvolvimento
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
APP_ENV = os.getenv("APP_ENV", "development")


# Lifespan: código executado na inicialização do servidor (antes de aceitar requests).
# Aqui garante que a tabela SQLite existe antes de qualquer chamada de API.
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield  # servidor fica ativo até ser encerrado


# Instância principal do FastAPI com metadados exibidos no Swagger UI (/docs)
app = FastAPI(
    title="Invoice Processing API",
    description="API para automação de processamento de invoices internacionais.",
    version="1.0.0",
    lifespan=lifespan,
)

# Origens permitidas no CORS (navegador bloqueia requests de origens não listadas)
_cors_origins = [FRONTEND_URL, "http://localhost:3000"]
# Em desenvolvimento, qualquer porta localhost é aceita (útil para Next.js em :3000, :3001...)
_cors_regex = r"http://localhost(:\d+)?" if APP_ENV == "development" else None

# Middleware que adiciona os headers CORS em todas as respostas
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],   # GET, POST, DELETE, etc.
    allow_headers=["*"],   # Content-Type, Authorization, etc.
)

# Registra as rotas de invoices sob /api/invoices (upload, confirm, download)
app.include_router(invoices.router, prefix="/api/invoices", tags=["Invoices"])
# Registra as rotas de histórico sob /api/history (list, delete)
app.include_router(history.router, prefix="/api/history", tags=["History"])


# Endpoint de health check — usado por load balancers e monitoramento para verificar se o servidor está de pé
@app.get("/health")
def health():
    return {"status": "ok"}