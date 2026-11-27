"""Universal date parser to ISO 8601."""

from typing import Optional

from dateutil import parser as date_parser


def parse_date(raw_text: str) -> Optional[str]:
    """Parses various date strings into ISO 8601 UTC format.

    Examples:
        'Nov 23, 2026' -> '2026-11-23T00:00:00'
        '2026-11-23T10:15:30Z' -> '2026-11-23T10:15:30'
    """
    if not raw_text:
        return None

    try:
        dt = date_parser.parse(raw_text)
        return dt.isoformat()
    except Exception:
        return None
