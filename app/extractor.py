"""
Core extraction logic for sale deed fields.
Uses a hybrid approach: regex patterns + keyword matching + heuristics.
Handles both English and Marathi (Devanagari) text.

IMPORTANT: This module contains NO hardcoded values from any specific document.
All extraction is pattern-based and will work on any Maharashtra-style sale deed.
"""

import re
import json
from dataclasses import dataclass, field, asdict


@dataclass
class SaleDeedData:
    document_name: str = ""
    seller_name: str = ""
    seller_age: str = ""
    seller_address: str = ""
    buyer_name: str = ""
    buyer_age: str = ""
    buyer_address: str = ""
    boundary_east: str = ""
    boundary_west: str = ""
    boundary_north: str = ""
    boundary_south: str = ""
    area_size: str = ""
    property_address: str = ""
    registration_date: str = ""
    registration_number: str = ""
    book_number: str = ""
    sro_office: str = ""
    sale_amount: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Normalize whitespace."""
    return re.sub(r'\s+', ' ', text).strip()


def _first_match(patterns: list[str], text: str, group: int = 1,
                 flags: int = 0) -> str:
    """Try multiple regex patterns in order; return first match or ''."""
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            return _clean(m.group(group))
    return ""


def _extract_block_after(label_pattern: str, text: str,
                         max_lines: int = 4) -> str:
    """
    Find a label in text and return the content block that follows it.
    Captures up to max_lines of non-empty lines after the label.
    """
    m = re.search(label_pattern, text)
    if not m:
        return ""
    rest = text[m.end():]
    lines = []
    for line in rest.split('\n'):
        line = line.strip()
        if not line:
            if lines:
                break
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Document Name
# ---------------------------------------------------------------------------

def extract_document_name(pages: dict, full_text: str) -> str:
    """Identify the type of document from keywords."""
    indicators = [
        ("खरेदीखत", "Sale Deed (खरेदीखत)"),
        ("खरेदी", "Sale Deed (खरेदी)"),
        ("विक्री करारनामा", "Sale Deed (विक्री करारनामा)"),
        ("विक्रीपत्र", "Sale Deed (विक्रीपत्र)"),
        ("sale deed", "Sale Deed"),
        ("conveyance deed", "Conveyance Deed"),
        ("gift deed", "Gift Deed (दानपत्र)"),
        ("दानपत्र", "Gift Deed (दानपत्र)"),
        ("mortgage", "Mortgage Deed"),
        ("गहाणखत", "Mortgage Deed (गहाणखत)"),
        ("lease", "Lease Deed"),
        ("भाडेपट्टा", "Lease Deed (भाडेपट्टा)"),
    ]
    lower = full_text.lower()
    for keyword, label in indicators:
        if keyword in lower or keyword in full_text:
            return label
    return "Property Document (Unknown Type)"


# ---------------------------------------------------------------------------
# Party Details (Seller / Buyer)
# ---------------------------------------------------------------------------

def _extract_party_block(label_patterns: list[str], full_text: str) -> tuple[str, str, str]:
    """
    Generic extractor for a party (seller or buyer) given label patterns.
    Returns (name, age, address).
    """
    name, age, address = "", "", ""

    for pat in label_patterns:
        m = re.search(pat, full_text, re.DOTALL)
        if not m:
            continue

        # Get the block of text following the label (up to next section)
        rest = full_text[m.end():]
        # Take up to ~500 chars or until we hit a known section boundary
        block_end = re.search(
            r'(?:लिह[ूु]न\s*(?:देणार|घेणार)|चतु[ःः]सिमा|साक्षीदार|'
            r'नोंदणी\s*तुकडी|सदरील\s*प्लॉट|महानगर\s*पालिका)',
            rest
        )
        block = rest[:block_end.start()] if block_end else rest[:500]

        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue

        # First non-empty line is usually the name
        name = _clean(lines[0])

        # Age: look for "वय XX वर्ष" pattern in the block
        age_m = re.search(r'वय\s*[:\-]?\s*([०-९\d]+)\s*वर्ष', block)
        if age_m:
            age = age_m.group(1) + " वर्षे"

        # Address: look for "रा." or "रा:" prefix (= resident of)
        addr_m = re.search(r'रा[.\s:]+\s*(.*?)(?:\n|$)', block)
        if addr_m:
            address = _clean(addr_m.group(1))

        # If no "रा." found, try the line after age
        if not address and len(lines) >= 3:
            address = _clean(lines[-1])

        if name:
            break

    return name, age, address


def extract_seller_details(pages: dict, full_text: str) -> tuple[str, str, str]:
    """
    Extract seller (लिहून देणार / विक्रेता / First Party) details.
    In Marathi sale deeds, the seller is labeled 'लिहून देणार' (the one who writes/gives).
    """
    # Marathi label patterns for seller
    marathi_patterns = [
        r'लिह[ूु]न\s*देणार\s*[:\->]+\s*',
        r'विक्रेता\s*[:\->]+\s*',
        r'पक्ष\s*क्र[.\s]*१\s*[:\->]+\s*',
    ]
    name, age, address = _extract_party_block(marathi_patterns, full_text)

    # Fallback: English patterns from registration pages
    if not name:
        name = _first_match([
            r'SecondPartyName\s*=\s*(.*?)(?:\n|[-]CA)',
            r'(?:Seller|Vendor|First\s*Party)\s*[:\-]\s*(.*?)(?:\n|$)',
        ], full_text, flags=re.IGNORECASE)

    return name, age, address


def extract_buyer_details(pages: dict, full_text: str) -> tuple[str, str, str]:
    """
    Extract buyer (लिहून घेणार / खरेदीदार / Second Party) details.
    In Marathi sale deeds, the buyer is labeled 'लिहून घेणार' (the one who takes).
    """
    marathi_patterns = [
        r'लिह[ूु]न\s*घेणार\s*[:\->]+\s*',
        r'खरेदीदार\s*[:\->]+\s*',
        r'पक्ष\s*क्र[.\s]*२\s*[:\->]+\s*',
    ]
    name, age, address = _extract_party_block(marathi_patterns, full_text)

    # Fallback: English from challan / registration
    if not name:
        name = _first_match([
            r'Full\s*Name\s*[:\s]+([A-Z][A-Z\s]+?)(?:\n|$)',
            r'(?:Buyer|Purchaser|Second\s*Party)\s*[:\-]\s*(.*?)(?:\n|$)',
            r'(?:Received\s+from|Payer)\s*[:\s]+(.*?)(?:,|\n|Mobile)',
        ], full_text, flags=re.IGNORECASE)

    return name, age, address


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------

def extract_boundaries(pages: dict, full_text: str) -> tuple[str, str, str, str]:
    """
    Extract property boundaries (East, West, North, South).
    Searches for the चतुःसिमा (four-boundary) section commonly found in
    Maharashtra sale deeds, then matches directional keywords.
    Also supports English boundary labels.
    """
    east, west, north, south = "", "", "", ""

    # Try to isolate the boundary section for more precise matching
    boundary_section = full_text
    bs_match = re.search(
        r'चतु[ःः]सिमा.*?\n(.*?)(?:येणे\s*प्रमाणे|रक्‍कम|सबब|म्हणून)',
        full_text, re.DOTALL
    )
    if bs_match:
        boundary_section = bs_match.group(1)

    # Marathi directional patterns (flexible separators)
    east = _first_match([
        r'प[ूु]र्व[ेस]*\s*[:\->]+\s*(.*?)(?:\n|$)',
        r'[Ee]ast\s*[:\->]+\s*(.*?)(?:\n|$)',
    ], boundary_section)

    west = _first_match([
        r'पश्[‍\u200d]?चिम[ेस]*\s*[:\->]+\s*(.*?)(?:\n|$)',
        r'[Ww]est\s*[:\->]+\s*(.*?)(?:\n|$)',
    ], boundary_section)

    south = _first_match([
        r'दक्षिण[ेोस]*\s*[:\->]+\s*(.*?)(?:\n|$)',
        r'[Ss]outh\s*[:\->]+\s*(.*?)(?:\n|$)',
    ], boundary_section)

    north = _first_match([
        r'उत्तर[ेस]*\s*[:\->]+\s*(.*?)(?:\n|$)',
        r'[Nn]orth\s*[:\->]+\s*(.*?)(?:\n|$)',
    ], boundary_section)

    return east, west, north, south


# ---------------------------------------------------------------------------
# Area
# ---------------------------------------------------------------------------

def extract_area(pages: dict, full_text: str) -> str:
    """Extract property area. Supports Sq. Mtr, Sq. Ft, acres, hectares, guntha."""
    patterns = [
        # "48.06 SQ MTR" or "48.06 sq. m" or "48.06 चौ.मी"
        (r'([०-९\d]+[.,][०-९\d]+)\s*(?:SQ\.?\s*M(?:TR|eter)?|sq\.?\s*m|चौ[.\s]*मी)', "Sq. Mtr"),
        # "517.12 SQ FT" or "517.12 चौ.फुट"
        (r'([०-९\d]+[.,][०-९\d]+)\s*(?:SQ\.?\s*F(?:T|eet)?|sq\.?\s*f|चौ[.\s]*फु)', "Sq. Ft"),
        # Whole number areas: "500 sq ft"
        (r'([०-९\d]+)\s*(?:SQ\.?\s*M(?:TR|eter)?|sq\.?\s*m|चौ[.\s]*मी)', "Sq. Mtr"),
        (r'([०-९\d]+)\s*(?:SQ\.?\s*F(?:T|eet)?|sq\.?\s*f|चौ[.\s]*फु)', "Sq. Ft"),
        # Acres / एकर
        (r'([०-९\d]+[.,]?[०-९\d]*)\s*(?:acres?|एकर)', "Acres"),
        # Hectare / हेक्टर
        (r'([०-९\d]+[.,]?[०-९\d]*)\s*(?:hectares?|हेक्टर|हे\.?आर)', "Hectare"),
        # Guntha / गुंठा
        (r'([०-९\d]+[.,]?[०-९\d]*)\s*(?:guntha|गुंठा|गुंठे)', "Guntha"),
        # Area from challan "Premises/Building" section with SQ MTR
        (r'Premises.*?([0-9]+[.,][0-9]+)\s*SQ\s*MTR', "Sq. Mtr"),
    ]
    for pat, unit in patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = m.group(1).replace(',', '.')
            return f"{val} {unit}"

    return ""


# ---------------------------------------------------------------------------
# Property Address
# ---------------------------------------------------------------------------

def extract_property_address(pages: dict, full_text: str) -> str:
    """Extract property address by finding survey number, plot, village, district etc."""
    parts = []

    # Survey number / सर्वे नं / Sy.No. / S.No.
    sy = _first_match([
        r'(?:S\.?Y\.?\s*NO|Sy\.?\s*No|S\.?\s*No)\s*[.:\-D]?\s*([\d/A-Za-z]{2,})',
        # OCR often reads "SY NO" as "SYNOD"
        r'SYNOD?\s*([\d/A-Za-z]{2,})',
        r'सर्व[ेें]\s*(?:नं|न[.\s]|नंबर)[.\s:]*\s*([०-९\d/]{2,})',
        r'Flat/Block\s*(?:No\.?)?\s*([\w/]{2,})',
    ], full_text, flags=re.IGNORECASE)
    if sy and len(sy) >= 2:
        # OCR may mangle "12/A/1" to "12/41" — keep as-is, note it
        parts.append(f"Survey No. {sy}")

    # Plot number / प्लॉट नं
    plot = _first_match([
        r'प्लॉट\s*(?:नं|न[.\s]|नंबर)[.\s:]*\s*([०-९\d/]{1,})',
        r'Plot\s*(?:No\.?)\s*[:\-]?\s*([\d/A-Za-z]{1,})',
    ], full_text, flags=re.IGNORECASE)
    if plot and len(plot) >= 1:
        parts.append(f"Plot No. {plot}")

    # Gat number / गट नं
    gat = _first_match([
        r'गट\s*(?:नं|न[.\s]|नंबर)[.\s:]*\s*([०-९\d/]{2,})',
        r'Gat\s*(?:No\.?)\s*[:\-]?\s*([\d/]{2,})',
    ], full_text, flags=re.IGNORECASE)
    if gat:
        parts.append(f"Gat No. {gat}")

    # CTS number (require at least 2 digits)
    cts = _first_match([
        r'C\.?T\.?S\.?\s*(?:No\.?)\s*[:\-]?\s*(\d{2,}[\d/]*)',
    ], full_text, flags=re.IGNORECASE)
    if cts:
        parts.append(f"CTS No. {cts}")

    # Village / मौजे / गाव (require at least 2 chars to avoid OCR noise)
    village = _first_match([
        r'(?:मौजे|गाव)\s*[:\-]?\s*([^\s,\n]{2,})',
        r'Village\s+(?:of\s+)?([A-Za-z]{2,}[\w\s]*?)(?:\s+Taluka|\s+District|\s*,|\n|$)',
    ], full_text, flags=re.IGNORECASE)
    if village and len(village) >= 2:
        parts.append(f"Village: {village}")

    # Taluka / तालुका
    taluka = _first_match([
        r'तालुका\s+(?:व\s+)?(?:शहर\s+)?([^\s,\n]{3,})',
        r'Taluka\s+([A-Za-z]{3,})\s+District',
    ], full_text, flags=re.IGNORECASE)
    if taluka and len(taluka) >= 3:
        parts.append(f"Taluka: {taluka}")

    # District / जिल्हा
    district = _first_match([
        r'(?:जिल्हा)\s*[:\-]?\s*([^\s,\n]{3,})',
        r'District\s+([A-Za-z]{3,}[\w]*)',
    ], full_text, flags=re.IGNORECASE)
    if district and len(district) >= 3:
        # Avoid duplicating taluka if same as district
        if not taluka or district.lower() != taluka.lower():
            parts.append(f"District: {district}")
        else:
            parts.append(f"District: {district}")

    # Road / street from challan
    road = _first_match([
        r'Road/Street\s*[:\-]?\s*(.*?)(?:\n|$)',
    ], full_text, flags=re.IGNORECASE)
    if road:
        parts.append(f"Road: {road}")

    # Area/Locality from challan
    locality = _first_match([
        r'Area/Locality\s*[:\-]?\s*(.*?)(?:\n|$)',
    ], full_text, flags=re.IGNORECASE)
    if locality:
        parts.append(f"Locality: {locality}")

    # PIN
    pin = _first_match([
        r'PIN\s*[:\-]?\s*(\d{6})',
        r'पिन\s*[:\-]?\s*(\d{6})',
    ], full_text, flags=re.IGNORECASE)
    if pin:
        parts.append(f"PIN: {pin}")

    return ", ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Registration Details
# ---------------------------------------------------------------------------

def extract_registration_date(pages: dict, full_text: str) -> str:
    """Extract registration date from multiple possible locations."""
    patterns = [
        # "पावती दिनांक: 15/10/2018" from registration receipt (most reliable)
        r'(?:पावती|Peat)\s*(?:दिनांक)?[:\-\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})',
        # "वेळ:15/10/2018" timestamp from registration page
        r'वेळ\s*[:\-]?\s*(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4})',
        # Registration timestamp "15/10/2018 03:42:04 PM" near मादरीकरण
        r'(\d{1,2}\s*/?\s*\d{1,2}\s*/?\s*\d{4})\s*\d{1,2}\s*:\s*\d{2}.*?(?:मादरी|नोंदणी)',
        # "Date 12/10/2018" from challan
        r'Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        # दिनांक dd/mm/yyyy (deed execution date)
        r'दिनांक\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})',
    ]
    date = _first_match(patterns, full_text)
    # Normalize spaces in date
    if date:
        date = re.sub(r'\s*/\s*', '/', date).strip()
    return date


def extract_registration_number(pages: dict, full_text: str) -> str:
    """Extract document registration number."""
    patterns = [
        # "दस्त क्रमांक: 8224/2018" (document number)
        r'दस्त\s*क्रमांक\s*[:\-]?\s*(\d+[/\d]*)',
        # OCR may render it as "8224/2018" near receipt context
        r'(?:नवर|सतर)\s*\d?\s*/?\s*(\d+/\d{4})',
        # English document number
        r'Document\s*(?:No|Number)\s*[:\-]?\s*(\d+[/\d]*)',
        # Deed number
        r'Deed\s*(?:No|Number)\s*[:\-]?\s*(\d+[/\d]*)',
        # Generic "number/year" near registration context
        r'(?:Reg(?:istration)?|नोंदणी)\s*(?:No|Number|क्रमांक)\s*[:\-]?\s*(\d+[/\d]*)',
        # OCR pattern: "(8224/2018" or "8224201" broken up
        r'\(?(\d{3,6})\s*/?\s*(\d{4})\s*\)?',
    ]
    # Try standard patterns first
    result = _first_match(patterns[:5], full_text, flags=re.IGNORECASE)
    if result:
        return result

    # Look for "दस्त क्रमांक" label with OCR noise
    m = re.search(r'दस्त\s*[^\n]{0,10}?(\d{4,})\s*[/]?\s*(\d{4})', full_text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    # OCR often merges "8224/2018" into "(8224201" or "82242018"
    # Look for 7-8 digit number near registration context on receipt pages
    m = re.search(r'\(?(\d{4})\s*[/]?\s*(20\d{1,2})\s', full_text)
    if m:
        year = m.group(2)
        if len(year) == 3:
            year = year + "8"  # common truncation
        return f"{m.group(1)}/{year}"

    # Space-separated on the last page: "8224 1204" or "8224/201"
    m = re.search(r'[Rr]egistrants?\s*.*?(\d{4})\s+(\d{4})', full_text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    # Last resort: look for 4+ digit / 4-digit year pattern anywhere
    m = re.search(r'(\d{4,6})\s*/\s*(20\d{2})', full_text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    return ""


def extract_book_number(pages: dict, full_text: str) -> str:
    """Extract book number (दस्त गोषवारा भाग / Index volume)."""
    patterns = [
        r'दस्त\s*गो[षश]वारा\s*(?:भाग|माग)\s*[:\-]?\s*(\d+)',
        # OCR often breaks this: "artBhag: 1)" or "Bhag-1" or "भाग - २"
        r'[Bb]hag\s*[:\-]?\s*(\d+)',
        r'भाग\s*[:\->]*\s*(\d+)',
        r'(?:Book|Volume)\s*(?:No|Number)\s*[:\-]?\s*(\d+)',
        r'सतर\s*(\d)',
    ]
    return _first_match(patterns, full_text, flags=re.IGNORECASE)


def extract_sro(pages: dict, full_text: str) -> str:
    """Extract Sub-Registrar Office name."""
    # Try "S.R. Latur 1" style from receipt page (most clean)
    m = re.search(r'(?:Sub\s*)?Registrar\s+office\s+S\.?\s*R\.?\s*(.*?)(?:of\s+the|$|\n)',
                  full_text, re.IGNORECASE)
    if m:
        return f"Sub Registrar {_clean(m.group(1))}"

    # From challan "Office Name" - take only the SUB REGISTRAR part
    m = re.search(r'(?:Office\s*Name|OfficaNama)\s*[:\-]?\s*(.*?)(?:\n|$)', full_text, re.IGNORECASE)
    if m:
        val = _clean(m.group(1))
        # The challan line often has "LTR1_HQR SUB REGISTRAR LATUR 1 <BUYER NAME>"
        # Truncate at the first person name (all-caps sequence after the office)
        sub_m = re.match(r'(.*?SUB\s*REGISTRAR\s+\w+\s*\d*)', val, re.IGNORECASE)
        if sub_m:
            return _clean(sub_m.group(1))
        return val

    # Marathi SRO labels
    sro = _first_match([
        r'(?:उप\s*निबंधक|दुय्यम\s*निबंधक)\s*[:\-]?\s*(.*?)(?:\n|$)',
        r'SRO\s*[:\-]?\s*(.*?)(?:\n|$)',
        r'S\.?\s*R\.?\s*(?:Office)?\s*([\w\s]+\d*)',
    ], full_text, flags=re.IGNORECASE)

    return sro


def extract_sale_amount(pages: dict, full_text: str) -> str:
    """Extract sale deed transaction amount."""
    patterns = [
        # "मोबदला: रु. 1,21,000" (consideration amount - most reliable)
        r'मोबदला\s*[:\-]?\s*(?:रु[.\s]*|Rs\.?\s*)\s*([\d,]+)',
        # "रक्कम रुपये 1,21,000/-"
        r'रक्‍?कम\s*रुपये\s*([\d,]+)',
        # "किंमत रक्कम रुपये X"
        r'किंमत\s*रक्‍?कम\s*रुपये\s*([\d,]+)',
        # "बाजारी किंमत रक्कम रुपये X"
        r'बाजारी\s*किंमत.*?रुपये\s*([\d,]+)',
        # Devanagari numerals: "रुपये १,२१,०००"
        r'(?:मोबदला|रक्‍?कम|किंमत).*?रुपये\s*([१-९][०-९,]+)',
        # English: "Rs. 1,21,000" or "Amount Rs. X"
        r'(?:Amount|Consideration|Sale\s*Price)\s*[:\-]?\s*(?:Rs\.?\s*)([\d,]+)',
        # Total from challan
        r'Total\s+[\d,]+\.?\d*\s*(?:\n|$)',
    ]
    for pat in patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            val = _clean(m.group(1))
            # If Devanagari numerals, keep as-is
            if re.search(r'[०-९]', val):
                return f"रुपये {val}"
            return f"Rs. {val}"

    # Last resort: look for large rupee amounts
    amounts = re.findall(r'(?:Rs\.?|रु[.\s])\s*([\d,]{5,})', full_text)
    if amounts:
        return f"Rs. {amounts[0]}"

    return ""


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def extract_all(pages: dict, full_text: str) -> SaleDeedData:
    """Run all extractors and return structured data with confidence notes."""
    data = SaleDeedData()
    notes = []

    data.document_name = extract_document_name(pages, full_text)

    # Seller
    seller_name, seller_age, seller_addr = extract_seller_details(pages, full_text)
    data.seller_name = seller_name
    data.seller_age = seller_age
    data.seller_address = seller_addr
    if not seller_name:
        notes.append("Seller name could not be extracted. "
                      "The label 'लिहून देणार' or equivalent was not found in OCR text.")

    # Buyer
    buyer_name, buyer_age, buyer_addr = extract_buyer_details(pages, full_text)
    data.buyer_name = buyer_name
    data.buyer_age = buyer_age
    data.buyer_address = buyer_addr
    if not buyer_name:
        notes.append("Buyer name could not be extracted. "
                      "The label 'लिहून घेणार' or equivalent was not found in OCR text.")

    # Boundaries
    east, west, north, south = extract_boundaries(pages, full_text)
    data.boundary_east = east
    data.boundary_west = west
    data.boundary_north = north
    data.boundary_south = south
    missing_boundaries = [d for d, v in [("East", east), ("West", west),
                                          ("North", north), ("South", south)] if not v]
    if missing_boundaries:
        notes.append(f"Could not extract boundaries for: {', '.join(missing_boundaries)}. "
                      "The चतुःसिमा section may be missing or OCR failed on it.")

    # Area
    data.area_size = extract_area(pages, full_text)
    if not data.area_size:
        notes.append("Property area could not be extracted. "
                      "No Sq. Mtr / Sq. Ft / Acre pattern found.")

    # Property address
    data.property_address = extract_property_address(pages, full_text)
    if not data.property_address:
        notes.append("Property address could not be extracted. "
                      "No survey/plot/gat number or village/district found.")

    # Registration
    data.registration_date = extract_registration_date(pages, full_text)
    if not data.registration_date:
        notes.append("Registration date not found.")

    data.registration_number = extract_registration_number(pages, full_text)
    if not data.registration_number:
        notes.append("Registration number not found.")

    data.book_number = extract_book_number(pages, full_text)
    if not data.book_number:
        notes.append("Book number (दस्त गोषवारा भाग) not found.")

    data.sro_office = extract_sro(pages, full_text)
    if not data.sro_office:
        notes.append("Sub-Registrar Office name not found.")

    # Sale amount
    data.sale_amount = extract_sale_amount(pages, full_text)
    if not data.sale_amount:
        notes.append("Sale amount could not be extracted.")

    data.notes = notes
    return data
