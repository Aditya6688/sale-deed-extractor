# Sale Deed Information Extractor

A Python-based system that extracts structured legal and property information from scanned sale deed PDFs. Supports **all Indian languages** and document formats.

## Two Extraction Methods

| Method | Languages | Accuracy | Requires |
|--------|-----------|----------|----------|
| **LLM Vision** (recommended) | All Indian languages + English | ~89% (measured) | OpenAI API key |
| **OCR + Regex** (offline) | Marathi + English | ~44% (measured) | Tesseract OCR installed |

The LLM Vision method sends document page images directly to OpenAI GPT-4o, which reads any script, understands layout, and reasons about legal context. No OCR needed.

## Extracted Fields

| Field | Description |
|-------|-------------|
| Document Name | Type of legal document |
| Seller Details | Name, age, address of Party 1 |
| Buyer Details | Name, age, address of Party 2 |
| Boundaries | East, West, North, South boundaries |
| Area Size | Property area with units |
| Property Address | Plot number, survey number, village, district |
| Registration Date | Date of document registration |
| Registration Number | Document registration number |
| Book Number | Index volume number |
| SRO Office | Sub-Registrar Office name |
| Sale Amount | Transaction amount |

## Supported Languages

Hindi, Marathi, Tamil, Telugu, Kannada, Gujarati, Bengali, Malayalam, Punjabi, Odia, Assamese, Urdu, English, and any other language GPT-4o supports.

## Prerequisites

- Python 3.9+
- **For LLM Vision method**: An [OpenAI API key](https://platform.openai.com/api-keys)
- **For OCR method** (optional): Tesseract OCR with language packs
  - Windows: `winget install tesseract-ocr.tesseract`
  - Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-mar`
  - macOS: `brew install tesseract tesseract-lang`

## Setup

```bash
cd sale_deed_extractor

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate      # Linux/Mac
# OR
venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure API key (copy template and add your key)
cp .env.example .env
# Edit .env and set: OPENAI_API_KEY=sk-your-key-here
```

> The API key is loaded from the `.env` file or `OPENAI_API_KEY` environment variable.
> It is **never displayed in the UI** or passed as a URL parameter.

## Usage

### Option 1: Streamlit UI (Recommended for Demo)

```bash
python run.py ui
# OR
streamlit run app/streamlit_app.py
```

Open http://localhost:8501 and upload a PDF. The sidebar shows whether the API key is configured.

### Option 2: FastAPI REST API

```bash
python run.py api
```

```bash
# LLM extraction (default)
curl -X POST "http://localhost:8000/extract" -F "file=@document.pdf"

# OCR extraction (offline)
curl -X POST "http://localhost:8000/extract?method=ocr" -F "file=@document.pdf"
```

### Option 3: Command Line

```bash
# LLM extraction (default)
python run.py cli --pdf "../Test Sale Deed.pdf" --output result.json

# OCR extraction (offline, no API key needed)
python run.py cli --pdf "../Test Sale Deed.pdf" --method ocr --output result.json
```

## Project Structure

```
sale_deed_extractor/
├── app/
│   ├── __init__.py           # Package init
│   ├── llm_extractor.py      # OpenAI GPT-4o vision extraction
│   ├── ocr.py                # Tesseract OCR pipeline (offline fallback)
│   ├── extractor.py          # Regex-based field extraction (offline fallback)
│   ├── api.py                # FastAPI endpoints
│   └── streamlit_app.py      # Streamlit UI
├── output/                   # Output directory for results
├── .env                      # API key (git-ignored, never committed)
├── .env.example              # Template for .env
├── .gitignore
├── run.py                    # Entry point (CLI/API/UI)
├── requirements.txt          # Python dependencies
├── design_note.md            # System design document
├── evaluation.md             # Evaluation and analysis
└── README.md                 # This file
```

## Sample Output

```json
{
  "document_name": "खरेदीखत",
  "seller_name": "साहेबराव बाजीराव देशमुख",
  "seller_age": "७५ वर्षे",
  "seller_address": "रा. कन्हेरी, लातूर",
  "buyer_name": "शितल दीपक पवार",
  "buyer_age": "२७ वर्षे",
  "buyer_address": "रा. गांधी चौक, कामदार पेट्रोल पंप जवळ, लातूर",
  "boundary_east": "सदरित सर्वे नंबर मधील जमीन",
  "boundary_west": "६ मीटर रुंदीचा रस्ता",
  "boundary_north": "सर्वे नंबर १२",
  "boundary_south": "सदरित प्लॉट नंबर ३ चा उर्वरित भाग",
  "area_size": "48.06 च. मी. (518.92 च. फूट)",
  "property_address": "सर्वे नंबर 12/31/9, कन्हेरी, तालुका लातूर, जिल्हा लातूर, महाराष्ट्र",
  "registration_date": "15/10/2018",
  "registration_number": "8224/2018",
  "book_number": "दस्त गोषवारा भाग-1",
  "sro_office": "S.R. Latur 1",
  "sale_amount": "1,21,000",
  "notes": [],
  "extraction_method": "LLM Vision (OpenAI gpt-4o)"
}
```

> This is **actual output** from running GPT-4o on the test document (not hand-crafted).
> 16 of 18 fields extracted correctly. North/South boundaries are swapped — a known LLM limitation.

## Measured Accuracy (Test Sale Deed)

| Metric | LLM (GPT-4o) | OCR + Regex |
|--------|--------------|-------------|
| Fields correct (usable) | 16/18 (89%) | 11/18 (61%) |
| Fields wrong | 2/18 (11%) | 4/18 (22%) |
| Fields missing | 0/18 (0%) | 3/18 (17%) |

**Known LLM weakness**: North/South boundary directions can be swapped on dense layouts.

## Limitations

- **LLM method**: Requires internet + API key; costs ~$0.05-0.15 per document (high detail, ~19 pages); may swap boundary directions
- **OCR method**: Limited to Marathi/English; corrupts names, garbles survey numbers, misses 17% of fields
- **Handwritten text**: LLM handles it better but not perfectly on very poor scans
