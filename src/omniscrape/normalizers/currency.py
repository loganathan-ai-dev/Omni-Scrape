"""Multi-currency price normalizer."""

import re
from typing import Optional, Tuple

CURRENCY_SYMBOLS = {
    "₹": "INR",
    "rs": "INR",
    "inr": "INR",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "¥": "JPY",
    "jpy": "JPY",
    "a$": "AUD",
    "c$": "CAD",
}


def parse_price(raw_text: str, default_currency: str = "USD") -> Tuple[Optional[float], str]:
    """Parses arbitrary localized price strings into (amount, currency_iso).

    Examples:
        '₹1,299.00' -> (1299.0, 'INR')
        '$49.99' -> (49.99, 'USD')
        '1.299,00 €' -> (1299.0, 'EUR')
        'FREE' -> (0.0, 'USD')
    """
    if not raw_text:
        return None, default_currency

    text = raw_text.strip().lower()

    if "free" in text or "gratis" in text:
        return 0.0, default_currency

    # Detect currency symbol
    currency = default_currency
    for sym, iso in CURRENCY_SYMBOLS.items():
        if sym in text:
            currency = iso
            break

    # Strip currency letters/symbols
    cleaned = re.sub(r"[^\d.,]", "", text).strip()
    if not cleaned:
        return None, currency

    # Handle European decimal convention (1.299,00 -> 1299.00)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned and len(cleaned.split(",")[-1]) <= 2:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")

    try:
        val = float(cleaned)
        return round(val, 2), currency
    except ValueError:
        return None, currency
