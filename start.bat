@echo off
cd /d "%~dp0"

echo Iniciando backend...
start "Backend" cmd /k "cd backend && venv\Scripts\activate && uvicorn main:app --reload"

echo Iniciando frontend...
start "Frontend" cmd /k "cd frontend && (if not exist node_modules npm install) && npm run dev"
