# Invoice Automation - User Guide

## Overview

Invoice Automation processes vendor invoices automatically by:
1. **Extracting** data from uploaded files (PDF, images, DOCX) using AI vision models
2. **Matching** extracted fields against your ERPNext master data (Suppliers, Items, Tax Templates)
3. **Learning** from your corrections so it improves over time

## Uploading Invoices

### Single Invoice
1. Navigate to **Invoice Processing Queue** → **+ Add**
2. Attach your invoice file in the **Source File** field
3. Save — extraction and matching start automatically in the background
4. Or use the API: call `parse_invoice` with a `file_url`

### Batch Upload
Use the API endpoint `parse_invoices_batch` with a list of file URLs to process multiple invoices at once. Enable batch parsing in **Invoice Automation Settings**.

### Supported File Formats
- **PDF** (native, scanned, or hybrid) — parsed via LlamaParse
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
| **Routed** | Matching complete, invoice routed based on confidence |
| **Under Review** | Waiting for human review |
| **Invoice Created** | Draft Purchase Invoice created |
| **Rejected** | Invoice was rejected by a reviewer |
| **Failed** | An error occurred during processing |

## Understanding Confidence Scores

Each matched field has a confidence score (0-100%):

| Score Range | Meaning | Action |
|-------------|---------|--------|
| **90-100%** | High confidence | Auto-created as Draft PI (if enabled) |
| **60-89%** | Likely correct, needs verification | Sent to Review Queue |
| **Below 60%** | Low confidence | Sent to Manual Entry Queue |

The **Overall Confidence** is the *lowest* confidence across all fields — one uncertain field means the whole invoice needs review.

## Reviewing and Correcting Mappings

When an invoice lands in the Review Queue:

1. Open the Invoice Processing Queue record
2. Review the **Matched Header** section: check the supplier, bill number, dates
3. Check the **Line Items** table — focus on low-confidence items
4. For each incorrect match:
   - Change the **Matched Item** link to the correct Item
   - Add **Correction Reasoning** explaining why (this teaches the system!)
5. Click **Confirm Mapping** to accept and create the Purchase Invoice

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

After matching, the system verifies that the computed total (sum of qty × rate + taxes) matches the extracted total. If there's a mismatch exceeding the configured tolerance (default ₹1), the invoice is flagged for review.

## Configuration

All settings are in **Invoice Automation Settings** (single doctype):
- **Ollama**: AI model server URL and model name
- **LlamaParse**: API key for PDF parsing
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

**Q: What if Ollama is not running?**
A: Extraction will fail gracefully with a clear error. Use the **Health Check** endpoint or check the processing_error field on the queue record.
