"""
Entry point for the Sale Deed Extractor.
Supports CLI, FastAPI, and Streamlit modes.
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_cli(pdf_path: str, output_path: str = None, method: str = "llm",
            model: str = "gpt-4o", dpi: int = 300):
    """Process a PDF and print/save JSON output."""
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Processing: {pdf_path}")
    print(f"Method: {method}")

    if method == "llm":
        from app.llm_extractor import extract_with_llm, _get_api_key

        if not _get_api_key():
            print("Error: OpenAI API key not found.")
            print("Set OPENAI_API_KEY in your environment or add it to .env file.")
            print("Tip: Use --method ocr for offline extraction without an API key.")
            sys.exit(1)

        print(f"Model: {model}")
        print("Sending document to OpenAI vision model...")
        result = extract_with_llm(pdf_path, model=model)
        json_output = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        from app.ocr import extract_text_from_pdf
        from app.extractor import extract_all

        print(f"OCR DPI: {dpi}")
        print("Running OCR...")
        ocr_result = extract_text_from_pdf(pdf_path, dpi=dpi)
        print(f"OCR complete. {len(ocr_result['pages'])} pages processed.")

        print("Extracting structured fields...")
        data = extract_all(ocr_result["pages"], ocr_result["full_text"])
        json_output = data.to_json(indent=2)

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("\n" + "=" * 60)
    print("EXTRACTED DATA:")
    print("=" * 60)
    print(json_output)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"\nJSON saved to: {output_path}")


def run_api():
    """Start the FastAPI server."""
    import uvicorn
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True)


def run_streamlit():
    """Start the Streamlit UI."""
    os.system("streamlit run app/streamlit_app.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sale Deed Information Extractor")
    parser.add_argument("mode", choices=["cli", "api", "ui"],
                        help="Run mode: 'cli' for command line, 'api' for FastAPI, 'ui' for Streamlit")
    parser.add_argument("--pdf", type=str, help="Path to PDF file (required for cli mode)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")
    parser.add_argument("--method", choices=["llm", "ocr"], default="llm",
                        help="Extraction method: 'llm' (default) or 'ocr'")
    parser.add_argument("--model", type=str, default="gpt-4o", help="OpenAI model (default: gpt-4o)")
    parser.add_argument("--dpi", type=int, default=300, help="OCR DPI (default: 300)")

    args = parser.parse_args()

    if args.mode == "cli":
        if not args.pdf:
            print("Error: --pdf is required for cli mode")
            sys.exit(1)
        run_cli(args.pdf, args.output, args.method, args.model, args.dpi)
    elif args.mode == "api":
        run_api()
    elif args.mode == "ui":
        run_streamlit()
