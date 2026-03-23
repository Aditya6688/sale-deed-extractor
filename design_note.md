# Design Note: Sale Deed Information Extraction System

## 1. Overall Approach and System Flow

The system uses a **dual-method architecture** with OpenAI GPT-4o vision as the primary path and Tesseract OCR + regex as an offline fallback.

### Primary: LLM Vision Pipeline
```
PDF → Page Images (PyMuPDF, 250 DPI) → Skip blank pages → OpenAI GPT-4o (high detail) → Structured JSON
```

Each PDF page is rendered as a 250 DPI PNG image. Blank and stamp-only pages are auto-detected and skipped (e.g., a 22-page document sends ~19 images). Images are sent to GPT-4o with `detail: "high"` alongside a structured extraction prompt with multilingual legal labels. The LLM reads the document directly — no OCR needed — and returns a JSON object with all 18 fields.

### Fallback: OCR + Regex Pipeline
```
PDF → Page Images (300 DPI) → Tesseract OCR (eng+mar) → Regex Pattern Matching → JSON
```

For offline or no-API-key scenarios. Tesseract extracts text from each page, then a set of regex patterns search for known Marathi/English field labels (लिहून देणार, चतुःसिमा, etc.). This method only supports Maharashtra-style Marathi/English sale deeds.

### Interface Layer
- **Streamlit UI**: Upload PDF, view extracted fields and JSON side-by-side. API key loaded from `.env` file, never shown in the UI.
- **FastAPI**: REST endpoint (`POST /extract`) for programmatic integration.
- **CLI**: Command-line processing for batch/scripting use.

### Robustness Features
- **Retry with backoff**: 3 retries with exponential backoff for rate limits, timeouts, and connection errors.
- **Blank page detection**: Pages with <2% dark pixels are skipped, reducing token usage and LLM confusion.
- **File size validation**: 50 MB limit enforced before processing.
- **JSON parsing**: Bracket-counting parser handles markdown fences, nested objects, and LLM formatting quirks.
- **Truncation detection**: Warns if OpenAI response hits max_tokens (incomplete JSON).

## 2. Why This Approach

**Why LLM vision over traditional OCR + NER?**

| Factor | OCR + Regex | LLM Vision (GPT-4o) |
|--------|-------------|---------------------|
| Language coverage | Marathi + English only | All Indian languages simultaneously |
| Layout handling | Brittle; tables/columns break | Native layout understanding |
| Handwriting | Very poor | Reasonable |
| New document formats | Requires new regex rules | Works out-of-the-box |
| Measured accuracy | 44% (on test document) | 89% (on test document) |
| Cost per document | Free (Tesseract) | ~$0.05-0.15 (high detail, ~19 pages) |
| Offline capability | Yes | No |

The core insight: Indian sale deeds vary massively by state, language, and registrar office. Building regex rules for each combination is impractical. A single LLM prompt handles all variations because the model already understands Indian legal documents, languages, and conventions.

**Why keep OCR as fallback?** Some deployments can't use external APIs (air-gapped environments, data sovereignty). The OCR path ensures the system works offline, even if at lower accuracy.

**Why OpenAI only (not multi-provider)?** Simplicity. One provider means one SDK, one auth flow, one set of known behaviors. GPT-4o has the best price-to-quality ratio for vision tasks. The prompt and image pipeline would work with Claude or Gemini with minimal changes if needed later.

## 3. Trade-offs

| Decision | Benefit | Cost |
|----------|---------|------|
| LLM-first over OCR-first | Any language, any layout, 89% accuracy | ~$0.10/doc, internet required |
| `detail: "high"` on all pages | LLM can read Devanagari and other scripts | Higher token cost vs "auto" |
| 250 DPI rendering | Good legibility for scanned text | Larger images than 150 DPI |
| Skip blank pages (dark pixel ratio <2%) | 22→19 pages, less noise for LLM | May occasionally skip a faded page |
| Single prompt (not multi-step chain) | Simpler, one API call, fewer failure points | Less granular control |
| API key in `.env` file (not in UI) | Secure, never exposed to users | Requires server-side config |
| No fine-tuning | Works immediately, zero training data | Could be more accurate with domain tuning |

## 4. What Would Need to Change for Production

### Accuracy Improvements
- **Fix North/South boundary swap**: The LLM occasionally swaps N/S boundaries. Add a post-processing validation step that cross-checks boundary labels against known directional keywords.
- **Few-shot examples**: Include 2-3 example extractions in the prompt for common state/language variants.
- **Ensemble approach**: Run both LLM and OCR, cross-validate outputs, flag discrepancies for human review.
- **Confidence scoring**: Ask the LLM to rate confidence (0-1) for each field, flag low-confidence fields.

### Scale and Cost
- **Smart page selection**: Classify pages first (challan, deed body, signatures, ID proofs) and only send the 4-5 key pages. Would cut cost by ~60%.
- **Caching**: Hash document content and cache results to avoid re-processing duplicates.
- **Async queue**: Use Celery or SQS for background processing at scale.
- **OpenAI Batch API**: Use batch endpoints for bulk processing at 50% cost reduction.

### Security and Compliance
- **PII handling**: Redact Aadhaar numbers and phone numbers from logs. Never store raw API responses containing PII beyond the extraction session.
- **Data residency**: For Indian financial institutions, ensure API calls comply with RBI data localization requirements.
- **Audit trail**: Log which pages, which model version, and which prompt version produced each extraction — critical for regulated lending workflows.
- **Human-in-the-loop**: Build a review UI where loan officers verify and correct extracted data before it enters the system of record.
