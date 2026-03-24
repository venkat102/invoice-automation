# Example Walkthrough: One Invoice from Upload to Purchase Invoice

This guide walks through a concrete example of processing a single vendor invoice end-to-end.

---

## The Invoice

Suppose you receive a PDF invoice from **ACME Industrial Supplies** with:

| Field | Value |
|-------|-------|
| Vendor | ACME Industrial Supplies Pvt. Ltd. |
| GSTIN | 27AAACT2727Q1ZW |
| Invoice # | INV-2024-0342 |
| Date | 15-Mar-2024 |
| Currency | INR |

| # | Description | Qty | Rate | Amount | HSN |
|---|-------------|-----|------|--------|-----|
| 1 | SS Steel Pipe 2mm x 6m | 5 | 1,200.00 | 6,000.00 | 7306 |
| 2 | Elec Cable 4mm Copper | 10 | 450.00 | 4,500.00 | 8544 |
| 3 | M8 Hex Bolt SS | 100 | 12.50 | 1,250.00 | 7318 |

| Tax | Rate | Amount |
|-----|------|--------|
| CGST | 9% | 1,057.50 |
| SGST | 9% | 1,057.50 |

**Grand Total: 13,865.00**

---

## Step 1: Upload

You upload the PDF file to **Invoice Processing Queue**:
- Navigate to **Invoice Processing Queue** > **+ Add Invoice Processing Queue**
- Attach the file in the **Source File** field
- Click **Save**

A new queue record `INV-Q-00042` is created with:
- **Workflow State**: Pending
- **Extraction Status**: Pending
- **Matching Status**: Pending

The system automatically queues extraction as a background job.

---

## Step 2: Extraction (automatic, ~5-15 seconds)

The extraction engine processes the PDF:

1. **File handling**: validates size (< 25 MB), detects type (PDF), computes SHA-256 hash
2. **Parsing**: PyMuPDF extracts selectable text from the PDF
3. **LLM extraction**: the configured extraction provider (e.g., Ollama with `qwen2.5vl:7b`) reads the text and outputs structured JSON
4. **Normalization**: dates converted to ISO format (`2024-03-15`), currency symbol to `INR`, amounts preserved as strings
5. **Validation**: checks total consistency (6000 + 4500 + 1250 + 1057.50 + 1057.50 = 13865 — matches)

The queue record now shows:
- **Workflow State**: Extracted
- **Extraction Status**: Completed
- **Extraction Confidence**: 95

The extracted data is stored as JSON on the queue record.

---

## Step 3: Matching (automatic, ~1-5 seconds)

The matching pipeline runs through enabled strategies for each field:

### Supplier Matching

| Strategy | What Happens | Result |
|----------|-------------|--------|
| **Exact** (priority 10) | Looks up GSTIN `27AAACT2727Q1ZW` in Redis | Found: "ACME Industrial Supplies" at 100% |

Supplier matched immediately via tax ID. Pipeline stops here for supplier.

### Line Item 1: "SS Steel Pipe 2mm x 6m"

| Strategy | What Happens | Result |
|----------|-------------|--------|
| **Exact** (priority 10) | Normalizes to `SS STEEL PIPE 2MM X 6M`, looks up in Redis | Not found |
| **Vendor SKU** (priority 15) | No item_code on invoice | Skip |
| **Alias** (priority 20) | Checks `ACME Industrial Supplies:SS STEEL PIPE 2MM X 6M:Item` | Not found |
| **Fuzzy** (priority 30) | Compares against all Item names. Best: `STEEL-PIPE-SS-2MM` with token_sort_ratio=88 | Match at 78% |

Result: Matched to `STEEL-PIPE-SS-2MM` at 78% confidence (Fuzzy stage). Needs review.

**Price validation**: No Supplier Item Catalog entry exists yet (first time). No change.

### Line Item 2: "Elec Cable 4mm Copper"

| Strategy | What Happens | Result |
|----------|-------------|--------|
| **Exact** | Normalized lookup | Not found |
| **Alias** | Composite key lookup | Not found |
| **Fuzzy** | Best: `CABLE-CU-4MM` with partial_ratio=72 | Match at 68% |

Result: Matched to `CABLE-CU-4MM` at 68% confidence (Fuzzy stage). Needs review.

### Line Item 3: "M8 Hex Bolt SS"

| Strategy | What Happens | Result |
|----------|-------------|--------|
| **Exact** | Normalizes to `M8 HEX BOLT SS`, Redis lookup | Found: `BOLT-M8-SS` at 95% |

Result: Exact match at 95% confidence. No review needed.

### Tax Template Matching

The system detects both GSTINs start with `27` (Maharashtra) → intra-state → expects CGST + SGST. Finds template "Input GST In-State" with 9% CGST + 9% SGST.

### Routing Decision

| Field | Confidence | Status |
|-------|-----------|--------|
| Supplier | 100% | OK |
| Line 1 (Steel Pipe) | 78% | Needs review |
| Line 2 (Cable) | 68% | Needs review |
| Line 3 (Bolt) | 95% | OK |
| Tax Template | 95% | OK |

**Minimum confidence: 68%** → Routing: **Review Queue**

Queue record now shows:
- **Workflow State**: Under Review
- **Routing Decision**: Review Queue
- **Overall Confidence**: 68%

---

## Step 4: Review (human, ~30 seconds)

You click **Review & Create Invoice**. The two-panel review dialog opens:

**Left panel**: PDF preview of the original invoice
**Right panel**: Matched data with corrections needed

### What you see:

**Header section** — all green (supplier matched at 100%, tax template at 95%)

**Line items** — sorted by attention needed:
1. **#2 Elec Cable 4mm Copper** — orange border, 68%, auto-expanded
   - Matched to: `CABLE-CU-4MM`
   - You verify this is correct. No correction needed.

2. **#1 SS Steel Pipe 2mm x 6m** — orange border, 78%, auto-expanded
   - Matched to: `STEEL-PIPE-SS-2MM`
   - You verify this is correct. No correction needed.

3. **#3 M8 Hex Bolt SS** — no border, 95%, collapsed
   - Matched to: `BOLT-M8-SS` — looks good.

**Summary bar**: "2 items need review | 0 changes"

In this case, the fuzzy matches were correct. You click **Confirm & Create Invoice**.

---

## Step 5: Purchase Invoice Created

The system:
1. Checks for duplicates (none found)
2. Creates a **Draft Purchase Invoice** with:
   - Supplier: ACME Industrial Supplies
   - Bill No: INV-2024-0342
   - Bill Date: 2024-03-15
   - Items: STEEL-PIPE-SS-2MM (qty 5, rate 1200), CABLE-CU-4MM (qty 10, rate 450), BOLT-M8-SS (qty 100, rate 12.50)
   - Tax Template: Input GST In-State

Queue record now shows:
- **Workflow State**: Invoice Created
- **Purchase Invoice**: ACC-PINV-2024-00156

---

## What If You Need to Correct?

Suppose "Elec Cable 4mm Copper" was wrongly matched to `CABLE-CU-4MM` — the correct item is `CABLE-COPPER-4SQ`.

In the review dialog, you would:
1. Expand line item #2
2. In the blue "Correct this match" area, change the Item to `CABLE-COPPER-4SQ`
3. Type reasoning: "Vendor abbreviates 4 sq mm as 4mm"
4. Summary bar now shows: "2 items need review | 1 change"
5. Click **Confirm & Create Invoice**

### What the system learns from this correction:

| Learning Mechanism | What Happens |
|-------------------|-------------|
| **Mapping Alias** | Creates alias: `ACME Industrial Supplies:ELEC CABLE 4MM COPPER:Item` → `CABLE-COPPER-4SQ` |
| **Correction Log** | Records: system proposed CABLE-CU-4MM at 68%, human chose CABLE-COPPER-4SQ, reasoning: "Vendor abbreviates..." |
| **Embedding Index** | Generates vector for "Elec Cable 4mm Copper" linked to CABLE-COPPER-4SQ (background job) |
| **Supplier Item Catalog** | Creates entry: ACME Industrial Supplies + CABLE-COPPER-4SQ, rate: 450, count: 1 |

### Next time ACME sends an invoice with "Elec Cable 4mm Copper":

The Alias strategy (priority 20) catches it instantly at 99% confidence. No fuzzy matching needed. The invoice may even auto-create without review.

---

## What Happens Over Time

| Time Period | What Improves |
|-------------|--------------|
| **After first invoice** | Aliases created for corrected items. GSTIN already in Redis for instant supplier match. |
| **After 5 invoices from ACME** | Most items have aliases. Supplier Item Catalog has price history. New items still need fuzzy/embedding. |
| **After 20 invoices from ACME** | Nearly all items match at Alias stage. Price validation active (boosts confidence when rates are consistent). Purchase History strategy helps match new items similar to past purchases. |
| **After 50+ invoices** | System runs on autopilot for this supplier. Only genuinely new items or significant price changes trigger review. |
