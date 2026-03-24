# Frappe Basics for Python Developers

If you know Python but have never used Frappe or ERPNext, this page explains the framework concepts you need to understand this project. Everything here maps to familiar Python/web patterns.

---

## What is Frappe?

Frappe is a full-stack Python web framework. Think of it as **Django + Django REST Framework + Django Admin + Celery + Redis caching** all bundled together. The key difference: instead of writing models, views, serializers, and admin configs separately, Frappe uses **DocTypes** — JSON files that define the database schema, form UI, permissions, and API all at once.

ERPNext is a large application built on Frappe that provides business modules (Accounting, Inventory, HR, etc.). Our Invoice Automation app extends ERPNext by adding automated invoice processing.

---

## How Frappe Apps Map to Python Concepts

| Python/Django Concept | Frappe Equivalent | Where in This Project |
|---|---|---|
| Django Model (class in `models.py`) | **DocType** (JSON file + optional Python controller) | `invoice_automation/doctype/invoice_processing_queue/invoice_processing_queue.json` |
| Database table | Auto-created from DocType JSON | `tabInvoice Processing Queue` in MariaDB |
| Model instance | **Document** (a single record, called "doc") | `frappe.get_doc("Invoice Processing Queue", "INV-Q-00001")` |
| Django Admin | **Desk** (auto-generated forms from DocType definition) | No code needed — Frappe auto-generates the form |
| Django REST API view | **Whitelisted function** (`@frappe.whitelist()`) | `api/endpoints.py` — each function becomes an HTTP endpoint |
| `settings.py` | **Single DocType** (one-record doctype for config) | `Invoice Automation Settings` |
| Foreign key field | **Link field** (`fieldtype: "Link"`) | `matched_supplier` links to `Supplier` doctype |
| Django signal | **Doc Event hook** (in `hooks.py`) | `on_update`, `after_insert`, `on_trash` handlers |
| Celery task | **`frappe.enqueue()`** (Redis Queue job) | `enqueue_if_scheduler_active(...)` in correction_handler.py |
| Cron job | **Scheduler event** (in `hooks.py`) | `scheduler_events.daily`, `scheduler_events.weekly` |
| Django management command | **`bench execute`** | `bench --site mysite execute invoice_automation.utils.redis_index.rebuild_all` |
| `requirements.txt` | **`pyproject.toml`** | Lists `thefuzz`, `sentence-transformers`, `pydantic`, etc. |
| Database migration | **`bench migrate`** | Reads DocType JSON, creates/alters tables automatically |

---

## The DocType: Frappe's Central Concept

A DocType is defined by a **JSON file** that describes:
- Table name and fields (like a Django model)
- Form layout (like Django admin `fieldsets`)
- Permissions (like Django `has_perm`)
- Naming rule (like Django `__str__` or `get_absolute_url`)

### Example: Mapping Alias DocType

**File**: `invoice_automation/doctype/mapping_alias/mapping_alias.json`

```json
{
  "name": "Mapping Alias",
  "autoname": "hash",           ← How records are named (hash = random ID)
  "fields": [
    {
      "fieldname": "source_doctype",
      "fieldtype": "Select",      ← Dropdown
      "options": "Supplier\nItem\nPurchase Taxes and Charges Template\nCost Center",
      "reqd": 1                    ← Required field
    },
    {
      "fieldname": "canonical_name",
      "fieldtype": "Dynamic Link",  ← Foreign key where target table varies
      "options": "source_doctype"   ← Target table determined by source_doctype field
    },
    {
      "fieldname": "composite_key",
      "fieldtype": "Data",
      "unique": 1,                  ← Unique constraint
      "read_only": 1
    }
  ],
  "permissions": [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
  ]
}
```

**What this creates automatically:**
- A MariaDB table `tabMapping Alias` with columns for each field
- A form at `/app/mapping-alias/{name}` in the desk
- A list view at `/app/mapping-alias`
- REST API endpoints: `GET/POST/PUT/DELETE /api/resource/Mapping Alias`
- Permission checks on every access

### The Python Controller (Optional)

Each DocType can have a Python file with the same name:

**File**: `invoice_automation/doctype/mapping_alias/mapping_alias.py`

```python
from frappe.model.document import Document

class MappingAlias(Document):
    pass  # No custom logic — the JSON definition is enough
```

If you need custom behavior (validation, computed fields, event hooks), add methods:

```python
class MappingAlias(Document):
    def validate(self):
        """Called before every save — like Django's clean()."""
        if not self.normalized_text:
            self.normalized_text = normalize_text(self.raw_text)

    def before_insert(self):
        """Called before first save only."""
        ...

    def on_update(self):
        """Called after every save — like Django's post_save signal."""
        ...
```

---

## How API Endpoints Work

In Django, you'd write a view function and register it in `urls.py`. In Frappe, you write a function and decorate it:

```python
# api/endpoints.py

@frappe.whitelist()
def parse_invoice(file_url, extracted_json=None):
    """This becomes callable at:
    POST /api/method/invoice_automation.api.endpoints.parse_invoice
    """
    # frappe.form_dict contains the request parameters
    # Return value is JSON-serialized as the response
    return {"queue_name": "INV-Q-00001", "status": "queued"}
```

**Key differences from Django views:**
- No URL routing — the function's dotted path IS the URL
- No request/response objects — use `frappe.form_dict` for input, return dicts for output
- Permissions checked via `frappe.has_permission()` or manual role checks
- `@frappe.whitelist()` = "this is a public API endpoint"
- `@frappe.whitelist(allow_guest=True)` = "no login required"

---

## How the Database Works

Frappe uses MariaDB (MySQL-compatible). You rarely write raw SQL.

```python
# Get a single record (like Django's Model.objects.get())
doc = frappe.get_doc("Supplier", "ACME Corp")
print(doc.supplier_name)  # Access fields as attributes

# Query records (like Django's Model.objects.filter())
suppliers = frappe.get_all("Supplier",
    filters={"supplier_group": "Hardware"},
    fields=["name", "supplier_name", "tax_id"],
    order_by="creation desc",
    limit=10,
)

# Get a single field value
name = frappe.db.get_value("Supplier", {"tax_id": "27AAACT2727Q1ZW"}, "name")

# Update a field directly (without loading the full document)
frappe.db.set_value("Mapping Alias", "MA-00001", "correction_count", 5)

# Create a new record
doc = frappe.new_doc("Mapping Alias")
doc.source_doctype = "Item"
doc.raw_text = "Steel Pipe 2mm"
doc.canonical_name = "STEEL-PIPE-2MM"
doc.insert(ignore_permissions=True)

# Commit transaction (Frappe auto-commits at end of request, but background jobs need explicit commits)
frappe.db.commit()
```

---

## How Background Jobs Work

Frappe uses Redis Queue (RQ) for background processing. Like Celery, but simpler.

```python
# Enqueue a function to run in the background
frappe.enqueue(
    "invoice_automation.memory.correction_handler._update_embedding_index",
    raw_text="Steel Pipe 2mm",
    corrected_item="STEEL-PIPE-2MM",
    queue="default",       # Which queue (default, short, long)
    timeout=120,           # Seconds before job times out
)
```

**Important**: background jobs run in separate worker processes. They don't share the web request's context. Always pass data as arguments, never rely on request-scoped state.

Workers must be running: `bench start` starts them in development. In production, they run as systemd services.

---

## How Hooks Work

`hooks.py` is the central configuration file for a Frappe app. It defines what runs when.

```python
# hooks.py

# Run after install
after_install = "invoice_automation.setup.after_install"

# When a Supplier document is saved, update our Redis index
doc_events = {
    "Supplier": {
        "on_update": ["invoice_automation.utils.redis_index.update_supplier_index"],
    },
}

# Run daily at midnight
scheduler_events = {
    "daily": ["invoice_automation.utils.redis_index.rebuild_all"],
}

# Include CSS in every page
app_include_css = "/assets/invoice_automation/css/invoice_review.css"
```

Doc event handlers receive the document and method name:

```python
def update_supplier_index(doc, method=None):
    """Called when any Supplier is saved.
    doc = the Supplier document that was saved
    method = "on_update" (the event name)
    """
    # Update Redis index for this supplier
    ...
```

---

## How the JavaScript Side Works

Frappe's desk forms use client-side JavaScript. Each DocType can have a `.js` file:

**File**: `invoice_processing_queue.js`

```javascript
frappe.ui.form.on("Invoice Processing Queue", {
    refresh: function(frm) {
        // frm = the form object
        // frm.doc = the current document's data

        // Add a button to the form
        frm.add_custom_button(__("Do Something"), function() {
            // Call a Python API endpoint from JavaScript
            frappe.call({
                method: "invoice_automation.api.endpoints.some_function",
                args: { queue_name: frm.doc.name },
                callback: function(r) {
                    // r.message = the return value from Python
                    console.log(r.message);
                },
            });
        });
    },
});
```

**Key patterns:**
- `frappe.call()` = AJAX call to a whitelisted Python function
- `frappe.ui.Dialog` = modal dialog (used for the review dialog)
- `frappe.ui.form.make_control()` = render a form field dynamically in HTML
- `__("text")` = translation wrapper (like Django's `gettext`)
- `frappe.show_alert()` = toast notification
- `frappe.msgprint()` = alert/message box

---

## File & Directory Structure Explained

```
frappe-bench/                    ← The "bench" — top-level directory
├── apps/
│   ├── frappe/                  ← The framework itself
│   ├── erpnext/                 ← The ERP application
│   └── invoice_automation/      ← OUR APP
│       ├── invoice_automation/  ← Python package (same name as app)
│       │   ├── hooks.py         ← App configuration (events, scheduler, install)
│       │   ├── api/             ← API endpoints (whitelisted functions)
│       │   ├── invoice_automation/  ← DocType definitions
│       │   │   └── doctype/
│       │   │       ├── invoice_processing_queue/
│       │   │       │   ├── invoice_processing_queue.json  ← Schema
│       │   │       │   ├── invoice_processing_queue.py    ← Controller
│       │   │       │   └── invoice_processing_queue.js    ← Client script
│       │   │       └── ...
│       │   ├── public/          ← Static assets (CSS, images)
│       │   └── ...              ← Business logic modules
│       ├── pyproject.toml       ← Python dependencies
│       └── setup.py             ← Install/migrate hooks
├── sites/
│   └── mysite.localhost/        ← Site data
│       ├── site_config.json     ← Database credentials, Redis URL
│       └── private/files/       ← Uploaded files (invoices)
├── env/                         ← Python virtualenv
└── logs/                        ← Worker and web server logs
```

**Why two `invoice_automation` directories?** The outer one is the app (git repo). The inner one is the Python package. This is Frappe convention — `bench get-app` clones the repo, and Python imports use the inner package.

---

## Common Frappe Patterns in This Codebase

### Pattern 1: Reading settings

```python
# Get a setting value from the Single DocType
threshold = frappe.db.get_single_value("Invoice Automation Settings", "auto_create_threshold")

# Or load the full settings document
settings = frappe.get_single("Invoice Automation Settings")
print(settings.extraction_llm_provider)
```

### Pattern 2: Redis caching

```python
# Store a value in Redis
frappe.cache().set_value("invoice_automation:alias:ACME:steel:Item", "STEEL-PIPE-2MM")

# Retrieve it
value = frappe.cache().get_value("invoice_automation:alias:ACME:steel:Item")
```

### Pattern 3: Error logging

```python
# Log to Frappe's Error Log doctype (visible in desk)
frappe.log_error("Something went wrong", "Invoice Extraction Error")

# Throw an error that the user sees
frappe.throw("Supplier not found")
```

### Pattern 4: Permission checking

```python
@frappe.whitelist()
def my_function():
    # Check if the current user has one of these roles
    if not frappe.has_permission("Invoice Processing Queue", "write"):
        frappe.throw("Insufficient permissions")
    # Or check roles directly
    roles = frappe.get_roles()
    if "Accounts Manager" not in roles:
        frappe.throw("Only Accounts Managers can do this")
```

### Pattern 5: Child table access

```python
# Get a document with its child table rows
queue = frappe.get_doc("Invoice Processing Queue", "INV-Q-00001")

# Iterate over child table (line items)
for line_item in queue.line_items:  # "line_items" is the child table fieldname
    print(line_item.extracted_description)
    print(line_item.matched_item)
    print(line_item.match_confidence)

# Add a new row to a child table
queue.append("line_items", {
    "line_number": 1,
    "extracted_description": "Steel Pipe",
    "extracted_qty": "5",
})
queue.save()
```

---

## What Happens When You Run `bench migrate`?

When DocType JSON files change (new fields, renamed fields, etc.), `bench migrate`:

1. Reads every DocType JSON file in the app
2. Compares with the current database schema
3. Runs `ALTER TABLE` to add/modify columns
4. Does NOT delete columns (safe by default)
5. Runs `after_migrate` hook from `hooks.py` — in our case, rebuilds Redis indexes and seeds Matching Strategy records

**You never write migration files.** Just change the DocType JSON and run `bench migrate`.

---

## Quick Command Reference

| What You Want | Command |
|---|---|
| Start dev server | `bench start` |
| Run a Python function | `bench --site mysite execute module.path.function` |
| Open Python shell with Frappe context | `bench --site mysite console` |
| Create a new site | `bench new-site mysite` |
| Install an app on a site | `bench --site mysite install-app invoice_automation` |
| Run database migrations | `bench --site mysite migrate` |
| Run tests | `bench --site mysite run-tests --app invoice_automation` |
| Rebuild static assets | `bench build` |
| View logs | `tail -f logs/worker.log` |
| Enable background jobs | `bench enable-scheduler` |
| Clear Redis cache | `bench --site mysite clear-cache` |
