import csv
import io


def suggest_delimiter(text):
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        return ";" if text.count(";") > text.count(",") else ","


def read_tabular(upload, delimiter_override="", max_rows=10000):
    def collect(iterator):
        rows = []
        for row in iterator:
            if not any(v is not None and str(v).strip() for v in row):
                continue
            if len(rows) >= max_rows:
                raise ValueError(
                    f"Il file contiene oltre {max_rows:,} righe; dividilo in file più piccoli.".replace(
                        ",", "."
                    )
                )
            rows.append(list(row))
        return rows

    if upload.name.lower().endswith(".xlsx"):
        from openpyxl import load_workbook

        wb = load_workbook(upload, read_only=True, data_only=True)
        try:
            iterator = iter(wb.active.iter_rows(values_only=True))
            header = next(iterator, None)
            if header is None:
                raise ValueError("Il file Excel è vuoto.")
            return [str(v or "").strip() for v in header], collect(iterator), ","
        finally:
            wb.close()
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    delimiter = delimiter_override or suggest_delimiter(text)
    iterator = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(iterator, None)
    if header is None:
        raise ValueError("Il CSV è vuoto.")
    return [str(v).strip() for v in header], collect(iterator), delimiter


def guess_column(headers, patterns):
    import re

    for i, name in enumerate(headers):
        normalized = re.sub(r"[^a-z0-9]", "", name.lower())
        if any(re.sub(r"[^a-z0-9]", "", p.lower()) in normalized for p in patterns):
            return str(i)
    return ""
