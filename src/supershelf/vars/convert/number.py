"""Lenient number spellings. The result is a string the strict cast accepts."""

import re

from supershelf.vars.convert.error import ConvertError

_SPACE = re.compile(r"\s+")
_LEADING_CODE = re.compile(r"^[A-Za-z]{3}")
_TRAILING_CODE = re.compile(r"[A-Za-z]{3}$")
_GROUP_SPLIT = re.compile(r"[.,]")
_TRIPLET = re.compile(r"[0-9]+[.,][0-9]{3}\Z")
_CURRENCY = str.maketrans("", "", "€$£¥")
_NUMBER_CHARS = frozenset("0123456789.,")


def to_float_text(value: str) -> str:
    """Return a dot spelling. The last separator is the decimal mark."""
    sign, body = _signed(value, "float")
    spelling = _float_spelling(body, value, "float")
    return f"{sign}{spelling}"


def to_int_text(value: str) -> str:
    """Return an int spelling. A zero fraction is dropped. One group of three is thousands."""
    sign, body = _signed(value, "int")
    if _TRIPLET.fullmatch(body):
        return _int_display(sign, _GROUP_SPLIT.sub("", body))
    spelling = _float_spelling(body, value, "int")
    if "." not in spelling:
        return _int_display(sign, spelling)
    whole, fraction = spelling.split(".", 1)
    if any(char != "0" for char in fraction):
        raise ConvertError(f"{value!r} is not an int")
    return _int_display(sign, whole or "0")


def _signed(value: str, kind: str) -> tuple[str, str]:
    text = _strip_noise(value)
    if text.startswith(("+", "-")):
        sign, body = text[0], text[1:]
    else:
        sign, body = "", text
    if not body or any(char not in _NUMBER_CHARS for char in body):
        raise ConvertError(f"{value!r} is not a {kind}")
    return sign, body


def _strip_noise(value: str) -> str:
    text = _SPACE.sub("", value.strip())
    text = text.replace("'", "").replace("_", "")
    text = text.translate(_CURRENCY)
    text = _LEADING_CODE.sub("", text, count=1)
    return _TRAILING_CODE.sub("", text, count=1)


def _float_spelling(body: str, original: str, kind: str) -> str:
    seps = [index for index, char in enumerate(body) if char in ".,"]
    if not seps:
        return body
    integer = body[: seps[-1]]
    fraction = body[seps[-1] + 1 :]
    whole = "".join(_integer_groups(integer, original, kind))
    if fraction == "":
        if not whole:
            raise ConvertError(f"{original!r} is not a {kind}")
        return f"{whole}."
    if not whole:
        return f".{fraction}"
    return f"{whole}.{fraction}"


def _integer_groups(integer: str, original: str, kind: str) -> list[str]:
    if integer == "":
        return []
    parts = _GROUP_SPLIT.split(integer)
    if any(part == "" or not part.isdigit() for part in parts):
        raise ConvertError(f"{original!r} is not a {kind}")
    if any(len(part) != 3 for part in parts[1:]):
        raise ConvertError(f"{original!r} is not a {kind}")
    return parts


def _int_display(sign: str, digits: str) -> str:
    number = int(digits)
    if sign == "-":
        number = -number
    return str(number)
