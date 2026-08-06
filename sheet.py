"""A spreadsheet writer, small enough to avoid a dependency for it.

An .xlsx is a zip of a handful of XML parts. What the app needs is one sheet
of text - no styling, no formulas, no numbers - so the whole format reduces to
the five parts below and a list of strings. openpyxl would do this too, but
generate.py already hand-writes its own TOML rather than take a dependency for
one narrow job, and the pins in requirements.txt exist so a deploy builds the
same way twice.

Only `xlsx_bytes` is meant to be called from outside.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

# XML 1.0 allows tab, newline and carriage return, and nothing else below 0x20.
# Form fields are free text, so a stray control character is possible and would
# otherwise produce a file no reader will open.
ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def _clean(value) -> str:
    return ILLEGAL.sub("", str(value))


def _sheet_title(name: str) -> str:
    """Excel refuses these characters in a sheet name, and caps it at 31."""
    title = re.sub(r"[\\/*?:\[\]]", " ", _clean(name)).strip()
    return (title or "Sheet1")[:31]


def _column(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    while True:
        index, remainder = divmod(index, 26)
        letters = chr(ord("A") + remainder) + letters
        if index == 0:
            return letters
        index -= 1


def _cell(column: int, row: int, value) -> str:
    text = _clean(value)
    if not text:
        return ""  # an empty cell is better left out than written blank
    # Inline strings keep everything in one part; a shared-string table would
    # only pay off on a sheet with heavy repetition.
    return (f'<c r="{_column(column)}{row}" t="inlineStr">'
            f'<is><t xml:space="preserve">{escape(text)}</t></is></c>')


def _worksheet(rows) -> str:
    body = []
    for number, row in enumerate(rows, start=1):
        cells = "".join(_cell(i, number, v) for i, v in enumerate(row))
        body.append(f'<row r="{number}">{cells}</row>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheetData>'
            + "".join(body) +
            "</sheetData></worksheet>")


def xlsx_bytes(rows, sheet_name: str = "Sheet1") -> bytes:
    """Turn rows of values into a one-sheet .xlsx.

    `rows` is any iterable of iterables; every value is written as text, and
    empty ones are skipped. The result opens in Excel, LibreOffice and Google
    Sheets.
    """
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<workbook xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main" xmlns:r="http://schemas.'
                'openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets><sheet name="{escape(_sheet_title(sheet_name))}" '
                'sheetId="1" r:id="rId1"/></sheets></workbook>')

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", _worksheet(rows))
    return buffer.getvalue()
