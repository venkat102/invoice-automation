import frappe
from frappe import _


def _is_gstin(tax_id):
    """Check if a tax ID looks like an Indian GSTIN (15 alphanumeric chars starting with 2 digits)."""
    import re
    if not tax_id:
        return False
    cleaned = re.sub(r"[\s\-]", "", tax_id).upper()
    return len(cleaned) == 15 and bool(re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z]$", cleaned))


def match_tax_template(tax_detail, supplier_tax_id=None, company_tax_id=None):
    """Validate tax calculations and match a Purchase Taxes and Charges Template.

    Args:
        tax_detail: dict with keys like ``tax_type`` (e.g. "CGST", "SGST",
            "IGST", "VAT"), ``rate``, ``amount``.
        supplier_tax_id: Supplier's tax identifier (GSTIN, VAT, TIN, etc.).
        company_tax_id: Company's tax identifier.

    Returns:
        dict with ``matched_template``, ``confidence``, ``is_valid``, ``details``.
    """
    tax_type = (tax_detail.get("tax_type") or "").upper()
    rate = float(tax_detail.get("rate") or 0)

    # GST-specific intra/inter-state validation only applies when both IDs are Indian GSTINs
    supplier_state = None
    company_state = None
    is_intra_state = None

    if _is_gstin(supplier_tax_id) and _is_gstin(company_tax_id):
        supplier_state = _extract_state_code(supplier_tax_id)
        company_state = _extract_state_code(company_tax_id)
        is_intra_state = (
            supplier_state is not None
            and company_state is not None
            and supplier_state == company_state
        )

    details = {
        "supplier_state_code": supplier_state,
        "company_state_code": company_state,
        "is_intra_state": is_intra_state,
        "tax_type": tax_type,
        "rate": rate,
    }

    # Validate tax type against interstate/intrastate expectation (GST-specific)
    is_valid = True
    if supplier_state and company_state:
        if is_intra_state and tax_type == "IGST":
            is_valid = False
            details["warning"] = "IGST applied for intra-state transaction"
        elif not is_intra_state and tax_type in ("CGST", "SGST"):
            is_valid = False
            details["warning"] = f"{tax_type} applied for inter-state transaction"

    # Look up a matching template
    matched_template = _find_template(tax_type, rate, is_intra_state)
    confidence = 100 if matched_template else 0

    return {
        "matched_template": matched_template,
        "confidence": confidence,
        "is_valid": is_valid,
        "details": details,
    }


def validate_tax_consistency(taxes, supplier_tax_id=None, company_tax_id=None):
    """Check that the list of taxes is internally consistent.

    Args:
        taxes: list of dicts, each with ``tax_type`` and ``rate``.
        supplier_tax_id: Supplier's tax identifier (GSTIN, VAT, TIN, etc.).
        company_tax_id: Company's tax identifier.

    Returns:
        dict with ``is_valid``, ``errors``, ``details``.
    """
    errors = []
    tax_types = [t.get("tax_type", "").upper() for t in taxes]

    has_igst = "IGST" in tax_types
    has_cgst = "CGST" in tax_types
    has_sgst = "SGST" in tax_types

    # GST-specific mixing checks only when GST tax types are present
    if has_igst and (has_cgst or has_sgst):
        errors.append("Cannot mix IGST with CGST/SGST")

    if has_cgst and has_sgst:
        cgst_rates = [float(t.get("rate") or 0) for t in taxes if t.get("tax_type", "").upper() == "CGST"]
        sgst_rates = [float(t.get("rate") or 0) for t in taxes if t.get("tax_type", "").upper() == "SGST"]
        if cgst_rates and sgst_rates and cgst_rates[0] != sgst_rates[0]:
            errors.append(
                f"CGST rate ({cgst_rates[0]}%) and SGST rate ({sgst_rates[0]}%) must be equal"
            )

    # GSTIN-based state code validation only when both IDs are Indian GSTINs
    supplier_state = None
    company_state = None

    if _is_gstin(supplier_tax_id) and _is_gstin(company_tax_id):
        supplier_state = _extract_state_code(supplier_tax_id)
        company_state = _extract_state_code(company_tax_id)

        if supplier_state and company_state:
            is_intra_state = supplier_state == company_state
            if is_intra_state and has_igst:
                errors.append("IGST should not be used for intra-state transactions")
            if not is_intra_state and (has_cgst or has_sgst):
                errors.append("CGST/SGST should not be used for inter-state transactions")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "details": {
            "supplier_state_code": supplier_state,
            "company_state_code": company_state,
            "tax_types_found": list(set(tax_types)),
        },
    }


def _extract_state_code(gstin):
    """Extract 2-digit state code from a GSTIN string."""
    if gstin and len(gstin) >= 2:
        code = gstin[:2]
        if code.isdigit():
            return code
    return None


def _find_template(tax_type, rate, is_intra_state):
    """Find a Purchase Taxes and Charges Template matching the given criteria."""
    # Try to find a template with matching tax rows
    templates = frappe.get_all(
        "Purchase Taxes and Charges Template",
        filters={"disabled": 0},
        fields=["name"],
    )

    for template in templates:
        taxes = frappe.get_all(
            "Purchase Taxes and Charges",
            filters={"parent": template.name, "parenttype": "Purchase Taxes and Charges Template"},
            fields=["charge_type", "account_head", "rate", "description"],
        )

        for tax_row in taxes:
            description = (tax_row.get("description") or "").upper()
            row_rate = float(tax_row.get("rate") or 0)

            if tax_type in description and abs(row_rate - rate) < 0.01:
                return template.name

    return None
