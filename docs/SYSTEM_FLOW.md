# Invoice Automation - System Flow Documentation

## End-to-End Pipeline

```mermaid
flowchart TD
    A[File Upload / API Call] --> B[FileHandler: Validate & Hash]
    B --> C{File Type Detection}
    C -->|PDF| D1[PDFParserStrategy: LlamaParse → PyMuPDF → LLM Vision]
    C -->|Image| D2[ImageParserStrategy: LLM Vision]
    C -->|DOCX| D3[DOCXParserStrategy: python-docx]
    C -->|DOC| D4[DOCParserStrategy: LibreOffice → DOCX]
    C -->|Other| D5[FallbackParser: Error]

    D1 --> E[Raw Text / Markdown]
    D2 --> E
    D3 --> E
    D4 --> E

    E --> F[LLM Provider: Extraction]
    F -->|JSON Output| G[JSON Repair if needed]
    G --> H[ExtractedInvoice Schema Validation]
    H --> I[Normalization: currency, dates, decimals, text]
    I --> J[Validation: amounts, dates, line items]
    J --> K[Extraction Complete → Stored on Queue]

    K --> L[Pluggable Matching Pipeline]
    L --> M[Strategy 1: Exact Lookup]
    M -->|Match| R[Price Validation → Route]
    M -->|No match| M2[Strategy 2: Vendor SKU]
    M2 -->|Match| R
    M2 -->|No match| N[Strategy 3: Alias Lookup]
    N -->|Match| R
    N -->|No match| N2[Strategy 4: Purchase History]
    N2 -->|Match| R
    N2 -->|No match| O[Strategy 5: Fuzzy Match]
    O -->|Match| R
    O -->|No match| O2[Strategy 6: HSN Filter]
    O2 -->|Match| R
    O2 -->|No match| P[Strategy 7: Embedding Search]
    P -->|Match| R
    P -->|No match| Q[Strategy 8: LLM Match]
    Q --> R

    R -->|All fields ≥90%| S[Auto Create Draft PI]
    R -->|Any field 60-89%| T[Review Queue]
    R -->|Any field <60%| U[Manual Entry Queue]

    T --> V[Review Dialog]
    V --> V1{Reviewer reviews extracted vs matched data}
    V1 -->|Override supplier/tax template/cost center| V2[Apply header corrections → create aliases]
    V1 -->|Correct line items with reasoning| V3[Apply item corrections → aliases + catalog + SKU]
    V1 -->|Confirm & Create Invoice| W[Create Draft PI]
    V1 -->|Reject| X[Rejected]

    W --> Y[Correction Memory Updated]
    Y --> Z1[Alias Created/Updated with Recency Weight]
    Y --> Z2[Embedding Index Updated]
    Y --> Z3[Correction Log Recorded]
    Y --> Z4[Supplier Item Catalog Updated]
    Y --> Z5[Vendor SKU Mapping Updated]
```

## Subsystem 1: Extraction Engine

### File Processing Pipeline

```
File Upload → Type Detection → Format Routing → Parsing → LLM Extraction → Schema Validation → Normalization → Validation → Output
```

**Step 1: File Handling** (`file_handler.py`)
- Validates file size against `max_file_size_mb` setting
- Validates extension against `allowed_extensions` setting
- Computes SHA-256 hash for dedup
- Detects MIME type and file category (PDF/Image/DOCX/DOC)

**Step 2: Parser Selection** (`parsers/base_parser.py` factory)
- `PDFParserStrategy` → 3-step fallback chain:
  1. LlamaParse API (if API key configured)
  2. PyMuPDF text extraction (for native PDFs with selectable text)
  3. LLM Vision (renders pages as images via PyMuPDF, sends to configured LLM — handles scanned PDFs)
- `ImageParserStrategy` → Configured LLM provider's vision model (Ollama, OpenAI, Anthropic, or Gemini)
- `DOCXParserStrategy` → python-docx text extraction
- `DOCParserStrategy` → LibreOffice conversion → DOCX parser
- `FallbackParser` → Structured error for unsupported types

**Step 3: LLM Extraction** (`llm/` providers + `prompt_templates.py`)
- Sends parsed text to the configured extraction LLM provider (Ollama, OpenAI, Anthropic, or Gemini)
- Default: Ollama with `qwen2.5vl:7b` (local, free). Paid alternatives: GPT-4o, Claude, Gemini
- Requests strict JSON output matching ExtractedInvoice schema
- Retries on malformed JSON (configurable retry count)
- OpenAI and Gemini use native JSON mode; Ollama and Anthropic use retry + `json_repair.py`

**Step 4: Normalization** (`normalizers/`)
- Currency: ₹ → INR, $ → USD, € → EUR
- Dates: diverse formats → ISO 8601 (YYYY-MM-DD)
- Decimals: Indian numbering (1,23,456.78), European (1.234,56)
- Text: unicode normalization, whitespace cleanup
- Tax IDs: GSTIN/PAN format validation
- Line items: dedup, empty row removal, total recalculation

**Step 5: Validation** (`validators/validation_service.py`)
- Date consistency (due_date not before invoice_date)
- Total consistency (subtotal + tax ≈ total)
- Line item math (qty × price ≈ line_total)
- Line item sum vs subtotal
- Negative amounts (credit note detection)
- Zero-value invoice warning
- Missing critical fields

## Subsystem 2: Pluggable Matching Pipeline

The matching pipeline loads strategies dynamically from the **Matching Strategy** doctype. Strategies are executed in priority order (lower = first). Each can be enabled/disabled and reordered without code changes. Falls back to hardcoded defaults if no strategy records exist.

### Strategy 1: Exact Lookup (Priority 10, ~0ms)
- GSTIN lookup → 100% confidence
- PAN (from GSTIN chars 3-12) → 98% confidence
- Normalized name → 95% confidence
- Uses Redis index for O(1) lookups

### Strategy 2: Vendor SKU Lookup (Priority 15, ~1ms)
- Matches vendor-specific item codes from the invoice against **Vendor SKU Mapping**
- Looks up `(supplier, extracted_item_code)` → mapped ERPNext Item
- 97% confidence — just below exact match
- Vendor SKU Mappings are auto-created from corrections when the invoice has an `item_code`

### Strategy 3: Context-Aware Alias Lookup (Priority 20, ~1ms)
- Supplier-specific: `{supplier}:{normalized_text}:{doctype}` → up to 99% confidence
- Supplier-agnostic: `ANY:{normalized_text}:{doctype}` → up to 90% confidence
- Confidence scaled by **decay_weight** (1.0 for fresh aliases, decays to 0.5 over 100+ days)
- Fed by human corrections on both line items and header fields (supplier, tax template, cost center)

### Strategy 4: Purchase History Match (Priority 25, ~10ms) — Disabled by default
- Queries **Supplier Item Catalog** for items this supplier has sold before
- Fuzzy matches against catalog items only (narrowed candidate set)
- Frequency-boosted: items bought more often score higher
- 70-85% confidence

### Strategy 5: Fuzzy String Matching (Priority 30, ~10-50ms)
- Token Sort Ratio + Partial Ratio + Token Set Ratio (best score wins)
- Score ≥85 → 75-89% confidence
- Score 60-84 → 60-74% confidence
- Score <60 → no match

### Strategy 6: HSN-Filtered Matching (Priority 35, ~10ms) — Disabled by default
- Pre-filters candidate Items by HSN/SAC code before fuzzy matching
- Falls back to HSN prefix (first 4 digits) if exact HSN has no matches
- Provides a confidence boost over regular fuzzy matching (+5-10%)

### Strategy 7: Embedding-Based Semantic Search (Priority 40, ~10-50ms)
- Uses `sentence-transformers/all-MiniLM-L6-v2` (384-dim, L2-normalized)
- In-memory NumPy index (no external vector DB) backed by `Embedding Index` DocType
- Cosine similarity via dot product — O(n) scan against all stored vectors
- Historical Invoice Index (human-corrected entries weighted 1.1x)
- Item Master Index (name + description + brand + HSN)
- Both agree on same item → +10% confidence boost
- Cosine similarity > 0.85 → high confidence

### Strategy 8: LLM-Assisted Match (Priority 50, ~500-2000ms)
- Only when all other strategies fail
- Uses the configured matching LLM provider (Ollama, OpenAI, Anthropic, or Gemini)
- Sends candidates + past corrections with reviewer reasoning
- Confidence capped at 88% (always requires review)

### Post-Match: Price Validation
After any strategy produces a match, the **price validator** adjusts confidence based on historical price data from the Supplier Item Catalog:
- Rate within 15% of average → +5% confidence boost
- Rate >50% off average → -10% confidence penalty
- Requires ≥2 historical occurrences

## Subsystem 3: Correction Memory (CodeRabbit Pattern)

```mermaid
flowchart TD
    A[Reviewer Corrects Match] --> B[Create/Update Mapping Alias<br/>with decay_weight = 1.0]
    A --> C[Log to Mapping Correction Log]
    A --> D[Update Historical Embedding Index]
    A --> E[Check for Conflicts]
    A --> F1[Update Supplier Item Catalog<br/>rate stats + occurrence count]
    A --> F2[Create Vendor SKU Mapping<br/>if item_code present]

    B --> G[Next Invoice: Alias catches it instantly]
    D --> H[Next Invoice: Embedding search finds similar text]
    C --> I[Next Invoice: LLM uses reviewer reasoning]
    F1 --> J[Next Invoice: Purchase History narrows candidates<br/>+ Price Validator adjusts confidence]
    F2 --> K[Next Invoice: Vendor SKU exact match at 97%]

    E -->|Conflict found| L{Correction count > 1?}
    L -->|Yes| M[New correction is authoritative]
    L -->|No| N[Flag both for senior review]

    A2[Reviewer Overrides Header<br/>Supplier / Tax Template / Cost Center] --> B2[Create Mapping Alias for header field]
    A2 --> C2[Log to Mapping Correction Log]
    B2 --> G2[Next Invoice: Alias catches header field instantly]
```

## Confidence-Based Routing

```mermaid
flowchart LR
    A[Min Confidence<br>Across All Fields] --> B{≥ 90%?}
    B -->|Yes| C[Auto Create Draft PI]
    B -->|No| D{≥ 60%?}
    D -->|Yes| E[Review Queue]
    D -->|No| F[Manual Entry]
```

## Data Flow Between Doctypes

| Doctype | Purpose | Fed By | Feeds Into |
|---------|---------|--------|------------|
| Invoice Automation Settings | Configuration + custom extraction fields | Admin | All modules |
| Invoice Processing Queue | Pipeline tracking per invoice | File upload / API | Purchase Invoice |
| Invoice Line Item Match | Per-line match results | Matching Pipeline | Review UI, PI creation |
| Mapping Alias | Learned mappings with recency decay | Human corrections (line items + headers) | Alias strategy lookup |
| Mapping Correction Log | Institutional knowledge | Human corrections | LLM strategy context |
| Embedding Index | Vector storage | Index builder / corrections | Embedding strategy search |
| Matching Strategy | Strategy registry (enable/disable/reorder) | Admin / seed data | Matching Pipeline |
| Supplier Item Catalog | Supplier-item affinity + price stats | PI submissions / corrections | Purchase History strategy, Price Validator |
| Vendor SKU Mapping | Vendor item codes → ERPNext Items | Human corrections | Vendor SKU strategy |
| Extraction Field | Custom extraction field definitions | Admin (child of Settings) | Dynamic prompt + schema |

## Queue Record Lifecycle

| Field | When Set | By Whom |
|-------|----------|---------|
| source_file, file_name, file_hash, file_type | On save (after_insert) | InvoiceProcessingQueue controller |
| extraction_status, extraction_method, extraction_time_ms | During extraction | ExtractionService |
| extracted_data, extraction_confidence, document_type_detected | After extraction | ExtractionService |
| validation_results | After extraction | ExtractionService |
| matched_supplier, supplier_match_confidence, supplier_match_stage | After matching | MatchingPipeline |
| matched_bill_no, matched_bill_date, matched_due_date | After matching | MatchingPipeline |
| matched_currency, matched_total, matched_tax_template | After matching | MatchingPipeline |
| amount_mismatch, amount_mismatch_details | After matching | amount_validator |
| routing_decision, overall_confidence, matching_time_ms | After routing | ConfidenceScorer |
| workflow_state = "Under Review" | After routing (confidence 60-89%) | MatchingPipeline |
| line_items (child table) | After matching | MatchingPipeline |
| purchase_invoice | After review confirmation | confirm_mapping API |
| processed_by | After review confirmation | confirm_mapping API |

## Review & Correction Flow

When a user clicks **Review & Create Invoice**:

1. `get_review_data` API returns extracted vs matched data side-by-side (including `source_file` for preview and enriched line item fields: item_code, SKU, tax_rate, discount)
2. A two-panel review dialog opens:
   - **Left panel**: Invoice preview (PDF iframe or image) with toggle to hide/show
   - **Right panel** (scrollable):
     - Color-coded validation warnings (amount mismatches, duplicates, extraction issues)
     - Compact header grid with confidence badges and pencil-to-edit for Supplier, Tax Template, Cost Center
     - Line item cards sorted by attention needed (low confidence first, auto-expanded)
     - Each card expands inline to show full extracted details (qty, rate, amount, UOM, HSN, item code, SKU, tax rate, discount) + correction fields
   - **Sticky summary bar**: attention count, change count, action buttons — updates in real-time
3. On confirm, `confirm_mapping` API:
   - Applies header overrides (supplier, tax template, cost center) — each creates aliases and correction logs via `process_header_correction()`
   - Processes line item corrections via `process_correction()`:
     - Creates/updates Mapping Alias with recency weight (Alias strategy learning)
     - Logs to Mapping Correction Log (LLM strategy context)
     - Enqueues embedding index update (Embedding strategy learning)
     - Updates Supplier Item Catalog (Purchase History strategy + Price Validator)
     - Creates Vendor SKU Mapping if vendor item code present (Vendor SKU strategy)
     - Checks for conflicts with prior corrections
   - Runs duplicate detection
   - Creates Draft Purchase Invoice with matched/extracted data + custom field mappings

## The Learning Curve

- **Week 1**: Most invoices go to Review Queue. System relies on exact lookups and fuzzy matching.
- **Month 1**: Alias table builds from corrections. Vendor SKU mappings established. Alias strategy catches 40-50% of repeat items.
- **Month 3**: Supplier Item Catalog populates from PI submissions. Purchase History strategy narrows candidates. Historical embedding index grows. Embedding strategy handles variations. Review drops significantly.
- **Month 6+**: 90%+ automatic. Price validation boosts confidence on well-known items. Older aliases with low decay weight get deprioritized in favor of recent corrections. Auto-create can be safely enabled.
