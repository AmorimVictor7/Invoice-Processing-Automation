import io
import json
import logging
import os
import re
from typing import Dict, Tuple

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# System instruction espelhada do projeto invoice-reader no AI Studio
_SYSTEM_INSTRUCTION = """\
Você terá como tarefa ler arquivos de invoices e encontrar as seguintes informações:
- Nome do fornecedor
- Invoice number
- Data de emissão
- Período de cobrança
- Valor total
- Moeda
- Descrição do serviço
- Taxas adicionais
- Subtotal
- Impostos, se existirem
- Valor final\
"""

# Prompt de usuário: define apenas o formato de saída (JSON) sem repetir os campos
_EXTRACTION_PROMPT = """\
Analise o documento e retorne SOMENTE um objeto JSON válido, sem nenhum texto antes ou depois, \
sem blocos markdown, sem comentários.

Estrutura exata (sem alterar os nomes das chaves):
{
  "raw_text": "<texto completo extraído literalmente do documento>",
  "supplier": "<nome do fornecedor>",
  "invoice_number": "<número da invoice>",
  "issue_date": "<data de emissão no formato YYYY-MM-DD ou null>",
  "billing_period": "<período de cobrança ex: March 2024, Jan-Mar 2024 ou null>",
  "description": "<descrição do serviço ou produto>",
  "currency": "<código ISO 4217: USD, EUR, BRL, GBP, JPY, etc. ou null>",
  "subtotal": <número float do subtotal ou null>,
  "taxes": <número float dos impostos ou null>,
  "additional_fees": <número float de taxas adicionais ou null>,
  "total_amount": <número float do valor final ou null>,
  "confidence": {
    "supplier": <0.0 a 1.0>,
    "invoice_number": <0.0 a 1.0>,
    "issue_date": <0.0 a 1.0>,
    "billing_period": <0.0 a 1.0>,
    "description": <0.0 a 1.0>,
    "currency": <0.0 a 1.0>,
    "subtotal": <0.0 a 1.0>,
    "taxes": <0.0 a 1.0>,
    "additional_fees": <0.0 a 1.0>,
    "total_amount": <0.0 a 1.0>
  }
}

Regras de confiança:
- 0.90–1.0  : campo explicitamente rotulado no documento
- 0.70–0.89 : campo presente mas inferido pelo contexto
- 0.50–0.69 : campo incerto, requer interpretação
- 0.0       : campo ausente no documento (valor deve ser null)

Regras para valores financeiros:
- Retorne sempre como float, sem símbolos de moeda nem separadores de milhar
- "R$ 1.234,56" → 1234.56  |  "$1,234.56" → 1234.56  |  "1.234,56 EUR" → 1234.56
"""


def _parse_json_response(text: str) -> dict:
    """
    Extrai o JSON da resposta do Gemini de forma robusta.
    Lida com respostas que incluem markdown, texto extra antes/depois do JSON, etc.
    """
    text = text.strip()

    # Remove bloco markdown ```json ... ``` ou ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    text = text.strip()

    # Tenta parse direto
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extrai o primeiro objeto JSON encontrado no texto
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())

    raise ValueError(f"Nenhum JSON válido encontrado na resposta do Gemini. Resposta recebida:\n{text[:500]}")


def extract_invoice_with_gemini(content: bytes, filename: str) -> Tuple[str, Dict, Dict]:
    """
    Envia o documento (PDF ou imagem) ao Gemini e retorna os dados estruturados da invoice.

    Returns:
        (raw_text, fields_dict, confidence_dict)

    Raises:
        RuntimeError: se GEMINI_API_KEY não estiver configurada ou a chamada falhar.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=_SYSTEM_INSTRUCTION,
        generation_config=genai.GenerationConfig(temperature=0.1),
    )

    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        # PDF enviado diretamente — Gemini lê todas as páginas nativamente, sem precisar de Poppler
        document_part = {"mime_type": "application/pdf", "data": content}
        parts = [_EXTRACTION_PROMPT, document_part]
        logger.info("Enviando PDF '%s' ao Gemini (%s) como inline data", filename, GEMINI_MODEL)
    else:
        parts = [_EXTRACTION_PROMPT, Image.open(io.BytesIO(content))]
        logger.info("Enviando imagem '%s' ao Gemini (%s)", filename, GEMINI_MODEL)

    response = model.generate_content(parts)
    logger.debug("Resposta bruta do Gemini para %s:\n%s", filename, response.text[:300])

    result = _parse_json_response(response.text)

    raw_text = result.pop("raw_text", "")
    confidence = result.pop("confidence", {})

    found = [k for k, v in result.items() if v is not None]
    logger.info("Gemini extraiu %d campos de %s: %s", len(found), filename, found)

    return raw_text, result, confidence
