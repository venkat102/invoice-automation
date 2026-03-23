### Invoice Automation

AI-powered invoice processing for ERPNext. Extracts data from uploaded invoices (PDF, images, DOCX), matches extracted fields against your Suppliers, Items, and Tax Templates, and learns from reviewer corrections to improve over time.

### Key Features

- **Multi-format extraction**: PDF (LlamaParse / PyMuPDF / LLM vision fallback for scanned docs), images (LLM vision), DOCX, DOC
- **5-stage matching pipeline**: Exact lookup, alias lookup, fuzzy matching, embedding search, LLM fallback
- **Review dialog**: Side-by-side view of extracted vs matched data with inline corrections and reasoning
- **Correction memory**: Learns from human corrections — aliases, embeddings, and reviewer reasoning
- **Confidence-based routing**: Auto-create, review queue, or manual entry based on match confidence
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

- [Technical Documentation](docs/TECHNICAL.md) — architecture, API reference, configuration
- [System Flow](docs/SYSTEM_FLOW.md) — pipeline diagrams and data flow
- [User Guide](docs/USER_GUIDE.md) — how to upload, review, and correct invoices

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

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
