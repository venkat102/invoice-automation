"""Text normalization utilities for invoice matching."""

import re
import string


COMMON_SUFFIXES = [
    "PRIVATE LIMITED",
    "PRIVATE",
    "LIMITED",
    "INCORPORATED",
    "CORPORATION",
    "CORP",
    "PVT",
    "LTD",
    "INC",
    "LLC",
]

UNIT_SUFFIXES = [
    "KG", "KGS", "KILOGRAM", "KILOGRAMS",
    "GM", "GMS", "GRAM", "GRAMS",
    "LTR", "LTRS", "LITER", "LITERS", "LITRE", "LITRES",
    "ML", "MLS", "MILLILITER", "MILLILITERS",
    "PCS", "PIECES", "PIECE",
    "NOS", "NUMBERS",
    "MTR", "MTRS", "METER", "METERS", "METRE", "METRES",
    "MM", "CM", "FT", "FEET", "INCH", "INCHES",
    "BOX", "BOXES", "PKT", "PACKET", "PACKETS",
    "BAG", "BAGS", "ROLL", "ROLLS",
    "SET", "SETS", "PAIR", "PAIRS",
    "BTL", "BOTTLE", "BOTTLES",
    "CAN", "CANS", "TIN", "TINS",
    "CARTON", "CARTONS", "CASE", "CASES",
    "DOZEN", "BUNDLE", "BUNDLES",
    "PACK", "PACKS",
]

PACKAGING_PATTERNS = [
    r"\b\d+\s*[xX]\s*\d+\s*(?:ML|GM|KG|LTR|PCS)?\b",
    r"\b\d+\s*(?:ML|GM|KG|LTR|PCS)\b",
    r"\bPACK\s+OF\s+\d+\b",
    r"\b\d+\s*(?:PACK|PKT|BOX|BTL|CAN)\b",
]


def normalize_text(text: str) -> str:
    """Uppercase, strip punctuation, remove common suffixes, trim and collapse whitespace."""
    if not text:
        return ""

    result = text.upper().strip()

    # Remove punctuation
    result = result.translate(str.maketrans("", "", string.punctuation))

    # Remove common suffixes (longest first to avoid partial matches)
    for suffix in COMMON_SUFFIXES:
        pattern = r"\b" + re.escape(suffix) + r"\b"
        result = re.sub(pattern, "", result)

    # Collapse multiple spaces and trim
    result = re.sub(r"\s+", " ", result).strip()

    return result


def normalize_tax_id(tax_id: str) -> str:
    """Strip spaces and special chars, uppercase. Works for any tax ID format (GSTIN, VAT, TIN, etc.)."""
    if not tax_id:
        return ""

    return re.sub(r"[^A-Za-z0-9]", "", tax_id).upper()


def normalize_gstin(gstin: str) -> str:
    """Strip spaces and special chars, uppercase, validate length 15 (Indian GSTIN)."""
    if not gstin:
        return ""

    result = re.sub(r"[^A-Za-z0-9]", "", gstin).upper()

    if len(result) != 15:
        return ""

    return result


def is_valid_gstin(tax_id: str) -> bool:
    """Check if a tax ID looks like a valid Indian GSTIN (15 alphanumeric chars)."""
    normalized = normalize_tax_id(tax_id)
    return len(normalized) == 15 and bool(re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z]$", normalized))


def extract_pan_from_gstin(gstin: str) -> str | None:
    """Extract PAN from GSTIN (characters at index 2-12, i.e. 3rd to 12th char)."""
    normalized = normalize_gstin(gstin)
    if not normalized:
        return None

    return normalized[2:12]


def normalize_item_text(text: str) -> str:
    """Same as normalize_text but also remove common unit suffixes and packaging descriptions."""
    if not text:
        return ""

    result = normalize_text(text)

    # Remove packaging descriptions
    for pattern in PACKAGING_PATTERNS:
        result = re.sub(pattern, "", result)

    # Remove unit suffixes at word boundaries
    for suffix in UNIT_SUFFIXES:
        pattern = r"\b" + re.escape(suffix) + r"\b"
        result = re.sub(pattern, "", result)

    # Collapse multiple spaces and trim again
    result = re.sub(r"\s+", " ", result).strip()

    return result
