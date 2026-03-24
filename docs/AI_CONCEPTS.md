# AI & ML Concepts for Python Developers

This document explains every AI/ML concept, library, and technique used in Invoice Automation. Written for someone who knows Python but has never worked with AI, LLMs, or embeddings.

---

## Table of Contents

1. [The Big Picture](#the-big-picture)
2. [Large Language Models (LLMs)](#large-language-models-llms)
3. [Prompt Engineering](#prompt-engineering)
4. [Vision Models](#vision-models)
5. [JSON Mode & Structured Output](#json-mode--structured-output)
6. [Text Embeddings & Semantic Search](#text-embeddings--semantic-search)
7. [Fuzzy String Matching](#fuzzy-string-matching)
8. [Text Normalization](#text-normalization)
9. [Confidence Scoring & Thresholds](#confidence-scoring--thresholds)
10. [The Learning Loop](#the-learning-loop)
11. [Libraries Used](#libraries-used)
12. [Parameters & Configuration](#parameters--configuration)

---

## The Big Picture

Invoice Automation uses AI at two points:

```
┌──────────────────────────────┐     ┌──────────────────────────────┐
│     EXTRACTION (AI reads)    │     │     MATCHING (AI helps find) │
│                              │     │                              │
│  PDF/Image → LLM Vision     │     │  Fuzzy matching (algorithms) │
│            → Structured JSON │     │  Embeddings (semantic AI)    │
│                              │     │  LLM fallback (AI reasoning) │
└──────────────────────────────┘     └──────────────────────────────┘
```

**Extraction** uses an LLM to read invoice files and output structured data (vendor name, items, amounts). This is the expensive AI part — it calls an external API or local model.

**Matching** mostly uses traditional algorithms (exact lookup, fuzzy string matching). AI is only involved in two of the eight strategies: embedding search (semantic similarity) and LLM fallback (as a last resort).

---

## Large Language Models (LLMs)

### What is an LLM?

A Large Language Model is a neural network trained on massive amounts of text that can understand and generate human language. Think of it as an extremely sophisticated autocomplete — you give it a prompt (text input), and it generates a response (text output).

**In this project, LLMs do two things:**
1. **Read invoices** — given invoice text/image, extract structured fields into JSON
2. **Match items** — given an item description and candidates, pick the best match

### How LLMs Are Called in This Project

Every LLM interaction goes through a provider abstraction (`llm/base.py`):

```python
# The interface every provider implements
class LLMProvider:
    def generate(self, prompt, system=None) -> str:
        """Send text, get text back."""
        ...

    def generate_with_image(self, prompt, image_base64) -> str:
        """Send text + image, get text back."""
        ...

    def generate_json(self, prompt, system=None) -> dict:
        """Send text, get parsed JSON back."""
        ...

    def health_check(self) -> dict:
        """Check if the provider is reachable."""
        ...
```

The actual call is a simple HTTP request or SDK call:

```python
# Example: OpenAI provider (simplified)
response = self.client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    max_tokens=4096,
)
return response.choices[0].message.content
```

### Supported Providers

| Provider | How It Works | Cost | Speed | Used In |
|----------|-------------|------|-------|---------|
| **Ollama** | Runs AI models locally on your machine | Free | Slower (depends on GPU) | Default for extraction |
| **OpenAI** | API call to OpenAI servers (GPT-4o) | ~$0.01-0.03 per invoice | Fast | Alternative |
| **Anthropic** | API call to Anthropic servers (Claude) | ~$0.01-0.03 per invoice | Fast | Default for matching |
| **Gemini** | API call to Google servers | ~$0.01 per invoice | Fast | Alternative |

### What Happens When You Call an LLM

```
Your code                    Provider API                  AI Model
    │                            │                            │
    ├─── prompt text ──────────► │                            │
    │    (+ system instructions) ├─── HTTP request ─────────► │
    │                            │                            │
    │                            │    ◄── generated text ─────┤
    │    ◄── response string ────┤                            │
    │                            │                            │
```

The AI model processes your prompt and generates a response token by token. You receive the complete text back. The model doesn't "understand" in a human sense — it predicts the most likely next tokens based on patterns learned during training.

### Key LLM Concepts

| Concept | What It Means | In This Project |
|---------|--------------|-----------------|
| **Token** | A chunk of text (roughly 4 characters or 0.75 words). LLMs process text as tokens, not characters. | Document text is limited to 8,000 characters (~2,000 tokens) to stay within limits |
| **Max Tokens** | Maximum response length the model will generate | Set to 4,096 tokens in all providers |
| **Temperature** | Controls randomness. 0 = deterministic, 1 = creative. | Not explicitly set (providers use their defaults, typically 0.7-1.0) |
| **System Prompt** | Instructions that set the LLM's behavior and role. Sent separately from the user's input. | "You are an expert invoice data extraction engine..." |
| **User Prompt** | The actual request — contains the invoice text and expected output format | The extraction prompt with `{document_text}` and JSON schema |
| **Hallucination** | When an LLM generates plausible-sounding but false information | The system prompt explicitly says "NEVER hallucinate or guess — return null for missing fields" |
| **Context Window** | The total amount of text (prompt + response) the model can handle at once | Varies by model: 4K-128K tokens. Document text truncated to 8,000 chars to be safe |

### Retry Logic

LLM API calls can fail (network issues, rate limits, timeouts). The system uses **exponential backoff**:

```python
# Simplified from llm/base.py
MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds

for attempt in range(MAX_RETRIES):
    try:
        return call_llm_api(prompt)
    except (TimeoutError, ConnectionError):
        if attempt < MAX_RETRIES - 1:
            delay = BASE_DELAY * (2 ** attempt)  # 1s, 2s, 4s
            time.sleep(delay)
        else:
            raise
```

Each retry waits twice as long as the previous one (1s → 2s → 4s) to give the provider time to recover.

---

## Prompt Engineering

### What is Prompt Engineering?

Prompt engineering is the practice of carefully crafting the text you send to an LLM to get the output you want. It's like writing very specific instructions for a very capable but literal assistant.

### How This Project Engineers Prompts

**The extraction prompt** (`extraction/prompt_templates.py`) has three layers:

#### Layer 1: System Prompt — Sets the Rules

```
You are an expert invoice data extraction engine. Your task is to extract
structured data from invoice text with absolute precision.

CRITICAL RULES:
- Extract ONLY what is explicitly present in the document
- Return null for any field that is not clearly visible — NEVER hallucinate
- Keep arrays empty rather than inventing line items
- Preserve original numeric precision using string representation
- Normalize dates to ISO 8601 format (YYYY-MM-DD)
- ...
```

**Why each rule exists:**
- "NEVER hallucinate" → LLMs tend to fill in blanks with plausible but wrong data
- "string representation" → floating-point numbers lose precision (`1234.56` might become `1234.5600000001`)
- "ISO 8601" → different invoices use different date formats; we need consistency

#### Layer 2: User Prompt — Provides Context + Schema

```
Extract all invoice data from the following document text into a strict JSON structure.

DOCUMENT TEXT:
---
{actual invoice text here}
---

Return a JSON object with EXACTLY these fields:
{
  "vendor_name": "string or null",
  "invoice_number": "string or null",
  "line_items": [
    {
      "description": "string",
      "quantity": "decimal string or null",
      ...
    }
  ],
  ...
}

IMPORTANT: Return ONLY the JSON object. No markdown, no explanation, no code fences.
```

**Why this structure:**
- Document text is clearly delimited with `---` markers → LLM knows where invoice ends
- Full JSON schema in the prompt → LLM follows the exact structure
- "ONLY the JSON" → prevents LLM from wrapping output in markdown

#### Layer 3: Dynamic Field Injection — Custom Fields

When users add custom extraction fields via settings, they're injected into the JSON schema portion of the prompt:

```python
# From prompt_templates.py
prompt = prompt.replace(
    '"notes": "string or null",',
    '"project_code": "string or null",  // 6-digit project code near PO reference\n'
    + '"notes": "string or null",',
)
```

The `// comment` after the field is the user's `description_for_llm` — it tells the AI where to find the value on the invoice.

### Zero-Shot vs Few-Shot

| Approach | What It Means | Used Here? |
|----------|--------------|------------|
| **Zero-shot** | No examples provided — just instructions and schema | Yes (current approach) |
| **Few-shot** | Include 1-3 example inputs + outputs in the prompt | No (would improve accuracy for unusual invoices but increases token cost) |
| **Fine-tuning** | Train a custom model on your specific invoices | No (expensive, requires large dataset) |

The project uses **zero-shot** — the LLM gets detailed instructions and a JSON schema, but no example invoice-to-JSON pairs. This works well for standard invoices. Unusual formats may need a human review.

---

## Vision Models

### What is a Vision Model?

A vision model (or multimodal model) is an LLM that can process both text AND images. Instead of just reading text, it can "see" an image and describe or extract information from it.

### How This Project Uses Vision

When an invoice is a **scanned PDF** (no selectable text) or an **image file** (PNG, JPG), the system:

1. Renders the PDF page as an image (using PyMuPDF)
2. Converts the image to base64 encoding (a text representation of binary image data)
3. Sends both the image and the extraction prompt to the LLM

```python
# Simplified from image_parser.py
import base64

with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode()

# Send to LLM provider
text = provider.generate_with_image(
    prompt="Extract all text and data from this invoice image.",
    image_base64=image_base64,
)
```

Each provider formats the image differently:

| Provider | Image Format in API |
|----------|-------------------|
| **OpenAI** | `{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}` |
| **Anthropic** | `{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}` |
| **Gemini** | `Part.from_bytes(data=image_bytes, mime_type="image/png")` |
| **Ollama** | `{"images": ["base64_string"]}` |

### When Vision is Used

```
PDF uploaded
    │
    ├── Has selectable text? → Extract text with PyMuPDF → Send TEXT to LLM
    │
    └── Scanned/image-only? → Render as image → Send IMAGE to LLM (vision model)

Image uploaded (PNG/JPG/etc.)
    │
    └── Always → Send IMAGE to LLM (vision model)
```

---

## JSON Mode & Structured Output

### The Problem

LLMs generate free-form text. When you ask for JSON, the model might return:

```
Here's the extracted data:

```json
{"vendor_name": "ACME Corp", "total": 1500}
```

Note: I wasn't able to read the due date clearly.
```

This isn't valid JSON — it has markdown fences and explanatory text around it.

### Solution 1: JSON Mode (OpenAI & Gemini)

These providers support a native "JSON mode" that constrains the model to output only valid JSON:

```python
# OpenAI
response = client.chat.completions.create(
    model="gpt-4o",
    response_format={"type": "json_object"},  # Forces valid JSON
    ...
)

# Gemini
config = types.GenerateContentConfig(
    response_mime_type="application/json",  # Forces valid JSON
)
```

The model is physically incapable of producing non-JSON output when this mode is active.

### Solution 2: Retry + JSON Repair (Ollama & Anthropic)

These providers don't have native JSON mode, so the system:

1. Asks the LLM to return JSON (via prompt instructions)
2. If the response isn't valid JSON, applies repair heuristics
3. If repair fails, retries the entire LLM call (up to 3 times)

**JSON repair steps** (`extraction/json_repair.py`):

```python
def repair_json(raw_text):
    # 1. Strip markdown code fences:  ```json ... ```  →  ...
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)

    # 2. Remove trailing commas:  {"a": 1,}  →  {"a": 1}
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # 3. Single quotes → double quotes:  {'a': 1}  →  {"a": 1}
    # (careful implementation to avoid replacing quotes inside strings)

    # 4. Quote unquoted keys:  {name: "ACME"}  →  {"name": "ACME"}

    # 5. Close truncated JSON:  {"a": 1  →  {"a": 1}
    # (balance unclosed braces and brackets)

    # 6. Extract JSON from surrounding text
    # Find first { and last } to isolate the JSON object

    return json.loads(text)  # Parse the repaired string
```

---

## Text Embeddings & Semantic Search

### What is an Embedding?

An embedding is a list of numbers (a "vector") that represents the **meaning** of text. Similar texts get similar vectors. It's like converting words into coordinates in a high-dimensional space where distance = difference in meaning.

```
"Steel Pipe 2mm"     → [0.23, -0.15, 0.87, 0.42, ... ]  (384 numbers)
"2mm Steel Tube"     → [0.21, -0.14, 0.85, 0.44, ... ]  (very similar!)
"Chocolate Cake"     → [-0.55, 0.78, -0.12, 0.33, ... ]  (very different!)
```

### Why Embeddings Matter for This Project

Fuzzy string matching compares characters. Embeddings compare **meaning**:

| Comparison | Fuzzy Match Score | Embedding Similarity |
|------------|------------------|---------------------|
| "Steel Pipe 2mm" vs "2mm Steel Tube" | Low (different characters) | High (same meaning) |
| "SS Pipe" vs "Stainless Steel Pipe" | Low (abbreviation) | High (same concept) |
| "Cable 4mm" vs "Cable 4mm" | 100% (identical) | 1.0 (identical) |

Embeddings catch **synonyms, abbreviations, and rewordings** that string matching misses.

### How Embeddings Are Generated

**Library:** `sentence-transformers` (built on PyTorch and Hugging Face Transformers)

**Model:** `all-MiniLM-L6-v2`
- Trained on 1 billion+ sentence pairs
- Produces 384-dimensional vectors
- Small size (22 MB) — runs on CPU, no GPU needed
- Optimized for semantic similarity tasks

```python
# From embeddings/model.py (simplified)
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

# Generate embedding for one text
embedding = model.encode("Steel Pipe 2mm", normalize_embeddings=True)
# Result: numpy array of 384 float32 values
# e.g., array([0.023, -0.015, 0.087, ...], dtype=float32)
```

**`normalize_embeddings=True`** scales each vector to length 1.0 (unit vector). This is important for the next step.

### How Similarity is Computed

**Cosine similarity** measures the angle between two vectors:
- 1.0 = identical direction (identical meaning)
- 0.0 = perpendicular (unrelated)
- -1.0 = opposite (rare in practice)

When vectors are normalized to unit length, cosine similarity simplifies to a **dot product** (matrix multiplication):

```python
# From embeddings/index_manager.py
# query_embedding shape: (384,)
# all_embeddings shape: (N, 384) where N = number of stored items

similarities = all_embeddings @ query_embedding  # Matrix multiplication
# Result shape: (N,) — one similarity score per stored item
# e.g., [0.92, 0.45, 0.88, 0.12, ...]

# Find the most similar
best_index = np.argmax(similarities)
best_score = similarities[best_index]
```

**Why dot product = cosine similarity:**
For unit vectors (length 1), `dot(a, b) = |a| * |b| * cos(angle) = 1 * 1 * cos(angle) = cos(angle)`. So the dot product directly gives the cosine of the angle between vectors.

### The Vector Index

All embeddings are stored in a **NumPy matrix** in memory for fast search:

```python
# Simplified from index_manager.py
class NumpyVectorIndex:
    def __init__(self):
        self._embeddings = None  # Shape: (N, 384)
        self._metadata = []      # List of dicts with source info

    def search(self, query_embedding, filters=None, top_k=5):
        # Compute similarity with ALL stored embeddings at once
        similarities = (self._embeddings @ query_embedding.T).flatten()

        # Apply filters (e.g., only search "Item" embeddings, not historical)
        if filters:
            mask = np.ones(len(self._metadata), dtype=bool)
            for key, value in filters.items():
                for i, meta in enumerate(self._metadata):
                    if meta.get(key) != value:
                        mask[i] = False
            similarities *= mask  # Zero out filtered entries

        # Return top K results
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [
            SearchResult(
                source_name=self._metadata[i]["source_name"],
                score=float(similarities[i]),
                metadata=self._metadata[i],
            )
            for i in top_indices
        ]
```

**Performance:** This is an O(N) brute-force scan — it compares against every stored embedding. Fast enough for up to ~50,000 items (takes milliseconds with NumPy). For larger catalogs, you'd use a dedicated vector database like Qdrant or Pinecone.

### Two Search Indexes

The system maintains two sets of embeddings:

| Index | What's Stored | Source | Purpose |
|-------|---------------|--------|---------|
| **Item Master** | Embeddings for all ERPNext Items (name + description + brand + HSN) | Built from Item records on install, synced daily | Find similar items by meaning |
| **Historical Invoice Line** | Embeddings for past invoice line items that were human-corrected | Created when reviewers make corrections | Leverage past corrections for similar text |

**Search order:**
1. Search Historical index filtered by same supplier → highest trust (human-verified)
2. If no match, search Historical index without supplier filter
3. Search Item Master index
4. Pick the best similarity score across all results
5. If both indexes agree on the same item → bonus confidence (+10%)

### Human Correction Boost

Embeddings from human corrections get a **1.1x multiplier** on their similarity score:

```python
# From embedding_matcher.py
if is_human_corrected and historical_match == best_match:
    best_score = min(best_score * 1.1, 1.0)  # 10% boost, capped at 1.0
```

This means the system trusts human-validated matches more than auto-generated ones.

---

## Fuzzy String Matching

### What is Fuzzy Matching?

Fuzzy matching compares two strings and returns a similarity score (0-100) that accounts for typos, reordering, and minor differences. Unlike exact matching (`==`), it handles real-world text variations.

### Library: thefuzz

**Package:** `thefuzz` (formerly `fuzzywuzzy`), uses the Levenshtein distance algorithm under the hood.

### Three Algorithms Used

The project runs three different fuzzy algorithms and takes the **best score**:

#### 1. Token Sort Ratio

Splits both strings into words, sorts them alphabetically, then compares:

```
Input A: "Steel Pipe 2mm Round"
Input B: "2mm Round Steel Pipe"

Sorted A: "2mm Pipe Round Steel"
Sorted B: "2mm Pipe Round Steel"

Score: 100 (identical after sorting)
```

**Good for:** Different word order (which is common when vendors describe the same item differently).

#### 2. Partial Ratio

Finds the best matching substring:

```
Input A: "Steel Pipe"
Input B: "SS Steel Pipe 2mm Galvanized"

Best substring of B matching A: "Steel Pipe"

Score: 100 (A is a perfect substring of B)
```

**Good for:** One description is a subset of the other (e.g., short vendor description vs long ERPNext item name).

#### 3. Token Set Ratio

Splits into tokens, removes duplicates, compares the set of unique tokens:

```
Input A: "Steel Pipe Steel Rod"
Input B: "Steel Pipe Rod"

Unique tokens A: {Steel, Pipe, Rod}
Unique tokens B: {Steel, Pipe, Rod}

Score: 100 (same unique tokens)
```

**Good for:** Repeated words or extra qualifiers that don't change meaning.

### How Scores Become Confidence

```python
# From fuzzy_matcher.py
score = max(token_sort, partial, token_set)  # Best of three

# Map raw score to confidence
if score >= 85:
    confidence = 75 + (score - 85) * (14 / 15)  # → 75-89%
elif score >= 60:
    confidence = 60 + (score - 60) * (14 / 25)  # → 60-74%
else:
    return no_match  # Below threshold
```

Raw scores are intentionally mapped to **lower confidence** than their face value because fuzzy matching can produce false positives.

---

## Text Normalization

### What is Normalization?

Normalization transforms text into a standard form so that equivalent strings compare as identical. It's a pre-processing step before any matching.

### Why It Matters

Without normalization:
```
"ACME Corp. Pvt. Ltd."  ≠  "Acme Corporation Private Limited"
```

After normalization:
```
"ACME CORP"  =  "ACME CORP"  (both stripped of suffixes, uppercased)
```

### Normalization Steps (in order)

**General text** (`normalize_text()`):

| Step | Before | After | Why |
|------|--------|-------|-----|
| 1. Uppercase | "Acme Corp" | "ACME CORP" | Case-insensitive comparison |
| 2. Strip whitespace | "  ACME CORP  " | "ACME CORP" | Remove accidental spaces |
| 3. Remove punctuation | "ACME, CORP." | "ACME CORP" | Periods, commas don't matter |
| 4. Remove suffixes | "ACME CORP PRIVATE LIMITED" | "ACME CORP" | Legal suffixes vary by document |
| 5. Collapse spaces | "ACME  CORP" | "ACME CORP" | Multiple spaces → single |

**Removed suffixes:** PRIVATE LIMITED, PRIVATE, LIMITED, INCORPORATED, CORPORATION, CORP, PVT, LTD, INC, LLC, LLP, CO, COMPANY

**Item-specific** (`normalize_item_text()`) — same as above, plus:

| Step | Before | After | Why |
|------|--------|-------|-----|
| 6. Remove packaging | "STEEL PIPE 12 X 500 ML" | "STEEL PIPE" | Pack size doesn't identify the item |
| 7. Remove units | "STEEL PIPE 2MM 5KG" | "STEEL PIPE 2MM" | Units like KG, PCS, BOX are noise |

**Tax ID normalization** (`normalize_tax_id()`):

```
"27-AAACT-2727Q-1ZW"  →  "27AAACT2727Q1ZW"  (remove hyphens, spaces, uppercase)
```

---

## Confidence Scoring & Thresholds

### What is a Confidence Score?

A number from 0 to 100 representing how sure the system is about a match. Higher = more certain. Each matching strategy produces its own confidence based on different criteria.

### How Different Strategies Score

| Strategy | What Determines Confidence | Range |
|----------|--------------------------|-------|
| Exact (tax ID) | Found or not | 100% or 0% |
| Exact (name) | Found or not | 95% or 0% |
| Vendor SKU | Found or not | 97% or 0% |
| Alias | Found + decay weight | 45-99% |
| Purchase History | Fuzzy score + frequency bonus | 70-85% |
| Fuzzy | Best of 3 algorithms | 60-89% |
| HSN Filter | Fuzzy score + HSN match bonus | 60-89% |
| Embedding | Cosine similarity + boosts | 65-92% |
| LLM | Model's self-reported confidence | Capped at 88% |

### How Scores Combine

Three categories are weighted:

```
Overall = (Supplier × 30%) + (Average of Line Items × 60%) + (Tax × 10%)
```

Line items dominate because they're the most important part of the invoice — getting the wrong items is more costly than a supplier name mismatch.

### How Scores Drive Routing

```python
if any_field_unmatched:
    max_routing = "Review Queue"  # Can't auto-create with gaps

if overall >= 90:
    routing = "Auto Create"      # Create Draft PI automatically
elif overall >= 60:
    routing = "Review Queue"     # Human must verify
else:
    routing = "Manual Entry"     # Human must enter manually
```

### Price Validation (Post-Match Adjustment)

After matching, the system checks if the price makes sense:

```python
# From price_validator.py
deviation = abs(extracted_rate - historical_avg_rate) / historical_avg_rate * 100

if deviation <= 15:     # Rate is close to historical average
    confidence += 5     # Boost: "price confirms the match"
elif deviation > 50:    # Rate is way off
    confidence -= 10    # Penalty: "might be the wrong item"
```

This catches cases where fuzzy matching picks the right name but wrong item variant (e.g., "Steel Pipe 2mm" matched to "Steel Pipe 10mm" — same name, very different price).

---

## The Learning Loop

### How AI Improves Over Time

The system doesn't retrain any AI model. Instead, it builds **lookup tables and indexed data** from human corrections that short-circuit the AI:

```
First invoice from Supplier X:
  "Elec Cable 4mm" → Fuzzy match → CABLE-CU-4MM (68% confidence) → Review Queue
  Human corrects to CABLE-COPPER-4SQ with reasoning "4mm = 4 sq mm"
    → Creates alias: "ELEC CABLE 4MM" → CABLE-COPPER-4SQ
    → Creates embedding: vector for "Elec Cable 4mm" → CABLE-COPPER-4SQ
    → Logs reasoning for LLM context

Second invoice from Supplier X:
  "Elec Cable 4mm" → Alias match → CABLE-COPPER-4SQ (99% confidence) → Auto Create
  (No AI needed — direct lookup from alias created by the correction)
```

### What Each Correction Creates

| Storage | How It Helps | Speed |
|---------|-------------|-------|
| **Mapping Alias** | Direct text → record lookup (like a dictionary) | Instant (O(1) Redis lookup) |
| **Embedding Index** | Semantic similarity search for similar (not identical) text | Fast (NumPy dot product) |
| **Correction Log** | Provides reasoning context to LLM for similar future items | Used only when LLM is called |
| **Supplier Item Catalog** | Narrows candidates + validates prices | Fast (DB query) |
| **Vendor SKU Mapping** | Direct item code → record lookup | Instant (DB lookup) |

### The Progression

```
Week 1:   LLM and Embedding do most work → 50% review rate
Month 1:  Aliases accumulate → 70% auto-create
Month 3:  Catalog + embeddings mature → 85% auto-create
Month 6+: System runs on aliases + SKUs → 95%+ auto-create
```

The AI models (LLM, embeddings) are the **bootstrapping mechanism**. Over time, the deterministic lookup systems (aliases, SKUs) handle most invoices without calling any AI at all.

---

## Libraries Used

### AI/ML Libraries

| Library | Version | What It Does | Where Used |
|---------|---------|-------------|-----------|
| `sentence-transformers` | >=2.2.0 | Loads pre-trained embedding model, generates 384-dim vectors | `embeddings/model.py` |
| `numpy` | >=1.24.0 | Matrix operations for vector similarity search (dot product, argsort) | `embeddings/index_manager.py` |
| `thefuzz` | >=0.20.0 | Fuzzy string matching (Levenshtein-based algorithms) | `matching/fuzzy_matcher.py` |
| `pydantic` | >=2.0.0 | Schema validation for extracted JSON (ensures LLM output matches expected structure) | `extraction/schema.py` |

### LLM Provider Libraries

| Library | Version | Provider |
|---------|---------|----------|
| `httpx` | >=0.27.0 | Ollama (HTTP calls to local server) |
| `openai` | >=1.0.0 | OpenAI (GPT-4o and other models) |
| `anthropic` | >=0.25.0 | Anthropic (Claude models) |
| `google-genai` | >=1.0.0 | Google Gemini |

### Document Processing Libraries

| Library | What It Does |
|---------|-------------|
| `PyMuPDF (fitz)` | PDF text extraction + rendering pages as images for vision models |
| `python-docx` | Extract text from DOCX files |
| `Pillow` | Image processing (resize, format conversion for vision models) |
| `llama-parse` | Cloud-based document parser (optional, needs API key) |

---

## Parameters & Configuration

All AI-related parameters are in **Invoice Automation Settings**:

### LLM Parameters

| Parameter | Default | What It Controls |
|-----------|---------|-----------------|
| `extraction_llm_provider` | Ollama | Which AI reads invoices |
| `matching_llm_provider` | Anthropic | Which AI helps match items (Stage 8) |
| `json_retry_count` | 3 | How many times to retry if LLM returns bad JSON |
| `ollama_model` | qwen2.5vl:7b | Which Ollama model to use |
| `openai_model` | gpt-4o | Which OpenAI model to use |
| `anthropic_model` | claude-sonnet-4-20250514 | Which Anthropic model to use |
| `gemini_model` | gemini-2.0-flash | Which Gemini model to use |
| `ollama_timeout_seconds` | 120 | How long to wait for Ollama response |
| `enable_llm_matching` | Yes | Whether to use LLM as matching fallback |
| `llm_max_candidates` | 10 | How many candidate items to send to LLM |
| `llm_max_corrections_context` | 5 | How many past corrections to include in LLM prompt |

### Embedding Parameters

| Parameter | Default | What It Controls |
|-----------|---------|-----------------|
| `embedding_model_name` | sentence-transformers/all-MiniLM-L6-v2 | Which embedding model to use |
| `embedding_similarity_threshold` | 0.85 | Cosine similarity above which a match is confident |
| `embedding_review_threshold` | 0.65 | Cosine similarity above which a match is possible but needs review |
| `human_correction_weight_boost` | 1.1 | Multiplier for human-corrected embeddings (10% boost) |
| `agreement_confidence_boost` | 10 | Bonus percentage points when both indexes agree |

### Matching Thresholds

| Parameter | Default | What It Controls |
|-----------|---------|-----------------|
| `auto_create_threshold` | 90% | Minimum confidence to auto-create Purchase Invoice |
| `review_threshold` | 60% | Minimum confidence to route to Review Queue (below = Manual Entry) |
| `fuzzy_match_threshold` | 85 | Fuzzy score above which match is considered high-confidence |

### Hardcoded Parameters (in code, not configurable)

| Parameter | Value | Where | Why Not Configurable |
|-----------|-------|-------|---------------------|
| Max tokens | 4096 | All LLM providers | Sufficient for invoice extraction; larger wastes money |
| Document text limit | 8000 chars | extraction_service.py | Prevents token overflow across all providers |
| Embedding dimensions | 384 | model.py | Determined by the chosen model |
| LLM confidence cap | 88% | llm_matcher.py | LLM matches should always be reviewed by humans |
| Retry delays | 1s, 2s, 4s | llm/base.py | Standard exponential backoff |
| Alias decay rate | 0.005/day | alias_manager.py | Tuned so aliases reach minimum weight at ~100 days |
| Alias minimum weight | 0.5 | alias_manager.py | Even old aliases retain some value |
