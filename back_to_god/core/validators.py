from __future__ import annotations

from datetime import date
import re


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match((email or "").strip()))


def only_digits(value: str, limit: int | None = None) -> str:
    digits = "".join(character for character in (value or "") if character.isdigit())
    return digits[:limit] if limit else digits


def luhn_valid(value: str) -> bool:
    total = 0
    reverse_digits = value[::-1]
    for index, character in enumerate(reverse_digits):
        digit = int(character)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def date_from_sa_id(id_number: str) -> str | None:
    digits = only_digits(id_number, 13)
    if len(digits) != 13 or not luhn_valid(digits):
        return None

    yy = int(digits[:2])
    mm = int(digits[2:4])
    dd = int(digits[4:6])
    current_year = date.today().year % 100
    century = 1900 if yy > current_year else 2000

    try:
        return date(century + yy, mm, dd).isoformat()
    except ValueError:
        return None


def validate_sa_id(id_number: str, required: bool = False) -> tuple[bool, str, str]:
    digits = only_digits(id_number, 13)
    if not digits and not required:
        return True, "", ""
    if len(digits) != 13:
        return False, digits, "South African ID number must be 13 digits."

    date_of_birth = date_from_sa_id(digits)
    if not date_of_birth:
        return False, digits, "South African ID number is not valid."
    return True, digits, date_of_birth


def validate_password_strength(password: str) -> list[str]:
    errors = []
    if len(password or "") < 8:
        errors.append("Password must be at least 8 characters.")
    if not re.search(r"[A-Z]", password or ""):
        errors.append("Password must include an uppercase letter.")
    if not re.search(r"[a-z]", password or ""):
        errors.append("Password must include a lowercase letter.")
    if not re.search(r"\d", password or ""):
        errors.append("Password must include a number.")
    if not re.search(r"[^A-Za-z0-9]", password or ""):
        errors.append("Password must include a symbol.")
    return errors
