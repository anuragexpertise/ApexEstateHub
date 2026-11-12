# app/utils/__init__.py

from datetime import date, datetime, timedelta, timezone

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Current time in IST."""
    return datetime.now(tz=IST)


def today_ist() -> date:
    """Current date in IST."""
    return now_ist().date()


def format_date_ist(d: date | datetime | None = None) -> str:
    """Format a date/datetime as dd/mm/yyyy in IST."""
    if d is None:
        d = today_ist()
    if isinstance(d, datetime):
        d = d.astimezone(IST).date()
    return d.strftime("%d/%m/%Y")


def parse_date_ddmmyyyy(s: str) -> date:
    """Parse a dd/mm/yyyy string into a date."""
    return datetime.strptime(s, "%d/%m/%Y").date()  # noqa: DTZ007


def format_datetime_ist(dt: datetime | None = None) -> str:
    """Format a datetime as dd/mm/yyyy HH:MM in IST."""
    if dt is None:
        dt = now_ist()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime("%d/%m/%Y %H:%M")
