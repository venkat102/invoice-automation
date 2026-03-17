"""Extraction prompt engineering for Ollama."""

EXTRACTION_SYSTEM_PROMPT = """You are an expert invoice data extraction engine. Your task is to extract structured data from invoice text with absolute precision.

CRITICAL RULES:
- Extract ONLY what is explicitly present in the document
- Return null for any field that is not clearly visible — NEVER hallucinate or guess
- Keep arrays empty rather than inventing line items
- Preserve original numeric precision using string representation
- Normalize dates to ISO 8601 format (YYYY-MM-DD)
- Normalize currency symbols to ISO 4217 codes (₹ → INR, $ → USD, € → EUR)
- Distinguish carefully between subtotal, tax amounts, and grand total
- Bank details are NOT totals — do not confuse them
- Tax summary tables are NOT line items — do not mix them up
- For each monetary value, use string representation (e.g., "1234.56" not 1234.56)"""

EXTRACTION_PROMPT = """Extract all invoice data from the following document text into a strict JSON structure.

DOCUMENT TEXT:
---
{document_text}
---

Return a JSON object with EXACTLY these fields (use null for missing data, empty arrays for missing lists):

{{
  "document_type": "invoice|credit_note|debit_note|proforma|quotation|delivery_challan|purchase_order|unknown",
  "document_type_confidence": 0-100,

  "vendor_name": "string or null",
  "vendor_address": "string or null",
  "vendor_tax_id": "GSTIN/VAT/TIN or null",
  "vendor_pan": "string or null",
  "vendor_phone": "string or null",
  "vendor_email": "string or null",

  "customer_name": "string or null",
  "customer_address": "string or null",
  "customer_tax_id": "string or null",

  "invoice_number": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "purchase_order_number": "string or null",

  "currency": "ISO 4217 code or null",
  "subtotal": "decimal string or null",
  "tax_amount": "decimal string or null",
  "cgst_amount": "decimal string or null",
  "sgst_amount": "decimal string or null",
  "igst_amount": "decimal string or null",
  "cess_amount": "decimal string or null",
  "discount_amount": "decimal string or null",
  "shipping_amount": "decimal string or null",
  "round_off_amount": "decimal string or null",
  "total_amount": "decimal string or null",
  "amount_paid": "decimal string or null",
  "balance_due": "decimal string or null",

  "tax_details": [
    {{"tax_type": "CGST|SGST|IGST|VAT|Cess|TDS", "rate": "decimal string", "amount": "decimal string", "description": "string"}}
  ],
  "is_reverse_charge": true/false/null,
  "place_of_supply": "string or null",

  "payment_terms": "string or null",
  "payment_method": "string or null",
  "bank_details": {{"bank_name": "...", "account_number": "...", "ifsc": "...", "branch": "...", "upi_id": "..."}} or null,

  "line_items": [
    {{
      "line_number": 1,
      "description": "string",
      "quantity": "decimal string or null",
      "unit": "string or null",
      "unit_price": "decimal string or null",
      "tax_rate": "decimal string or null",
      "tax_amount": "decimal string or null",
      "discount_amount": "decimal string or null",
      "line_total": "decimal string or null",
      "hsn_sac_code": "string or null",
      "sku": "string or null",
      "item_code": "string or null"
    }}
  ],

  "notes": "string or null",
  "extraction_confidence": 0-100,
  "field_group_confidence": {{
    "supplier_fields": 0-100,
    "invoice_header": 0-100,
    "totals": 0-100,
    "line_items": 0-100
  }},
  "warnings": [
    {{"category": "string", "message": "string", "severity": "warning|error|info", "field_path": "string or null"}}
  ]
}}

IMPORTANT: Return ONLY the JSON object. No markdown, no explanation, no code fences."""
