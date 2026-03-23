"""
OCR module for extracting text from scanned PDF documents.
Uses PyMuPDF for PDF-to-image conversion and Pytesseract for OCR.
Supports both English and Marathi (Devanagari) text.
"""

import io
import os
import shutil
import fitz  # PyMuPDF
from PIL import Image
import pytesseract

# Auto-configure Tesseract paths on Windows
if os.name == "nt":
    _tesseract_exe = shutil.which("tesseract")
    if not _tesseract_exe:
        _default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(_default):
            pytesseract.pytesseract.tesseract_cmd = _default
    # Use user-local tessdata if it exists (avoids admin permission issues)
    _user_tessdata = os.path.join(os.path.expanduser("~"), "tessdata")
    if os.path.isdir(_user_tessdata):
        os.environ["TESSDATA_PREFIX"] = _user_tessdata


def pdf_to_images(pdf_path: str, dpi: int = 300) -> list[Image.Image]:
    """Convert each page of a PDF to a PIL Image."""
    doc = fitz.open(pdf_path)
    images = []
    zoom = dpi / 72  # 72 is default PDF DPI
    matrix = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append(img)
    doc.close()
    return images


def ocr_image(image: Image.Image, lang: str = "eng+mar") -> str:
    """Run OCR on a single image. Defaults to English + Marathi."""
    try:
        text = pytesseract.image_to_string(image, lang=lang)
    except pytesseract.TesseractError:
        # Fallback to English only if Marathi is not installed
        text = pytesseract.image_to_string(image, lang="eng")
    return text


def extract_text_from_pdf(pdf_path: str, dpi: int = 300) -> dict:
    """
    Extract OCR text from a PDF, returning per-page and full text.

    Returns:
        {
            "pages": {1: "text...", 2: "text...", ...},
            "full_text": "all pages concatenated"
        }
    """
    images = pdf_to_images(pdf_path, dpi=dpi)
    pages = {}
    for i, img in enumerate(images, start=1):
        pages[i] = ocr_image(img)
    full_text = "\n\n--- PAGE BREAK ---\n\n".join(pages.values())
    return {"pages": pages, "full_text": full_text}
