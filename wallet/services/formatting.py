import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def money_it(value):
    """Format Decimal values using Italian separators without float conversion."""
    value = Decimal(value or 0)
    rendered = (
        f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    return ("−" if value < 0 else "") + rendered + " €"


def parse_money(value):
    if value is None:
        raise ValueError("importo mancante")
    raw = (
        str(value)
        .strip()
        .replace("€", "")
        .replace("EUR", "")
        .replace("eur", "")
        .replace("\u00a0", "")
        .replace(" ", "")
    )
    if not raw:
        raise ValueError("importo mancante")
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()")
    if not re.fullmatch(r"[+\-]?[0-9.,]+", raw):
        raise ValueError("importo non valido")
    if not raw or raw in {"-", "+", ",", "."}:
        raise ValueError("importo non valido")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        if len(raw.rsplit(",", 1)[-1]) in (1, 2):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif raw.count(".") > 1:
        pieces = raw.split(".")
        if all(1 <= len(part) <= 3 for part in pieces[:-1]) and all(
            len(part) == 3 for part in pieces[1:]
        ):
            raw = "".join(pieces)
        else:
            raw = "".join(pieces[:-1]) + "." + pieces[-1]
    elif (
        "." in raw
        and len(raw.rsplit(".", 1)[-1]) == 3
        and 1 <= len(raw.rsplit(".", 1)[0]) <= 3
    ):
        raw = raw.replace(".", "")
    try:
        result = Decimal(raw)
    except InvalidOperation:
        raise ValueError("importo non valido")
    if negative:
        result = -result
    if abs(result) > Decimal("999999999999.99"):
        raise ValueError("importo troppo grande")
    if result.as_tuple().exponent < -2:
        raise ValueError("sono ammesse al massimo due cifre decimali")
    return result


def parse_date(value, date_format=""):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value or "").strip()
    if not value:
        raise ValueError("data mancante")
    formats = ([date_format] if date_format else []) + [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d/%m/%y",
    ]
    for fmt in formats:
        if not fmt:
            continue
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError("formato data non riconosciuto")


def month_starts(start, end):
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    result = []
    while cursor <= last:
        result.append(cursor)
        cursor = date(
            cursor.year + (cursor.month == 12),
            1 if cursor.month == 12 else cursor.month + 1,
            1,
        )
    return result


def month_label(day):
    names = [
        "gen",
        "feb",
        "mar",
        "apr",
        "mag",
        "giu",
        "lug",
        "ago",
        "set",
        "ott",
        "nov",
        "dic",
    ]
    return f"{names[day.month - 1]} {day.year}"
