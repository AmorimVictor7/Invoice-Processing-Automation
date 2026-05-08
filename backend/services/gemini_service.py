"""
Serviço Gemini com circuit breaker e retry com backoff exponencial.

Circuit breaker:
  - Após 5 falhas consecutivas, abre o circuito por 5 minutos
  - Em circuito aberto, lança GeminiCircuitOpenError para o OCR service usar fallback

Retry:
  - Até 2 tentativas adicionais (3 total) com espera 1s → 2s
  - Erros de quota/rate-limit NÃO são retentados (já são limitantes)
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import time
from typing import Dict, Tuple

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

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


# ── Circuit Breaker ───────────────────────────────────────────────────────────

class GeminiCircuitOpenError(RuntimeError):
    """Levantado quando o circuit breaker está aberto (muitas falhas recentes)."""


class _CircuitBreaker:
    def __init__(self, threshold: int = 5, reset_after: int = 300):
        self._failures = 0
        self._threshold = threshold
        self._opened_at: float = 0.0
        self._reset_after = reset_after   # segundos até auto-reset

    @property
    def is_open(self) -> bool:
        if self._failures >= self._threshold:
            if time.time() - self._opened_at > self._reset_after:
                self._failures = 0        # reset automático após timeout
                logger.info("Circuit breaker Gemini: reset automático após %ds", self._reset_after)
                return False
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.time()
            logger.warning(
                "Circuit breaker Gemini ABERTO após %d falhas. Fechará em %ds.",
                self._failures, self._reset_after,
            )


_circuit = _CircuitBreaker(threshold=5, reset_after=300)

_QUOTA_KEYWORDS = ("429", "quota", "RESOURCE_EXHAUSTED", "rate limit")


def _is_quota_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(k.lower() in s for k in _QUOTA_KEYWORDS)


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _parse_json_response(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Nenhum JSON válido na resposta do Gemini:\n{text[:300]}")


# ── Chamada com retry ─────────────────────────────────────────────────────────

def _call_with_retry(model: genai.GenerativeModel, parts: list, max_retries: int = 2):
    """Chama o Gemini com retry exponencial. Não retenta erros de quota."""
    last_exc: Exception = RuntimeError("Sem tentativas realizadas")
    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(parts)
            _circuit.record_success()
            return response
        except Exception as exc:
            last_exc = exc
            if _is_quota_error(exc):
                _circuit.record_failure()
                raise
            if attempt < max_retries:
                wait = 2 ** attempt      # 1s, 2s
                logger.warning(
                    "Gemini tentativa %d/%d falhou (%s). Aguardando %ds...",
                    attempt + 1, max_retries + 1, exc, wait,
                )
                time.sleep(wait)
            else:
                _circuit.record_failure()
    raise last_exc


# ── Entry point público ───────────────────────────────────────────────────────

def extract_invoice_with_gemini(content: bytes, filename: str) -> Tuple[str, Dict, Dict]:
    """
    Extrai campos de uma invoice via Gemini API.
    Levanta GeminiCircuitOpenError se o circuito estiver aberto (use fallback OCR).

    Returns:
        (raw_text, fields_dict, confidence_dict)
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")

    if _circuit.is_open:
        raise GeminiCircuitOpenError(
            "Circuit breaker aberto — Gemini com muitas falhas recentes. Usando fallback."
        )

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=_SYSTEM_INSTRUCTION,
        generation_config=genai.GenerationConfig(temperature=0.1),
    )

    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        parts = [_EXTRACTION_PROMPT, {"mime_type": "application/pdf", "data": content}]
        logger.info("Gemini (%s): enviando PDF '%s'", GEMINI_MODEL, filename)
    else:
        parts = [_EXTRACTION_PROMPT, Image.open(io.BytesIO(content))]
        logger.info("Gemini (%s): enviando imagem '%s'", GEMINI_MODEL, filename)

    response = _call_with_retry(model, parts)
    logger.debug("Gemini raw response for %s: %.300s", filename, response.text)

    result = _parse_json_response(response.text)
    raw_text = result.pop("raw_text", "")
    confidence = result.pop("confidence", {})

    found = [k for k, v in result.items() if v is not None]
    logger.info("Gemini extraiu %d campos de '%s': %s", len(found), filename, found)

    return raw_text, result, confidence
