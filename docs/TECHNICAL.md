# Invoice Automation - Technical Documentation

> **New here?** Start with the [Glossary](GLOSSARY.md) for terminology, then the [Example Walkthrough](EXAMPLE_WALKTHROUGH.md) for a concrete end-to-end example. This document is for developers and system administrators.

**Related docs:** [Glossary](GLOSSARY.md) | [AI Concepts](AI_CONCEPTS.md) | [Frappe Basics](FRAPPE_BASICS.md) | [Permissions](PERMISSIONS.md) | [Deployment](DEPLOYMENT.md) | [Development](DEVELOPMENT.md)

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
│   ├── ollama_client.py           # Backward-compatible shim (use llm/ package instead)
│   ├── json_repair.py             # Auto-repair malformed LLM JSON output
│   ├── prompt_templates.py        # Extraction prompt engineering
│   ├── base_extractor.py          # Abstract InvoiceExtractor interface
│   ├── json_extractor.py          # Pre-extracted JSON input adapter
│   ├── parsers/
│   │   ├── base_parser.py         # ParserStrategy ABC + get_parser() factory
│   │   ├── pdf_parser.py          # 3-step: LlamaParse → PyMuPDF text → LLM vision
│   │   ├── image_parser.py        # LLM vision model (provider-agnostic)
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
├── matching/                      # ── SUBSYSTEM 2: Pluggable Matching Pipeline ──
│   ├── pipeline.py                # MatchingPipeline: dynamic strategy orchestrator
│   ├── base_strategy.py           # BaseMatchingStrategy ABC for pluggable strategies
│   ├── normalizer.py              # Text normalization for matching (company suffixes, units)
│   ├── exact_matcher.py           # Strategy: Redis exact lookups + MatchResult dataclass
│   ├── vendor_sku_matcher.py      # Strategy: Vendor SKU Mapping lookups (97% confidence)
│   ├── alias_matcher.py           # Strategy: Mapping Alias composite key lookups with decay
│   ├── purchase_history_matcher.py # Strategy: Supplier Item Catalog fuzzy matching
│   ├── fuzzy_matcher.py           # Strategy: thefuzz token_sort/partial/token_set
│   ├── hsn_filter.py              # Strategy: HSN code-filtered fuzzy matching
│   ├── embedding_matcher.py       # Strategy: Dual-index semantic vector search
│   ├── llm_matcher.py             # Strategy: LLM matching (provider-agnostic)
│   ├── price_validator.py         # Post-match: confidence adjustment from price history
│   └── confidence.py              # get_config(), determine_routing(), ConfidenceScorer
│
├── memory/                        # ── SUBSYSTEM 3: Correction Memory ──
│   ├── correction_handler.py      # process_correction() + process_header_correction()
│   ├── alias_manager.py           # AliasManager + apply_decay_weights() daily job
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
├── llm/                              # ── LLM Provider Abstraction ──
│   ├── base.py                   # LLMProvider ABC (generate, generate_with_image, generate_json, health_check)
│   ├── factory.py                # get_llm_provider(purpose) factory
│   ├── ollama_provider.py        # Ollama (local open models)
│   ├── openai_provider.py        # OpenAI / ChatGPT (GPT-4o, etc.)
│   ├── anthropic_provider.py     # Anthropic / Claude (Sonnet, Opus, Haiku)
│   └── gemini_provider.py        # Google Gemini (Flash, Pro)
│
├── public/
│   └── css/
│       └── invoice_review.css     # Review dialog styles (two-panel layout, cards, badges)
│
├── api/endpoints.py               # All whitelisted API endpoints (14 endpoints)
├── utils/
│   ├── redis_index.py             # rebuild_all, _build_supplier_index, _build_item_index, doc events
│   ├── exceptions.py              # InvoiceAutomationError hierarchy (12 exception classes)
│   ├── file_utils.py              # compute_sha256, detect_mime_type, validate_file
│   ├── decimal_utils.py           # to_decimal, safe_multiply, round_decimal (never float)
│   └── helpers.py                 # get_config_value (reads from Invoice Automation Settings)
└── hooks.py                       # doc_events, scheduler_events, after_install/migrate, app_include_css
```

---

## Installation & Setup

### Prerequisites
- Frappe bench with ERPNext installed
- Python 3.11+
- At least one LLM provider configured:
  - **Ollama** (default for extraction): Install and run locally (`ollama serve`), pull a vision model (`ollama pull qwen2.5vl:7b`)
  - **OpenAI**: API key from https://platform.openai.com/api-keys
  - **Anthropic** (default for matching): API key from https://console.anthropic.com/
  - **Gemini**: API key from https://aistudio.google.com/apikey
- (Optional) LlamaParse API key for PDF parsing

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
2. Choose your **Extraction LLM Provider** (default: Ollama for local/free usage)
3. Choose your **Matching LLM Provider** (default: Anthropic for Stage 5 matching)
4. Configure the selected providers:
   - **Ollama**: Set `ollama_base_url` and `ollama_model` (needs `ollama serve` running locally)
   - **OpenAI**: Set `openai_api_key` and `openai_model` (default: `gpt-4o`)
   - **Anthropic**: Set `anthropic_api_key` and `anthropic_model` (default: `claude-sonnet-4-20250514`)
   - **Gemini**: Set `gemini_api_key` and `gemini_model` (default: `gemini-2.0-flash`)
5. (Optional) Set `llamaparse_api_key` for PDF parsing
6. Review and adjust matching thresholds, file handling limits, and other settings as needed

See [Configuration Reference](#configuration-reference) for the full field list.

### What Happens on Install

When the app is installed on an existing site (`bench install-app`), the following runs automatically:

1. **Redis indexes** are built synchronously — Suppliers (name, GSTIN, PAN), Items (name, barcodes, MPN), and all active Mapping Aliases are loaded into Redis for O(1) lookups (Stages 1 & 2).
2. **Embedding index** is built in the background via `frappe.enqueue` (long queue, up to 1 hour timeout) — generates vector embeddings for all Items and historical corrections (Stage 4). This requires `sentence-transformers` and may take several minutes depending on the number of Items.

No manual `bench execute` commands are needed for initial setup.

### Verify Installation
```bash
bench --site {site} execute invoice_automation.api.endpoints.health_check
```

### Manual Index Rebuild (if needed)
```bash
# Rebuild Redis indexes (Suppliers + Items + Aliases)
bench --site {site} execute invoice_automation.utils.redis_index.rebuild_all

# Rebuild embedding index (slow — loads ML model)
bench --site {site} execute invoice_automation.embeddings.index_builder.build_full_index
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

ParsedDocument.text → get_llm_provider("extraction").generate_json()
    → EXTRACTION_PROMPT + EXTRACTION_SYSTEM_PROMPT
    → Configured provider API call (Ollama / OpenAI / Anthropic / Gemini)
    → OpenAI and Gemini use native JSON mode; others use retry + json_repair
    → If malformed JSON → json_repair.repair_json() → retry (up to json_retry_count)
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
- Sends to the configured extraction LLM provider's vision model via `provider.generate_with_image()`
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

### LLM Provider Abstraction (`llm/`)

The extraction engine uses a provider-agnostic LLM abstraction. The provider is selected via `extraction_llm_provider` in Invoice Automation Settings.

**Supported providers:**

| Provider | Package | Vision Support | JSON Mode | Config Fields |
|----------|---------|---------------|-----------|---------------|
| **Ollama** (default) | `httpx` (built-in) | Yes | Retry + repair | `ollama_base_url`, `ollama_model`, `ollama_timeout_seconds` |
| **OpenAI** | `openai` | Yes (GPT-4o) | Native `json_object` | `openai_api_key`, `openai_model` |
| **Anthropic** | `anthropic` | Yes (Claude) | Retry + repair | `anthropic_api_key`, `anthropic_model` |
| **Gemini** | `google-genai` | Yes | Native `application/json` | `gemini_api_key`, `gemini_model` |

**Common interface** (`LLMProvider` ABC):
- `generate(prompt, system)` → raw text response
- `generate_with_image(prompt, image_base64)` → raw text response (vision)
- `generate_json(prompt, system)` → parsed dict (with retry + JSON repair fallback)
- `health_check()` → provider status dict

**Factory:** `get_llm_provider(purpose)` returns the configured provider for `"extraction"` or `"matching"`.

API calls for Ollama go to `{base_url}/api/generate` with `stream: false`.

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

The extraction prompt supports **custom fields** configured in Invoice Automation Settings. `build_dynamic_prompt(custom_fields)` injects user-defined fields into the JSON template. `build_dynamic_model(custom_fields)` creates a dynamic Pydantic model extending `ExtractedInvoice`. When no custom fields are configured, the original static prompt and schema are used unchanged.

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

## Subsystem 2: Pluggable Matching Pipeline

### Pipeline Orchestration (`pipeline.py`)

`MatchingPipeline.process(extracted_data)` runs sequentially:

1. **Load strategies** from `Matching Strategy` doctype (sorted by priority). Falls back to hardcoded defaults if no records exist.
2. **Match Supplier** through enabled strategies that apply to "Supplier"
3. **Match each Line Item** through enabled strategies that apply to "Item", with **price validation** applied after each successful match
4. **Match Tax Templates** (rule-based only, via ExactMatcher — not pluggable)
5. **Compute routing** from minimum confidence across all fields
6. Return `PipelineResult` with all matches, routing decision, processing time

The pipeline accepts both `dict` and Pydantic `ExtractedInvoice` objects via duck typing.

### Matching Strategy Doctype

Each strategy record has: `strategy_name`, `strategy_class` (dotted Python path), `enabled`, `priority` (lower = earlier), `applies_to` (Supplier/Item/Both), `max_confidence`, `settings_json`.

Strategies are instantiated via `importlib.import_module()` at pipeline init. Each strategy class must implement `match_supplier(extracted_data)` and `match_item(line_item, supplier)` returning `MatchResult`.

### Strategy: Exact Lookup (`exact_matcher.py`)

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

### Strategy: Vendor SKU Lookup (`vendor_sku_matcher.py`)

Matches extracted vendor item codes against `Vendor SKU Mapping` records:

| Lookup | Confidence |
|--------|-----------|
| `(supplier, vendor_item_code)` → Item | 97% |

Only applies to Items (not Suppliers). Requires supplier to be already matched.

### Strategy: Alias Lookup (`alias_matcher.py`)

| Lookup | Base Confidence | Composite Key |
|--------|-----------|---------------|
| Supplier-specific alias | 99% × decay_weight | `{supplier}:{normalized_text}:{doctype}` |
| Supplier-agnostic alias | 90% × decay_weight | `ANY:{normalized_text}:{doctype}` |

Aliases are stored in the `Mapping Alias` doctype. Lookup tries Redis cache first, then DB query for `canonical_name` and `decay_weight`. Updates `last_used` on hit.

**Recency decay**: `decay_weight = max(0.5, 1.0 - 0.005 × days_since_last_correction)`. Fresh corrections get full confidence; aliases unused for 100+ days decay to 50%. Recalculated daily by `apply_decay_weights()` scheduled job.

Now also fed by **header corrections** (supplier, tax template, cost center overrides) in addition to line item corrections.

### Strategy: Purchase History Match (`purchase_history_matcher.py`) — Disabled by default

Queries `Supplier Item Catalog` for items this supplier has sold before, then fuzzy matches against that narrowed set.

- Frequency boost: `+0.5 per occurrence` (capped at +5)
- Confidence: 70-85% based on fuzzy score + frequency
- Requires Supplier Item Catalog to be populated (from PI submissions or corrections)

### Strategy: Fuzzy Match (`fuzzy_matcher.py`)

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

### Strategy: HSN-Filtered Match (`hsn_filter.py`) — Disabled by default

Pre-filters candidate Items by HSN code before fuzzy matching:

1. Find Items with matching `gst_hsn_code`
2. If no exact match, try prefix match (first 4 digits)
3. Fuzzy match within HSN-filtered candidates only
4. Confidence boost of +5-10% over regular fuzzy matching

### Strategy: Embedding Search (`embedding_matcher.py`)

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

### Strategy: LLM Match (`llm_matcher.py`)

Only invoked when Stages 1-4 all fail. Uses the configured `matching_llm_provider` (default: Anthropic/Claude).

**Supported providers:** Ollama, OpenAI (ChatGPT), Anthropic (Claude), or Google Gemini — configured in Invoice Automation Settings.

**Prompt construction:**
1. Extracted line item text
2. Top candidates from fuzzy cache (up to `llm_max_candidates`, default 10)
3. Past corrections from `ReasoningRetriever` (up to `llm_max_corrections_context`, default 5) — each includes the raw text, what it was corrected to, and the reviewer's reasoning note

**Response:** JSON `{"matched_item": "...", "confidence": 0-100, "reasoning": "..."}`

**Confidence capped at 88%** — LLM matches always require human review.

Gated by `enable_llm_matching` setting. Provider and API key configured in Invoice Automation Settings.

### Post-Match: Price Validation (`price_validator.py`)

Applied automatically after any strategy produces a match for a line item:

| Condition | Effect |
|-----------|--------|
| Rate within 15% of avg_rate in Supplier Item Catalog | +5% confidence |
| Rate >50% off avg_rate | -10% confidence |
| <2 historical occurrences or no catalog entry | No change |

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

#### Line Item Corrections

When a reviewer corrects a line item mapping, `process_correction()` triggers ALL of these:

**Step 1: Create/Update Alias** (`alias_manager.py`)
- Build composite key: `{supplier}:{normalized_text}:{doctype}`
- If alias exists: increment `correction_count`, update `canonical_name`, set `decay_weight=1.0`, set `last_correction_date`
- If new: create `Mapping Alias` record with `decay_weight=1.0`
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

**Step 4: Update Supplier Item Catalog** (`supplier_item_catalog.py`)
- Upsert `Supplier Item Catalog` entry with corrected item, supplier, extracted rate, HSN
- Updates rolling average rate, min/max rates, occurrence count

**Step 5: Create Vendor SKU Mapping** (`vendor_sku_mapping.py`)
- If the line item has an `extracted_item_code` (vendor's SKU), creates/updates `Vendor SKU Mapping`
- Maps `(supplier, vendor_item_code)` → corrected Item

**Step 6: Conflict Detection** (`conflict_resolver.py`)
- Query existing corrections for same `{supplier}:{normalized_text}` but different `human_selected`
- If new correction has `correction_count > 1` on the alias → treat as authoritative
- If first-time conflict → flag both corrections as conflicting (`is_conflicting=1`)
- Most recent correction always wins for the active alias
- `resolve_stale_conflicts()` runs weekly: auto-resolves conflicts >30 days old by picking the most frequent correction

#### Header Corrections

When a reviewer overrides a header field (supplier, tax template, or cost center), `process_header_correction()` triggers:

1. **Create/Update Alias** — same as line item corrections, with appropriate `source_doctype`
2. **Log the Correction** — records what the system proposed vs what the reviewer chose
3. **Conflict Detection** — same as line item corrections

Header corrections are new — previously, supplier overrides were applied silently without creating aliases or logs.

### Reasoning Replay (`reasoning_retriever.py`)

When Stage 5 (LLM) is invoked:
1. Query `Mapping Correction Log` for same supplier with `reviewer_reasoning IS NOT NULL`
2. Compute embedding similarity between current text and stored `raw_text_embedding`
3. Return top 5 most similar corrections with their reasoning
4. Fallback: return most recent corrections for the supplier if embeddings unavailable

---

## Embedding System

**No external vector database is used.** The system uses a custom in-memory NumPy index backed by a Frappe DocType (MariaDB table):

| Component | Implementation |
|-----------|---------------|
| **Embedding model** | `sentence-transformers/all-MiniLM-L6-v2` — 384 dimensions, L2-normalized |
| **Vector storage** | `Embedding Index` DocType — each record stores a JSON array of 384 floats in MariaDB |
| **Search engine** | `NumpyVectorIndex` — loads all vectors into a NumPy matrix in RAM, cosine similarity via dot product (O(n) full scan) |
| **Similarity method** | Cosine similarity = dot product (vectors are L2-normalized at generation time via `normalize_embeddings=True`) |

**Limitations:** All vectors must fit in worker process RAM. Search is O(n) against every stored vector. Suitable for up to ~50K entries. For larger catalogs, swap to Qdrant — see [Extension Guide](#swapping-embedding-backend-numpy--qdrant).

### Model (`model.py`)

- Uses `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, L2-normalized)
- **Lazy-loaded** — only in worker processes, never in web server
- Model name configurable via `embedding_model_name` setting
- Functions: `generate_embedding(text)`, `generate_embeddings_batch(texts)`, `embedding_to_list()`, `list_to_embedding()`

### Index Manager (`index_manager.py`)

Abstract `VectorIndexBase` interface with methods:
- `search(query_embedding, filters, top_k)` → `list[SearchResult]`
- `upsert(source_doctype, source_name, embedding, metadata)`
- `remove(source_doctype, source_name)`
- `rebuild()`

**`NumpyVectorIndex`** implementation (current default — no external vector DB needed):
- **Storage:** `Embedding Index` DocType in MariaDB (JSON-serialized float arrays)
- **In-memory index:** Loads all embeddings into a single NumPy matrix on first use
- `search()`: cosine similarity via matrix dot product (`embeddings @ query.T`), apply metadata filters, return top-k
- `upsert()`: updates both the DB record and the in-memory matrix
- `remove()`: deletes from both
- Thread-safe via `threading.Lock`
- Singleton per worker process via `get_index_manager()`

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

**Sections:** LLM Provider Configuration, Ollama Config, LlamaParse Config, Matching Thresholds, Embedding Config, Anthropic Configuration, Validation, File Handling, General. See [Configuration Reference](#configuration-reference) for all fields.

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

Learned aliases fed by human corrections (line items + headers). Composite key for fast lookup.

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
| `last_correction_date` | Datetime of last correction reinforcement |
| `decay_weight` | Float (1.0 = fresh, decays to 0.5 over 100+ days). Applied to confidence during matching. |
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

### Matching Strategy

Registry of pluggable matching strategies. Loaded by the pipeline at init.

| Field | Description |
|-------|-------------|
| `strategy_name` | Unique name (e.g., "Exact", "Vendor SKU") |
| `strategy_class` | Dotted Python path (e.g., `invoice_automation.matching.vendor_sku_matcher.VendorSKUMatcher`) |
| `enabled` | Check — disabled strategies are skipped |
| `priority` | Int — lower = executed first (10=Exact, 50=LLM) |
| `applies_to` | Supplier / Item / Both |
| `max_confidence` | Float — confidence cap for this strategy |
| `settings_json` | JSON — strategy-specific configuration |

Seeded with 8 default strategies on install/migrate.

### Supplier Item Catalog

Tracks supplier-item affinity and price statistics. Populated from Purchase Invoice submissions and human corrections.

| Field | Description |
|-------|-------------|
| `supplier` | Link: Supplier |
| `item` | Link: Item |
| `item_group` | Link: Item Group (denormalized) |
| `avg_rate` | Rolling average rate |
| `last_rate` | Most recent rate |
| `min_rate` / `max_rate` | Rate range |
| `occurrence_count` | Number of times this pair appeared |
| `last_invoice_date` | Date of most recent invoice |
| `hsn_code` | HSN/SAC code |

Unique together: `supplier` + `item`. Used by Purchase History matcher and Price Validator.

### Vendor SKU Mapping

Maps vendor-specific item codes to ERPNext Items per supplier. Auto-created from corrections when the invoice has an item code.

| Field | Description |
|-------|-------------|
| `supplier` | Link: Supplier |
| `vendor_item_code` | The code as printed on the vendor's invoice |
| `item` | Link: Item (the correct ERPNext Item) |
| `last_seen_rate` | Most recent rate for this SKU |
| `occurrence_count` | Number of times this mapping was confirmed |

Unique together: `supplier` + `vendor_item_code`. Used by Vendor SKU matching strategy.

### Extraction Field (Child Table)

Custom extraction field definitions. Child of Invoice Automation Settings.

| Field | Description |
|-------|-------------|
| `field_name` | Machine key (e.g., `project_code`) |
| `field_label` | Human label (e.g., "Project Code") |
| `field_type` | String / Decimal / Date / Boolean |
| `is_line_item_field` | Check — header vs per-line-item |
| `target_doctype` | Purchase Invoice or Purchase Invoice Item |
| `target_field` | ERPNext field to map to |
| `normalizer` | None / Text / Date / Currency / Decimal |
| `description_for_llm` | Instructions for the AI on how to extract |
| `enabled` | Check — disabled fields are ignored |

---

## Configuration Reference

All configuration is centralized in the **Invoice Automation Settings** DocType (Single document). No environment variables (`.env`) or `site_config.json` entries are needed — the DocType is the single source of truth for all settings.

Full field list:

### LLM Providers
| Field | Default | Description |
|-------|---------|-------------|
| `extraction_llm_provider` | `Ollama` | Provider for extraction + vision (Ollama / OpenAI / Anthropic / Gemini) |
| `matching_llm_provider` | `Anthropic` | Provider for Stage 5 matching (Ollama / OpenAI / Anthropic / Gemini) |
| `json_retry_count` | 3 | Retries on malformed JSON (applies to all providers) |
| `openai_api_key` | — | Password field (shown when OpenAI selected) |
| `openai_model` | `gpt-4o` | Any OpenAI chat model (shown when OpenAI selected) |
| `gemini_api_key` | — | Password field (shown when Gemini selected) |
| `gemini_model` | `gemini-2.0-flash` | Any Gemini model (shown when Gemini selected) |

The form dynamically shows/hides provider-specific fields based on the selected `extraction_llm_provider` and `matching_llm_provider` values via `depends_on` expressions. You only see the fields relevant to your chosen providers.

### Ollama
| Field | Default | Description |
|-------|---------|-------------|
| `ollama_base_url` | `http://localhost:11434` | Ollama server URL |
| `ollama_model` | `qwen2.5vl:7b` | Vision model (NEVER hardcode) |
| `ollama_timeout_seconds` | 120 | Request timeout |

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

### Anthropic
| Field | Default | Description |
|-------|---------|-------------|
| `anthropic_api_key` | — | Password field (required if Anthropic selected) |
| `anthropic_model` | `claude-sonnet-4-20250514` | Any Anthropic model |
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

**`GET get_review_data`** — Get extracted vs matched data for the review dialog
```bash
curl '...?queue_name=INV-Q-00001'
# Response: {
#   source_file: "/files/invoice.pdf",
#   file_type: "PDF",
#   overall_confidence: 82,
#   routing_decision: "Review Queue",
#   header: {supplier: {extracted, extracted_tax_id, matched, confidence, stage}, ...},
#   line_items: [{
#     line_number, extracted_description, extracted_qty, extracted_rate, extracted_amount,
#     extracted_hsn, extracted_unit, extracted_item_code, extracted_sku,
#     extracted_tax_rate, extracted_tax_amount, extracted_discount,
#     matched_item, match_confidence, match_stage, is_corrected
#   }],
#   validation: {amount_mismatch, amount_mismatch_details, duplicate_flag, duplicate_details},
#   extraction_warnings: [{severity, message}]
# }
```

**`POST confirm_mapping`** — Accept matches, apply corrections, create Draft PI
```bash
curl -X POST '...' -d '{
  "queue_name": "INV-Q-00001",
  "header_overrides": {"supplier": "SUP-00001"},
  "corrections": [
    {"line_number": 1, "corrected_item": "ITEM-001", "reasoning": "Vendor abbreviation"}
  ]
}'
# Response: {"status": "success", "purchase_invoice": "ACC-PINV-2024-00001"}
```
- `header_overrides.supplier`: overrides the matched supplier + creates alias and correction log
- `header_overrides.supplier_reasoning`: optional reasoning for the supplier override
- `header_overrides.tax_template`: overrides the matched tax template + creates alias and correction log
- `header_overrides.tax_template_reasoning`: optional reasoning for the tax template override
- `header_overrides.cost_center`: overrides the matched cost center + creates alias and correction log
- `header_overrides.cost_center_reasoning`: optional reasoning for the cost center override
- `corrections[].reasoning`: stored in Mapping Correction Log and used as LLM context for future matching

**`POST save_corrections`** — Save corrections without creating a Purchase Invoice (teaches the system)
```bash
curl -X POST '...' -d '{
  "queue_name": "INV-Q-00001",
  "corrections": [{"line_number": 1, "corrected_item": "ITEM-001", "reasoning": "Vendor abbreviation"}],
  "header_overrides": {"supplier": "SUP-00001", "supplier_reasoning": "Correct company name"}
}'
# Response: {"status": "corrections_saved", "queue_name": "INV-Q-00001", "corrections_applied": 1}
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

**`GET health_check`** — System health (requires login)
```bash
curl 'http://site/api/method/invoice_automation.api.endpoints.health_check'
# Response: {extraction_llm: {provider, status, ...}, matching_llm: {provider, status, ...}, redis: {status}, embedding_index: {count}, queue: {pending, processing}}
```

**`GET get_system_stats`** — Analytics
```bash
curl '...'
# Response: {total_processed, total_corrections, auto_create_rate, top_corrected_items, top_corrected_suppliers}
```

**`GET get_config`** — Current non-sensitive settings
```bash
curl '...'
# Response: {extraction_llm_provider, matching_llm_provider, ollama_base_url, ollama_model, thresholds, limits}
```

---

## Hooks & Scheduled Jobs

### Document Event Hooks (`hooks.py`)

| Doctype | Event | Handler | Purpose |
|---------|-------|---------|---------|
| Purchase Invoice | on_submit | `supplier_item_catalog.update_catalog_from_purchase_invoice` | Upsert Supplier Item Catalog entries for all line items |
| Supplier | on_update | `utils.redis_index.update_supplier_index` | Update Redis index for name, GSTIN, PAN |
| Supplier | on_update | `matching.fuzzy_matcher.clear_master_cache` | Invalidate fuzzy matcher cache |
| Supplier | after_insert | Same as on_update | Same |
| Supplier | on_trash | `utils.redis_index.remove_supplier_index` | Remove from Redis |
| Supplier | on_trash | `matching.fuzzy_matcher.clear_master_cache` | Invalidate fuzzy matcher cache |
| Item | on_update | `utils.redis_index.update_item_index` | Update Redis for name, barcodes, MPN |
| Item | on_update | `embeddings.index_builder.update_item_embedding` | Regenerate embedding (background) |
| Item | on_update | `matching.fuzzy_matcher.clear_master_cache` | Invalidate fuzzy matcher cache |
| Item | after_insert | Same as on_update (all handlers) | Same |
| Item | on_trash | `utils.redis_index.remove_item_index` | Remove from Redis |
| Item | on_trash | `embeddings.index_builder.remove_item_embedding` | Remove from embedding index |
| Item | on_trash | `matching.fuzzy_matcher.clear_master_cache` | Invalidate fuzzy matcher cache |

### Scheduled Jobs

| Schedule | Handler | Purpose |
|----------|---------|---------|
| Daily | `utils.redis_index.rebuild_all` | Full Redis index rebuild: Suppliers, Items, and Aliases (safety net) |
| Daily | `embeddings.index_builder.sync_missing` | Add Items not yet in embedding index |
| Daily | `memory.alias_manager.apply_decay_weights` | Recalculate alias decay weights based on age since last correction |
| Weekly | `memory.conflict_resolver.resolve_stale_conflicts` | Auto-resolve correction conflicts >30 days old |

### Install/Migrate Hooks

| Hook | Handler | Purpose |
|------|---------|---------|
| `after_install` | `setup.after_install` | Build Redis indexes + seed default Matching Strategy records + enqueue embedding build |
| `after_migrate` | `setup.after_migrate` | Rebuild Redis indexes + seed missing Matching Strategy records |

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

### Adding a New Matching Strategy

No code changes to the pipeline needed — just create a strategy class and register it:

1. Create `matching/my_matcher.py`:
```python
from invoice_automation.matching.exact_matcher import MatchResult

class MyMatcher:
    name = "My Strategy"
    applies_to = ["Item"]  # or ["Supplier"] or ["Supplier", "Item"]

    def __init__(self, config=None):
        self.config = config or {}

    def match_supplier(self, extracted_data):
        return MatchResult(matched=False, doctype="Supplier", stage="My Strategy")

    def match_item(self, line_item, supplier=None):
        description = line_item.get("description", "") if isinstance(line_item, dict) else getattr(line_item, "description", "")
        # ... your matching logic ...
        return MatchResult(matched=True, doctype="Item", matched_name="ITEM-001",
                          confidence=85.0, stage="My Strategy")
```
2. Create a **Matching Strategy** record:
   - Strategy Name: "My Strategy"
   - Strategy Class: `invoice_automation.matching.my_matcher.MyMatcher`
   - Enabled: Yes
   - Priority: 28 (between Alias and Fuzzy, for example)
   - Applies To: Item
   - Max Confidence: 90
3. Add stage name to `match_stage` Select options in `invoice_line_item_match.json`

### Swapping Embedding Backend (NumPy → Qdrant)

1. Create `embeddings/qdrant_index.py` implementing `VectorIndexBase`
2. Implement `search()`, `upsert()`, `remove()`, `rebuild()`
3. Update `get_index_manager()` to return Qdrant based on a config flag
4. `Embedding Index` doctype remains as persistence/source-of-truth

### Swapping the Extraction LLM

Change `extraction_llm_provider` in Invoice Automation Settings to switch between Ollama, OpenAI, Anthropic, or Gemini. Each provider's model name is configurable independently. To add a new provider:

1. Create `llm/my_provider.py` implementing `LLMProvider` (generate, generate_with_image, generate_json, health_check)
2. Add to `PROVIDERS` dict in `llm/factory.py`
3. Add provider name to `extraction_llm_provider` / `matching_llm_provider` Select options in the DocType JSON

---

## Exception Hierarchy

```
InvoiceAutomationError (base) — message, code, original exception
├── ExtractionError
│   ├── FileValidationError     # bad type, too large, corrupt, empty, password-protected
│   ├── ParsingError            # LlamaParse failure, LibreOffice timeout/missing
│   ├── LLMConnectionError     # can't reach LLM provider (alias: OllamaConnectionError)
│   ├── LLMProviderError       # unusable output or misconfigured provider (alias: OllamaExtractionError)
│   └── SchemaValidationError   # extracted data doesn't match Pydantic schema
├── MatchingError
│   ├── IndexNotReadyError      # Redis or embedding index not built
│   ├── LLMMatchingError        # LLM provider failure during Stage 5 matching
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
| "Cannot connect to Ollama" | Ollama not running (when Ollama is the configured provider) | `ollama serve` |
| "Model not available" | Ollama model not pulled | `ollama pull qwen2.5vl:7b` |
| LLM provider API error | API key invalid or provider unreachable | Check API key for the configured provider in Invoice Automation Settings |
| Extraction returns empty | Scanned PDF, no LlamaParse, no PyMuPDF | Install PyMuPDF (`pip install PyMuPDF`) for vision fallback, or set `llamaparse_api_key` |
| Supplier not matching | GSTIN/name not in Redis | `bench execute invoice_automation.utils.redis_index.rebuild_all` |
| Items not matching | Normalization mismatch | Check `normalize_text()` output |
| Embedding search empty | Index not built | `bench execute invoice_automation.embeddings.index_builder.build_full_index` |
| LLM stage not firing | Disabled or no API key | Check `enable_llm_matching` + API key for the configured `matching_llm_provider` |
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
| LLM extraction | 5-30s per invoice (varies by provider) | Use faster model; paid providers (OpenAI, Gemini) are typically faster than local Ollama; use GPU for Ollama |
| LLM matching | 0.5-2s per LLM API call | Reduce `llm_max_candidates`; use faster model; local Ollama avoids network latency |
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

# Backfill Supplier Item Catalog from existing Purchase Invoices
bench --site {site} execute invoice_automation.invoice_automation.doctype.supplier_item_catalog.supplier_item_catalog.backfill_catalog

# Export corrections
bench --site {site} execute invoice_automation.memory.correction_handler.export_corrections --args '["2024-01-01", "2024-12-31"]'

# Health check
bench --site {site} execute invoice_automation.api.endpoints.health_check
```
