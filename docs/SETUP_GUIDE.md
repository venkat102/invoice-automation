# Setup Guide

New to Frappe/ERPNext? Read the **[Glossary](GLOSSARY.md)** first to understand the terminology.

## Prerequisites

| Dependency | Version | Required? | Notes |
|---|---|---|---|
| **Python** | 3.11+ | Yes | 3.12 recommended |
| **Node.js** | 18+ | Yes | 20 LTS recommended (for bench asset builds) |
| **Frappe** | v15+ | Yes | The web framework ERPNext runs on |
| **ERPNext** | v15+ | Yes | The ERP system this app extends |
| **Redis** | 6+ | Yes | Used for fast index lookups and caching |
| **RQ Scheduler** | (bundled with Frappe) | Yes | Enable with `bench enable-scheduler` for background jobs |
| **LibreOffice** | Any | Only for .doc files | `apt install libreoffice` or `brew install libreoffice` |
| **Ollama** | Latest | Only if using Ollama as LLM provider | `ollama serve` must be running, model must be pulled |

### What is each prerequisite for?

- **Frappe/ERPNext**: The platform this app runs on. Provides Suppliers, Items, Purchase Invoices, and the desk UI.
- **Redis**: Stores fast-lookup indexes for supplier names, tax IDs, and aliases. Also used by Frappe for caching and real-time updates.
- **RQ Scheduler**: Runs background jobs like extraction, embedding generation, and daily index rebuilds. Without it, invoices won't process automatically.
- **LibreOffice**: Only needed if you upload `.doc` files (not `.docx`). Converts DOC to DOCX for text extraction.
- **Ollama**: A free, local AI model runner. Default for extraction. Alternative paid providers (OpenAI, Anthropic, Gemini) don't need Ollama.

## Installation

```bash
bench get-app invoice_automation <repo-url>
bench --site <site-name> install-app invoice_automation
bench enable-scheduler
```

This automatically:
- Rebuilds Redis indexes (Suppliers, Items, Aliases)
- Seeds default Matching Strategy records
- Enqueues embedding index build in the background (may take several minutes)

---

## Configuration

All settings are in **Invoice Automation Settings** (a Single DocType). Navigate to it via the search bar in your Frappe/ERPNext site.

### 1. LLM Providers

You need to configure **two** LLM providers — one for extraction (parsing invoices) and one for matching (supplier/item matching).

| Setting | Default | Options |
|---|---|---|
| `Extraction LLM Provider` | Ollama | Ollama, OpenAI, Anthropic, Gemini |
| `Matching LLM Provider` | Anthropic | Ollama, OpenAI, Anthropic, Gemini |
| `JSON Retry Count` | 3 | Number of retries for malformed JSON |

#### Provider-specific configuration

- **Ollama** (default for extraction)
  - `Base URL`: `http://localhost:11434`
  - `Model`: `qwen2.5vl:7b` — must be pulled beforehand (`ollama pull qwen2.5vl:7b`)
  - `Timeout`: 120 seconds

- **OpenAI** — requires `API Key` (stored encrypted), model defaults to `gpt-4o`

- **Anthropic** (default for matching) — requires `API Key` (stored encrypted), model defaults to `claude-sonnet-4-20250514`

- **Gemini** — requires `API Key` (stored encrypted), model defaults to `gemini-2.0-flash`

- **LlamaParse** (optional) — alternative document parser, requires `API Key`, result type: `markdown` or `text`

### 2. Matching Thresholds

| Setting | Default | Purpose |
|---|---|---|
| `Auto Create Threshold` | 90% | Confidence above which Purchase Invoice is auto-created |
| `Review Threshold` | 60% | Confidence below which invoice is routed for review |
| `Fuzzy Match Threshold` | 85% | Threshold for fuzzy text matching |
| `Enable LLM Matching` | Yes | Use LLM as a fallback matching stage |
| `Enable Auto Create` | **No** | Must be explicitly enabled to auto-create invoices |
| `LLM Max Candidates` | 10 | Max candidates sent to LLM matching stage |
| `LLM Max Corrections Context` | 5 | Max historical corrections included in LLM context |

### 3. Embedding Configuration

| Setting | Default | Purpose |
|---|---|---|
| `Embedding Model Name` | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model for semantic matching |
| `Embedding Similarity Threshold` | 0.85 | Auto-match threshold |
| `Embedding Review Threshold` | 0.65 | Review routing threshold |
| `Human Correction Weight Boost` | 1.1 | Weight multiplier for human corrections |
| `Agreement Confidence Boost` | 10% | Boost when multiple stages agree |

### 4. Validation & Duplicate Detection

| Setting | Default | Purpose |
|---|---|---|
| `Amount Tolerance` | 1 (currency) | Allowed difference in line item amounts |
| `Duplicate Amount Tolerance` | 5% | Tolerance for duplicate detection |
| `Duplicate Date Range` | 7 days | Date window for duplicate detection |

### 5. File Handling

| Setting | Default | Purpose |
|---|---|---|
| `Max File Size` | 25 MB | Maximum upload size |
| `Allowed Extensions` | `pdf,png,jpg,jpeg,tiff,webp,docx,doc` | Accepted file types |
| `Enable Batch Parse` | Yes | Allow batch file processing |

### 6. Matching Strategies

The matching pipeline is pluggable. Navigate to **Matching Strategy** list to manage strategies:

| Strategy | Priority | Default | What It Does |
|---|---|---|---|
| Exact | 10 | Enabled | Redis lookups by tax ID, PAN, normalized name |
| Vendor SKU | 15 | Enabled | Looks up vendor-specific item codes |
| Alias | 20 | Enabled | Human-corrected mapping aliases with recency weighting |
| Purchase History | 25 | **Disabled** | Matches against items from Supplier Item Catalog |
| Fuzzy | 30 | Enabled | Token-based string similarity |
| HSN Filter | 35 | **Disabled** | HSN code-filtered fuzzy matching |
| Embedding | 40 | Enabled | Semantic vector similarity search |
| LLM | 50 | Enabled | AI-based fallback with correction context |

Enable/disable strategies and change priority order without code changes. Lower priority number = executed first.

### 7. Custom Extraction Fields

Define additional fields to extract from invoices in **Invoice Automation Settings** → **Custom Extraction Fields** section:

| Column | Purpose |
|---|---|
| Field Name | Machine key (e.g., `project_code`) |
| Field Label | Human label (e.g., "Project Code") |
| Field Type | String / Decimal / Date / Boolean |
| Is Line Item Field | Header vs per-line-item field |
| Target Doctype | Purchase Invoice or Purchase Invoice Item |
| Target Field | ERPNext field to map to |
| Normalizer | None / Text / Date / Currency / Decimal |
| Description for LLM | Instructions for the AI on how to extract this field |

Custom fields are injected into the LLM extraction prompt and automatically mapped to the target ERPNext field when creating Purchase Invoices.

### 8. General

| Setting | Default | Options |
|---|---|---|
| `Log Level` | INFO | DEBUG, INFO, WARNING, ERROR |
| `App Environment` | development | development, staging, production |

---

## Post-Setup

1. **Verify health** — call the `/api/method/invoice_automation.api.endpoints.health_check` endpoint to check LLM connectivity, Redis status, and embedding index health.

2. **Rebuild indexes** — use the buttons in Invoice Automation Settings or call the `rebuild_index` API if needed.

3. **Scheduled tasks** (configured automatically via hooks):
   - **Daily**: Redis index rebuild + sync missing embeddings + alias decay weight recalculation
   - **Weekly**: Resolve stale correction conflicts

4. **Backfill Supplier Item Catalog** (optional) — if you have existing Purchase Invoices, run this once to populate the supplier-item catalog:
   ```bash
   bench --site <site-name> execute invoice_automation.invoice_automation.doctype.supplier_item_catalog.supplier_item_catalog.backfill_catalog
   ```

---

## Minimum Viable Setup

For the quickest start:

1. Install the app
2. Set up **Ollama** locally with `qwen2.5vl:7b` for extraction
3. Add an **Anthropic API key** for matching
4. Leave all thresholds at defaults
5. Keep `Enable Auto Create` off until you've validated results
