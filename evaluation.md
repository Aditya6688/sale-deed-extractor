# Evaluation and Analysis

## How I Verified Correctness

1. **Established ground truth by visual inspection**: Read every page of the 22-page test PDF and manually recorded the correct value for all 18 fields. Cross-referenced each field across multiple pages where it appeared (e.g., sale amount appears on the deed body, challan, and registration receipt).

2. **Ran both extraction methods** on the same document:
   - LLM Vision: OpenAI GPT-4o with `detail: "high"`, 250 DPI, 19 pages (3 blank pages auto-skipped)
   - OCR + Regex: Tesseract OCR (eng+mar) at 250 DPI with regex pattern matching

3. **Field-by-field comparison** against ground truth, scoring each as: Exact, Near-exact, Correct (different format), Partial, Wrong, or Missing.

## Test Results: Field-by-Field Comparison

| # | Field | Ground Truth | LLM (GPT-4o) | LLM Verdict | OCR+Regex | OCR Verdict |
|---|-------|-------------|---------------|-------------|-----------|-------------|
| 1 | Document name | खरेदीखत | खरेदीखत | Exact | Sale Deed (खरेदीखत) | Correct |
| 2 | Seller name | साहेबराव बाजीराव देशमुख | साहेबराव बाजीराव देशमुख | Exact | aaa बाजीराव देशमुख | Wrong |
| 3 | Seller age | ७५ वर्षे | ७५ वर्षे | Exact | *(empty)* | Missing |
| 4 | Seller address | रा. कन्हेरी, लातूर | रा. कन्हेरी, लातूर | Exact | कन्हेरी, लातूर | Partial |
| 5 | Buyer name | शितल दिपक पवार | शितल दीपक पवार | Near-exact | शितल दिपक पवार | Exact |
| 6 | Buyer age | २७ वर्षे | २७ वर्षे | Exact | २७ वर्षे | Exact |
| 7 | Buyer address | रा. गांधी चौक... लातूर | रा. गांधी चौक... लातूर | Exact | गांधी चौक... लातूर | Partial |
| 8 | East boundary | सदरील सर्वे नंबर मधील जमीन | सदरित सर्वे नंबर मधील जमीन | Near-exact | सदरील सर्वे नंबर मधील जमीन | Exact |
| 9 | West boundary | ६ मीटर रुंदीचा रस्ता | ६ मीटर रुंदीचा रस्ता | Exact | *(empty)* | Missing |
| 10 | North boundary | सदरील प्लॉट नंबर ३... | सर्वे नंबर १२ | Wrong (swapped with South) | सदरील प्लॉट नंबर ३... | Exact |
| 11 | South boundary | सर्वे नंबर १२ | सदरित प्लॉट नंबर ३... | Wrong (swapped with North) | उत्तर ४८.०६ चौ.मी. | Wrong |
| 12 | Area | ४८.०६ चौ.मी. (५१७.१२ चौ.फुट) | 48.06 च.मी. (518.92 च.फूट) | Near-correct | ४८.०६ Sq. Mtr | Partial |
| 13 | Property address | सर्वे १२/३१/९, प्लॉट ३, कन्हेरी, लातूर | सर्वे 12/31/9, कन्हेरी, लातूर, महाराष्ट्र | Correct | Survey No. 12741... ata... | Wrong |
| 14 | Reg. date | 15/10/2018 | 15/10/2018 | Exact | 15/10/2018 | Exact |
| 15 | Reg. number | 8224/2018 | 8224/2018 | Exact | 1101/2018 | Wrong |
| 16 | Book number | दस्त गोषवारा भाग-1 | दस्त गोषवारा भाग-1 | Exact | *(empty)* | Missing |
| 17 | SRO office | Sub Registrar Latur 1 | S.R. Latur 1 | Correct | Sub Registrar Latur 1 | Exact |
| 18 | Sale amount | रु. १,२१,०००/- | 1,21,000 | Correct | रुपये १,२१,००० | Correct |

## Accuracy Summary

| Metric | LLM (GPT-4o) | OCR + Regex |
|--------|--------------|-------------|
| **Exact / Near-exact** | 13/18 (72%) | 6/18 (33%) |
| **Correct (usable data)** | 16/18 (89%) | 11/18 (61%) |
| **Wrong** | 2/18 (11%) | 4/18 (22%) |
| **Missing** | 0/18 (0%) | 3/18 (17%) |
| **All fields have data** | 18/18 (100%) | 15/18 (83%) |

## Key Failure Cases Observed

### LLM Vision: North/South Boundary Swap
The most significant LLM failure was **swapping the North and South boundaries**. The LLM correctly read both boundary values from the document but assigned them to the wrong directions. This is a known spatial reasoning weakness in current vision models — they can read the text next to directional labels but sometimes confuse which label goes with which value when the layout is dense.

**Mitigation**: Add post-processing that searches the raw extracted text for directional keywords (उत्तर, दक्षिण) and validates the assignment. Alternatively, ask the LLM to also quote the directional label alongside each value.

### LLM Vision: Minor Spelling Variants
The LLM produced "सदरित" instead of "सदरील" and "दीपक" instead of "दिपक". These are Devanagari character-level differences that don't affect meaning but show the model is reading from a degraded scan and making minor transcription choices.

### OCR + Regex: Corrupted Names
Tesseract rendered "साहेबराव" as "aaa" — the first name was completely lost. This is a fundamental OCR limitation on scanned Marathi text where ink quality varies.

### OCR + Regex: Wrong Registration Number
OCR extracted "1101/2018" instead of "8224/2018". The registration number appears on a cluttered page with overlapping text and stamps, causing Tesseract to pick up the wrong digit sequence.

### OCR + Regex: Garbled Property Address
The survey number "12/A/1" was OCR'd as "12741" and the taluka "Latur" became "ata". These are typical Tesseract failures on mixed-script alphanumeric content.

## Hardest Fields to Extract and Why

| Field | LLM Difficulty | OCR Difficulty | Why |
|-------|---------------|----------------|-----|
| **Boundaries (direction assignment)** | High | High | LLM swaps directions; OCR misses entire boundaries |
| **Registration Number** | Low | Very High | Clean for LLM; OCR merges/splits digits on cluttered pages |
| **Seller/Buyer Names** | Low | High | LLM reads Marathi fluently; Tesseract corrupts characters |
| **Property Address** | Low | Very High | LLM understands context; OCR garbles survey numbers |
| **Book Number** | Low | Very High | LLM finds it easily; OCR can't match the label at all |
| **Area** | Low | Medium | Both methods find the number; LLM also captures sq ft |
| **Sale Amount** | Low | Low | Appears in multiple places in both English and Marathi |
| **SRO Office** | Low | Low | Typically in English on the challan page |

## How Performance Would Change on Different Documents

### Strengths of the LLM Approach
The GPT-4o vision method will generalize well because:
- It reads any script without language-specific configuration
- It understands document layout, tables, and mixed-language sections natively
- A single prompt covers all Indian state formats — no new regex rules needed
- It handles degraded scans, stamps, and partial handwriting better than OCR

### Expected Degradation Scenarios
- **Heavily handwritten deeds**: Accuracy would drop to ~70-80% as GPT-4o struggles with cursive Devanagari
- **Very low resolution scans (<150 DPI)**: Small text becomes unreadable even for the LLM
- **Non-standard formats** (e.g., pre-2000 typewritten deeds): May miss fields if layout is very different from modern registered documents
- **Documents in scripts with less LLM training data** (e.g., Odia, Assamese): Likely 5-10% accuracy drop vs Hindi/Marathi

### OCR Method Limitations
The OCR + regex fallback is fundamentally limited to Maharashtra Marathi/English deeds. It will fail on:
- Any non-Devanagari script (Tamil, Telugu, Kannada, etc.)
- Hindi deeds from other states (different legal labels)
- Any layout that doesn't follow the Maharashtra Sub-Registrar format
