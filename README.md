### Invoice Automation

AI-powered invoice processing for ERPNext. Extracts data from uploaded invoices (PDF, images, DOCX), matches extracted fields against your Suppliers, Items, and Tax Templates, and learns from reviewer corrections to improve over time.

### Key Features

- **Multi-format extraction**: PDF (LlamaParse / PyMuPDF / LLM vision fallback for scanned docs), images (LLM vision), DOCX, DOC
- **Pluggable matching pipeline**: 8 matching strategies (Exact, Vendor SKU, Alias, Purchase History, Fuzzy, HSN Filter, Embedding, LLM) — enable/disable and reorder via config
- **Review dialog**: Side-by-side view of extracted vs matched data with inline corrections and reasoning for supplier, tax template, cost center, and line items
- **Correction memory**: Learns from human corrections — aliases, embeddings, vendor SKU mappings, supplier-item catalog, and reviewer reasoning
- **Price validation**: Compares extracted rates against historical price data to boost or penalize match confidence
- **Configurable extraction**: Add custom fields to the extraction schema via UI — no code changes needed
- **Confidence-based routing**: Auto-create, review queue, or manual entry based on match confidence with alias recency weighting
- **Multi-provider LLM support**: Ollama (free/local), OpenAI (ChatGPT), Anthropic (Claude), Google Gemini

### Quick Start

1. Install the app:
```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench --site your-site install-app invoice_automation
```

2. Configure LLM providers in **Invoice Automation Settings**:
   - **Extraction LLM Provider** (default: Ollama) — for reading invoices
   - **Matching LLM Provider** (default: Anthropic) — for Stage 5 item matching
   - Set API keys for your chosen providers

3. Upload invoices via **Invoice Processing Queue** or the `parse_invoice` API

### Supported LLM Providers

| Provider | Type | Default For | Requires |
|----------|------|-------------|----------|
| **Ollama** | Free, local | Extraction | `ollama serve` running locally |
| **OpenAI** | Paid API | — | `openai_api_key` |
| **Anthropic** | Paid API | Matching | `anthropic_api_key` |
| **Gemini** | Paid API | — | `gemini_api_key` |

All configuration is managed through a single DocType: **Invoice Automation Settings**.

### Documentation

**Only know Python? Start here (in order):**

| # | Document | What You'll Learn |
|---|----------|------------------|
| 1 | **[Frappe Basics](docs/FRAPPE_BASICS.md)** | How Frappe maps to Python/Django concepts you already know |
| 2 | **[AI Concepts](docs/AI_CONCEPTS.md)** | LLMs, embeddings, semantic search, prompt engineering — from scratch |
| 3 | **[Glossary](docs/GLOSSARY.md)** | Every term defined: Frappe, ERPNext, and system-specific |
| 4 | **[Example Walkthrough](docs/EXAMPLE_WALKTHROUGH.md)** | One invoice traced step-by-step through the entire pipeline |
| 5 | **[Setup Guide](docs/SETUP_GUIDE.md)** | Install, configure, verify |
| 6 | **[User Guide](docs/USER_GUIDE.md)** | Full workflow: upload, review, correct |

**Going deeper:**

| # | Document | What You'll Learn |
|---|----------|------------------|
| 7 | **[System Flow](docs/SYSTEM_FLOW.md)** | Visual diagrams of the 3 subsystems |
| 8 | **[Technical Docs](docs/TECHNICAL.md)** | Architecture, API reference, extension guide |
| 9 | **[Permissions](docs/PERMISSIONS.md)** | Roles and access control |
| 10 | **[Deployment](docs/DEPLOYMENT.md)** | Production checklist, monitoring, scaling |
| 11 | **[Development](docs/DEVELOPMENT.md)** | Dev setup, tests, adding features |

> Already know Frappe/ERPNext? Skip 1-3, start at the [User Guide](docs/USER_GUIDE.md) — it has reading paths for every role.

### Contributing

See the **[Development Guide](docs/DEVELOPMENT.md)** for full setup instructions. Quick version:

```bash
cd apps/invoice_automation
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
