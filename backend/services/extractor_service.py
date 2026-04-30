"""
Serviço de extração de campos de NF a partir de texto bruto (saída do OCR).
Usa expressões regulares com múltiplos padrões por campo, ordenados do mais
específico ao mais genérico. Retorna um score de confiança (0.0–1.0) por campo:
  0.90 = padrão mais específico casou
  -0.05 por padrão menos específico usado
  0.0  = não encontrou nada
"""
import re
from typing import Optional, Tuple, Dict, Any
from dateutil import parser as dateutil_parser


# Mapeamento de símbolo → código ISO da moeda
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "R$": "BRL"}

# Códigos de moeda reconhecidos explicitamente no texto
KNOWN_CURRENCIES = {
    "USD", "EUR", "GBP", "BRL", "JPY", "CAD", "AUD", "CHF", "CNY", "MXN", "ARS",
}


def _clean(s: str) -> str:
    """Remove espaços extras e normaliza o texto extraído."""
    return " ".join(s.split()).strip()


def _first_match(text: str, patterns: list[str], flags=re.IGNORECASE) -> Tuple[Optional[str], float]:
    """
    Tenta cada padrão na ordem. Retorna (valor, confiança) do primeiro que casar.
    Padrões mais à frente na lista recebem confiança menor (cada um perde 0.05).
    """
    for i, pattern in enumerate(patterns):
        m = re.search(pattern, text, flags)
        if m:
            value = _clean(m.group(1))
            confidence = 0.90 - i * 0.05       # confiança decai com padrões mais genéricos
            return value, max(confidence, 0.50) # mínimo de 0.50 para qualquer match
    return None, 0.0


def extract_invoice_number(text: str) -> Tuple[Optional[str], float]:
    """Extrai o número da nota fiscal (ex: INV-12345, BILL-001, etc.)."""
    patterns = [
        r"invoice\s*(?:#|no\.?|number|num\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_\/]{2,})",
        r"inv\.?\s*(?:#|no\.?)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_\/]{2,})",
        r"bill\s*(?:#|no\.?|number)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_\/]{2,})",
        r"receipt\s*(?:#|no\.?|number)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_\/]{2,})",
        r"reference\s*(?:#|no\.?)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_\/]{4,})",
        r"\b(INV[\-_]?[0-9]{3,})\b",         # padrão comum: INV-001
        r"\b([A-Z]{2,5}[\-_][0-9]{4,})\b",   # padrão genérico: XX-0000
    ]
    return _first_match(text, patterns)


def extract_issue_date(text: str) -> Tuple[Optional[str], float]:
    """
    Extrai a data de emissão e normaliza para o formato YYYY-MM-DD.
    Aceita vários formatos (DD/MM/YYYY, Month DD YYYY, YYYY-MM-DD, etc.).
    """
    patterns = [
        r"(?:invoice\s+date|date\s+of\s+issue|issue\s+date|issued\s+on|billing\s+date|bill\s+date)\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:invoice\s+date|date\s+of\s+issue|issue\s+date|issued\s+on)\s*[:\-]?\s*(\d{1,2}\s+\w+\s+\d{4})",
        r"(?:invoice\s+date|date|issued)\s*[:\-]?\s*(\w+\s+\d{1,2},?\s+\d{4})",
        r"date\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"\b(\d{4}[-\/]\d{2}[-\/]\d{2})\b",  # ISO: 2024-03-15
        r"\b(\d{1,2}[-\/]\d{1,2}[-\/]\d{4})\b",
    ]
    value, conf = _first_match(text, patterns)
    if value:
        try:
            # dateutil.parser interpreta formatos ambíguos com dayfirst=True (padrão brasileiro)
            parsed = dateutil_parser.parse(value, dayfirst=True)
            return parsed.strftime("%Y-%m-%d"), conf
        except Exception:
            # Se não conseguiu parsear, retorna o valor bruto com confiança reduzida
            return value, conf * 0.7
    return None, 0.0


def extract_currency(text: str) -> Tuple[Optional[str], float]:
    """
    Detecta a moeda da NF. Prioridade:
    1. Código ISO explícito (USD, EUR...) — confiança 0.95
    2. Símbolo ($, €...) — confiança 0.85
    """
    # Busca código ISO primeiro (mais confiável)
    for code in KNOWN_CURRENCIES:
        if re.search(rf"\b{code}\b", text):
            return code, 0.95

    # Fallback para símbolo de moeda
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code, 0.85

    return None, 0.0


def extract_amount(text: str, label: str) -> Tuple[Optional[float], float]:
    """
    Extrai um valor monetário associado a um label específico (ex: "total", "subtotal").
    Normaliza separadores de milhar e decimal antes de converter para float.
    """
    patterns = [
        # Padrão 1: label seguido de qualquer coisa e número (ex: "Total: 1.234,56")
        rf"{label}\s*[:\-]?\s*[^\d]*?([\d]{{1,3}}(?:[,.][\d]{{3}})*(?:[.,]\d{{1,2}})?)",
        # Padrão 2: label seguido de código de moeda e número (ex: "Total USD 1234.56")
        rf"{label}\s*[:\-]?\s*[A-Z]{{3}}\s*([\d]{{1,3}}(?:[,.][\d]{{3}})*(?:[.,]\d{{1,2}})?)",
    ]
    value, conf = _first_match(text, patterns)
    if value:
        # Normaliza o separador decimal: troca vírgula por ponto e remove separadores de milhar extras
        normalized = value.replace(",", ".")
        if normalized.count(".") > 1:
            normalized = normalized.replace(".", "", normalized.count(".") - 1)
        try:
            return float(normalized), conf
        except ValueError:
            pass
    return None, 0.0


def extract_total_amount(text: str) -> Tuple[Optional[float], float]:
    """
    Extrai o valor total da NF. Tenta labels do mais específico ao mais genérico.
    Cada label menos específico reduz levemente a confiança.
    """
    labels = [
        r"(?:total\s+amount\s+due|amount\s+due|total\s+due)",  # mais específico
        r"(?:grand\s+total|total\s+amount|total)",
        r"(?:amount\s+payable|due\s+amount)",                  # mais genérico
    ]
    for i, label in enumerate(labels):
        amount, conf = extract_amount(text, label)
        if amount is not None:
            return amount, conf - i * 0.03  # penalidade por label menos específico
    return None, 0.0


def extract_subtotal(text: str) -> Tuple[Optional[float], float]:
    """Extrai o subtotal (valor antes de impostos e taxas)."""
    return extract_amount(text, r"sub\s*total")


def extract_taxes(text: str) -> Tuple[Optional[float], float]:
    """Extrai o valor de impostos (IVA, GST, ISS, etc.)."""
    labels = [r"(?:tax|vat|gst|iva|sales\s+tax)", r"(?:taxes|impostos)"]
    for label in labels:
        amount, conf = extract_amount(text, label)
        if amount is not None:
            return amount, conf
    return None, 0.0


def extract_supplier(text: str) -> Tuple[Optional[str], float]:
    """
    Extrai o nome do fornecedor. Estratégia em três camadas:
    1. Lista de fornecedores conhecidos (alta confiança) — busca nas primeiras 12 linhas
    2. Label explícito ("from:", "vendor:", etc.)
    3. Heurística: primeira linha não vazia que não começa com número e não é "invoice"
    """
    # Foca nas primeiras linhas porque o nome do fornecedor geralmente fica no cabeçalho da NF
    first_lines = text.split("\n")[:12]

    known_suppliers = [
        "Google", "Amazon", "AWS", "Microsoft", "Apple", "Meta", "Facebook",
        "OpenAI", "Anthropic", "Notion", "Slack", "Zoom", "GitHub", "GitLab",
        "Atlassian", "Jira", "Confluence", "Dropbox", "HubSpot", "Salesforce",
        "Stripe", "Twilio", "SendGrid", "Mailchimp", "Figma", "Adobe",
        "LinkedIn", "Twitter", "Cloudflare", "Heroku", "DigitalOcean",
        "Datadog", "PagerDuty", "Sentry", "Zendesk",
    ]
    for supplier in known_suppliers:
        if any(supplier.lower() in line.lower() for line in first_lines):
            return supplier, 0.95  # alta confiança: nome exato na lista

    # Tenta encontrar label explícito como "from:", "vendor:", "seller:"
    m = re.search(r"(?:from|seller|vendor|supplier|company)\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    if m:
        return _clean(m.group(1))[:60], 0.80

    # Último recurso: primeira linha que pareça nome de empresa (não começa com número, não é "invoice")
    for line in first_lines:
        line = _clean(line)
        if len(line) > 3 and not re.match(r"^\d", line) and "invoice" not in line.lower():
            return line[:60], 0.50  # baixa confiança: é só a primeira linha candidata

    return None, 0.0


def extract_billing_period(text: str) -> Tuple[Optional[str], float]:
    """Extrai o período de cobrança/competência (ex: 'March 2024', 'Jan 1 – Jan 31, 2024')."""
    patterns = [
        r"(?:billing\s+period|service\s+period|period|for\s+(?:the\s+)?(?:month|period)\s+of)\s*[:\-]?\s*(.{5,40}?)(?:\n|$)",
        r"(?:from|period)\s*[:\-]?\s*(\w+\s+\d{1,2}(?:,?\s+\d{4})?)\s*(?:to|-)\s*(\w+\s+\d{1,2}(?:,?\s+\d{4})?)",
    ]
    value, conf = _first_match(text, patterns)
    return _clean(value)[:80] if value else None, conf


def extract_description(text: str) -> Tuple[Optional[str], float]:
    """Extrai a descrição do serviço ou produto cobrado."""
    patterns = [
        r"(?:description|services?|item|product)\s*[:\-]?\s*(.{10,120}?)(?:\n|$)",
        r"(?:for\s+(?:services?|the\s+use\s+of))\s*[:\-]?\s*(.{10,120}?)(?:\n|$)",
    ]
    value, conf = _first_match(text, patterns)
    return _clean(value)[:200] if value else None, conf


def extract_all(text: str) -> Dict[str, Any]:
    """
    Função principal: executa todas as extrações e retorna dois dicts:
      - 'data': valores extraídos por campo
      - 'confidence': score de confiança (0.0–1.0) por campo
    """
    invoice_number, c_inv = extract_invoice_number(text)
    issue_date, c_date = extract_issue_date(text)
    currency, c_curr = extract_currency(text)
    total_amount, c_total = extract_total_amount(text)
    subtotal, c_sub = extract_subtotal(text)
    taxes, c_tax = extract_taxes(text)
    supplier, c_supp = extract_supplier(text)
    billing_period, c_period = extract_billing_period(text)
    description, c_desc = extract_description(text)

    return {
        "data": {
            "supplier": supplier,
            "invoice_number": invoice_number,
            "issue_date": issue_date,
            "billing_period": billing_period,
            "description": description,
            "currency": currency,
            "subtotal": subtotal,
            "taxes": taxes,
            "total_amount": total_amount,
        },
        "confidence": {
            "supplier": c_supp,
            "invoice_number": c_inv,
            "issue_date": c_date,
            "billing_period": c_period,
            "description": c_desc,
            "currency": c_curr,
            "subtotal": c_sub,
            "taxes": c_tax,
            "total_amount": c_total,
        },
    }