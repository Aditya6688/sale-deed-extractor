"""
FastAPI endpoint for sale deed extraction.
Uses OpenAI GPT-4o vision (primary) or OCR+regex (offline fallback).
API key is loaded from .env / environment variable — never passed as query param.
"""

import os
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.ocr import extract_text_from_pdf
from app.extractor import extract_all
from app.llm_extractor import extract_with_llm, _get_api_key

app = FastAPI(
    title="Sale Deed Extractor API",
    description=(
        "Extracts structured fields from scanned sale deed PDFs. "
        "Supports all Indian languages via OpenAI GPT-4o vision, "
        "or offline OCR+regex for Marathi/English."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    has_key = bool(_get_api_key())
    return {
        "message": "Sale Deed Extractor API v2.0",
        "openai_key_configured": has_key,
        "endpoints": {
            "POST /extract": "Extract fields (default: LLM vision)",
            "POST /extract?method=ocr": "Extract fields (offline OCR+regex)",
        },
    }


@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    method: str = Query("llm", description="Extraction method: 'llm' or 'ocr'"),
    model: str = Query("gpt-4o", description="OpenAI model (for LLM method)"),
):
    """Upload a sale deed PDF and get extracted fields as JSON."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if method == "llm":
            if not _get_api_key():
                raise HTTPException(
                    status_code=400,
                    detail="OpenAI API key not configured. "
                           "Set OPENAI_API_KEY in environment or .env file.",
                )
            result = extract_with_llm(tmp_path, model=model)
            return JSONResponse(content={"status": "success", "extracted_data": result})
        else:
            ocr_result = extract_text_from_pdf(tmp_path, dpi=300)
            data = extract_all(ocr_result["pages"], ocr_result["full_text"])
            return JSONResponse(content={
                "status": "success",
                "extracted_data": {**data.to_dict(), "extraction_method": "OCR + Regex"},
            })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
