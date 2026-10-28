"""Money arithmetic (Plan v3, task 3.4).

Rounding policy:
  * ledgers and statements: paisa, ROUND_HALF_UP  -> money()
  * TDS (and other tax amounts the law rounds to the rupee): whole rupee, ROUND_HALF_UP -> rupee()
  * nothing in a money path uses a binary float: values from the database arrive as Decimal; text from a form is parsed
    as Decimal; a float is converted through its shortest text form, so 0.1 stays 0.10 and never 0.1000000000000000055.
Totals are summed as Decimal and rounded once, at the end.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAISA = Decimal("0.01")
RUPEE = Decimal("1")


def D(value, default=0) -> Decimal:
    """Any number-like value as a Decimal. None or '' becomes `default`. A bad value raises ValueError (never silently 0)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        value = default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        value = repr(value)                       # shortest text that round-trips: no binary noise
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc


def money(value, default=0) -> Decimal:
    """Rounded to the paisa."""
    return D(value, default).quantize(PAISA, rounding=ROUND_HALF_UP)


def rupee(value, default=0) -> Decimal:
    """Rounded to the whole rupee (TDS)."""
    return D(value, default).quantize(RUPEE, rounding=ROUND_HALF_UP)
