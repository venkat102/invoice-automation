# Permissions & Roles

## Required Roles

Invoice Automation uses standard ERPNext roles. No custom roles are created.

### Role Matrix

| Action | Accounts User | Accounts Manager | System Manager |
|--------|:---:|:---:|:---:|
| Upload invoices (parse_invoice) | Yes | Yes | Yes |
| View queue records | Yes | Yes | Yes |
| Review & create Purchase Invoice | Yes | Yes | Yes |
| Make corrections (save_corrections) | Yes | Yes | Yes |
| Reject invoices | Yes | Yes | Yes |
| View match results | Yes | Yes | Yes |
| Rebuild indexes | No | Yes | Yes |
| View system stats | No | Yes | Yes |
| View/edit Invoice Automation Settings | No | No | Yes |
| Manage Matching Strategies | No | No | Yes |
| View Mapping Aliases | Yes (read) | Yes (read/write) | Yes (all) |
| View Mapping Correction Logs | Yes (read) | Yes (read) | Yes (all) |
| View Supplier Item Catalog | Yes (read) | Yes (read) | Yes (all) |
| View/edit Vendor SKU Mappings | Yes (read/write) | Yes (read/write) | Yes (all) |

### How roles are checked

API endpoints check roles at the top of each function:

```python
INVOICE_ROLES = ("Accounts Manager", "Accounts User", "System Manager")
ADMIN_ROLES = ("Accounts Manager", "System Manager")
```

- **Invoice operations** (upload, review, correct, reject): any role in `INVOICE_ROLES`
- **Admin operations** (rebuild indexes, system stats, config): any role in `ADMIN_ROLES`
- **Settings**: controlled by DocType-level permissions (System Manager only)

### Assigning Roles

To give a user access to Invoice Automation:

1. Go to the user's record in **User** list
2. In the **Roles** section, add one of:
   - **Accounts User** — for reviewers who process invoices daily
   - **Accounts Manager** — for supervisors who also manage indexes and view stats
   - **System Manager** — for admins who configure settings and strategies

These are standard ERPNext roles — if the user already has one of these for other ERPNext functions, they automatically have access to Invoice Automation.

### DocType-Level Permissions

Each DocType has its own permission rules:

| DocType | Accounts User | Accounts Manager | System Manager |
|---------|:---:|:---:|:---:|
| Invoice Processing Queue | Read, Write, Create | Read, Write, Create, Delete | All |
| Invoice Automation Settings | — | — | All |
| Matching Strategy | — | — | All |
| Mapping Alias | Read | Read, Write, Create | All |
| Mapping Correction Log | Read | Read | All |
| Supplier Item Catalog | Read | Read | All |
| Vendor SKU Mapping | Read, Write | Read, Write | All |
| Embedding Index | — | — | All |
