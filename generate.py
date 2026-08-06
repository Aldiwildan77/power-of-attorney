#!/usr/bin/env python3
"""Indonesian power-of-attorney (Surat Kuasa) PDF generator.

Layout follows the reference document from suratkuasa.com
(contoh-sk-umum-perorangan.pdf): title, principal identity, agent identity,
the "K H U S U S" rule, the granted powers, closing, and a signature block
with a stamp-duty (materai) placeholder.

The printed document is Indonesian; everything else here is English.

Usage:
    python generate.py                            # interactive menu (no args)
    python generate.py -c config.toml
    python generate.py -t bank -o out.pdf
    python generate.py -t skck,bank,hr            # several at once
    python generate.py --all --blank-agent        # 15 blank forms
    python generate.py --list-types

Config formats: .toml (stdlib), .json (stdlib), .yaml/.yml (needs PyYAML).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, LEGAL, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from templates import TEMPLATES, get_template

# F4 / Folio: the paper size Indonesian offices commonly ask for.
F4 = (215 * mm, 330 * mm)
PAGE_SIZES = {"A4": A4, "F4": F4, "FOLIO": F4, "LETTER": LETTER, "LEGAL": LEGAL}

MONTHS_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

# Row labels printed in the document (Indonesian by design).
LABELS = {
    "name": "Nama:",
    "birth": "Tempat/Tgl. Lahir:",
    "occupation": "Pekerjaan:",
    "position": "Jabatan:",
    "address": "Alamat:",
    "rt_rw": "RT/RW:",  # appended to the address line, only a prompt label
    "village": "Kelurahan:",
    "district": "Kecamatan:",
    "city": "Kota:",
    "province": "Provinsi:",
    "nik": "NIK:",
    "phone": "No. Telepon:",
}

# Anchor strings dropped invisibly on each signature area, in the document's
# own language so they read sensibly inside an e-sign platform.
DEFAULT_ANCHORS = {"principal": "/ttd_pemberi/", "agent": "/ttd_penerima/"}

# Party fields that hold data (used when blanking a party).
PARTY_FIELDS = (
    "name", "nik", "birth", "occupation", "position", "address", "rt_rw",
    "village", "district", "city", "province", "phone",
)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

def load_config(path: Path) -> dict:
    suffix = path.suffix.lower()
    raw = path.read_bytes()

    if suffix == ".toml":
        import tomllib

        return tomllib.loads(raw.decode("utf-8"))
    if suffix == ".json":
        return json.loads(raw.decode("utf-8"))
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            sys.exit("YAML config needs PyYAML: pip install pyyaml")
        return yaml.safe_load(raw.decode("utf-8"))
    sys.exit(f"Unsupported config format: {suffix} (use .toml/.json/.yaml)")


def dump_toml(data: dict) -> str:
    """Minimal TOML writer for the config shapes used here.

    Enough for strings, numbers, booleans, string lists and nested tables -
    which is all a config file holds. Comments are not preserved, so saving
    over a hand-written config trades its comments for the new values.
    """
    def fmt(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return repr(value)
        if isinstance(value, (list, tuple)):
            return "[" + ", ".join(fmt(v) for v in value) + "]"
        text = (str(value)
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t"))
        return f'"{text}"'

    lines: list[str] = []

    def is_table_array(value) -> bool:
        return (isinstance(value, (list, tuple)) and value
                and all(isinstance(v, dict) for v in value))

    def emit(prefix: str, table: dict) -> None:
        scalars = {k: v for k, v in table.items()
                   if not isinstance(v, dict) and not is_table_array(v)}
        if prefix:
            lines.append(f"[{prefix}]")
        for key, value in scalars.items():
            lines.append(f"{key} = {fmt(value)}")
        if scalars:
            lines.append("")
        for key, value in table.items():
            if isinstance(value, dict):
                emit(f"{prefix}.{key}" if prefix else key, value)
            elif is_table_array(value):
                # [[profile]] blocks: a list of tables, one per entry.
                name = f"{prefix}.{key}" if prefix else key
                for entry in value:
                    lines.append(f"[[{name}]]")
                    for k, v in entry.items():
                        lines.append(f"{k} = {fmt(v)}")
                    lines.append("")

    emit("", data)
    return "\n".join(lines).strip() + "\n"


def get(cfg: dict, path: str, default=None):
    """Read a nested value, e.g. get(cfg, 'document.stamp.enabled', False)."""
    node = cfg
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return default if node in (None, "") else node


# A letter can go out undated, or unplaced, with a dotted line to fill in at
# the counter. Shared by the date and the place of signing.
BLANK_WORDS = ("", "kosong", "none", "blank", "-")

# Ruled lines drawn when the powers list is left empty on purpose.
BLANK_POWER_LINES = 3


def format_date_id(value) -> str:
    """date/datetime, 'YYYY-MM-DD', 'auto' or free text -> Indonesian date.

    Returns "" when the date is meant to stay open: an empty string, or one of
    the words for it. A missing key still means today, so old configs keep
    behaving the way they did.
    """
    if isinstance(value, str) and value.strip().lower() in BLANK_WORDS:
        return ""
    if value in (None, "auto", "today", "hari ini"):
        value = _dt.date.today()
    if isinstance(value, _dt.datetime):
        value = value.date()
    if isinstance(value, _dt.date):
        return f"{value.day} {MONTHS_ID[value.month - 1]} {value.year}"
    text = str(value).strip()
    try:
        d = _dt.date.fromisoformat(text)
    except ValueError:
        return text  # already written by hand, e.g. "1 Juni 2026"
    return f"{d.day} {MONTHS_ID[d.month - 1]} {d.year}"


def format_place_id(value, fallback: str = "") -> str:
    """Place of signing, or "" when left open for a dotted line.

    A missing key falls back to the principal's city, same as a missing date
    means today. An explicit blank ("", "kosong", ...) stays open even when a
    fallback city is available.
    """
    if isinstance(value, str) and value.strip().lower() in BLANK_WORDS:
        return ""
    if value is None:
        return fallback
    return str(value)


def register_font(path: str, fallback: str) -> str:
    """Register a .ttf so the letter can use it; fall back if it will not load.

    Returns the font name to draw with. The file is embedded in the PDF, which
    adds a few hundred kilobytes but makes the letter look the same everywhere.
    """
    if not path:
        return fallback
    file = Path(path)
    if not file.is_file():
        print(f"Note: font file not found, using {fallback}: {path}",
              file=sys.stderr)
        return fallback
    name = f"custom-{file.stem}".replace(" ", "-")
    if name not in pdfmetrics.getRegisteredFontNames():
        try:
            pdfmetrics.registerFont(TTFont(name, str(file)))
        except Exception as exc:
            print(f"Note: could not load {file.name} ({exc}); using {fallback}",
                  file=sys.stderr)
            return fallback
    return name


def blank_party(party: dict) -> dict:
    """Strip a party's data so it prints as dotted lines to fill in by hand.

    Standard rows (name, address, village/district, city/province, NIK) are
    always printed. Extra rows come from `blank_fields`, e.g.
    `blank_fields = ["birth", "occupation", "phone"]`.
    """
    extra = party.get("blank_fields") or []
    result = {k: "" for k in extra if k in PARTY_FIELDS}
    result["blank"] = True
    return result


def esc(value) -> str:
    """Escape characters that are markup in reportlab Paragraphs."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# --------------------------------------------------------------------------- #
# Signature / stamp area
# --------------------------------------------------------------------------- #

class SignatureArea(Flowable):
    """Blank space kept for a signature (and the materai, when it sits here).

    Nothing is drawn by default - a printed letter takes a wet signature and a
    physical stamp, an e-signed one gets its own overlay. What the area does do
    is record its exact position on the page and, when asked, drop an invisible
    anchor string there so e-sign platforms can place their fields on it.
    """

    def __init__(self, sink: list, name: str, role: str, width: float,
                 height: float, anchor: str = "", image: str = "",
                 holds_stamp: bool = False, font: str = "Times-Roman"):
        super().__init__()
        self.sink = sink
        self.name = name
        self.role = role
        self.width = width
        self.height = height
        self.anchor = anchor
        self.image = image
        self.holds_stamp = holds_stamp
        self.font = font

    def draw(self):
        c = self.canv
        if self.image and Path(self.image).is_file():
            c.drawImage(self.image, 0, 0, width=self.width, height=self.height,
                        preserveAspectRatio=True, anchor="c", mask="auto")
        if self.anchor:
            # Text render mode 3 = never painted, still extractable, which is
            # exactly what DocuSign/Adobe Sign anchor strings need.
            text = c.beginText(1, 1)
            text.setTextRenderMode(3)
            text.setFont(self.font, 6)
            text.textOut(self.anchor)
            c.drawText(text)

        x, y = c.absolutePosition(0, 0)
        page_w, page_h = c._pagesize
        self.sink.append({
            "name": self.name,
            "role": self.role,
            "kind": "signature",
            "holds_stamp": self.holds_stamp,
            "anchor": self.anchor or None,
            "page": c.getPageNumber(),
            # PDF user space: origin bottom-left (pyhanko, Acrobat).
            "rect": {"x": round(x, 2), "y": round(y, 2),
                     "width": round(self.width, 2), "height": round(self.height, 2)},
            # Origin top-left, points: DocuSign tabs, Privy, most web viewers.
            "rect_top_left": {
                "x": round(x, 2),
                "y": round(page_h - y - self.height, 2),
                "width": round(self.width, 2),
                "height": round(self.height, 2),
            },
        })


# --------------------------------------------------------------------------- #
# Document builder
# --------------------------------------------------------------------------- #

class LetterBuilder:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.font = register_font(get(cfg, "layout.font_file", ""),
                                  get(cfg, "layout.font", "Times-Roman"))
        self.font_bold = register_font(get(cfg, "layout.font_bold_file", ""),
                                       get(cfg, "layout.font_bold", "Times-Bold"))
        if self.font_bold == get(cfg, "layout.font_bold", "Times-Bold") \
                and get(cfg, "layout.font_file", "") \
                and not get(cfg, "layout.font_bold_file", ""):
            # Only a regular face was supplied: use it for bold too, so the
            # letter stays in one family instead of mixing two.
            self.font_bold = self.font
        # <b> inside a paragraph looks the bold face up by family, so the pair
        # has to be registered as one; without this a custom font never bolds.
        pdfmetrics.registerFontFamily(self.font, normal=self.font,
                                      bold=self.font_bold, italic=self.font,
                                      boldItalic=self.font_bold)
        self.base_size = float(get(cfg, "layout.font_size", 11))
        # Signature areas record themselves here while the PDF is drawn.
        self.areas: list[dict] = []
        self._init_styles(self.base_size)

    def _init_styles(self, size: float) -> None:
        self.size = size
        self.leading = self.size * 1.42

        self.style_body = ParagraphStyle(
            "body", fontName=self.font, fontSize=self.size,
            leading=self.leading, alignment=TA_JUSTIFY,
        )
        self.style_left = ParagraphStyle("left", parent=self.style_body, alignment=0)
        self.style_center = ParagraphStyle("center", parent=self.style_body,
                                           alignment=TA_CENTER)
        self.style_title = ParagraphStyle(
            "title", fontName=self.font_bold, fontSize=self.size + 3,
            leading=(self.size + 3) * 1.3, alignment=TA_CENTER,
        )
        self.style_cell = ParagraphStyle(
            "cell", fontName=self.font, fontSize=self.size,
            leading=self.leading * 0.92,
        )
        self.style_item = ParagraphStyle(
            "item", parent=self.style_body, leftIndent=0.9 * cm, spaceAfter=2,
        )
        self.style_aka = ParagraphStyle(
            "aka", parent=self.style_left, leftIndent=0.8 * cm,
        )

    # -- identity block ----------------------------------------------------- #

    def _dots(self, width: float) -> str:
        """A dotted leader roughly `width` wide, to be filled in by hand."""
        dot = stringWidth(".", self.font, self.size)
        return "." * max(3, int(width / dot) - 2)

    def _identity_rows(self, party: dict, blank: bool = False,
                       fill_widths: tuple[float, float] = (0, 0)):
        """Build identity rows; empty fields are skipped.

        With `blank=True` every standard row is printed and unfilled values
        become dotted lines.

        Returns (rows, left-column labels, right-column labels) - the label
        lists drive column widths so labels never wrap.
        """
        rows, labels_left, labels_right = [], [], []
        wide, half = fill_widths

        def full(label, markup):
            labels_left.append(label)
            rows.append([
                Paragraph(esc(label), self.style_cell),
                Paragraph(markup, self.style_cell), "", "",
            ])

        def pair(l1, v1, l2, v2):
            labels_left.append("  " + l1)
            labels_right.append(l2)
            rows.append([
                Paragraph(f"&nbsp;&nbsp;{esc(l1)}", self.style_cell),
                Paragraph(esc(v1) or self._dots(half), self.style_cell),
                Paragraph(esc(l2), self.style_cell),
                Paragraph(esc(v2) or self._dots(half), self.style_cell),
            ])

        def wanted(field: str) -> bool:
            """Print the row when it has a value, or when this is a blank form
            and the field was listed in the config."""
            return bool(party.get(field)) or (blank and field in party)

        name = esc(party.get("name", ""))
        full(LABELS["name"], f"<b>{name}</b>" if name else self._dots(wide))

        for field in ("birth", "occupation", "position"):
            if wanted(field):
                full(LABELS[field], esc(party.get(field, "")) or self._dots(wide))

        address = esc(party.get("address", ""))
        if party.get("rt_rw"):
            address += f" - RT/RW: {esc(party['rt_rw'])}"
        if address.strip():
            full(LABELS["address"], address)
        elif blank:
            full(LABELS["address"], self._dots(wide))

        if blank or party.get("village") or party.get("district"):
            pair(LABELS["village"], party.get("village", ""),
                 LABELS["district"], party.get("district", ""))
        if blank or party.get("city") or party.get("province"):
            pair(LABELS["city"], party.get("city", ""),
                 LABELS["province"], party.get("province", ""))

        if party.get("nik"):
            nik = f"<b>{esc(party['nik'])}</b>"
            if party.get("attach_id_copy", True):
                nik += " (fotokopi KTP terlampir)"
            full(LABELS["nik"], nik)
        elif blank:
            full(LABELS["nik"], self._dots(wide))

        if wanted("phone"):
            full(LABELS["phone"], esc(party.get("phone", "")) or self._dots(wide))

        return rows, labels_left, labels_right

    def _identity_table(self, party: dict, width: float, blank: bool = False,
                        scale: float = 1.0) -> Table:
        # First pass only collects the labels in use; column widths follow from
        # them, then rows are rebuilt so dotted lines match the value columns.
        _, labels_left, labels_right = self._identity_rows(party, blank)
        indent = 0.8 * cm
        avail = width - indent
        pad = 0.3 * cm

        def label_width(labels, minimum, maximum):
            if not labels:
                return minimum
            widest = max(stringWidth(l, self.font, self.size) for l in labels)
            return min(max(widest + pad, minimum), maximum)

        c0 = label_width(labels_left, 0.185 * avail, 0.34 * avail)
        c2 = label_width(labels_right, 0.185 * avail, 0.26 * avail)
        rest = (avail - c0 - c2) / 2
        cols = [c0, rest, c2, rest]

        rows, _, _ = self._identity_rows(party, blank, (avail - c0, rest))

        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1.2 * scale),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2 * scale),
        ]
        for i, row in enumerate(rows):
            if row[2] == "":  # single-value row -> merge columns 1..3
                style.append(("SPAN", (1, i), (3, i)))

        table = Table(rows, colWidths=cols, hAlign="LEFT")
        table.setStyle(TableStyle(style))
        return Table(
            [[table]], colWidths=[width], hAlign="LEFT",
            style=[
                ("LEFTPADDING", (0, 0), (-1, -1), indent),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ],
        )

    # -- "K H U S U S" rule ------------------------------------------------- #

    def _clause_rule(self, width: float, label: str = "K H U S U S") -> Paragraph:
        text = f" {label} "
        text_w = stringWidth(text, self.font_bold, self.size)
        dash_w = stringWidth("-", self.font, self.size)
        # two dashes of slack so the line never wraps
        n = max(4, int((width - text_w) / dash_w / 2) - 2)
        dashes = "-" * n
        return Paragraph(f"{dashes}<b>{esc(text)}</b>{dashes}", self.style_center)

    # -- signature block ---------------------------------------------------- #

    def _signature_block(self, width: float, principal: dict, agent: dict,
                         scale: float = 1.0) -> Table:
        stamp_on = str(get(self.cfg, "document.stamp.on", "principal")).lower()
        stamp_enabled = bool(get(self.cfg, "document.stamp.enabled", True))
        image = get(self.cfg, "document.stamp.image", "")
        stamp_w = float(get(self.cfg, "document.stamp.width_cm", 3.0)) * cm
        stamp_h = float(get(self.cfg, "document.stamp.height_cm", 2.0)) * cm
        base_gap = float(get(self.cfg, "layout.signature_space_cm", 2.4)) * cm
        anchors_on = bool(get(self.cfg, "esign.anchors", False))

        stamp_principal = stamp_enabled and stamp_on in ("principal", "both")
        stamp_agent = stamp_enabled and stamp_on in ("agent", "both")
        # Keep at least the stamp's height when a stamp goes on either side.
        floor = stamp_h if (stamp_principal or stamp_agent) else 1.4 * cm
        gap = max(floor, base_gap * scale)

        def space(role: str, with_stamp: bool):
            return SignatureArea(
                self.areas,
                name=f"{role}_signature",
                role=role,
                width=stamp_w if with_stamp else width / 3,
                height=gap,
                anchor=(get(self.cfg, f"esign.anchor_{role}",
                            DEFAULT_ANCHORS[role]) if anchors_on else ""),
                image=image if with_stamp else "",
                holds_stamp=with_stamp,
                font=self.font,
            )

        def name_cell(party: dict):
            text = esc(party.get("name", ""))
            if text:
                line = Paragraph(f"<b>{text}</b>", self.style_center)
            else:  # blank form -> handwritten name
                line = Paragraph(f"( {self._dots(width / 2 * 0.62)} )",
                                 self.style_center)
            cell = [line]
            if party.get("show_nik_on_signature") and party.get("nik"):
                cell.append(Paragraph(f"NIK: {esc(party['nik'])}", self.style_center))
            return cell

        # Three separate rows keep both names on the same baseline whether or
        # not a column carries the stamp box.
        rows = [
            [Paragraph("<u>Penerima Kuasa</u>", self.style_center),
             Paragraph("<u>Pemberi Kuasa</u>", self.style_center)],
            [space("agent", stamp_agent), space("principal", stamp_principal)],
            [name_cell(agent), name_cell(principal)],
        ]
        table = Table(rows, colWidths=[width / 2, width / 2], hAlign="CENTER")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, 0), "TOP"),
            ("VALIGN", (0, 1), (-1, 1), "MIDDLE"),
            ("ALIGN", (0, 1), (-1, 1), "CENTER"),
            ("VALIGN", (0, 2), (-1, 2), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
            ("BOTTOMPADDING", (0, 2), (-1, 2), 0),
        ]))
        return table

    # -- granted powers ----------------------------------------------------- #

    def _clause_text(self) -> tuple[str, list, str]:
        doc_type = get(self.cfg, "document.type", "umum")
        tpl = get_template(doc_type)
        purpose = get(self.cfg, "document.purpose", tpl["purpose"])
        powers = self.cfg.get("document", {}).get("powers", tpl.get("powers", []))
        limits = get(self.cfg, "document.limits", tpl.get("limits", ""))
        return purpose, list(powers or []), limits or ""

    # -- story -------------------------------------------------------------- #

    def _story(self, w: float, scale: float = 1.0, size: float | None = None) -> list:
        """Build every flowable.

        `scale` tightens the gaps between blocks and `size` shrinks the font;
        both are driven by the single-page auto-fit.
        """
        self._init_styles(size or self.base_size)
        cfg = self.cfg
        principal = cfg.get("principal", {})
        agent = cfg.get("agent", {})
        if principal.get("blank"):
            principal = blank_party(principal)
        if agent.get("blank"):
            agent = blank_party(agent)
        sp = self.size * 0.55 * scale  # gap between paragraphs

        story = [Paragraph("SURAT KUASA", self.style_title)]

        number = get(cfg, "document.number", "")
        if number:
            story.append(Paragraph(f"Nomor: {esc(number)}", self.style_center))

        story += [
            Spacer(1, sp * 2),
            Paragraph("Yang bertanda-tangan di bawah ini,", self.style_left),
            Spacer(1, sp),
            self._identity_table(principal, w, bool(principal.get("blank")), scale),
            Spacer(1, sp),
            Paragraph("- Selanjutnya disebut sebagai <b>Pemberi Kuasa</b>",
                      self.style_aka),
            Spacer(1, sp * 1.4),
            Paragraph("Dengan ini memberi kuasa kepada:", self.style_left),
            Spacer(1, sp),
            self._identity_table(agent, w, bool(agent.get("blank")), scale),
            Spacer(1, sp),
            Paragraph("- Selanjutnya disebut sebagai <b>Penerima Kuasa</b>",
                      self.style_aka),
            Spacer(1, sp * 1.6),
            self._clause_rule(w, str(get(cfg, "document.clause_label", "K H U S U S"))),
            Spacer(1, sp * 1.6),
        ]

        purpose, powers, limits = self._clause_text()
        story.append(Paragraph(esc(purpose), self.style_body))

        story += [
            Spacer(1, sp),
            Paragraph("Untuk keperluan tersebut, Penerima Kuasa berwenang untuk:",
                      self.style_body),
            Spacer(1, sp * 0.6),
        ]
        if powers:
            for i, item in enumerate(powers, start=1):
                story.append(Paragraph(f"{i}.&nbsp;&nbsp;{esc(item)}", self.style_item))
        else:
            # An empty list is a deliberate blank, not a missing value: leave
            # ruled lines to write the powers in by hand. Unnumbered, so the
            # count is up to whoever fills it in.
            for _ in range(BLANK_POWER_LINES):
                story.append(Paragraph(self._dots(w * 0.86), self.style_item))

        if limits:
            story += [Spacer(1, sp), Paragraph(esc(limits), self.style_body)]

        substitution = (
            "Kuasa ini diberikan dengan hak substitusi."
            if get(cfg, "document.substitution_right", False)
            else "Kuasa ini diberikan tanpa hak substitusi."
        )
        story += [Spacer(1, sp), Paragraph(substitution, self.style_body)]

        valid_until = get(cfg, "document.valid_until", "")
        if valid_until:
            story += [Spacer(1, sp), Paragraph(esc(valid_until), self.style_body)]

        place = format_place_id(cfg.get("document", {}).get("place"),
                                principal.get("city", ""))
        placed = f"<b>{esc(place)}</b>" if place else self._dots(w * 0.18)
        date = format_date_id(cfg.get("document", {}).get("date"))
        dated = f"<b>{esc(date)}</b>" if date else self._dots(w * 0.22)
        story += [
            Spacer(1, sp * 1.6),
            Paragraph(
                "Demikian Surat Kuasa ini dibuat dengan benar, agar dapat "
                "dipergunakan sebagaimana mestinya.",
                self.style_body,
            ),
            Spacer(1, sp * 0.4),
            Paragraph(
                f"Dibuat dan ditandatangani di {placed} "
                f"pada tanggal {dated}",
                self.style_left,
            ),
            Spacer(1, sp * 2.4),
            # single-row table -> never split across pages
            self._signature_block(w, principal, agent, scale),
        ]

        footnote = get(cfg, "document.footnote", "")
        if footnote:
            story += [
                Spacer(1, sp * 2.5),
                Paragraph(
                    f"<i>{esc(footnote)}</i>",
                    ParagraphStyle("footnote", parent=self.style_body,
                                   fontSize=self.size - 1.5,
                                   textColor=colors.HexColor("#555555")),
                ),
            ]

        return story


    # -- page furniture: kop surat and a page footer ------------------------ #

    def _furniture_metrics(self) -> tuple[float, float]:
        """How much room the header and footer need, in points."""
        cfg = self.cfg
        head_lines = [l for l in str(get(cfg, "document.header.text", "")).splitlines()
                      if l.strip()]
        head = 0.0
        if head_lines:
            head = len(head_lines) * (self.base_size + 3) * 1.25 + 6
        image = get(cfg, "document.header.image", "")
        if image and Path(image).is_file():
            head = max(head, float(get(cfg, "document.header.image_cm", 1.8)) * cm) + 6
        if head and get(cfg, "document.header.rule", True):
            head += 6

        foot_lines = [l for l in str(get(cfg, "document.footer.text", "")).splitlines()
                      if l.strip()]
        foot = 0.0
        if foot_lines or get(cfg, "document.footer.page_numbers", False):
            foot = (len(foot_lines) or 1) * (self.base_size - 1) * 1.35 + 6
        return head, foot

    def _draw_furniture(self, canvas, doc) -> None:
        """Paint the header and footer outside the text frame, on every page."""
        cfg = self.cfg
        page_w, page_h = doc.pagesize
        margin = doc.leftMargin
        head, foot = self._furniture_metrics()

        if head:
            top = page_h - float(get(cfg, "layout.margin_top_cm", 2.5)) * cm
            canvas.saveState()
            image = get(cfg, "document.header.image", "")
            text_left = margin
            if image and Path(image).is_file():
                size = float(get(cfg, "document.header.image_cm", 1.8)) * cm
                canvas.drawImage(image, margin, top - size, width=size,
                                 height=size, preserveAspectRatio=True,
                                 anchor="nw", mask="auto")
                text_left = margin + size + 0.4 * cm

            lines = [l for l in str(get(cfg, "document.header.text", "")).splitlines()
                     if l.strip()]
            align = str(get(cfg, "document.header.align", "center")).lower()
            y = top
            for i, text in enumerate(lines):
                size = self.base_size + (2 if i == 0 else -0.5)
                canvas.setFont(self.font_bold if i == 0 else self.font, size)
                y -= size * 1.25
                if align == "center":
                    canvas.drawCentredString(page_w / 2, y, text)
                else:
                    canvas.drawString(text_left, y, text)
            if get(cfg, "document.header.rule", True):
                canvas.setLineWidth(0.8)
                canvas.line(margin, y - 5, page_w - margin, y - 5)
            canvas.restoreState()

        if foot:
            canvas.saveState()
            canvas.setFont(self.font, self.base_size - 1.5)
            canvas.setFillColor(colors.HexColor("#555555"))
            y = doc.bottomMargin - foot + (self.base_size - 1) * 1.35
            for text in [l for l in str(get(cfg, "document.footer.text", "")).splitlines()
                         if l.strip()]:
                canvas.drawCentredString(page_w / 2, y, text)
                y -= (self.base_size - 1) * 1.35
            if get(cfg, "document.footer.page_numbers", False):
                canvas.drawRightString(page_w - margin, y, f"Halaman {doc.page}")
            canvas.restoreState()

    def _template(self, target, page, margin, margin_top, principal):
        head, foot = self._furniture_metrics()
        return SimpleDocTemplate(
            target, pagesize=page,
            leftMargin=margin, rightMargin=margin,
            topMargin=margin_top + head, bottomMargin=margin + foot,
            title=f"Surat Kuasa - {principal.get('name', '')}",
            author=principal.get("name", ""), subject="Surat Kuasa",
        )

    def _pages_for(self, scale: float, size: float, page, margin, margin_top,
                   principal) -> tuple[int, bytes]:
        """Render to memory and report how many pages it actually took.

        Estimating the height from the flowables was close for Times and wrong
        for wider faces like Courier, so the fit is measured by rendering.
        """
        buffer = io.BytesIO()
        doc = self._template(buffer, page, margin, margin_top, principal)
        self.areas.clear()
        doc.build(self._story(doc.width, scale, size),
                  onFirstPage=self._draw_furniture,
                  onLaterPages=self._draw_furniture)
        return doc.page, buffer.getvalue()

    def build(self, output: Path) -> Path:
        cfg = self.cfg
        principal = cfg.get("principal", {})
        agent = cfg.get("agent", {})
        for role, party in (("principal", principal), ("agent", agent)):
            if not party.get("name") and not party.get("blank"):
                sys.exit(
                    f"[{role}].name is empty. Fill it in, or set [{role}].blank = true "
                    f"(or pass --blank-{role}) to print a fill-in-by-hand form."
                )

        page = PAGE_SIZES.get(str(get(cfg, "layout.paper", "A4")).upper(), A4)
        margin = float(get(cfg, "layout.margin_cm", 2.5)) * cm
        margin_top = float(get(cfg, "layout.margin_top_cm", 2.5)) * cm

        output.parent.mkdir(parents=True, exist_ok=True)
        self.page_size = (page[0], page[1])

        # Auto-fit: tighten the gaps, then step the font down, so the signature
        # block never ends up stranded alone on a second page.
        if bool(get(cfg, "layout.fit_one_page", True)):
            min_size = float(get(cfg, "layout.font_size_min", 8.5))
            sizes = [self.base_size]
            while sizes[-1] - 0.5 >= min_size:
                sizes.append(round(sizes[-1] - 0.5, 1))

            pdf = None
            for size in sizes:
                for scale in (1.0, 0.85, 0.7, 0.55, 0.4):
                    pages, data = self._pages_for(scale, size, page, margin,
                                                  margin_top, principal)
                    pdf = data  # keep the tightest attempt as the fallback
                    if pages == 1:
                        output.write_bytes(data)
                        return output
            output.write_bytes(pdf)  # genuinely needs more than one page
            return output

        _, data = self._pages_for(1.0, self.base_size, page, margin,
                                  margin_top, principal)
        output.write_bytes(data)
        return output


# --------------------------------------------------------------------------- #
# Type selection & file naming
# --------------------------------------------------------------------------- #

def parse_types(value: str | None, all_types: bool = False) -> list[str]:
    """'skck,bank' -> ['skck', 'bank']; 'all' or --all -> every type."""
    if all_types or (value or "").strip().lower() in ("all", "semua", "*"):
        return sorted(TEMPLATES)
    if not value:
        return []
    ordered, seen = [], set()
    for part in value.split(","):
        t = part.strip()
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def slug(text: str) -> str:
    """'Siti Rahmawati' -> 'siti-rahmawati' (safe inside a file name)."""
    cleaned = "".join(c.lower() if c.isalnum() else "-" for c in str(text).strip())
    return re.sub(r"-+", "-", cleaned).strip("-") or "unnamed"


def output_pattern(cfg: dict, cli_output: str | None = None,
                   cli_dir: str | None = None) -> str:
    """Combine output dir + file pattern into one path pattern.

    Everything here is a default you can override: -o wins outright, then
    [output].pattern / [output].dir, then a built-in fallback. A pattern that
    already contains a directory is used as-is.
    """
    if cli_output:
        return cli_output
    pattern = get(cfg, "output.pattern") or get(cfg, "output.file") \
        or "surat-kuasa-{type}.pdf"
    directory = cli_dir or get(cfg, "output.dir") or "output"
    p = Path(pattern)
    if p.is_absolute() or len(p.parts) > 1:
        return str(p)
    return str(Path(directory) / p)


def output_path(pattern: str, doc_type: str, many: bool,
                cfg: dict | None = None) -> Path:
    """Fill in the placeholders; in batch runs keep every file name unique."""
    cfg = cfg or {}
    values = {
        "type": doc_type,
        "jenis": doc_type,  # Indonesian alias, since the letters are Indonesian
        "date": _dt.date.today().isoformat(),
        "principal": slug(cfg.get("principal", {}).get("name", "")),
        "agent": slug(cfg.get("agent", {}).get("name", "")),
    }
    try:
        filled = pattern.format(**values)
    except (KeyError, IndexError, ValueError):
        filled = pattern  # unknown placeholder: keep the pattern, never crash

    p = Path(filled)
    if p.suffix.lower() != ".pdf":
        p = p.with_suffix(".pdf")
    if many and not any(k in pattern for k in ("{type}", "{jenis}")):
        p = p.with_name(f"{p.stem}-{doc_type}{p.suffix}")
    return p


# --------------------------------------------------------------------------- #
# Interactive mode
# --------------------------------------------------------------------------- #

def ask(prompt: str, default: str = "") -> str:
    label = f"{prompt} [{default}]: " if default else f"{prompt}: "
    try:
        answer = input(label).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit("Cancelled.")
    return answer or default


def ask_yes(prompt: str, default_yes: bool = False) -> bool:
    return ask(f"{prompt} (y/n)", "y" if default_yes else "n").lower() in ("y", "yes")


def choose(title: str, options: list[tuple[str, str]], default_key: str,
           multi: bool = False):
    """Numbered menu. `multi=True` returns a list of keys, otherwise one key."""
    print(f"\n{title}")
    width = max(len(k) for k, _ in options)
    default_idx = 1
    for i, (key, label) in enumerate(options, start=1):
        if key == default_key:
            default_idx = i
        print(f"  {str(i).rjust(2)}. {key.ljust(width)}  {label}")

    prompt = "Pick a number or name"
    if multi:
        prompt += " (comma-separated, or 'all')"

    while True:
        answer = ask(prompt, str(default_idx))
        if multi and answer.strip().lower() in ("all", "semua", "*"):
            return [k for k, _ in options]

        picked, bad = [], []
        for part in (answer.split(",") if multi else [answer]):
            item = part.strip()
            if item.isdigit() and 1 <= int(item) <= len(options):
                picked.append(options[int(item) - 1][0])
            elif any(item == k for k, _ in options):
                picked.append(item)
            elif item:
                bad.append(item)
        if picked and not bad:
            return picked if multi else picked[0]
        print(f"  Invalid choice: {', '.join(bad) or '(empty)'}. Try again.")


EDITABLE_FIELDS = ("name", "nik", "birth", "occupation", "address", "rt_rw",
                   "village", "district", "city", "province", "phone")


def edit_party(title: str, party: dict) -> dict:
    """Walk through one party's fields, Enter keeps the current value."""
    print(f"\n{title} - press Enter to keep what is in brackets")
    edited = dict(party)
    for field in EDITABLE_FIELDS:
        label = LABELS[field].rstrip(":")
        edited[field] = ask(f"  {label}", str(party.get(field, "") or ""))
    return edited


def save_details(cfg: dict, current_config: Path) -> None:
    """Offer to write the (possibly edited) details back to a config file."""
    if not ask_yes("Save these details for next time?", default_yes=True):
        return
    target = Path(ask("Save to", str(current_config)))
    if target.exists():
        print(f"  {target} already exists. Rewriting it keeps the values but "
              "drops the comments.")
        if not ask_yes(f"  Overwrite {target}?", default_yes=False):
            print("  Not saved.")
            return
    target.write_text(dump_toml(cfg), encoding="utf-8")
    print(f"  Saved to {target}")


def find_configs(default_config: Path) -> list[Path]:
    found = [default_config] if default_config.is_file() else []
    examples = Path("examples")
    if examples.is_dir():
        for p in sorted(examples.iterdir()):
            if p.suffix.lower() in (".toml", ".json", ".yaml", ".yml"):
                found.append(p)
    return found


def interactive(default_config: Path) -> dict:
    """Ask a few questions in the terminal, return the choices."""
    print("=" * 58)
    print("  Surat Kuasa generator - interactive")
    print("  (press Enter to accept the value in brackets)")
    print("=" * 58)

    candidates = find_configs(default_config)
    if not candidates:
        sys.exit(f"No config found. Create one first: {default_config}")
    if len(candidates) == 1:
        cfg_path = candidates[0]
        print(f"\nConfig: {cfg_path}")
    else:
        options = [(str(p), "your details for the letter") for p in candidates]
        cfg_path = Path(choose("Which config holds your details?", options,
                               str(candidates[0])))

    cfg = load_config(cfg_path)
    cfg.setdefault("document", {})
    current_type = cfg["document"].get("type", "umum")
    if current_type not in TEMPLATES:
        current_type = "umum"

    types = choose(
        "Which letter do you need?",
        [(k, TEMPLATES[k]["label"]) for k in sorted(TEMPLATES)],
        current_type,
        multi=True,
    )
    batch = len(types) > 1

    # Custom clause text belongs to one type only; changing type would leave
    # that text describing the wrong errand.
    custom = [k for k in ("purpose", "powers", "limits") if cfg["document"].get(k)]
    use_template = False
    if custom and (batch or types[0] != current_type):
        print(f"\n  This config carries custom clause text ({', '.join(custom)})")
        print(f"  written for type '{current_type}'.")
        question = ("  Replace it with each type's template text?" if batch
                    else f"  Replace it with the '{types[0]}' template text?")
        use_template = ask_yes(question, default_yes=True)

    print()
    blank_agent = ask_yes("Leave the agent's details blank (dotted lines)?",
                          default_yes=bool(cfg.get("agent", {}).get("blank")))
    blank_principal = ask_yes("Leave your (principal's) details blank?",
                              default_yes=bool(cfg.get("principal", {}).get("blank")))

    principal_name = cfg.get("principal", {}).get("name", "")
    agent_name = cfg.get("agent", {}).get("name", "")
    print(f"\nCurrent details - principal: {principal_name or '(empty)'}, "
          f"agent: {agent_name or '(empty)'}")
    edited = ask_yes("Edit them?", default_yes=not (principal_name and agent_name))
    if edited:
        if not blank_principal:
            cfg["principal"] = edit_party("Pemberi Kuasa (principal)",
                                          cfg.get("principal", {}))
        if not blank_agent:
            cfg["agent"] = edit_party("Penerima Kuasa (agent)",
                                      cfg.get("agent", {}))
    print()

    place = ask("Place of signing ('-' to leave open)",
                str(get(cfg, "document.place", "")
                    or cfg.get("principal", {}).get("city", "")))
    date = ask("Date (YYYY-MM-DD, 'auto', or free text)",
               str(cfg["document"].get("date", "auto") or "auto"))

    if edited:
        # Save once everything is collected, so place/date/type go in too.
        cfg["document"].update(type=types[0], place=place, date=date)
        print()
        save_details(cfg, cfg_path)

    # File names follow the default pattern; usually only the folder matters.
    directory = ask("Save into folder", str(get(cfg, "output.dir", "output")))
    pattern = output_pattern(cfg, cli_dir=directory)
    files = [output_path(pattern, t, many=batch, cfg=cfg) for t in types]
    existing = [f for f in files if f.exists()]

    def summarize(role, blank):
        name = cfg.get(role, {}).get("name", "")
        return "(blank - fill in by hand)" if blank else (name or "(empty)")

    print("\n" + "-" * 58)
    print(f"  Config   : {cfg_path}")
    if batch:
        print(f"  Letters  : {len(types)} documents - {', '.join(types)}")
    else:
        print(f"  Letter   : {types[0]} - {TEMPLATES[types[0]]['label']}")
    print(f"  Principal: {summarize('principal', blank_principal)}")
    print(f"  Agent    : {summarize('agent', blank_agent)}")
    print(f"  Place    : {format_place_id(place) or '(open - dotted line)'}")
    print(f"  Date     : {format_date_id(date)}")
    print(f"  Output   : {files[0]}"
          + (f" (+{len(files) - 1} more)" if batch else ""))
    if existing:
        print(f"  Overwrite: {len(existing)} existing file(s)"
              + (f", e.g. {existing[0]}" if batch else ""))
    print("-" * 58)
    if not ask_yes("Generate now?" if not batch else "Generate all now?",
                   default_yes=True):
        sys.exit("Cancelled.")

    return {"config": cfg_path, "cfg": cfg, "types": ",".join(types),
            "place": place, "date": date, "output": pattern,
            "use_template": use_template, "blank_agent": blank_agent,
            "blank_principal": blank_principal}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate Indonesian power-of-attorney letters (PDF). "
                    "Runs the interactive menu when called without arguments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("-c", "--config", default="config.toml",
                    help="config file (.toml/.json/.yaml). Default: config.toml")
    ap.add_argument("-t", "--type",
                    help="letter type; comma-separated for several "
                         "(e.g. skck,bank,hr) or 'all'")
    ap.add_argument("--all", action="store_true",
                    help="generate every letter type at once")
    ap.add_argument("-o", "--output",
                    help="output path or pattern, e.g. 'out/{type}.pdf'. "
                         "Overrides [output] in the config")
    ap.add_argument("-d", "--dir",
                    help="output folder (keeps the config's file pattern)")
    ap.add_argument("--blank-agent", action="store_true",
                    help="print a form: agent details become dotted lines")
    ap.add_argument("--blank-principal", action="store_true",
                    help="print a form: principal details become dotted lines")
    ap.add_argument("--date",
                    help="override [document].date: YYYY-MM-DD, free text, "
                         "'auto' for today, or '' to leave a dotted line")
    ap.add_argument("--place",
                    help="override [document].place, or '' to leave a "
                         "dotted line instead of the principal's city")
    ap.add_argument("--esign", action="store_true",
                    help="e-sign ready: invisible anchor strings, a "
                         ".fields.json with the signature coordinates, and "
                         "empty AcroForm signature fields")
    ap.add_argument("--sign", metavar="P12",
                    help="sign the PDF (PAdES) with a PKCS#12 certificate")
    ap.add_argument("--sign-as", choices=("principal", "agent"),
                    default="principal",
                    help="which signature field to sign. Default: principal")
    ap.add_argument("--sign-pass", metavar="PASSPHRASE",
                    help="PKCS#12 passphrase. Prefer the PKCS12_PASSPHRASE env "
                         "var or the prompt: a CLI passphrase is visible to "
                         "other processes")
    ap.add_argument("-i", "--interactive", action="store_true",
                    help="force the interactive menu")
    ap.add_argument("--list-types", action="store_true",
                    help="list the available letter types and exit")
    args = ap.parse_args(argv)

    if args.list_types:
        width = max(len(k) for k in TEMPLATES)
        for key in sorted(TEMPLATES):
            print(f"  {key.ljust(width)}  {TEMPLATES[key]['label']}")
        return 0

    # No arguments at all -> interactive, which is the normal way to use this.
    no_args = not (argv if argv is not None else sys.argv[1:])
    drop_custom = False
    edited_cfg = None
    if args.interactive or no_args:
        picked = interactive(Path(args.config))
        edited_cfg = picked["cfg"]  # may hold edits that were never saved
        args.config = str(picked["config"])
        args.type = picked["types"]
        args.place = picked["place"]
        args.date = picked["date"]
        args.output = picked["output"]
        drop_custom = picked["use_template"]
        args.blank_agent = args.blank_agent or picked["blank_agent"]
        args.blank_principal = args.blank_principal or picked["blank_principal"]

    if edited_cfg is not None:
        cfg = edited_cfg
    else:
        cfg_path = Path(args.config)
        if not cfg_path.is_file():
            sys.exit(f"Config not found: {cfg_path}")
        cfg = load_config(cfg_path)
    cfg.setdefault("document", {})

    types = parse_types(args.type, args.all) or [cfg["document"].get("type", "umum")]
    unknown = [t for t in types if t not in TEMPLATES]
    if unknown:
        sys.exit(f"Unknown letter type: {', '.join(unknown)}. "
                 f"Available: {', '.join(sorted(TEMPLATES))}")

    custom = [k for k in ("purpose", "powers", "limits") if cfg["document"].get(k)]
    config_type = cfg["document"].get("type", "umum")
    if custom and (drop_custom or len(types) > 1):
        # Custom clause text only fits one type, so batch runs fall back to
        # each type's template.
        for k in custom:
            cfg["document"].pop(k)
        if not drop_custom:
            print(f"Note: custom clause text ({', '.join(custom)}) from type "
                  f"'{config_type}' was skipped; each letter uses its own "
                  "template text.", file=sys.stderr)
    elif custom and types[0] != config_type:
        print(f"Note: the config's custom clause text ({', '.join(custom)}) was "
              f"written for type '{config_type}' but is kept for "
              f"'{types[0]}'.", file=sys.stderr)

    if args.date is not None:
        cfg["document"]["date"] = args.date
    if args.place is not None:
        cfg["document"]["place"] = args.place
    if args.blank_agent:
        cfg.setdefault("agent", {})["blank"] = True
    if args.blank_principal:
        cfg.setdefault("principal", {})["blank"] = True

    cfg.setdefault("esign", {})
    if args.esign:
        cfg["esign"].update(anchors=True, fields_json=True, signature_fields=True)
    want_anchors = bool(get(cfg, "esign.anchors", False))
    want_json = bool(get(cfg, "esign.fields_json", False))
    want_fields = bool(get(cfg, "esign.signature_fields", False))
    cfg["esign"]["anchors"] = want_anchors

    passphrase = None
    if args.sign:
        import os

        if not Path(args.sign).is_file():
            sys.exit(f"Certificate not found: {args.sign}")
        raw = args.sign_pass or os.environ.get("PKCS12_PASSPHRASE")
        if raw is None:
            import getpass

            try:
                raw = getpass.getpass("PKCS#12 passphrase (blank if none): ")
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit("No passphrase given. Set PKCS12_PASSPHRASE or pass "
                         "--sign-pass.")
        passphrase = raw.encode() if raw else None

    pattern = output_pattern(cfg, args.output, args.dir)
    for doc_type in types:
        cfg["document"]["type"] = doc_type
        out = output_path(pattern, doc_type, many=len(types) > 1, cfg=cfg)
        builder = LetterBuilder(cfg)
        result = builder.build(out)
        extras = []

        if want_json:
            import esign

            sidecar = esign.write_fields_json(
                result, builder.areas, builder.page_size,
                extra={"type": doc_type, "label": TEMPLATES[doc_type]["label"]},
            )
            extras.append(sidecar.name)
        if want_fields:
            import esign

            if esign.have_pyhanko():
                added = esign.add_signature_fields(result, builder.areas)
                extras.append(f"{len(added)} signature field(s)")
            else:
                # The PDF and the sidecar are already usable, so this is a
                # note rather than a failure.
                print("Note: skipping AcroForm signature fields (pip install "
                      "pyhanko to add them). Anchors and the .fields.json "
                      "sidecar are unaffected.", file=sys.stderr)
                want_fields = False
        if args.sign:
            import esign

            field = esign.FIELD_NAMES[args.sign_as]
            esign.sign_pades(
                result, Path(args.sign), passphrase, field,
                reason="Surat Kuasa",
                location=format_place_id(cfg.get("document", {}).get("place")),
            )
            extras.append(f"signed as {field}")

        note = f"  [+ {', '.join(extras)}]" if extras else ""
        print(f"OK: {result}  ({doc_type} - {TEMPLATES[doc_type]['label']}){note}")

    if len(types) > 1:
        print(f"Done: {len(types)} documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
