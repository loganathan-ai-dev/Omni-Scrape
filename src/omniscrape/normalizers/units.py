"""Weight, volume, and quantity measurement normalizer."""

import re
from typing import Optional, Tuple


def parse_unit(raw_text: str) -> Tuple[Optional[float], str]:
    """Normalizes product weights, volumes, and count strings.

    Examples:
        '500 g' -> (500.0, 'g')
        '1.5 kg' -> (1500.0, 'g')
        '200 ml' -> (200.0, 'ml')
        '1 L' -> (1000.0, 'ml')
        'Pack of 6' -> (6.0, 'pcs')
        '250 g x 2' -> (500.0, 'g')
    """
    if not raw_text:
        return None, ""

    text = raw_text.strip().lower()

    # Pattern: Pack of 6 / Box of 12
    pack_match = re.search(r"(?:pack|box|set|case)\s+of\s+(\d+(?:\.\d+)?)", text)
    if pack_match:
        return round(float(pack_match.group(1)), 2), "pcs"

    # Pattern: 250 g x 2 or 2 x 250 g
    multi_match = re.search(r"(\d+(?:\.\d+)?)\s*([a-z]+)?\s*[xX*]\s*(\d+(?:\.\d+)?)\s*([a-z]+)?", text)
    if multi_match:
        n1, u1, n2, u2 = multi_match.groups()
        unit = u1 or u2 or "pcs"
        val = float(n1) * float(n2)
        if unit == "kg":
            return val * 1000.0, "g"
        if unit == "l":
            return val * 1000.0, "ml"
        return round(val, 2), unit

    # Pattern: 500 g / 1.5 kg / 200 ml / 1 L
    match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|gm|gms|grams|l|ltr|litre|litres|ml|pcs|pc|pack|pieces)", text)
    if match:
        val = float(match.group(1))
        raw_u = match.group(2)
        if raw_u in ("kg",):
            return round(val * 1000.0, 2), "g"
        if raw_u in ("g", "gm", "gms", "grams"):
            return round(val, 2), "g"
        if raw_u in ("l", "ltr", "litre", "litres"):
            return round(val * 1000.0, 2), "ml"
        if raw_u in ("ml",):
            return round(val, 2), "ml"
        return round(val, 2), "pcs"

    return None, ""
