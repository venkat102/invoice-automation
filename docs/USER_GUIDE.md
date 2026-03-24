# Invoice Automation - User Guide

## How to Read This Documentation

We have 11 docs. You don't need to read all of them — pick the path that matches you.

### Path A: "I only know Python, I'm completely new to Frappe, ERPNext, and AI"

Read in this exact order:

| # | Document | What You'll Learn | Time |
|---|----------|------------------|------|
| 1 | **[Frappe Basics](FRAPPE_BASICS.md)** | How Frappe works if you know Python/Django — DocTypes, APIs, hooks, database, background jobs, JS patterns, directory structure | 15 min |
| 2 | **[AI Concepts](AI_CONCEPTS.md)** | LLMs, prompts, vision models, JSON mode, embeddings, semantic search, fuzzy matching, confidence scoring — all from scratch | 20 min |
| 3 | **[Glossary](GLOSSARY.md)** | Quick-reference definitions for every term: Frappe concepts, ERPNext business concepts (Supplier, Item, Purchase Invoice, GSTIN, HSN), and system-specific terms (Mapping Alias, Decay Weight, etc.) | 5 min |
| 4 | **[Example Walkthrough](EXAMPLE_WALKTHROUGH.md)** | One real invoice traced step-by-step: upload → extraction → each matching strategy's decision → review → correction → what the system learns | 10 min |
| 5 | **[Setup Guide](SETUP_GUIDE.md)** | Install the app, configure LLM providers, set thresholds, verify health | 10 min |
| 6 | **This guide** (below) | The full user workflow: uploading, reviewing, correcting, and how the system learns | 15 min |

After these 6, you'll understand everything. Then go deeper as needed with Path D.

### Path B: "I know Frappe/ERPNext, just need to set up and use the app"

| # | Document | Why |
|---|----------|-----|
| 1 | **[Setup Guide](SETUP_GUIDE.md)** | Install, configure providers, set thresholds |
| 2 | **This guide** (below) | Full workflow from upload to Purchase Invoice |
| 3 | **[Example Walkthrough](EXAMPLE_WALKTHROUGH.md)** | See a concrete invoice processed end-to-end |
| 4 | **[System Flow](SYSTEM_FLOW.md)** | Visual diagrams of the pipeline |

### Path C: "I'm a reviewer who processes invoices daily"

| # | Document | Why |
|---|----------|-----|
| 1 | **This guide** → [Uploading Invoices](#uploading-invoices) | How to upload |
| 2 | **This guide** → [Reviewing and Correcting Mappings](#reviewing-and-correcting-mappings) | The review dialog — where you'll spend most time |
| 3 | **This guide** → [Why Reasoning Notes Matter](#why-reasoning-notes-matter) | Your corrections directly improve the system |
| 4 | **[Example Walkthrough](EXAMPLE_WALKTHROUGH.md)** | See exactly what happens with a real invoice |

### Path D: "I'm a developer or admin going deeper"

| # | Document | Why |
|---|----------|-----|
| 1 | **[System Flow](SYSTEM_FLOW.md)** | Visual diagrams of all 3 subsystems |
| 2 | **[Technical Documentation](TECHNICAL.md)** | Architecture, all 14 API endpoints, extension guide, troubleshooting |
| 3 | **[Permissions](PERMISSIONS.md)** | Role matrix — who can do what |
| 4 | **[Deployment Guide](DEPLOYMENT.md)** | Production checklist, monitoring, scaling, backups |
| 5 | **[Development Guide](DEVELOPMENT.md)** | Dev setup, running tests, adding strategies/providers/parsers, debugging |

### Quick Concept Map

Before diving in, here's how the key pieces fit together:

```
Upload Invoice ──→ Extract Data (AI reads the PDF/image)
                        │
                        ▼
                   Match to ERPNext (8 strategies try to find the right Supplier, Items, Tax Template)
                        │
                        ▼
                   Route by Confidence
                   ├── ≥90% → Auto-create Draft PI
                   ├── 60-89% → Review Queue (you review and correct)
                   └── <60% → Manual Entry
                        │
                        ▼
                   Your Corrections Teach the System
                   ├── Aliases → instant match next time
                   ├── Vendor SKU Mapping → item code remembered
                   ├── Supplier Item Catalog → price patterns learned
                   └── Reasoning notes → AI uses your logic for similar items
```

The system gets smarter with every correction. Most items that need review today will match automatically within weeks.

---

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
| **Trigger Matching** | Extraction done, matching pending/failed | Re-runs the matching pipeline through all enabled strategies |
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

When an invoice is ready for review, click the **Review & Create Invoice** button. This opens a two-panel review dialog.

### Review Dialog Layout

The dialog opens near-fullscreen (95% viewport width) with two panels side by side:

```
┌───────────────────────┬─────────────────────────────────────┐
│                       │  Warnings (if any)                  │
│   Invoice Preview     │  Header Details (compact grid)      │
│   (PDF or image)      │  Line Items (cards, sorted)         │
│                       │                                     │
│   [Hide Preview]      │  Inline corrections per item        │
├───────────────────────┴─────────────────────────────────────┤
│  2 need review │ 1 change │ [Save Only] [Confirm & Create]  │
└─────────────────────────────────────────────────────────────┘
```

**Left panel — Invoice Preview**
- Shows the original invoice file (PDF via iframe, or image preview)
- Toggle "Hide" / "Show Preview" button to collapse and give more space to the data panel
- Lets you reference the original document while reviewing matches

**Right panel — Review Data**

The right panel has three areas, scrollable:

### 1. Warnings

Color-coded alerts at the top:
- **Yellow** — Amount mismatch (computed total vs extracted total)
- **Red** — Duplicate invoice warning
- **Blue** — Extraction warnings (OCR issues, ambiguous dates, etc.)

### 2. Header Details

A compact two-column grid showing all header fields:

| Field | What's Shown |
|-------|-------------|
| Supplier | Matched name + confidence badge + tax ID |
| Invoice # | Extracted value |
| Date / Due Date | Extracted values |
| Currency / Total | Extracted values |
| Tax Template | Matched template + confidence badge |
| Cost Center | Matched cost center |

Editable fields (Supplier, Tax Template, Cost Center) show a pencil icon on hover. Click the pencil to reveal the **Header Overrides** area with Link fields and reasoning inputs for each.

All header corrections create aliases and correction logs, so the system learns from them for future invoices.

### 3. Line Items (Sorted by Attention)

Line items are displayed as **interactive cards**, sorted so items needing attention appear first:

- **Red left border** — unmatched items (no match found)
- **Orange left border** — low/medium confidence (below 90%)
- **Blue left border** — items you've modified in this session
- **No colored border** — high confidence matches (90%+)

Items below 90% confidence are **auto-expanded** so you can review them immediately. High-confidence items are collapsed by default — click to expand.

**Each card shows:**

**Collapsed view** — one-line summary:
- Line number, description (truncated), qty, rate, amount, matched item, confidence badge, matching stage pill

**Expanded view** — click to toggle:
- **Full extracted details grid**: description, quantity, unit price, amount, UOM, HSN/SAC code, item code, SKU, tax rate, tax amount, discount
- **Current match**: matched item name with confidence and stage
- **Correction area** (blue highlight): Item link field (with autocomplete) + reasoning text field

### Making Corrections

Corrections happen **inline** — directly inside each line item card:

1. **Click** a line item card to expand it (low-confidence items are already expanded)
2. In the blue "Correct this match" area, use the **Item** link field to select the correct item
3. Add a **Reasoning** note explaining why — this teaches the system
4. The card gets a blue left border indicating it's been modified
5. The **summary bar** at the bottom updates the change count in real-time

For header corrections, click the pencil icon next to Supplier, Tax Template, or Cost Center to reveal override fields.

### Summary Bar

A sticky bar at the bottom of the dialog shows:
- **Attention count** — how many items still need review (below 90%)
- **Change count** — how many corrections you've made in this session
- **Action buttons** — "Save Corrections Only" and "Confirm & Create Invoice"

### Confirming

Click **Confirm & Create Invoice** to:
1. Save your corrections (aliases created, correction log updated, embeddings re-indexed, catalog and SKU mappings updated)
2. Check for duplicate invoices
3. Create a **Draft Purchase Invoice** with all the mapped data

Click **Save Corrections Only** to teach the system without creating a Purchase Invoice.

The Purchase Invoice is always created as a Draft — it is never auto-submitted.

### Why Reasoning Notes Matter

When you add a reasoning note, you're teaching the system:
- The note gets stored in the Mapping Correction Log
- Similar items from the same supplier will reference your reasoning
- The AI matching engine uses your notes as context for better decisions

### What the System Learns from Corrections

Each correction triggers multiple learning mechanisms:

| What You Correct | What the System Learns |
|---|---|
| **Line item** | Alias mapping, embedding update, Supplier Item Catalog entry, Vendor SKU mapping (if item code present) |
| **Supplier** | Alias mapping (vendor name → Supplier), correction log |
| **Tax Template** | Alias mapping (supplier → Tax Template), correction log |
| **Cost Center** | Alias mapping (supplier → Cost Center), correction log |

The **Supplier Item Catalog** tracks which items each supplier sells along with price statistics (average, min, max rate). This data feeds the Purchase History matching strategy.

The **Vendor SKU Mapping** remembers vendor-specific item codes printed on invoices. Next time the same vendor sends an invoice with the same item code, it's matched instantly at 97% confidence.

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
A: The system uses up to 8 matching strategies. Sometimes vendor descriptions differ from your Item names. Correcting it once creates an alias that catches it next time.

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

**Q: What matching strategies are available?**
A: There are 8 pluggable strategies: Exact, Vendor SKU, Alias, Purchase History, Fuzzy, HSN Filter, Embedding, and LLM. You can enable/disable and reorder them in **Matching Strategy** list. Purchase History and HSN Filter are disabled by default — enable them once you have enough data.

**Q: What is the Supplier Item Catalog?**
A: It tracks which items each supplier has sold to you, along with price statistics. It's auto-populated from Purchase Invoice submissions and human corrections. The Purchase History matching strategy uses this catalog to narrow candidates.

**Q: How does price validation work?**
A: After matching an item, the system checks the extracted rate against the historical average from the Supplier Item Catalog. If the rate is within 15% of average, confidence gets a +5% boost. If it's >50% off, confidence gets a -10% penalty. This helps catch wrong matches where the price doesn't make sense.

**Q: Can I add custom fields to extract from invoices?**
A: Yes. Go to **Invoice Automation Settings** → **Custom Extraction Fields**. Add fields with a name, type, and LLM description. Custom fields are injected into the extraction prompt and can be mapped to ERPNext fields on the Purchase Invoice.

**Q: What if the LLM provider is not running or misconfigured?**
A: Extraction will fail gracefully with a clear error. Use the **Health Check** endpoint or check the `processing_error` field on the queue record. Ensure your configured provider is running and API keys are set in **Invoice Automation Settings**.

**Q: What happens with scanned PDFs if I don't have a LlamaParse key?**
A: The system renders each PDF page as an image using PyMuPDF and sends it to your configured extraction LLM's vision model. This requires `PyMuPDF` to be installed and a vision-capable LLM (e.g. Ollama with `qwen2.5vl`, OpenAI GPT-4o, Anthropic Claude, or Gemini).
