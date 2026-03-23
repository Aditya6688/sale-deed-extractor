"""
Streamlit UI for Sale Deed Information Extraction.
Uses OpenAI GPT-4o vision (primary) or OCR+regex (offline fallback).
API key is loaded from .env file — never exposed in the UI.
"""

import os
import sys
import json
import tempfile
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.llm_extractor import extract_with_llm, _get_api_key
from app.ocr import extract_text_from_pdf
from app.extractor import extract_all

st.set_page_config(page_title="Sale Deed Extractor", page_icon="📄", layout="wide")

st.title("Sale Deed Information Extractor")
st.markdown(
    "Upload a scanned sale deed PDF to extract structured legal and property information. "
    "Supports **all Indian languages** and document formats."
)

# --- Sidebar: Configuration ---
st.sidebar.header("Settings")

# Check if API key is available (don't display it)
has_api_key = bool(_get_api_key())

if has_api_key:
    st.sidebar.success("OpenAI API key loaded")
else:
    st.sidebar.error(
        "OpenAI API key not found. "
        "Add `OPENAI_API_KEY=sk-...` to the `.env` file in the project root, "
        "or set it as an environment variable."
    )

method = st.sidebar.radio(
    "Extraction method:",
    ["LLM Vision (Recommended)", "OCR + Regex (Offline)"],
    index=0 if has_api_key else 1,
    help=(
        "**LLM Vision**: Uses OpenAI GPT-4o to read document images directly. "
        "Works with any Indian language and layout. Requires API key.\n\n"
        "**OCR + Regex**: Uses Tesseract OCR + pattern matching. "
        "Works offline but limited to Marathi/English Maharashtra deeds."
    ),
)

model = "gpt-4o"
if method == "LLM Vision (Recommended)":
    model = st.sidebar.selectbox(
        "Model:",
        ["gpt-4o", "gpt-4o-mini", "gpt-4.1"],
        index=0,
    )

# --- Main area ---
uploaded_file = st.file_uploader("Upload Sale Deed PDF", type=["pdf"])

if uploaded_file is not None:
    # Validate file size (50 MB limit)
    file_bytes = uploaded_file.read()
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > 50:
        st.error(f"File is {file_size_mb:.1f} MB. Maximum allowed is 50 MB.")
        st.stop()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        if method == "LLM Vision (Recommended)":
            if not has_api_key:
                st.error(
                    "Cannot use LLM Vision without an API key. "
                    "Please add your OpenAI API key to the `.env` file or switch to OCR + Regex."
                )
                st.stop()

            with st.spinner(f"Analyzing document with OpenAI {model}... This may take 30-60 seconds."):
                result = extract_with_llm(tmp_path, model=model)
            st.success("Extraction complete!")
            extraction_method = result.pop("extraction_method", "LLM Vision")

        else:
            with st.spinner("Running OCR on document... This may take a minute."):
                ocr_result = extract_text_from_pdf(tmp_path, dpi=300)

            with st.spinner("Extracting structured fields..."):
                data = extract_all(ocr_result["pages"], ocr_result["full_text"])
                result = data.to_dict()
            st.success("Extraction complete!")
            extraction_method = "OCR + Regex (Offline)"

        # ---- Display Results ----
        notes = result.pop("notes", [])

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Extracted Fields")
            st.caption(f"Method: {extraction_method}")

            st.markdown("**Document Name:**")
            st.info(result.get("document_name", "") or "Not found")

            st.markdown("---")
            st.markdown("### Seller Details (Party 1)")
            st.markdown(f"**Name:** {result.get('seller_name', '') or 'Not found'}")
            st.markdown(f"**Age:** {result.get('seller_age', '') or 'Not found'}")
            st.markdown(f"**Address:** {result.get('seller_address', '') or 'Not found'}")

            st.markdown("---")
            st.markdown("### Buyer Details (Party 2)")
            st.markdown(f"**Name:** {result.get('buyer_name', '') or 'Not found'}")
            st.markdown(f"**Age:** {result.get('buyer_age', '') or 'Not found'}")
            st.markdown(f"**Address:** {result.get('buyer_address', '') or 'Not found'}")

            st.markdown("---")
            st.markdown("### Property Boundaries")
            st.markdown(f"**East:** {result.get('boundary_east', '') or 'Not found'}")
            st.markdown(f"**West:** {result.get('boundary_west', '') or 'Not found'}")
            st.markdown(f"**North:** {result.get('boundary_north', '') or 'Not found'}")
            st.markdown(f"**South:** {result.get('boundary_south', '') or 'Not found'}")

            st.markdown("---")
            st.markdown("### Property Details")
            st.markdown(f"**Area:** {result.get('area_size', '') or 'Not found'}")
            st.markdown(f"**Address/Plot:** {result.get('property_address', '') or 'Not found'}")
            st.markdown(f"**Sale Amount:** {result.get('sale_amount', '') or 'Not found'}")

            st.markdown("---")
            st.markdown("### Registration Details")
            st.markdown(f"**Registration Date:** {result.get('registration_date', '') or 'Not found'}")
            st.markdown(f"**Registration Number:** {result.get('registration_number', '') or 'Not found'}")
            st.markdown(f"**Book Number:** {result.get('book_number', '') or 'Not found'}")
            st.markdown(f"**SRO Office:** {result.get('sro_office', '') or 'Not found'}")

        with col2:
            st.subheader("JSON Output")
            output = {**result, "notes": notes}
            json_output = json.dumps(output, indent=2, ensure_ascii=False)
            st.code(json_output, language="json")

            st.download_button(
                label="Download JSON",
                data=json_output,
                file_name="extracted_sale_deed.json",
                mime="application/json",
            )

            if notes:
                st.markdown("---")
                st.subheader("Extraction Notes")
                for note in notes:
                    st.warning(note)

        # Debug: show OCR text if using OCR method
        if method == "OCR + Regex (Offline)":
            with st.expander("View Raw OCR Text (Debug)"):
                for page_num, text in ocr_result["pages"].items():
                    st.markdown(f"**Page {page_num}:**")
                    st.text(text[:2000])
                    st.markdown("---")

    except Exception as e:
        st.error(f"Error during extraction: {str(e)}")
        st.exception(e)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass  # File may already be deleted or locked on Windows

else:
    st.info("Upload a sale deed PDF to begin extraction.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Supported Languages")
        st.markdown("""
        - Marathi, Hindi, Tamil, Telugu
        - Kannada, Gujarati, Bengali
        - Malayalam, Punjabi, Odia
        - English and more
        """)
    with col2:
        st.markdown("### Fields Extracted")
        st.markdown("""
        - Document name & type
        - Seller details (name, age, address)
        - Buyer details (name, age, address)
        - Boundaries (East, West, North, South)
        - Property area & address
        - Registration date & number
        - Book number & SRO office
        - Sale deed amount
        """)
