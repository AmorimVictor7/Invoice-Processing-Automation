@echo off
cd /d "%~dp0"
if not exist ".env" (
    copy .env.example .env
    echo .env criado a partir do .env.example — configure as variaveis antes de usar.
)
call venv\Scripts\activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
