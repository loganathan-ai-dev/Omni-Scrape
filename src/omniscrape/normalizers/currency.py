"""Multi-currency price normalizer."""

import re
from typing import Optional, Tuple

# Longest symbols first so "A$" wins over "$". Letter codes only match as whole words.
_SYMBOLS: list[tuple[str, str]] = sorted([
    ("US$", "USD"), ("A$", "AUD"), ("AU$", "AUD"), ("C$", "CAD"), ("CA$", "CAD"), ("NZ$", "NZD"), ("HK$", "HKD"),
    ("S$", "SGD"), ("R$", "BRL"), ("MX$", "MXN"), ("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("¥", "JPY"),
    ("₹", "INR"), ("₩", "KRW"), ("₽", "RUB"), ("₺", "TRY"), ("₪", "ILS"), ("₫", "VND"), ("฿", "THB"), ("₱", "PHP"),
    ("zł", "PLN"), ("Kč", "CZK"),
], key=lambda kv: -len(kv[0]))
_CODES = {"USD", "EUR", "GBP", "JPY", "INR", "AUD", "CAD", "CHF", "SEK", "NOK", "DKK", "PLN", "BRL", "MXN", "CNY",
          "SGD", "HKD", "NZD", "ZAR", "AED", "SAR", "KRW", "TRY", "CZK", "HUF", "ILS", "THB", "PHP", "IDR", "MYR"}
_CODE_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(sorted(_CODES)) + r"|Rs\.?|RS\.?)(?![A-Za-z])")
_NUMBER_RE = re.compile(r"\d[\d.,\s  ']*\d|\d")

# Kept for backward compatibility (lower-case lookup table used by older code).
CURRENCY_SYMBOLS = {sym.lower(): iso for sym, iso in _SYMBOLS} | {"rs": "INR", "inr": "INR", "usd": "USD",
                                                                    "eur": "EUR", "gbp": "GBP", "jpy": "JPY"}


def detect_currency(text: str) -> Optional[str]:
    for sym, iso in _SYMBOLS:
        if sym in text:
            return iso
    m = _CODE_RE.search(text)
    if m:
        code = m.group(1).upper().rstrip(".")
        return "INR" if code == "RS" else code
    return None


def _to_float(raw: str) -> Optional[float]:
    s = re.sub(r"[\s  ']", "", raw)
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        # 1,299 / 12,345,678 / Indian 1,29,999 are thousands; 12,5 or 1,99 are decimals
        if re.fullmatch(r"\d{1,3}(?:,\d{2})*,\d{3}", s):
            s = s.replace(",", "")
        else:
            head, _, tail = s.rpartition(",")
            s = head.replace(",", "") + "." + tail
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")  # 1.299.000 or 1.299 (dot as thousands separator)
    try:
        return float(s)
    except ValueError:
        return None


def parse_money(raw_text: str, default_currency: Optional[str] = None) -> Tuple[Optional[float], Optional[str]]:
    """Parse a localized price into (amount, ISO currency). Currency is None when not shown.

    '₹1,29,999' -> (129999.0, 'INR');  '1.299,00 €' -> (1299.0, 'EUR');  'A$12.50' -> (12.5, 'AUD')
    """
    if raw_text is None:
        return None, default_currency
    text = str(raw_text).strip()
    if not text:
        return None, default_currency
    currency = detect_currency(text) or default_currency
    m = _NUMBER_RE.search(text)
    if not m:
        return None, currency
    amount = _to_float(m.group(0))
    return (round(amount, 2) if amount is not None else None), currency


def parse_price(raw_text: str, default_currency: str = "USD") -> Tuple[Optional[float], str]:
    """Parse arbitrary localized price strings into (amount, currency_iso).

    Examples:
        '₹1,299.00' -> (1299.0, 'INR')
        '$49.99' -> (49.99, 'USD')
        '1.299,00 €' -> (1299.0, 'EUR')
        'FREE' -> (0.0, 'USD')
    """
    if not raw_text:
        return None, default_currency
    low = str(raw_text).lower()
    if re.search(r"\b(free|gratis|gratuit|kostenlos)\b", low):
        return 0.0, detect_currency(str(raw_text)) or default_currency
    amount, currency = parse_money(raw_text, default_currency)
    return amount, currency or default_currency
