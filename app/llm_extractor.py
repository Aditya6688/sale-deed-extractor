"""
LLM Vision-based extraction for sale deed documents.

Sends document page images directly to OpenAI GPT-4o, which can:
- Read any Indian language/script (Hindi, Marathi, Tamil, Telugu, Kannada, etc.)
- Understand document layout without OCR
- Reason about legal context to identify the right fields
- Handle handwritten text, stamps, seals
"""

import os
import re
import json
import base64
import logging
import time
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Max pages to send to the LLM (cost + token limit control)
MAX_PAGES = 25
# Max file size in MB
MAX_FILE_SIZE_MB = 50
# API call timeout in seconds
API_TIMEOUT = 120
# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubles each retry


EXTRACTION_PROMPT = """You are an expert legal document analyst specializing in Indian property documents.

Analyze the provided sale deed document images VERY CAREFULLY and extract the following fields into a JSON object.

CRITICAL INSTRUCTIONS:
1. The document may be in ANY Indian language (Hindi, Marathi, Tamil, Telugu, Kannada, Gujarati, Bengali, etc.) or English.
2. Extract the ORIGINAL text as it appears in the document, followed by an English translation in parentheses if the original is not in English.
3. If a field is genuinely not present in the document, return an empty string "" for that field.
4. NEVER guess or fabricate information. Only extract what you can CLEARLY READ in the images. If text is blurry or uncertain, return "" rather than guessing.
5. For party details, correctly identify who is the SELLER and who is the BUYER based on the legal language used.
6. Focus on the MAIN DEED PAGES (the typed/printed text pages with party names, boundaries, and amounts). Ignore Aadhaar card copies, blank pages, and stamp-only pages.
7. The seller and buyer names appear prominently in the deed body text, NOT on ID cards or witness sections. Look for labels like "लिहून देणार" (seller) and "लिहून घेणार" (buyer) in Marathi deeds.
8. Read EVERY text page carefully — boundaries, area, and property address are often on a different page than the party names.
9. Party addresses usually appear on the SAME page as their name, often starting with "रा." (resident of) or on the line below their occupation/age. Always extract the full address.
10. For boundaries: carefully check which direction each boundary label refers to — "पुर्वेस" = East, "पश्चिमेस" = West, "उत्तरेस" = North, "दक्षिणेस" = South. Do NOT swap them.

Common Indian language labels for reference:
- Seller: "लिहून देणार" (Marathi), "विक्रेता" (Hindi), "விற்பனையாளர்" (Tamil), "विक्रेता" (Gujarati)
- Buyer: "लिहून घेणार" (Marathi), "क्रेता" (Hindi), "வாங்குபவர்" (Tamil), "ખરીદનાર" (Gujarati)
- Boundaries: "चतुःसिमा" / "चतुर्दिशा" / "हद्द" = four boundaries
  - East: "पूर्व" / "கிழக்கு" / "पूर्वेस"
  - West: "पश्चिम" / "மேற்கு" / "पश्चिमेस"
  - North: "उत्तर" / "வடக்கு" / "उत्तरेस"
  - South: "दक्षिण" / "தெற்கு" / "दक्षिणेस"

Extract these fields:

{
  "document_name": "Type of document (e.g., Sale Deed / खरेदीखत / विक्रीपत्र)",
  "seller_name": "Full name of the seller (Party 1 / First Party / लिहून देणार / विक्रेता)",
  "seller_age": "Age of the seller if mentioned",
  "seller_address": "Address of the seller",
  "buyer_name": "Full name of the buyer (Party 2 / Second Party / लिहून घेणार / क्रेता)",
  "buyer_age": "Age of the buyer if mentioned",
  "buyer_address": "Address of the buyer",
  "boundary_east": "What is on the eastern boundary of the property",
  "boundary_west": "What is on the western boundary of the property",
  "boundary_north": "What is on the northern boundary of the property",
  "boundary_south": "What is on the southern boundary of the property",
  "area_size": "Total area of the property with units (sq. mtr, sq. ft, acres, hectares, guntha, etc.)",
  "property_address": "Full property address including survey number, plot number, village, taluka, district, state",
  "registration_date": "Date when the document was registered (not the execution date)",
  "registration_number": "Document registration number / दस्त क्रमांक",
  "book_number": "Book/volume number (दस्त गोषवारा भाग) if available",
  "sro_office": "Sub-Registrar Office where document was registered",
  "sale_amount": "Total sale/consideration amount in Rupees"
}

Return ONLY the JSON object. No markdown, no explanation, no code fences."""


# ---------------------------------------------------------------------------
# PDF → Images
# ---------------------------------------------------------------------------

def _is_low_content_page(pix) -> bool:
    """
    Check if a page is mostly blank or contains only a stamp/seal
    (very little actual text content). Skipping these saves tokens
    and reduces confusion for the LLM.
    """
    samples = pix.samples
    if not samples:
        return True

    # Sample pixels across the image (not just the first 3000 bytes)
    total = len(samples)
    step = max(1, total // 5000)
    sampled = samples[::step]

    # Count "dark" pixels (text, stamps, etc.) — below threshold 200
    dark_count = sum(1 for b in sampled if b < 200)
    dark_ratio = dark_count / len(sampled) if sampled else 0

    # A page with less than 2% dark pixels is essentially blank or stamp-only
    return dark_ratio < 0.02


def pdf_to_base64_images(pdf_path: str, dpi: int = 200,
                         max_pages: int = MAX_PAGES) -> list[str]:
    """
    Convert PDF pages to base64-encoded PNG images.
    Skips blank pages to save tokens and cost.
    """
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(
            f"PDF file is {file_size_mb:.1f} MB, exceeds limit of {MAX_FILE_SIZE_MB} MB."
        )

    doc = fitz.open(pdf_path)
    images = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    for i, page in enumerate(doc):
        if len(images) >= max_pages:
            logger.info(f"Reached max page limit ({max_pages}), skipping remaining pages.")
            break
        pix = page.get_pixmap(matrix=matrix)
        if _is_low_content_page(pix):
            logger.debug(f"Skipping low-content page {i + 1}")
            continue
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        images.append(b64)

    total_pages = doc.page_count
    doc.close()

    if not images:
        raise ValueError("No readable pages found in the PDF.")

    logger.info(f"Prepared {len(images)} page images from {total_pages}-page PDF.")
    return images


# ---------------------------------------------------------------------------
# JSON Parsing
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """
    Extract JSON from LLM response.
    Handles: raw JSON, markdown-fenced JSON, JSON embedded in text.
    """
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        text = text.strip()

    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: find the outermost { ... } block
    # Use a bracket-counting approach instead of fragile regex
    start = text.find('{')
    if start == -1:
        raise ValueError(f"No JSON object found in LLM response: {text[:300]}")

    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if depth != 0:
        raise ValueError(f"Malformed JSON in LLM response (unclosed braces): {text[:300]}")

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse JSON from LLM response: {e}. Text: {text[start:start+300]}")


# ---------------------------------------------------------------------------
# API Key Loading
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """
    Load the OpenAI API key from (in priority order):
    1. OPENAI_API_KEY environment variable
    2. .env file in the project root
    """
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key

    env_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for env_path in env_paths:
        if os.path.isfile(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("\"'")
                    if k == "OPENAI_API_KEY" and v:
                        return v
    return ""


# ---------------------------------------------------------------------------
# OpenAI Extraction (with retry)
# ---------------------------------------------------------------------------

def extract_with_openai(pdf_path: str, api_key: str = "",
                        model: str = "gpt-4o") -> dict:
    """
    Extract sale deed fields using OpenAI GPT-4o vision.
    Includes retry logic for transient API errors.
    """
    import openai

    api_key = api_key or _get_api_key()
    if not api_key:
        raise ValueError(
            "OpenAI API key not found. Set OPENAI_API_KEY in your environment "
            "or add it to the .env file in the project root."
        )

    # Use 250 DPI for good text legibility in scanned documents
    images = pdf_to_base64_images(pdf_path, dpi=250)

    # Always use "high" detail — scanned Indian-language documents need it
    # for the model to read Devanagari, Tamil, and other scripts accurately.
    content = [{"type": "text", "text": "Here are the pages of a sale deed document. Read each page carefully:"}]
    for i, b64 in enumerate(images):
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
        })
    content.append({"type": "text", "text": EXTRACTION_PROMPT})

    client = openai.OpenAI(api_key=api_key, timeout=API_TIMEOUT)

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )

            # Check if response was truncated
            choice = response.choices[0]
            if choice.finish_reason == "length":
                logger.warning("OpenAI response was truncated (hit max_tokens). JSON may be incomplete.")

            return _parse_json_response(choice.message.content)

        except openai.RateLimitError as e:
            last_error = e
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(f"Rate limited (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)

        except openai.APITimeoutError as e:
            last_error = e
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(f"Timeout (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)

        except openai.APIConnectionError as e:
            last_error = e
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(f"Connection error (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)

        except openai.BadRequestError as e:
            # Non-retryable: bad input, invalid model, content policy, etc.
            raise ValueError(f"OpenAI rejected the request: {e}") from e

        except openai.AuthenticationError as e:
            raise ValueError(f"Invalid OpenAI API key: {e}") from e

    raise RuntimeError(f"OpenAI API failed after {MAX_RETRIES} retries. Last error: {last_error}")


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

EXPECTED_FIELDS = [
    "document_name", "seller_name", "seller_age", "seller_address",
    "buyer_name", "buyer_age", "buyer_address",
    "boundary_east", "boundary_west", "boundary_north", "boundary_south",
    "area_size", "property_address", "registration_date",
    "registration_number", "book_number", "sro_office", "sale_amount",
]


def extract_with_llm(pdf_path: str, model: str = "gpt-4o") -> dict:
    """
    Extract sale deed fields using OpenAI GPT-4o vision.
    API key is loaded automatically from environment / .env file.

    Returns:
        Dict with extracted fields + metadata
    """
    result = extract_with_openai(pdf_path, model=model)

    # Ensure all expected fields are present
    for field in EXPECTED_FIELDS:
        if field not in result:
            result[field] = ""

    # Add notes about extraction
    notes = []
    empty_fields = [f for f in EXPECTED_FIELDS if not result.get(f)]
    if empty_fields:
        notes.append(f"Fields not found in document: {', '.join(empty_fields)}")
    result["notes"] = notes
    result["extraction_method"] = f"LLM Vision (OpenAI {model})"

    return result
