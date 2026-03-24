# Deployment & Production Guide

## Prerequisites

### System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.11+ | 3.12 |
| Node.js | 18+ | 20 LTS |
| Frappe | v15+ | Latest v15 |
| ERPNext | v15+ | Latest v15 |
| MariaDB | 10.6+ | 10.11 |
| Redis | 6+ | 7 |
| RAM | 2 GB | 4 GB (8 GB if using Ollama locally) |
| Disk | 1 GB for app | + space for uploaded invoices |

### System Packages

```bash
# Required for DOC file processing (optional — only if you process .doc files)
sudo apt install libreoffice    # Ubuntu/Debian
brew install libreoffice        # macOS

# Required for PDF rendering (scanned PDF fallback)
# PyMuPDF is installed as a Python dependency
```

### Python Dependencies

Installed automatically with the app. Key packages:

| Package | Purpose |
|---------|---------|
| `thefuzz` | Fuzzy string matching (Stage 5: Fuzzy) |
| `sentence-transformers` | Embedding model for semantic search (Stage 7: Embedding) |
| `numpy` | In-memory vector index |
| `pydantic` | Schema validation for extracted data |
| `PyMuPDF (fitz)` | PDF text extraction and page rendering |
| `python-docx` | DOCX file parsing |
| `httpx` | HTTP client for Ollama API |

Provider-specific (install only what you use):

| Package | When Needed |
|---------|-------------|
| `openai` | If using OpenAI as LLM provider |
| `anthropic` | If using Anthropic as LLM provider |
| `google-genai` | If using Google Gemini as LLM provider |

---

## Production Checklist

### Before Going Live

- [ ] **Set `app_env` to `production`** in Invoice Automation Settings
- [ ] **Set `log_level` to `WARNING`** (reduce noise; use `INFO` or `DEBUG` only for troubleshooting)
- [ ] **Configure LLM providers** with production API keys
- [ ] **Disable `Enable Auto Create`** initially — let reviewers validate matches for the first few weeks
- [ ] **Set appropriate thresholds** — defaults (90% auto-create, 60% review) are conservative and good for production
- [ ] **Run initial index build** (happens automatically on install, but verify):
  ```bash
  bench --site {site} execute invoice_automation.utils.redis_index.rebuild_all
  bench --site {site} execute invoice_automation.embeddings.index_builder.build_full_index
  ```
- [ ] **Backfill Supplier Item Catalog** from existing Purchase Invoices:
  ```bash
  bench --site {site} execute invoice_automation.invoice_automation.doctype.supplier_item_catalog.supplier_item_catalog.backfill_catalog
  ```
- [ ] **Enable scheduler** for background jobs:
  ```bash
  bench enable-scheduler
  ```
- [ ] **Verify health**:
  ```bash
  bench --site {site} execute invoice_automation.api.endpoints.health_check
  ```
- [ ] **Assign roles** to users (see [Permissions Guide](PERMISSIONS.md))

### Scheduled Jobs (Automatic)

These run automatically once the scheduler is enabled:

| Schedule | Job | Purpose |
|----------|-----|---------|
| Daily | Redis index rebuild | Safety net — ensures indexes stay in sync |
| Daily | Sync missing embeddings | Catches new Items not yet embedded |
| Daily | Alias decay weights | Recalculates alias confidence decay |
| Weekly | Resolve stale conflicts | Auto-resolves correction conflicts >30 days old |

### Workers

Invoice processing uses Frappe's background workers. For production:

```bash
# Check current worker count
bench config workers

# Increase workers for faster processing (adjust based on server capacity)
bench config workers 4
```

Extraction and matching run in the `default` queue. Embedding generation uses the `default` queue with 120-second timeout. Full index builds use the `long` queue with 1-hour timeout.

---

## Monitoring

### Health Check Endpoint

```bash
curl -H "Authorization: token api_key:api_secret" \
  https://your-site/api/method/invoice_automation.api.endpoints.health_check
```

Returns status of:
- Extraction LLM provider (connected? model available?)
- Matching LLM provider
- Redis (connected? index count?)
- Embedding index (entry count?)
- Queue (pending/processing counts?)

### Key Metrics to Watch

| Metric | Where to Find | Concern If |
|--------|--------------|-----------|
| Pending queue count | `health_check` response | Growing steadily (workers not keeping up) |
| Failed extractions | Invoice Processing Queue list, filter `extraction_status = Failed` | >5% failure rate |
| Auto-create rate | `get_system_stats` endpoint | Dropping (model quality issue or threshold too high) |
| Top corrected items | `get_system_stats` endpoint | Same items corrected repeatedly (alias not working) |
| Redis index count | Invoice Automation Settings | Suddenly drops to 0 (Redis restart without rebuild) |

### Log Analysis

```bash
# View extraction errors
bench --site {site} execute frappe.client.get_list \
  --args '{"doctype": "Error Log", "filters": {"method": ["like", "%invoice%"]}, "limit": 10}'

# Or check bench logs directly
tail -f logs/worker.log | grep "invoice_automation"
```

---

## Scaling

### For Higher Invoice Volume

| Volume | Recommendation |
|--------|---------------|
| < 50/day | Default setup, 1-2 workers |
| 50-200/day | 4 workers, consider paid LLM provider for speed |
| 200-500/day | 8 workers, OpenAI/Gemini for extraction (faster than Ollama), dedicated Redis |
| 500+/day | Multiple worker servers, consider Qdrant for embedding search (replace NumPy index) |

### Embedding Index Scaling

The default NumPy-based index loads all vectors into RAM. Suitable for up to ~50K items.

For larger catalogs, swap to a vector database:
1. Create `embeddings/qdrant_index.py` implementing `VectorIndexBase`
2. Update `get_index_manager()` factory
3. See the Extension Guide in [Technical Documentation](TECHNICAL.md)

---

## Backup & Recovery

### What to Back Up

| Data | How | Frequency |
|------|-----|-----------|
| MariaDB database | `bench backup` | Daily (standard Frappe backup) |
| Uploaded files | Include `/sites/{site}/private/files/` in backup | Daily |
| Redis indexes | No separate backup needed — rebuilt from DB daily | N/A |
| Embedding index | No separate backup needed — rebuilt from Embedding Index DocType | N/A |

### Recovery After Data Loss

If Redis is lost (restart without persistence):
```bash
bench --site {site} execute invoice_automation.utils.redis_index.rebuild_all
```

If the embedding in-memory index is stale (worker restart):
```bash
bench --site {site} execute invoice_automation.embeddings.index_builder.build_full_index
```

Both are safe to run at any time — they rebuild from the database.

---

## Upgrading

```bash
cd apps/invoice_automation
git pull origin main
cd ../..
bench --site {site} migrate
bench build
bench restart
```

`bench migrate` automatically:
- Runs database schema migrations
- Rebuilds Redis indexes
- Seeds any new Matching Strategy records
