# Setup Guide

## Prerequisites

| Dependency | Required? |
|---|---|
| **Frappe** | Yes |
| **ERPNext** | Yes |
| **Redis** | Yes (for indexes & caching) |
| **RQ Scheduler** | Yes (for background jobs) |
| **Ollama** | Only if using Ollama as LLM provider |

## Installation

```bash
bench get-app invoice_automation <repo-url>
bench --site <site-name> install-app invoice_automation
```

This automatically rebuilds Redis indexes and builds the embedding index in the background.

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

### 6. General

| Setting | Default | Options |
|---|---|---|
| `Log Level` | INFO | DEBUG, INFO, WARNING, ERROR |
| `App Environment` | development | development, staging, production |

---

## Post-Setup

1. **Verify health** — call the `/api/method/invoice_automation.api.endpoints.health_check` endpoint to check LLM connectivity, Redis status, and embedding index health.

2. **Rebuild indexes** — use the buttons in Invoice Automation Settings or call the `rebuild_index` API if needed.

3. **Scheduled tasks** (configured automatically via hooks):
   - **Daily**: Redis index rebuild + sync missing embeddings
   - **Weekly**: Resolve stale correction conflicts

---

## Minimum Viable Setup

For the quickest start:

1. Install the app
2. Set up **Ollama** locally with `qwen2.5vl:7b` for extraction
3. Add an **Anthropic API key** for matching
4. Leave all thresholds at defaults
5. Keep `Enable Auto Create` off until you've validated results
