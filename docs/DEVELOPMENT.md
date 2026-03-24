# Development Guide

## Developer Setup

### Prerequisites

- A working [Frappe Bench](https://frappeframework.com/docs/user/en/installation) with ERPNext installed
- Python 3.11+
- Node.js 18+
- Redis running
- At least one LLM provider (Ollama is free and local)

### Install for Development

```bash
cd frappe-bench

# Get the app
bench get-app invoice_automation <repo-url>
bench --site {site} install-app invoice_automation

# Install Python dependencies in editable mode
./env/bin/pip install -e apps/invoice_automation

# Install pre-commit hooks
cd apps/invoice_automation
pre-commit install
cd ../..

# Enable scheduler for background jobs
bench enable-scheduler

# Start development server
bench start
```

### Running Tests

```bash
# Run all tests
bench --site {site} run-tests --app invoice_automation

# Run a specific test file
bench --site {site} run-tests --module invoice_automation.tests.test_extraction_service

# Run a specific test
bench --site {site} run-tests --module invoice_automation.tests.test_extraction_service --test test_extract_simple_invoice

# Run with verbose output
bench --site {site} run-tests --app invoice_automation -v
```

### Code Style

The project uses these tools via pre-commit:

| Tool | Purpose | Config |
|------|---------|--------|
| **ruff** | Python linting and formatting | `pyproject.toml` |
| **pyupgrade** | Modernize Python syntax | pre-commit config |
| **eslint** | JavaScript linting | `.eslintrc` |
| **prettier** | JavaScript/CSS formatting | `.prettierrc` |

Pre-commit runs automatically on `git commit`. To run manually:

```bash
cd apps/invoice_automation
pre-commit run --all-files
```

---

## Project Structure

```
invoice_automation/
├── extraction/          # Subsystem 1: File → Parse → LLM → Schema → Normalize → Validate
├── matching/            # Subsystem 2: Pluggable strategy pipeline
├── memory/              # Subsystem 3: Correction learning (aliases, logs, embeddings)
├── embeddings/          # Vector embedding model and index management
├── validation/          # Amount, tax, and duplicate validation
├── llm/                 # LLM provider abstraction (Ollama, OpenAI, Anthropic, Gemini)
├── api/endpoints.py     # All public API endpoints
├── utils/               # Redis indexes, exceptions, helpers
├── public/css/          # Review dialog CSS
├── invoice_automation/  # DocType definitions (JSON + Python)
│   └── doctype/
│       ├── invoice_processing_queue/
│       ├── invoice_automation_settings/
│       ├── invoice_line_item_match/
│       ├── mapping_alias/
│       ├── mapping_correction_log/
│       ├── embedding_index/
│       ├── matching_strategy/
│       ├── supplier_item_catalog/
│       ├── vendor_sku_mapping/
│       └── extraction_field/
├── hooks.py             # Doc events, scheduler, install hooks
├── setup.py             # Install/migrate hooks, strategy seeding
└── tests/               # Test files
```

---

## Adding Features

### Adding a New Matching Strategy

No pipeline code changes needed:

1. Create `matching/my_matcher.py`:
```python
from invoice_automation.matching.exact_matcher import MatchResult

class MyMatcher:
    name = "My Strategy"
    applies_to = ["Item"]

    def __init__(self, config=None):
        self.config = config or {}

    def match_supplier(self, extracted_data):
        return MatchResult(matched=False, doctype="Supplier", stage="My Strategy")

    def match_item(self, line_item, supplier=None):
        # Your matching logic here
        description = line_item.get("description", "") if isinstance(line_item, dict) else getattr(line_item, "description", "")
        # ... find a match ...
        return MatchResult(
            matched=True, doctype="Item", matched_name="ITEM-CODE",
            confidence=85.0, stage="My Strategy",
            details={"your_key": "your_value"},
        )
```

2. Create a **Matching Strategy** record (via desk or fixtures):
   - Strategy Name: "My Strategy"
   - Strategy Class: `invoice_automation.matching.my_matcher.MyMatcher`
   - Priority: 28 (between Alias at 20 and Fuzzy at 30)
   - Enabled: Yes

3. Add "My Strategy" to the `match_stage` Select options in `invoice_line_item_match.json`

### Adding a New LLM Provider

1. Create `llm/my_provider.py` implementing `LLMProvider`:
```python
from invoice_automation.llm.base import LLMProvider

class MyProvider(LLMProvider):
    def generate(self, prompt, system=None):
        # Return text response
        ...

    def generate_with_image(self, prompt, image_base64):
        # Return text response from image
        ...

    def generate_json(self, prompt, system=None):
        # Return parsed dict
        ...

    def health_check(self):
        return {"status": "ok", "provider": "my_provider"}
```

2. Register in `llm/factory.py` → `PROVIDERS` dict
3. Add option to `extraction_llm_provider` / `matching_llm_provider` Select fields in Settings DocType JSON

### Adding a New File Parser

1. Create `extraction/parsers/my_parser.py`:
```python
from invoice_automation.extraction.parsers.base_parser import ParserStrategy, ParsedDocument
from invoice_automation.extraction.file_handler import FileInfo

class MyParserStrategy(ParserStrategy):
    def supports(self, file_info: FileInfo) -> bool:
        return file_info.extension == "xyz"

    def parse(self, file_info: FileInfo) -> ParsedDocument:
        text = ...  # Your extraction logic
        return ParsedDocument(text=text, parsing_method="my_parser")
```

2. Add to `get_parser()` factory in `parsers/base_parser.py` (before FallbackParser)
3. Add extension to `allowed_extensions` default in Settings

### Adding Custom Extraction Fields (No Code)

Users can add fields via **Invoice Automation Settings** > **Custom Extraction Fields**:

1. Field Name: `project_code` (machine key)
2. Field Label: "Project Code"
3. Field Type: String
4. Description for LLM: "The internal project code, usually a 6-digit number near the PO reference"
5. Target Doctype: Purchase Invoice
6. Target Field: `project` (if a custom field exists on PI)
7. Enabled: Yes

The field is injected into the LLM extraction prompt and mapped to the PI automatically.

---

## Debugging

### Enable Debug Logging

Set **Log Level** to `DEBUG` in Invoice Automation Settings. Then check:

```bash
# Watch worker logs (extraction and matching run in workers)
tail -f logs/worker.log | grep "invoice_automation"

# Check error logs in Frappe
bench --site {site} console
>>> frappe.get_all("Error Log", filters={"method": ["like", "%invoice%"]}, limit=5)
```

### Common Debug Scenarios

**Extraction returns wrong data**: Check `raw_parsed_text` field on the queue record — this is what the LLM received. If the text is garbled, the parser has an issue. If text is fine but extraction is wrong, the LLM model may need upgrading.

**Matching picks wrong item**: Check `match_details` JSON field on the line item. Shows which strategy matched and what scores were. Check `matched_data` JSON on the queue record for the full pipeline result.

**Alias not working**: Check Mapping Alias list — is the alias `is_active`? Is the `composite_key` correct? Check Redis: `bench --site {site} console` → `frappe.cache().get_value("invoice_automation:alias:{key}")`.

**Correction not learning**: Check Mapping Correction Log — was the log created? Check if the background embedding job ran (look for errors in worker logs).
