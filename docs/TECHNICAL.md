# Invoice Automation - Technical Documentation

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Installation & Setup](#installation--setup)
3. [Subsystem 1: Extraction Engine](#subsystem-1-extraction-engine)
4. [Subsystem 2: Matching Pipeline](#subsystem-2-matching-pipeline)
5. [Subsystem 3: Correction Memory](#subsystem-3-correction-memory)
6. [Embedding System](#embedding-system)
7. [Validation & Safety](#validation--safety)
8. [Doctype Reference](#doctype-reference)
9. [Configuration Reference](#configuration-reference)
10. [API Endpoint Reference](#api-endpoint-reference)
11. [Hooks & Scheduled Jobs](#hooks--scheduled-jobs)
12. [Extension Guide](#extension-guide)
13. [Exception Hierarchy](#exception-hierarchy)
14. [Troubleshooting](#troubleshooting)
15. [Performance Tuning](#performance-tuning)

---

## Architecture Overview

Three integrated subsystems forming a pipeline: **File → Extract → Match → Route → Review → Learn → Loop**.

```
invoice_automation/
├── extraction/                    # ── SUBSYSTEM 1: Extraction Engine ──
│   ├── schema.py                  # Pydantic v2: ExtractedInvoice, ExtractedLineItem, ExtractionWarning
│   ├── extraction_service.py      # Orchestrator: file → parse → LLM → normalize → validate
│   ├── file_handler.py            # File validation, SHA-256 hashing, MIME detection
│   ├── ollama_client.py           # Ollama HTTP API client with JSON retry + health check
│   ├── json_repair.py             # Auto-repair malformed LLM JSON output
│   ├── prompt_templates.py        # Extraction prompt engineering
│   ├── base_extractor.py          # Abstract InvoiceExtractor interface
│   ├── json_extractor.py          # Pre-extracted JSON input adapter
│   ├── parsers/
│   │   ├── base_parser.py         # ParserStrategy ABC + get_parser() factory
│   │   ├── pdf_parser.py          # LlamaParse integration (fallback: PyMuPDF)
│   │   ├── image_parser.py        # Ollama vision model direct
│   │   ├── docx_parser.py         # python-docx text + table extraction
│   │   ├── doc_parser.py          # LibreOffice conversion → DOCX
│   │   └── fallback_parser.py     # Structured error for unsupported types
│   ├── normalizers/
│   │   ├── currency_normalizer.py # ₹ → INR, $ → USD, € → EUR
│   │   ├── date_normalizer.py     # 15 date formats → ISO 8601
│   │   ├── decimal_normalizer.py  # Indian/European numbering → Decimal string
│   │   ├── text_normalizer.py     # Unicode NFKC, whitespace collapse
│   │   ├── tax_id_normalizer.py   # GSTIN (15-char) / PAN (10-char) validation
│   │   └── line_item_normalizer.py # Dedup, clean empty rows, recalculate totals
│   └── validators/
│       └── validation_service.py  # 8 consistency checks
│
├── matching/                      # ── SUBSYSTEM 2: Matching Pipeline ──
│   ├── pipeline.py                # MatchingPipeline: 5-stage orchestrator
│   ├── normalizer.py              # Text normalization for matching (company suffixes, units)
│   ├── exact_matcher.py           # Stage 1: Redis exact lookups + MatchResult dataclass
│   ├── alias_matcher.py           # Stage 2: Mapping Alias composite key lookups
│   ├── fuzzy_matcher.py           # Stage 3: thefuzz token_sort/partial/token_set
│   ├── embedding_matcher.py       # Stage 4: Dual-index semantic vector search
│   ├── llm_matcher.py             # Stage 5: Claude API with correction context
│   └── confidence.py              # get_config(), determine_routing(), ConfidenceScorer
│
├── memory/                        # ── SUBSYSTEM 3: Correction Memory ──
│   ├── correction_handler.py      # process_correction(): alias + log + embedding + conflict
│   ├── alias_manager.py           # AliasManager: upsert/lookup/deactivate + Redis sync
│   ├── conflict_resolver.py       # check_for_conflicts(), resolve_stale_conflicts()
│   └── reasoning_retriever.py     # ReasoningRetriever: embedding-based correction lookup
│
├── embeddings/
│   ├── model.py                   # sentence-transformers lazy loader (worker process only)
│   ├── index_manager.py           # VectorIndexBase ABC + NumpyVectorIndex + get_index_manager()
│   └── index_builder.py           # build_full_index, rebuild_item_embeddings, sync_missing, doc events
│
├── validation/
│   ├── amount_validator.py        # validate_amounts(): qty×rate sum vs extracted total
│   ├── tax_validator.py           # match_tax_template(), validate_tax_consistency()
│   └── duplicate_detector.py      # check_duplicate(): exact (block) + near (flag)
│
├── api/endpoints.py               # All whitelisted API endpoints (12 endpoints)
├── utils/
│   ├── redis_index.py             # rebuild_all, _build_supplier_index, _build_item_index, doc events
│   ├── exceptions.py              # InvoiceAutomationError hierarchy (12 exception classes)
│   ├── file_utils.py              # compute_sha256, detect_mime_type, validate_file
│   ├── decimal_utils.py           # to_decimal, safe_multiply, round_decimal (never float)
│   └── helpers.py                 # get_config_value (reads from Invoice Automation Settings)
└── hooks.py                       # doc_events, scheduler_events, after_install/migrate
```

---

## Installation & Setup

### Prerequisites
- Frappe bench with ERPNext installed
- Python 3.11+
- Ollama installed and running locally (`ollama serve`)
- Vision model pulled: `ollama pull qwen2.5vl:7b`
- (Optional) LlamaParse API key for PDF parsing
- (Optional) Anthropic API key for Stage 5 LLM matching

### Install the App
```bash
cd frappe-bench
bench get-app invoice_automation <repo-url>
bench --site {site} install-app invoice_automation
bench --site {site} migrate
```

### Install Python Dependencies
```bash
cd frappe-bench
./env/bin/pip install -e apps/invoice_automation
```

### Configuration

All configuration is managed through a single DocType: **Invoice Automation Settings** (a Single document in the Frappe desk). There is no need for `.env` files or `site_config.json` overrides — every setting lives in this DocType.

1. Navigate to **Invoice Automation Settings** in the desk
2. Set `ollama_base_url` (default: `http://localhost:11434`)
3. Set `ollama_model` (default: `qwen2.5vl:7b`)
4. (Optional) Set `llamaparse_api_key` for PDF parsing
5. (Optional) Set `anthropic_api_key` for Stage 5 LLM matching
6. Review and adjust matching thresholds, file handling limits, and other settings as needed

See [Configuration Reference](#configuration-reference) for the full field list.

### Build Indexes
```bash
bench --site {site} execute invoice_automation.utils.redis_index.rebuild_all
bench --site {site} execute invoice_automation.embeddings.index_builder.build_full_index
```

### Verify Installation
```bash
bench --site {site} execute invoice_automation.api.endpoints.health_check
```

---

## Subsystem 1: Extraction Engine

### End-to-End Extraction Flow

```
File Upload → FileHandler.process_file()
    → validate size, extension
    → compute SHA-256 hash
    → detect MIME type & file category
    → return FileInfo

FileInfo → get_parser() factory
    → PDFParserStrategy (if PDF)
    → ImageParserStrategy (if Image)
    → DOCXParserStrategy (if DOCX)
    → DOCParserStrategy (if DOC)
    → FallbackParser (otherwise → error)

Parser.parse() → ParsedDocument (text + page_count + warnings)

ParsedDocument.text → OllamaClient.generate_json()
    → EXTRACTION_PROMPT + EXTRACTION_SYSTEM_PROMPT
    → Ollama API call (HTTP POST to /api/generate)
    → If malformed JSON → json_repair.repair_json()
    → If still malformed → retry (up to json_retry_count)
    → Parse into dict

dict → ExtractedInvoice(**data) Pydantic validation

ExtractedInvoice → ExtractionService._normalize()
    → normalize_currency(invoice.currency)
    → normalize_date(invoice.invoice_date)
    → normalize_date(invoice.due_date)
    → normalize_text(invoice.vendor_name)
    → normalize_text(invoice.customer_name)

ExtractedInvoice → validation_service.run_all_checks()
    → check_date_consistency
    → check_total_consistency
    → check_line_item_totals
    → check_line_item_sum
    → check_negative_amounts
    → check_zero_value
    → check_currency_consistency
    → check_missing_critical_fields

Result → ExtractionResult stored on Invoice Processing Queue
```

### File Handler (`file_handler.py`)

`FileHandler.process_file(file_url)` performs:
1. Resolves Frappe file URL to local path (handles `/files/` and `/private/files/`)
2. Validates file exists and is non-empty
3. Checks file size against `max_file_size_mb` setting (default 25 MB)
4. Checks extension against `allowed_extensions` setting
5. Computes SHA-256 hash via `compute_sha256()`
6. Detects file category: PDF, Image, DOCX, DOC, Unknown
7. Returns `FileInfo` dataclass

`FileHandler.check_duplicate_hash(file_hash)` checks if the same file was already processed.

### Parser Strategies

**`PDFParserStrategy`** — For PDF files
- Primary: LlamaParse API (needs `llamaparse_api_key` in settings)
  - Handles native, scanned, hybrid PDFs
  - Multi-page support (each page = one document)
  - Returns markdown or text (configurable via `llamaparse_result_type`)
- Fallback: PyMuPDF (`fitz`) for basic text extraction
  - Works for native PDFs only
  - Warns if no selectable text found (scanned PDF)

**`ImageParserStrategy`** — For PNG, JPG, JPEG, TIFF, WEBP
- Reads image file, base64-encodes it
- Sends to Ollama vision model via `OllamaClient.generate_with_image()`
- Warns if very little text extracted (<50 chars)

**`DOCXParserStrategy`** — For DOCX files
- Uses `python-docx` library
- Extracts text from paragraphs and tables
- Table cells joined with ` | ` separator

**`DOCParserStrategy`** — For DOC files
- Attempts conversion via LibreOffice: `libreoffice --headless --convert-to docx`
- If successful, delegates to `DOCXParserStrategy`
- 60-second timeout on conversion
- Graceful error if LibreOffice not installed

**`FallbackParser`** — Last resort
- Raises `FileValidationError` with supported formats listed

### Ollama Client (`ollama_client.py`)

**`OllamaClient`** reads all config from Invoice Automation Settings:
- `ollama_base_url`, `ollama_model`, `ollama_timeout_seconds`, `json_retry_count`

Methods:
- `generate(prompt, system)` → raw text response
- `generate_with_image(prompt, image_base64)` → raw text response
- `generate_json(prompt, system)` → parsed dict (with retry + JSON repair)
- `health_check()` → `{status, base_url, configured_model, model_available, available_models}`

API calls go to `{base_url}/api/generate` with `stream: false`.

### JSON Repair (`json_repair.py`)

When Ollama returns malformed JSON, `repair_json(raw)` attempts fixes in order:
1. Strip markdown code fences (` ```json ... ``` `)
2. Remove trailing commas before `}` or `]`
3. Replace single quotes with double quotes
4. Quote unquoted JSON keys
5. Close truncated JSON (balance unclosed braces/brackets)
6. Extract first complete JSON object from surrounding text

Returns `None` if unrecoverable.

### Extraction Prompt (`prompt_templates.py`)

The system prompt instructs the model to:
- Extract ONLY what is explicitly present — never hallucinate
- Return `null` for missing fields
- Keep arrays empty rather than inventing items
- Use string representation for all monetary values
- Normalize dates to ISO 8601, currency to ISO 4217
- Distinguish subtotal/tax/total carefully
- Not confuse bank details with totals
- Not confuse tax summary tables with line items
- Classify document type (invoice, credit_note, debit_note, etc.)
- Report confidence per field group

The user prompt provides the document text and requests a strict JSON structure matching the ExtractedInvoice schema (50+ fields).

### ExtractedInvoice Schema (`schema.py`)

| Field Group | Fields | Type |
|-------------|--------|------|
| **Document Classification** | `document_type`, `document_type_confidence` | str, float |
| **Vendor** | `vendor_name`, `vendor_address`, `vendor_tax_id`, `vendor_pan`, `vendor_phone`, `vendor_email` | str |
| **Customer** | `customer_name`, `customer_address`, `customer_tax_id`, `customer_pan` | str |
| **Invoice Header** | `invoice_number`, `invoice_date`, `due_date`, `purchase_order_number`, `delivery_note_number` | str |
| **Financial Summary** | `currency`, `subtotal`, `tax_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `cess_amount`, `discount_amount`, `shipping_amount`, `round_off_amount`, `total_amount`, `amount_paid`, `balance_due` | str (Decimal) |
| **Tax Details** | `tax_details` (list of dicts), `is_reverse_charge`, `place_of_supply` | list, bool, str |
| **Payment** | `payment_terms`, `payment_method`, `bank_details` | str, dict |
| **Line Items** | `line_items` (list of ExtractedLineItem) | list |
| **Quality** | `extraction_confidence`, `field_group_confidence`, `warnings`, `raw_text_excerpt` | float, dict, list, str |

**ExtractedLineItem fields:** `line_number`, `description`, `quantity`, `unit`, `unit_price`, `tax_rate`, `tax_amount`, `discount_amount`, `line_total`, `hsn_sac_code`, `sku`, `item_code`

All monetary fields are `str | None` — string representation of Decimal, never float.

### Normalizers

| Normalizer | Input Example | Output | Warnings |
|-----------|---------------|--------|----------|
| **currency** | `"₹"`, `"Rs."`, `"USD"` | `"INR"`, `"INR"`, `"USD"` | None |
| **date** | `"15/01/2024"`, `"Jan 15, 2024"`, `"03/04/2024"` | `"2024-01-15"`, `"2024-01-15"`, `"2024-04-03"` (ambiguous → warning) | `ambiguous_date` |
| **decimal** | `"1,23,456.78"` (Indian), `"1.234,56"` (European) | `"123456.78"`, `"1234.56"` | None |
| **text** | `"  Hello\x00  World  "` | `"Hello World"` | None |
| **tax_id** | `"27-AAACT-2727Q-1ZW"` | `"27AAACT2727Q1ZW"` | None |
| **line_items** | List with empty rows, duplicates | Cleaned, deduped, totals recalculated | None |

### Extraction Validators

| Check | What It Does | Severity |
|-------|-------------|----------|
| `check_date_consistency` | due_date not before invoice_date | warning |
| `check_total_consistency` | subtotal + tax + shipping - discount + round_off ≈ total (within ₹1) | warning |
| `check_line_item_totals` | qty × unit_price ≈ line_total per line | warning |
| `check_line_item_sum` | sum(line_totals) ≈ subtotal | warning |
| `check_negative_amounts` | Flags negative totals (may be credit note) | info |
| `check_zero_value` | Flags zero-total invoices | warning |
| `check_currency_consistency` | Currency detected or not | info |
| `check_missing_critical_fields` | Missing invoice_number, vendor_name, total_amount, line_items | warning/error |

---

## Subsystem 2: Matching Pipeline

### Pipeline Orchestration (`pipeline.py`)

`MatchingPipeline.process(extracted_data)` runs sequentially:

1. **Match Supplier** through Stages 1→5
2. **Match each Line Item** through Stages 1→5
3. **Match Tax Templates** (rule-based only, via Stage 1)
4. **Compute routing** from minimum confidence across all fields
5. Return `PipelineResult` with all matches, routing decision, processing time

The pipeline accepts both `dict` and Pydantic `ExtractedInvoice` objects via duck typing.

### Stage 1: Exact Lookup (`exact_matcher.py`)

**Supplier matching order:**
| Lookup | Confidence | Redis Key Pattern |
|--------|-----------|-------------------|
| GSTIN | 100% | `invoice_automation:Supplier:lookup:{GSTIN}` |
| PAN (from GSTIN chars 3-12) | 98% | `invoice_automation:Supplier:lookup:{PAN}` |
| Normalized name | 95% | `invoice_automation:Supplier:lookup:{NORMALIZED_NAME}` |

**Item matching order:**
| Lookup | Confidence | Key Pattern |
|--------|-----------|-------------|
| Normalized item name/description | 95% | `invoice_automation:Item:lookup:{NORMALIZED}` |

Normalization: uppercase, strip punctuation, remove company suffixes (PVT, LTD, LLC, etc.), collapse whitespace.

### Stage 2: Alias Lookup (`alias_matcher.py`)

| Lookup | Confidence | Composite Key |
|--------|-----------|---------------|
| Supplier-specific alias | 99% | `{supplier}:{normalized_text}:{doctype}` |
| Supplier-agnostic alias | 90% | `ANY:{normalized_text}:{doctype}` |

Aliases are stored in the `Mapping Alias` doctype. Lookup tries Redis cache first (`invoice_automation:alias:{composite_key}`), falls back to DB query. Updates `last_used` on hit.

### Stage 3: Fuzzy Match (`fuzzy_matcher.py`)

Runs three algorithms against all master data names, takes the best score:
- `fuzz.token_sort_ratio` — handles word reordering ("Steel Rod 10mm" vs "10mm Steel Rod")
- `fuzz.partial_ratio` — handles substring matches ("Steel" in "Stainless Steel Rod")
- `fuzz.token_set_ratio` — handles extra/missing words

**Confidence mapping:**
| Fuzzy Score | Confidence | Route |
|-------------|-----------|-------|
| ≥ 85 | 75-89% | Review Queue |
| 60-84 | 60-74% | Review Queue |
| < 60 | No match | Next stage |

For Items, also matches against `item_name` and `description` (not just the `name` field).

Master data is cached per-doctype in `FuzzyMatcher._master_data_cache`.

### Stage 4: Embedding Search (`embedding_matcher.py`)

Searches TWO indexes sequentially:
1. **Historical Invoice Line Index** — past line items that were human-corrected (weighted 1.1x via `human_correction_weight_boost`). Filtered by same supplier first, then broadened.
2. **Item Master Index** — all Items with composite text: `"{item_name} | {description} | {brand} | {manufacturer_part_no} | HSN {hsn_code}"`

**Confidence mapping:**
| Cosine Similarity | Confidence | Route |
|-------------------|-----------|-------|
| ≥ 0.85 (configurable) | 80-92% | May auto-create |
| 0.65-0.84 | 65-79% | Review Queue |
| < 0.65 | No match | Next stage |

**Boosts:**
- If both indexes agree on the same item → `+agreement_confidence_boost` (default +10%)
- If match came from human-corrected entry → `×human_correction_weight_boost` (default ×1.1)

### Stage 5: LLM Match (`llm_matcher.py`)

Only invoked when Stages 1-4 all fail. Uses Claude Sonnet via Anthropic API.

**Prompt construction:**
1. Extracted line item text
2. Top candidates from fuzzy cache (up to `llm_max_candidates`, default 10)
3. Past corrections from `ReasoningRetriever` (up to `llm_max_corrections_context`, default 5) — each includes the raw text, what it was corrected to, and the reviewer's reasoning note

**Response:** JSON `{"matched_item": "...", "confidence": 0-100, "reasoning": "..."}`

**Confidence capped at 88%** — LLM matches always require human review.

Gated by `enable_llm_matching` setting. API key read from `anthropic_api_key` in Invoice Automation Settings.

### Confidence-Based Routing (`confidence.py`)

`determine_routing(field_confidences)` uses the MINIMUM confidence across all matched fields:

| Min Confidence | Routing Decision |
|---------------|-----------------|
| ≥ 90% (configurable: `auto_create_threshold`) | Auto Create (Draft PI) |
| ≥ 60% (configurable: `review_threshold`) | Review Queue |
| < 60% | Manual Entry Queue |

---

## Subsystem 3: Correction Memory

### The CodeRabbit Pattern

When a reviewer corrects a mapping, `process_correction()` triggers ALL of these atomically:

**Step 1: Create/Update Alias** (`alias_manager.py`)
- Build composite key: `{supplier}:{normalized_text}:{doctype}`
- If alias exists: increment `correction_count`, update `canonical_name`
- If new: create `Mapping Alias` record
- Push to Redis immediately: `invoice_automation:alias:{composite_key}` → canonical_name

**Step 2: Log the Correction** (`correction_handler.py`)
- Create `Mapping Correction Log` with:
  - What the system proposed (`system_proposed`, `system_confidence`, `system_match_stage`)
  - What the reviewer chose (`human_selected`)
  - Reviewer's reasoning (`reviewer_reasoning`) — high-value for LLM context
  - Full invoice context (supplier, other line items, date, totals)

**Step 3: Update Historical Embedding Index** (background job)
- Generate embedding for the raw extracted text via sentence-transformers
- Store embedding on the Correction Log record (`raw_text_embedding`)
- Upsert into `Embedding Index` with `source_doctype="Historical Invoice Line"`, `is_human_corrected=1`
- Next time similar text appears → Stage 4 embedding search catches it

**Step 4: Conflict Detection** (`conflict_resolver.py`)
- Query existing corrections for same `{supplier}:{normalized_text}` but different `human_selected`
- If new correction has `correction_count > 1` on the alias → treat as authoritative
- If first-time conflict → flag both corrections as conflicting (`is_conflicting=1`)
- Most recent correction always wins for the active alias
- `resolve_stale_conflicts()` runs weekly: auto-resolves conflicts >30 days old by picking the most frequent correction

### Reasoning Replay (`reasoning_retriever.py`)

When Stage 5 (LLM) is invoked:
1. Query `Mapping Correction Log` for same supplier with `reviewer_reasoning IS NOT NULL`
2. Compute embedding similarity between current text and stored `raw_text_embedding`
3. Return top 5 most similar corrections with their reasoning
4. Fallback: return most recent corrections for the supplier if embeddings unavailable

---

## Embedding System

### Model (`model.py`)

- Uses `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- **Lazy-loaded** — only in worker processes, never in web server
- Model name configurable via `embedding_model_name` setting
- Functions: `generate_embedding(text)`, `generate_embeddings_batch(texts)`, `embedding_to_list()`, `list_to_embedding()`

### Index Manager (`index_manager.py`)

Abstract `VectorIndexBase` interface with methods:
- `search(query_embedding, filters, top_k)` → `list[SearchResult]`
- `upsert(source_doctype, source_name, embedding, metadata)`
- `remove(source_doctype, source_name)`
- `rebuild()`

**`NumpyVectorIndex`** implementation:
- Loads all embeddings from `Embedding Index` doctype into a NumPy matrix on first use
- `search()`: cosine similarity via matrix dot product (embeddings are pre-normalized), apply filters, return top-k
- `upsert()`: updates both DB record and in-memory matrix
- `remove()`: deletes from both
- Thread-safe via `threading.Lock`
- Singleton via `get_index_manager()`

### Index Builder (`index_builder.py`)

| Function | Purpose | When Called |
|----------|---------|------------|
| `build_full_index()` | Build item + historical embeddings | Initial setup |
| `rebuild_item_embeddings()` | Delete and regenerate all Item embeddings | Manual rebuild |
| `sync_missing()` | Add Items not yet in index | Daily scheduled job |
| `update_item_embedding(doc)` | Update one item's embedding | Item on_update/after_insert hook |
| `remove_item_embedding(doc)` | Remove one item's embedding | Item on_trash hook |

**Item composite text:** `"{item_name} | {description} | {brand} | {default_manufacturer_part_no} | HSN {gst_hsn_code}"`

Batch processing: 256 items per batch with `frappe.publish_progress()`.

---

## Validation & Safety

### Amount Validation (`validation/amount_validator.py`)

`validate_amounts(extracted_data, matched_line_items)`:
- Computes subtotal = Σ(qty × rate) for all matched line items
- Applies tax rates: total_tax = Σ(line_amount × tax_rate / 100)
- Compares computed_total vs extracted total_amount
- Returns `is_valid=False` if difference exceeds `amount_tolerance` (default ₹1)

### Tax Matching (`validation/tax_validator.py`)

**Rule-based ONLY — never fuzzy or probabilistic:**

`match_tax_template(tax_detail, supplier_gstin, company_gstin)`:
1. Extract state codes from GSTINs (first 2 digits)
2. Same state → intra-state (expect CGST + SGST)
3. Different state → inter-state (expect IGST)
4. Search `Purchase Taxes and Charges Template` for matching tax_type + rate in template rows
5. If no match → flag for review (never auto-assign wrong template)

`validate_tax_consistency(taxes, supplier_gstin, company_gstin)`:
- Cannot mix IGST with CGST/SGST
- CGST and SGST rates must be equal
- IGST invalid for intra-state; CGST/SGST invalid for inter-state

### Duplicate Detection (`validation/duplicate_detector.py`)

`check_duplicate(supplier, bill_no, bill_date, grand_total)`:

| Type | Criteria | Action |
|------|----------|--------|
| **Exact** | Same supplier + bill_no + bill_date | **Block** creation |
| **Near** | Same supplier + grand_total within ±`duplicate_check_amount_tolerance_pct`% + bill_date within ±`duplicate_check_date_range_days` | **Flag** but allow after confirmation |

---

## Doctype Reference

### Invoice Automation Settings (Single)

System-wide configuration. All thresholds and connection settings.

**Sections:** Ollama Config, LlamaParse Config, Matching Thresholds, Embedding Config, Claude API Config, Validation, File Handling, General. See [Configuration Reference](#configuration-reference) for all fields.

### Invoice Processing Queue

One record per invoice. Tracks the full pipeline lifecycle.

**Key Sections:**
- **File Info:** `source_file` (Attach), `file_name`, `file_hash` (SHA-256), `file_type`, `file_size_bytes`
- **Status:** `extraction_status`, `matching_status`, `workflow_state`, `routing_decision`, `overall_confidence`
- **Extraction:** `extraction_method`, `document_type_detected`, `extraction_confidence`, `extraction_time_ms`, `extraction_warnings` (JSON), `raw_parsed_text`, `extracted_data` (JSON — full ExtractedInvoice)
- **Matched Header:** `matched_supplier` (Link), `supplier_match_confidence`, `supplier_match_stage`, `matched_bill_no`, `matched_bill_date`, `matched_due_date`, `matched_currency`, `matched_total`, `matched_tax_template`, `matched_cost_center`
- **Match Data:** `matched_data` (JSON — full PipelineResult), `matching_time_ms`
- **Line Items:** `line_items` (child table: Invoice Line Item Match)
- **Validation:** `validation_results` (JSON), `amount_mismatch`, `amount_mismatch_details`, `duplicate_flag`, `duplicate_details`
- **Output:** `purchase_invoice` (Link), `total_processing_time_ms`, `processing_error`, `processed_by`

**Workflow States:** Pending → Extracting → Extracted → Matching → Matched → Routed → Under Review → Invoice Created / Rejected / Failed

**Autoname:** `INV-Q-.#####`

### Invoice Line Item Match (Child Table)

Per-line match result, child of Invoice Processing Queue.

| Field | Type | Description |
|-------|------|-------------|
| `line_number` | Int | Sequential line number |
| `extracted_description` | Small Text | Raw extracted item description |
| `extracted_qty` | Data | Quantity (string for Decimal) |
| `extracted_rate` | Data | Unit price (string for Decimal) |
| `extracted_amount` | Data | Line total (string for Decimal) |
| `extracted_hsn` | Data | HSN/SAC code |
| `extracted_unit` | Data | Unit of measure |
| `extracted_item_code` | Data | Vendor's item code |
| `matched_item` | Link: Item | System's matched ERPNext Item |
| `match_confidence` | Float | 0-100% |
| `match_stage` | Select | Exact / Alias / Fuzzy / Embedding / LLM / Manual |
| `match_details` | JSON | Debug info (scores, which stage, etc.) |
| `is_corrected` | Check | 1 if reviewer changed the match |
| `original_match` | Link: Item | What system proposed before correction |
| `correction_reasoning` | Small Text | Reviewer's note explaining the correction |

### Mapping Alias

Learned aliases fed by human corrections. Composite key for fast lookup.

| Field | Description |
|-------|-------------|
| `source_doctype` | Supplier / Item / Purchase Taxes and Charges Template / Cost Center |
| `raw_text` | Original extracted text |
| `normalized_text` | Normalized for matching |
| `canonical_name` | Dynamic Link to the correct ERPNext record |
| `supplier_context` | Link: Supplier (makes alias supplier-specific) |
| `composite_key` | `{supplier or "ANY"}:{normalized_text}:{source_doctype}` (unique) |
| `created_from_correction` | Check — 1 if auto-created from review |
| `correction_count` | How many times confirmed |
| `last_used` | Datetime of last hit |
| `is_active` | Check — can deactivate without deletion |

### Mapping Correction Log

Full correction history. Never deleted.

| Field | Description |
|-------|-------------|
| `source_doctype` | What was corrected |
| `raw_extracted_text` | What the invoice said |
| `system_proposed` / `system_confidence` / `system_match_stage` | What the system suggested |
| `human_selected` | What the reviewer chose |
| `reviewer` / `reviewer_reasoning` | Who corrected and why |
| `invoice_context` | JSON with supplier, line items, date, totals |
| `supplier` / `extracted_hsn` / `item_group_of_correction` | Context fields |
| `raw_text_embedding` | JSON embedding vector for similarity search |
| `is_conflicting` / `conflicting_correction` | Conflict tracking |

### Embedding Index

Vector storage for semantic search.

| Field | Description |
|-------|-------------|
| `source_doctype` | Item / Historical Invoice Line |
| `source_name` | The Item name or correction mapping |
| `composite_text` | Text that was embedded |
| `embedding_vector` | JSON array of 384 floats |
| `supplier_context` | For historical entries |
| `is_human_corrected` | Higher-quality flag |
| `item_group` / `hsn_code` | For search filtering |

---

## Configuration Reference

All configuration is centralized in the **Invoice Automation Settings** DocType (Single document). No environment variables (`.env`) or `site_config.json` entries are needed — the DocType is the single source of truth for all settings.

Full field list:

### Ollama
| Field | Default | Description |
|-------|---------|-------------|
| `ollama_base_url` | `http://localhost:11434` | Ollama server URL |
| `ollama_model` | `qwen2.5vl:7b` | Vision model (NEVER hardcode) |
| `ollama_timeout_seconds` | 120 | Request timeout |
| `json_retry_count` | 3 | Retries on malformed JSON |

### LlamaParse
| Field | Default | Description |
|-------|---------|-------------|
| `llamaparse_api_key` | — | Password field |
| `llamaparse_result_type` | markdown | markdown / text |

### Matching
| Field | Default | Description |
|-------|---------|-------------|
| `auto_create_threshold` | 90 | Min % for Draft PI auto-creation |
| `review_threshold` | 60 | Min % for Review Queue |
| `fuzzy_match_threshold` | 85 | Fuzzy score for high-confidence |
| `embedding_similarity_threshold` | 0.85 | Cosine sim for high-confidence |
| `embedding_review_threshold` | 0.65 | Cosine sim for review-level |
| `human_correction_weight_boost` | 1.1 | Multiplier for human-corrected entries |
| `agreement_confidence_boost` | 10 | Bonus % when both indexes agree |
| `enable_llm_matching` | 1 | Enable/disable Stage 5 |
| `enable_auto_create` | 0 | Enable/disable auto PI creation |

### Claude API
| Field | Default | Description |
|-------|---------|-------------|
| `anthropic_api_key` | — | Password field |
| `llm_max_candidates` | 10 | Max items sent to LLM |
| `llm_max_corrections_context` | 5 | Max corrections in LLM prompt |

### Embedding
| Field | Default | Description |
|-------|---------|-------------|
| `embedding_model_name` | `sentence-transformers/all-MiniLM-L6-v2` | 384 dimensions |

### Validation
| Field | Default | Description |
|-------|---------|-------------|
| `amount_tolerance` | 1.0 | Max mismatch (₹) |
| `duplicate_check_amount_tolerance_pct` | 5 | Near-duplicate tolerance % |
| `duplicate_check_date_range_days` | 7 | Near-duplicate date range |

### File Handling
| Field | Default | Description |
|-------|---------|-------------|
| `max_file_size_mb` | 25 | Max upload size |
| `allowed_extensions` | pdf,png,jpg,jpeg,tiff,webp,docx,doc | Comma-separated |
| `enable_batch_parse` | 1 | Enable batch upload API |

### General
| Field | Default | Description |
|-------|---------|-------------|
| `log_level` | INFO | DEBUG / INFO / WARNING / ERROR |
| `app_env` | development | development / staging / production |

---

## API Endpoint Reference

### Extraction

**`POST parse_invoice`** — `invoice_automation.api.endpoints.parse_invoice`
```bash
curl -X POST 'http://site/api/method/invoice_automation.api.endpoints.parse_invoice' \
  -H 'Authorization: token api_key:api_secret' \
  -d '{"file_url": "/files/invoice.pdf"}'
# Response: {"queue_name": "INV-Q-00001", "status": "queued"}
```
Also accepts `extracted_json` for pre-extracted data (skips extraction).

**`POST parse_invoices_batch`** — Batch upload
```bash
curl -X POST '...' -d '{"file_urls": ["/files/inv1.pdf", "/files/inv2.pdf"]}'
# Response: {"queued": [...], "rejected": [...], "total": 2}
```

**`GET get_extraction_result`** — Check extraction status
```bash
curl '...?queue_name=INV-Q-00001'
# Response: {extraction_status, extracted_data, extraction_warnings, extraction_confidence}
```

### Matching

**`POST trigger_matching`** — Re-trigger matching on extracted invoice
```bash
curl -X POST '...' -d '{"queue_name": "INV-Q-00001"}'
```

**`GET get_match_results`** — Get match results with per-field confidence
```bash
curl '...?queue_name=INV-Q-00001'
# Response: {matched_supplier, supplier_match_confidence, line_items: [{matched_item, confidence, stage}], routing_decision}
```

### Review & Correction

**`POST confirm_mapping`** — Accept matches, apply corrections, create Draft PI
```bash
curl -X POST '...' -d '{
  "queue_name": "INV-Q-00001",
  "corrections": [
    {"line_number": 1, "corrected_item": "ITEM-001", "reasoning": "Vendor abbreviation"}
  ]
}'
# Response: {"status": "success", "purchase_invoice": "ACC-PINV-2024-00001"}
```

**`POST reject_invoice`** — Reject an invoice
```bash
curl -X POST '...' -d '{"queue_name": "INV-Q-00001", "reason": "Not an invoice"}'
```

### Index Management

**`POST rebuild_index`** — Rebuild Redis and/or embedding indexes
```bash
curl -X POST '...' -d '{"index_type": "all"}'  # "redis" | "embeddings" | "all"
```

### Health & Diagnostics

**`GET health_check`** (allow_guest) — System health
```bash
curl 'http://site/api/method/invoice_automation.api.endpoints.health_check'
# Response: {ollama: {status, model_available}, redis: {status}, embedding_index: {count}, queue: {pending, processing}}
```

**`GET get_system_stats`** — Analytics
```bash
curl '...'
# Response: {total_processed, total_corrections, auto_create_rate, top_corrected_items, top_corrected_suppliers}
```

**`GET get_config`** — Current non-sensitive settings
```bash
curl '...'
# Response: {ollama_base_url, ollama_model, thresholds, limits}
```

---

## Hooks & Scheduled Jobs

### Document Event Hooks (`hooks.py`)

| Doctype | Event | Handler | Purpose |
|---------|-------|---------|---------|
| Supplier | on_update | `utils.redis_index.update_supplier_index` | Update Redis index for name, GSTIN, PAN |
| Supplier | after_insert | `utils.redis_index.update_supplier_index` | Same |
| Supplier | on_trash | `utils.redis_index.remove_supplier_index` | Remove from Redis |
| Item | on_update | `utils.redis_index.update_item_index` | Update Redis for name, barcodes, MPN |
| Item | on_update | `embeddings.index_builder.update_item_embedding` | Regenerate embedding (background) |
| Item | after_insert | Same as on_update (both handlers) | Same |
| Item | on_trash | `utils.redis_index.remove_item_index` | Remove from Redis |
| Item | on_trash | `embeddings.index_builder.remove_item_embedding` | Remove from embedding index |

### Scheduled Jobs

| Schedule | Handler | Purpose |
|----------|---------|---------|
| Daily | `utils.redis_index.rebuild_all` | Full Redis index rebuild (safety net) |
| Daily | `embeddings.index_builder.sync_missing` | Add Items not yet in embedding index |
| Weekly | `memory.conflict_resolver.resolve_stale_conflicts` | Auto-resolve correction conflicts >30 days old |

### Install/Migrate Hooks

| Hook | Handler | Purpose |
|------|---------|---------|
| `after_install` | `utils.redis_index.rebuild_all` | Build Redis index on fresh install |
| `after_migrate` | `utils.redis_index.rebuild_all` | Rebuild index after schema changes |

---

## Extension Guide

### Adding a New Parser Strategy

1. Create `extraction/parsers/my_parser.py`:
```python
from invoice_automation.extraction.parsers.base_parser import ParserStrategy, ParsedDocument
from invoice_automation.extraction.file_handler import FileInfo

class MyParserStrategy(ParserStrategy):
    def supports(self, file_info: FileInfo) -> bool:
        return file_info.extension == "xyz"
    def parse(self, file_info: FileInfo) -> ParsedDocument:
        text = ...  # your extraction logic
        return ParsedDocument(text=text, parsing_method="my_parser")
```
2. Add to `get_parser()` factory in `parsers/base_parser.py` (before FallbackParser)
3. Add extension mapping in `utils/file_utils.py` → `EXTENSION_TO_FILE_TYPE`

### Adding a New Matching Stage

1. Create `matching/my_matcher.py` with `match(raw_text, source_doctype, supplier) → MatchResult`
2. Import in `MatchingPipeline.__init__` and add to `_match_item`/`_match_supplier`
3. Add stage name to `match_stage` Select options in `invoice_line_item_match.json`

### Swapping Embedding Backend (NumPy → Qdrant)

1. Create `embeddings/qdrant_index.py` implementing `VectorIndexBase`
2. Implement `search()`, `upsert()`, `remove()`, `rebuild()`
3. Update `get_index_manager()` to return Qdrant based on a config flag
4. `Embedding Index` doctype remains as persistence/source-of-truth

### Swapping the Extraction LLM

The `OllamaClient` reads model name from settings. Options:
1. Change `ollama_model` in settings to any Ollama model
2. Replace `OllamaClient` entirely — `ExtractionService` only calls `client.generate_json(prompt, system)`

---

## Exception Hierarchy

```
InvoiceAutomationError (base) — message, code, original exception
├── ExtractionError
│   ├── FileValidationError     # bad type, too large, corrupt, empty, password-protected
│   ├── ParsingError            # LlamaParse failure, LibreOffice timeout/missing
│   ├── OllamaConnectionError  # can't reach Ollama server
│   ├── OllamaExtractionError  # unusable output after all retries
│   └── SchemaValidationError   # extracted data doesn't match Pydantic schema
├── MatchingError
│   ├── IndexNotReadyError      # Redis or embedding index not built
│   ├── LLMMatchingError        # Claude API failure/timeout
│   └── InvoiceCreationError    # failed to create Draft Purchase Invoice
└── MemoryError
    ├── AliasConflictError      # contradictory alias corrections
    └── EmbeddingUpdateError    # failed to update embedding index
```

Every exception carries: `message` (human-readable), `code` (machine-readable), `original` (exception chain).

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "Cannot connect to Ollama" | Ollama not running | `ollama serve` |
| "Model not available" | Model not pulled | `ollama pull qwen2.5vl:7b` |
| Extraction returns empty | Scanned PDF without LlamaParse | Set `llamaparse_api_key` |
| Supplier not matching | GSTIN/name not in Redis | `bench execute invoice_automation.utils.redis_index.rebuild_all` |
| Items not matching | Normalization mismatch | Check `normalize_text()` output |
| Embedding search empty | Index not built | `bench execute invoice_automation.embeddings.index_builder.build_full_index` |
| LLM stage not firing | Disabled or no API key | Check `enable_llm_matching` + `anthropic_api_key` in Invoice Automation Settings |
| LlamaParse failure | Invalid/missing API key | Check `llamaparse_api_key` in Invoice Automation Settings |
| DOC parsing fails | LibreOffice not installed | `apt install libreoffice` |
| Password-protected PDF | Not supported | Clear error message returned |
| Amount mismatch flagged | Line items don't sum to total | Review extracted amounts, check for missing lines |

---

## Performance Tuning

| Component | Bottleneck | Mitigation |
|-----------|-----------|------------|
| Fuzzy matching | O(n) scan over master data | Pre-filter by item_group; cache enabled by default |
| Embedding search | NumPy matrix size | Swap to Qdrant for >50K entries |
| LLM extraction | 5-30s per invoice via Ollama | Use faster model; increase timeout; use GPU |
| LLM matching | 0.5-2s per Claude API call | Reduce `llm_max_candidates` |
| Redis index rebuild | Full scan of Supplier + Item | Runs daily; incremental updates via hooks |
| Embedding model load | ~2-3s cold start | Worker processes keep model warm |
| Batch processing | Sequential per worker | Scale with more Frappe workers |
| PDF parsing | LlamaParse API latency | Network dependent; consider caching |

### Bench Commands Reference

```bash
# Full index build (initial setup)
bench --site {site} execute invoice_automation.embeddings.index_builder.build_full_index
bench --site {site} execute invoice_automation.utils.redis_index.rebuild_all

# Rebuild specific indexes
bench --site {site} execute invoice_automation.embeddings.index_builder.rebuild_item_embeddings

# Sync missing items
bench --site {site} execute invoice_automation.embeddings.index_builder.sync_missing

# Export corrections
bench --site {site} execute invoice_automation.memory.correction_handler.export_corrections --args '["2024-01-01", "2024-12-31"]'

# Health check
bench --site {site} execute invoice_automation.api.endpoints.health_check
```
