# Invoice Automation - User Guide

## Overview

Invoice Automation processes vendor invoices automatically by:
1. **Extracting** data from uploaded files (PDF, images, DOCX) using AI vision models
2. **Matching** extracted fields against your ERPNext master data (Suppliers, Items, Tax Templates)
3. **Learning** from your corrections so it improves over time

## Uploading Invoices

### Single Invoice
1. Navigate to **Invoice Processing Queue** → **+ Add**
2. Attach your invoice file in the **Source File** field (required)
3. Save — extraction and matching start automatically in the background
4. Or use the API: call `parse_invoice` with a `file_url`

### Batch Upload
Use the API endpoint `parse_invoices_batch` with a list of file URLs to process multiple invoices at once. Enable batch parsing in **Invoice Automation Settings**.

### Supported File Formats
- **PDF** (native or scanned) — native PDFs use PyMuPDF text extraction; scanned PDFs are rendered as images and sent to the LLM vision model; LlamaParse is used if an API key is configured
- **Images** (PNG, JPG, JPEG, TIFF, WEBP) — sent directly to the AI vision model
- **DOCX** — text extracted via python-docx
- **DOC** — converted via LibreOffice, then processed as DOCX

File size limit is configurable (default: 25 MB). See **Invoice Automation Settings**.

### Pre-Extracted JSON
If you already have structured invoice data, pass it as `extracted_json` to skip the extraction step and go directly to matching.

## What Happens After Upload

Each invoice goes through these stages (visible in the **Workflow State** field):

| State | What's Happening |
|-------|-----------------|
| **Pending** | Queued for processing |
| **Extracting** | AI is reading and interpreting the invoice file |
| **Extracted** | Data extracted, ready for matching |
| **Matching** | System is mapping extracted data to ERPNext records |
| **Routed** | Matching complete, all fields high confidence |
| **Under Review** | Some fields have medium confidence, waiting for human review |
| **Invoice Created** | Draft Purchase Invoice created |
| **Rejected** | Invoice was rejected by a reviewer |
| **Failed** | An error occurred during processing |

### Form Actions

The Invoice Processing Queue form shows contextual action buttons based on the current state:

| Button | When Visible | What It Does |
|--------|-------------|--------------|
| **Review & Create Invoice** | Extraction completed, no PI created yet | Opens the review dialog (see below) |
| **Trigger Matching** | Extraction done, matching pending/failed | Re-runs the 5-stage matching pipeline |
| **Retry Extraction** | Extraction failed | Creates a new queue entry and re-processes the file |
| **Reject** | Invoice is under review/routed | Marks the invoice as rejected with a reason |
| **View Purchase Invoice** | PI has been created | Navigates to the linked Purchase Invoice |

## Understanding Confidence Scores

Each matched field has a confidence score (0-100%):

| Score Range | Meaning | Action |
|-------------|---------|--------|
| **90-100%** | High confidence | Auto-created as Draft PI (if enabled) |
| **60-89%** | Likely correct, needs verification | Sent to Review Queue |
| **Below 60%** | Low confidence | Sent to Manual Entry Queue |

The **Overall Confidence** is the *lowest* confidence across all fields — one uncertain field means the whole invoice needs review.

## Reviewing and Correcting Mappings

When an invoice is ready for review, click the **Review & Create Invoice** button. This opens a dialog showing:

### Review Dialog

The review dialog has three sections:

**1. Validation Warnings** (top)
- Amount mismatch alerts (computed total vs extracted total)
- Duplicate invoice warnings

**2. Header Comparison Table**

A side-by-side view of extracted vs matched data with confidence scores:

| Field | Extracted | Matched | Confidence |
|-------|-----------|---------|------------|
| Supplier | Vendor name from invoice | Matched ERPNext Supplier | 95% |
| Invoice No. | From invoice | Mapped value | - |
| Invoice Date | From invoice | Mapped value | - |
| Due Date | From invoice | Mapped value | - |
| Currency | From invoice | Mapped value | - |
| Total Amount | From invoice | Mapped value | - |
| Tax Template | - | Matched template | - |

Confidence scores are color-coded: green (90%+), orange (60-89%), red (below 60%).

If the supplier is wrong, use the **Supplier Override** field below the table to select the correct one.

**3. Line Items Table**

Each extracted line item shows:
- **Extracted data**: description, qty, rate, amount, HSN code
- **Matched Item**: the ERPNext Item the system matched it to
- **Confidence**: how sure the system is about the match
- **Stage**: which matching stage found it (Exact, Alias, Fuzzy, Embedding, LLM)

### Making Corrections

Below the line items table, each line has:
- **Item field**: Change the matched Item if the system got it wrong
- **Reasoning field**: Explain *why* this correction is right — this teaches the system!

### Confirming

Click **Confirm & Create Invoice** to:
1. Save your corrections (aliases created, correction log updated, embeddings re-indexed)
2. Check for duplicate invoices
3. Create a **Draft Purchase Invoice** with all the mapped data

The Purchase Invoice is always created as a Draft — it is never auto-submitted.

### Why Reasoning Notes Matter

When you add a reasoning note, you're teaching the system:
- The note gets stored in the Mapping Correction Log
- Similar items from the same supplier will reference your reasoning
- The AI matching engine uses your notes as context for better decisions

## Handling Duplicates

The system checks for duplicates before creating a Purchase Invoice:

- **Exact Duplicate**: Same supplier + invoice number + date → **Blocked** (cannot create PI)
- **Near Duplicate**: Same supplier + similar amount + close dates → **Flagged** but you can proceed after confirmation

Check the **Duplicate Details** field for information about the existing invoice.

## Handling Amount Mismatches

After matching, the system verifies that the computed total (sum of qty x rate + taxes) matches the extracted total. If there's a mismatch exceeding the configured tolerance (default: 1), the invoice is flagged in the review dialog with details.

## Configuration

All settings are in **Invoice Automation Settings** (single doctype). Navigate to it in the desk sidebar.

### Choosing Your LLM Provider

The first section — **LLM Provider Configuration** — has two dropdowns that control which AI backend is used:

| Field | Controls | Options | Default |
|-------|----------|---------|---------|
| **Extraction LLM Provider** | Invoice data extraction + image parsing | Ollama / OpenAI / Anthropic / Gemini | Ollama |
| **Matching LLM Provider** | Stage 5 item/supplier matching fallback | Ollama / OpenAI / Anthropic / Gemini | Anthropic |

When you select a provider, the form automatically shows the relevant API key and model fields for that provider. You can use different providers for extraction and matching (e.g. Ollama for extraction, OpenAI for matching).

**Provider details:**
- **Ollama** — free, runs locally, requires `ollama serve` running and a vision model pulled
- **OpenAI** — GPT-4o and other models, requires `openai_api_key`
- **Anthropic** — Claude models, requires `anthropic_api_key`
- **Gemini** — Google's models, requires `gemini_api_key`

### Other Settings
- **LlamaParse**: API key for PDF parsing (optional — without it, scanned PDFs fall back to LLM vision)
- **Matching Thresholds**: Confidence levels for auto-create and review routing
- **File Handling**: Max file size and allowed extensions

## FAQ

**Q: Why did the system match this wrong?**
A: The system uses 5 matching strategies. Sometimes vendor descriptions differ from your Item names. Correcting it once creates an alias that catches it next time.

**Q: How long until it learns my corrections?**
A: Immediately. An alias is created on correction and used for the very next invoice from that supplier. Embedding-based learning updates within minutes.

**Q: Can I undo a correction?**
A: Go to **Mapping Alias** list, find the alias, and deactivate it. The correction history is preserved in **Mapping Correction Log**.

**Q: What if two reviewers correct the same thing differently?**
A: The system detects conflicts and flags them. The most recent correction wins, but conflicts are auto-resolved weekly based on frequency.

**Q: Can the system auto-create invoices without review?**
A: Yes, but disabled by default. Enable in **Invoice Automation Settings** → **Enable Auto Create**. Invoices are always created as Drafts — never submitted.

**Q: What file types are supported?**
A: PDF (native and scanned), PNG, JPG, JPEG, TIFF, WEBP, DOCX, and DOC. Configurable in settings.

**Q: What if the LLM provider is not running or misconfigured?**
A: Extraction will fail gracefully with a clear error. Use the **Health Check** endpoint or check the `processing_error` field on the queue record. Ensure your configured provider is running and API keys are set in **Invoice Automation Settings**.

**Q: What happens with scanned PDFs if I don't have a LlamaParse key?**
A: The system renders each PDF page as an image using PyMuPDF and sends it to your configured extraction LLM's vision model. This requires `PyMuPDF` to be installed and a vision-capable LLM (e.g. Ollama with `qwen2.5vl`, OpenAI GPT-4o, Anthropic Claude, or Gemini).
