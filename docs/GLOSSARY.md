# Glossary

Quick reference for all terminology used in Invoice Automation. If you're new to Frappe, ERPNext, or this app, start here.

---

## Frappe Framework Concepts

| Term | What It Means |
|------|---------------|
| **Frappe** | The Python + JavaScript web framework that ERPNext is built on. It provides DocTypes, forms, APIs, permissions, background jobs, and the desk UI. Think of it as Django + admin panel + workflow engine in one. |
| **Bench** | The CLI tool for managing Frappe sites. Commands like `bench get-app`, `bench install-app`, `bench migrate` are how you install and maintain apps. A "bench" is a directory containing one or more Frappe sites and apps. |
| **Site** | A single Frappe installation with its own database, files, and configuration. One bench can host multiple sites. |
| **DocType** | Frappe's equivalent of a database model/table. Each DocType defines fields, permissions, and behavior. When you see "Invoice Processing Queue" — that's a DocType. Each record is called a "document" or "doc". |
| **Single DocType** | A DocType that has only ONE record, used for global settings. "Invoice Automation Settings" is a Single DocType — there's only one settings page for the whole site. |
| **Child Table** | A DocType that exists only as rows inside another DocType. "Invoice Line Item Match" is a child table of "Invoice Processing Queue" — each queue record has multiple line items. |
| **Link Field** | A field that references a record in another DocType. Like a foreign key. `matched_supplier` is a Link field pointing to the `Supplier` DocType. |
| **Dynamic Link** | A Link field where the target DocType is determined by another field. `canonical_name` in Mapping Alias links to Supplier, Item, or Tax Template depending on `source_doctype`. |
| **Workflow State** | A status field that tracks where a document is in a process. Invoice Processing Queue uses states like "Pending", "Extracting", "Under Review", etc. |
| **Redis** | An in-memory key-value store used by Frappe for caching, real-time updates, and (in this app) fast index lookups. Must be running for the app to work. |
| **RQ (Redis Queue)** | Frappe's background job system built on Python RQ. Long-running tasks like extraction and embedding generation run as background jobs so they don't block the web server. |
| **Scheduler** | Frappe's built-in cron-like system that runs scheduled jobs (daily, weekly, etc.). Must be enabled: `bench enable-scheduler`. |
| **Hooks** | Python functions that Frappe calls automatically when events happen (document saved, app installed, etc.). Defined in `hooks.py`. |
| **Whitelist** | The `@frappe.whitelist()` decorator that makes a Python function callable via HTTP API. Only whitelisted functions can be called from JavaScript or external systems. |
| **Desk** | Frappe's web-based admin UI where you manage documents, run reports, and configure settings. |

## ERPNext Business Concepts

| Term | What It Means |
|------|---------------|
| **Supplier** | A vendor or company that sells goods/services to you. Each supplier has a name, address, tax IDs (GSTIN, PAN), and contact details. This is the master record you're matching invoices against. |
| **Item** | A product, material, or service in your inventory. Each item has a code (like `STEEL-PIPE-2MM`), a name, description, HSN code, item group, and pricing. Line items on invoices are matched to Item records. |
| **Purchase Invoice (PI)** | The ERPNext document that records a purchase from a supplier. This is the OUTPUT of the invoice automation process. Contains supplier, line items (with matched Item codes, qty, rate), taxes, and totals. |
| **Draft** | A Purchase Invoice state where it's saved but not yet finalized. Invoice Automation always creates Draft PIs — they are never auto-submitted. A human must review and submit. |
| **Purchase Taxes and Charges Template** | A reusable template defining tax rules (e.g., "GST 18%" with CGST 9% + SGST 9%). When matched, it auto-fills the tax rows on the Purchase Invoice. |
| **Cost Center** | An ERPNext concept for tracking costs by department, project, or business unit. Optional — used for expense allocation. |
| **Item Group** | A category for Items (e.g., "Raw Materials", "Electronics"). Used for organizing and filtering. |
| **HSN/SAC Code** | Harmonized System Nomenclature (goods) or Service Accounting Code (services). Indian GST classification codes that identify what type of product/service is being sold. Used for tax compliance. |
| **GSTIN** | Goods and Services Tax Identification Number. A 15-character alphanumeric code assigned to businesses in India. Format: `{2-digit state}{10-digit PAN}{1-entity}{1-Z}{1-checksum}`. Example: `27AAACT2727Q1ZW`. |
| **PAN** | Permanent Account Number. A 10-character Indian tax ID. Can be extracted from GSTIN (characters 3-12). Format: `{5 letters}{4 digits}{1 letter}`. Example: `AAACT2727Q`. |
| **Intra-state vs Inter-state** | In Indian GST, if both buyer and seller are in the same state → intra-state (CGST + SGST). Different states → inter-state (IGST). Determined by comparing the first 2 digits of buyer/seller GSTINs. |

## Invoice Automation Concepts

| Term | What It Means |
|------|---------------|
| **Invoice Processing Queue** | The main DocType that tracks one invoice through the entire pipeline. Each uploaded file creates one queue record that moves through states: Pending → Extracting → Matching → Routed/Under Review → Invoice Created. |
| **Extraction** | The first phase: an AI model (LLM) reads the invoice file and outputs structured data (vendor name, line items, amounts, etc.) as JSON. |
| **Matching** | The second phase: the system maps extracted data to ERPNext records. "Match supplier" means finding which Supplier record corresponds to the vendor name on the invoice. |
| **Matching Strategy** | A pluggable algorithm that tries to match extracted data to ERPNext records. There are 8 strategies (Exact, Vendor SKU, Alias, Purchase History, Fuzzy, HSN Filter, Embedding, LLM) executed in priority order. |
| **Match Stage** | Which strategy successfully matched a field. Shown as "Exact", "Alias", "Fuzzy", "Embedding", "LLM", or "Manual" (human-corrected). |
| **Confidence Score** | A 0-100% number indicating how sure the system is about a match. Higher = more certain. Determines routing: >=90% auto-create, 60-89% review, <60% manual entry. |
| **Routing Decision** | Based on the minimum confidence across all matched fields: "Auto Create" (all fields >=90%), "Review Queue" (some 60-89%), or "Manual Entry" (some <60%). |
| **Mapping Alias** | A learned mapping from invoice text to an ERPNext record. Created when a human corrects a match. Example: the text "ACME Corp Pvt Ltd" maps to Supplier "ACME Corporation". Next time the same text appears, it's matched instantly. |
| **Composite Key** | The unique lookup key for an alias: `{supplier_or_ANY}:{normalized_text}:{source_doctype}`. Example: `ACME Corp:steel pipe 2mm:Item`. |
| **Decay Weight** | A number (0.5 to 1.0) that reduces alias confidence over time. Fresh corrections = 1.0 (full confidence). After 100+ days without reinforcement = 0.5 (half confidence). Ensures stale aliases don't dominate. |
| **Supplier Item Catalog** | A record tracking which items each supplier has sold, with price statistics (average, min, max rate). Auto-populated from Purchase Invoice submissions and corrections. |
| **Vendor SKU Mapping** | A record mapping a vendor's item code (printed on their invoice) to your ERPNext Item. Enables instant matching when the same vendor sends the code again. |
| **Correction Memory** | The collective learning system: aliases, correction logs, embeddings, catalog entries, and SKU mappings — all created from human corrections and used to improve future matching. |
| **Embedding** | A 384-dimensional numerical vector that represents the "meaning" of text. Two similar texts have similar embeddings. Used for semantic matching (Stage 7) when exact and fuzzy matching fail. |
| **Cosine Similarity** | A measure of how similar two embeddings are, from 0 (unrelated) to 1 (identical). The system uses this to find items semantically similar to the extracted description. |
| **Normalization** | Text cleanup before matching: uppercase, remove punctuation, strip company suffixes (Pvt, Ltd, LLC), collapse whitespace. "ACME Corp Pvt. Ltd." becomes "ACME CORP". |
| **LLM (Large Language Model)** | The AI model used for extraction and matching. Supported providers: Ollama (free/local), OpenAI (GPT-4o), Anthropic (Claude), Google Gemini. |
| **Custom Extraction Field** | A user-defined field added to the extraction schema via settings. Injected into the LLM prompt so the AI extracts it from invoices. Can be mapped to ERPNext fields on the Purchase Invoice. |

## Matching Strategy Details

| Strategy | Priority | What It Does | Confidence Range |
|----------|----------|-------------|-----------------|
| **Exact** | 10 | Looks up tax IDs, PAN, and normalized names in Redis | 95-100% |
| **Vendor SKU** | 15 | Matches vendor's item code from the invoice | 97% |
| **Alias** | 20 | Looks up human-corrected mappings (with decay weighting) | 45-99% |
| **Purchase History** | 25 | Fuzzy matches against items this supplier has sold before | 70-85% |
| **Fuzzy** | 30 | String similarity using token-based algorithms | 60-89% |
| **HSN Filter** | 35 | Narrows candidates by HSN code, then fuzzy matches | 60-89% |
| **Embedding** | 40 | Semantic vector similarity search | 65-92% |
| **LLM** | 50 | AI-based reasoning with past correction context | Up to 88% |
