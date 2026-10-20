"""utils.py - small formatting helpers."""
import re


def _indian_grouping(int_str):
    """Group a non-negative integer's digit string the Indian way: last 3 digits, then pairs of 2
    (e.g. 1234567 -> '12,34,567'). Revision item 18 - Indian number formatting throughout."""
    if len(int_str) <= 3:
        return int_str
    head, tail = int_str[:-3], int_str[-3:]
    head = re.sub(r"(\d)(?=(\d{2})+(?!\d))", r"\1,", head)
    return f"{head},{tail}"


def fmt_inr_full(x):
    """Full Indian-grouped rupee figure, e.g. Rs 5,00,000 / Rs 12,50,000 / Rs 1,25,00,000 - for
    tables, inputs and anywhere the exact figure (not a L/Cr abbreviation) should be shown."""
    if x is None:
        return "-"
    x = float(x)
    sign = "-" if x < 0 else ""
    return f"{sign}Rs {_indian_grouping(f'{abs(x):.0f}')}"


def fmt_inr(x):
    """Compact Indian rupee figure for cards/metrics: Rs 5L, Rs 12.5L, Rs 1.25Cr. Falls back to the
    full grouped figure (fmt_inr_full) below Rs 1 lakh, where an L/Cr abbreviation reads worse than
    the plain amount (e.g. 'Rs 45,000', not 'Rs 0.45L')."""
    if x is None:
        return "-"
    x = float(x)
    sign = "-" if x < 0 else ""
    ax = abs(x)
    if ax >= 1e7:
        return f"{sign}Rs {ax / 1e7:.2f}Cr"
    if ax >= 1e5:
        return f"{sign}Rs {ax / 1e5:.2f}L"
    return fmt_inr_full(x)


def pct(x, digits=0):
    return "-" if x is None else f"{x * 100:.{digits}f}%"
