@echo off
cd /d "%~dp0"
if not exist ".env" (
    copy .env.example .env
    echo .env criado a partir do .env.example — configure as variaveis antes de usar.
)
if not exist "venv\Scripts\activate" (
    echo Criando ambiente virtual...
    python -m venv venv
)
call venv\Scripts\activate
if not exist "venv\Lib\site-packages\uvicorn" (
    echo Instalando dependencias...
    pip install -r requirements.txt
)
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
