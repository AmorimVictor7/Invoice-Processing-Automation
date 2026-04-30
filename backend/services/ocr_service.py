# Serviço de OCR — extrai texto bruto de PDFs e imagens.
# Suporta três provedores configuráveis via variável OCR_PROVIDER:
#   - "tesseract" (padrão): local, gratuito, sem necessidade de API
#   - "google": Google Cloud Vision API, melhor qualidade em documentos complexos
# Para PDFs, tenta extrair texto nativo primeiro (pdfplumber) antes de usar OCR nas imagens,
# pois texto nativo é mais rápido e preciso que OCR.

import io
import os
import logging
from typing import Tuple
from PIL import Image, ImageFilter, ImageEnhance
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configurações lidas do .env — permitem trocar o provedor sem alterar código
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")           # caminho do executável tesseract (Windows)
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "")
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "tesseract")    # "tesseract" ou "google"

# Configura o caminho do executável Tesseract se fornecido (necessário no Windows)
if TESSERACT_CMD:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def _preprocess_image(img: Image.Image) -> Image.Image:
    """
    Pré-processa a imagem para melhorar a qualidade do OCR:
    1. Converte para escala de cinza (L) — Tesseract performa melhor em grayscale
    2. Aumenta o contraste (fator 1.8) — melhora legibilidade de texto claro
    3. Aplica filtro de sharpening — destaca bordas das letras
    """
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    if img.mode != "L":
        img = img.convert("L")     # escala de cinza
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.8)    # aumenta contraste
    img = img.filter(ImageFilter.SHARPEN)
    return img


def _tesseract_from_image(img: Image.Image) -> str:
    """
    Executa o Tesseract OCR em uma imagem PIL.
    lang="eng+por": reconhece inglês e português simultaneamente.
    --psm 3: modo de segmentação automática de página (mais robusto para layouts variados).
    """
    import pytesseract
    img = _preprocess_image(img)
    return pytesseract.image_to_string(img, lang="eng+por", config="--psm 3")


def _extract_from_pdf_text(content: bytes) -> Tuple[str, str]:
    """
    Tenta extrair o texto nativo do PDF usando pdfplumber (sem OCR).
    Funciona para PDFs gerados digitalmente (não escaneados).
    Retorna ("", "") se o PDF for escaneado ou pdfplumber falhar.
    O threshold de 30 caracteres filtra PDFs com texto corrompido ou quase vazio.
    """
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(pages_text)
            if len(text.strip()) > 30:  # mínimo de conteúdo para considerar válido
                return text, "pdfplumber"
    except Exception as e:
        logger.warning("pdfplumber failed: %s", e)
    return "", ""


def _extract_from_pdf_ocr(content: bytes) -> Tuple[str, str]:
    """
    Converte cada página do PDF em imagem e aplica Tesseract OCR.
    Usado como fallback quando pdfplumber não extrai texto útil (PDFs escaneados).
    DPI=200: bom equilíbrio entre qualidade e velocidade de processamento.
    """
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(content, dpi=200)
        parts = [_tesseract_from_image(img) for img in images]
        return "\n".join(parts), "tesseract"
    except Exception as e:
        logger.warning("pdf2image/tesseract failed: %s", e)
    return "", "error"


def _google_vision_image(content: bytes) -> Tuple[str, str]:
    """
    Envia a imagem para a Google Cloud Vision API e retorna o texto detectado.
    document_text_detection é otimizado para documentos (vs text_detection para cenas).
    """
    try:
        from google.cloud import vision as gv
        client = gv.ImageAnnotatorClient()
        image = gv.Image(content=content)
        response = client.document_text_detection(image=image)
        if response.error.message:
            raise RuntimeError(response.error.message)
        text = response.full_text_annotation.text
        return text, "google_vision"
    except Exception as e:
        logger.warning("Google Vision failed: %s", e)
    return "", "error"


def extract_text(file_content: bytes, filename: str) -> Tuple[str, str]:
    """
    Função principal do serviço. Decide qual estratégia de extração usar com base em:
    - Extensão do arquivo (pdf vs imagem)
    - Provedor configurado (google vs tesseract)

    Fluxo para Google Vision + PDF:
      1. Tenta texto nativo (pdfplumber) → mais rápido
      2. Converte primeira página para imagem e envia ao Vision → melhor qualidade

    Fluxo para Tesseract (padrão) + PDF:
      1. Tenta texto nativo (pdfplumber) → mais rápido
      2. Converte todas as páginas e usa Tesseract → fallback para PDFs escaneados

    Fluxo para imagens (PNG/JPG):
      - Abre com PIL e executa Tesseract diretamente

    Retorna (texto_extraído, método_usado).
    """
    ext = filename.lower().rsplit(".", 1)[-1]

    if OCR_PROVIDER == "google" and GOOGLE_VISION_API_KEY:
        if ext == "pdf":
            # Tenta texto nativo primeiro para PDFs digitais
            text, method = _extract_from_pdf_text(file_content)
            if text:
                return text, method
            # Fallback: converte a primeira página em PNG e envia ao Vision
            try:
                from pdf2image import convert_from_bytes
                images = convert_from_bytes(file_content, dpi=200)
                buf = io.BytesIO()
                images[0].save(buf, format="PNG")
                text, method = _google_vision_image(buf.getvalue())
                if text:
                    return text, method
            except Exception:
                pass
        else:
            # Para imagens, envia direto ao Google Vision
            text, method = _google_vision_image(file_content)
            if text:
                return text, method

    # Caminho padrão com Tesseract
    if ext == "pdf":
        text, method = _extract_from_pdf_text(file_content)
        if text:
            return text, method          # PDF com texto nativo → retorna direto
        return _extract_from_pdf_ocr(file_content)  # PDF escaneado → OCR
    else:
        try:
            img = Image.open(io.BytesIO(file_content))
            return _tesseract_from_image(img), "tesseract"
        except Exception as e:
            logger.error("Image OCR failed: %s", e)
            return "", "error"