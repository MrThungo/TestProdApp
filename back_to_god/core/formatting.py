from __future__ import annotations

from datetime import date, datetime


def pretty_date(value: str | None) -> str:
    if not value:
        return "Not yet"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        return value


def chat_timestamp(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return value


def age_from_dob(value: str | None) -> str:
    if not value:
        return "Not added"
    try:
        born = date.fromisoformat(value[:10])
    except ValueError:
        return "Not added"
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return f"{age} years" if age >= 0 else "Not added"


def bits_size(value: int | str | None) -> str:
    try:
        bits = int(value or 0) * 8
    except (TypeError, ValueError):
        bits = 0
    return f"{bits:,} bits"
