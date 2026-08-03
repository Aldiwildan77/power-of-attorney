"""E-signature helpers: field coordinates, empty signature fields, PAdES.

Three levels, cheapest first:

1. `write_fields_json` - a sidecar JSON listing every signature area with its
   page and coordinates (both PDF and top-left origin) plus the anchor string.
   Feed it to the DocuSign/Privy/Adobe Sign API instead of guessing positions.
2. `add_signature_fields` - empty AcroForm signature fields placed on those
   areas, so Acrobat and friends show a "click to sign" box.
3. `sign_pades` - actually sign the PDF with a PKCS#12 certificate.

Steps 2 and 3 need pyhanko: pip install pyhanko
"""

from __future__ import annotations

import json
from pathlib import Path

# Field names as they will show up in a PDF viewer.
FIELD_NAMES = {"principal": "PemberiKuasa", "agent": "PenerimaKuasa"}


def have_pyhanko() -> bool:
    try:
        import pyhanko  # noqa: F401
    except ImportError:
        return False
    return True


def _require_pyhanko():
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import fields, signers
    except ImportError:
        raise SystemExit(
            "This step needs pyhanko: pip install pyhanko"
        ) from None
    return IncrementalPdfFileWriter, fields, signers


def sidecar_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".fields.json")


def write_fields_json(pdf_path: Path, areas: list[dict],
                      page_size: tuple[float, float],
                      extra: dict | None = None) -> Path:
    """Write <name>.fields.json describing where the signatures go."""
    payload = {
        "file": pdf_path.name,
        "unit": "pt",
        "page_size": {"width": round(page_size[0], 2),
                      "height": round(page_size[1], 2)},
        "coordinates": {
            "rect": "PDF user space, origin bottom-left (Acrobat, pyHanko)",
            "rect_top_left": "origin top-left (DocuSign tabs, Privy, web viewers)",
        },
        "fields": [
            {**area, "field_name": FIELD_NAMES.get(area["role"], area["name"])}
            for area in areas
        ],
    }
    if extra:
        payload.update(extra)
    out = sidecar_path(pdf_path)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return out


def add_signature_fields(pdf_path: Path, areas: list[dict]) -> list[str]:
    """Add one empty AcroForm signature field per recorded area."""
    IncrementalPdfFileWriter, fields, _ = _require_pyhanko()

    added = []
    with open(pdf_path, "rb+") as fh:
        writer = IncrementalPdfFileWriter(fh)
        for area in areas:
            name = FIELD_NAMES.get(area["role"], area["name"])
            r = area["rect"]
            fields.append_signature_field(
                writer,
                fields.SigFieldSpec(
                    sig_field_name=name,
                    on_page=area.get("page", 1) - 1,
                    box=(r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"]),
                ),
            )
            added.append(name)
        writer.write_in_place()
    return added


def sign_pades(pdf_path: Path, pkcs12_file: Path, passphrase: bytes | None,
               field_name: str, output: Path | None = None,
               reason: str = "", location: str = "") -> Path:
    """Sign the PDF (PAdES/PKCS#7) with a PKCS#12 (.p12/.pfx) certificate."""
    IncrementalPdfFileWriter, fields, signers = _require_pyhanko()

    signer = signers.SimpleSigner.load_pkcs12(
        pfx_file=str(pkcs12_file), passphrase=passphrase
    )
    if signer is None:
        raise SystemExit(f"Could not load certificate: {pkcs12_file}")

    meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        subfilter=fields.SigSeedSubFilter.PADES,
        reason=reason or None,
        location=location or None,
    )
    output = output or pdf_path
    with open(pdf_path, "rb") as src:
        writer = IncrementalPdfFileWriter(src)
        signed = signers.sign_pdf(writer, meta, signer=signer)
        data = signed.getvalue()
    output.write_bytes(data)
    return output
