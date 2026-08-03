"""Streamlit front-end for the surat kuasa generator.

Run locally:      streamlit run app.py
Deploy for free:  Streamlit Community Cloud, or a Hugging Face Space
                  (SDK: streamlit) - both need only requirements.txt.

Design notes
------------
* The page scrolls as one; the preview column sticks so the letter stays in
  view while the form is filled in.
* No database, no files kept. Letters are rendered into a temporary directory,
  handed to the browser, and the directory is removed. Your details live on
  your own device - a cookie in this browser, or a config.toml you keep.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import re
import tempfile
import tomllib
import zipfile
import zlib
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st
import streamlit.components.v1 as components

import esign
from generate import (
    DEFAULT_ANCHORS,
    LetterBuilder,
    PAGE_SIZES,
    TEMPLATES,
    dump_toml,
    find_configs,
    load_config,
    output_path,
)

PARTY_LABELS = {
    "name": "Nama",
    "nik": "NIK",
    "birth": "Tempat/Tgl. Lahir",
    "occupation": "Pekerjaan",
    "position": "Jabatan",
    "address": "Alamat",
    "rt_rw": "RT/RW",
    "village": "Kelurahan",
    "district": "Kecamatan",
    "city": "Kota",
    "province": "Provinsi",
    "phone": "No. Telepon",
}
BLANK_EXTRA = ["birth", "occupation", "position", "phone"]
# Faces built into every PDF reader: label and the matching bold.
LETTER_FONTS = {
    "Times-Roman": ("Times New Roman (lazim di surat dinas)", "Times-Bold"),
    "Courier": ("Courier (mesin tik)", "Courier-Bold"),
    "Helvetica": ("Helvetica / Arial", "Helvetica-Bold"),
}
SHARED_ADDRESS = ("address", "rt_rw", "village", "district", "city", "province")
COOKIE = "sk_details_v1"
COOKIE_TEMPLATE = "sk_template_v1"
COOKIE_PROFILES = "sk_profiles_v1"

st.set_page_config(page_title="Surat Kuasa", page_icon="📄", layout="wide",
                   initial_sidebar_state="collapsed")


# --------------------------------------------------------------------------- #
# Look and feel
#
# A pale desk, and on it the rendered letter: the brightest surface on screen,
# lifted by a hairline border and a soft shadow. Inputs borrow the document's
# own vocabulary: a dotted fill-in line that turns solid ballpoint blue when
# focused, and section rules built like the letter's own "K H U S U S" divider.
# --------------------------------------------------------------------------- #

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;1,6..72,300&family=IBM+Plex+Mono:wght@400&display=swap');

:root {
  --desk: #F4F6F9;
  --raised: #FFFFFF;
  --rule: rgba(20, 26, 35, 0.18);
  --muted: #5B6677;
  --tinta: #2F5FD0;
  --cap: #B03A31;
}

[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {
  display: none !important;
}
[data-testid="stHeader"] { background: transparent; }

html, body, [data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] input,
[data-testid="stAppViewContainer"] textarea,
[data-testid="stAppViewContainer"] button {
  font-family: 'Newsreader', 'Times New Roman', Georgia, serif;
}
[data-testid="stAppViewContainer"] .block-container {
  padding-top: 2rem; padding-bottom: 4rem;
  max-width: min(1800px, 96vw);
}

/* ---- masthead ---------------------------------------------------------- */
.sk-eyebrow {
  font-size: 0.7rem; letter-spacing: 0.2em; text-transform: uppercase;
  color: var(--muted);
}
.sk-title {
  font-family: 'Newsreader', Georgia, serif; font-weight: 300;
  font-size: clamp(1.8rem, 3.2vw, 2.7rem); line-height: 1.06;
  letter-spacing: -0.015em; margin: 0.35rem 0 0.4rem;
}
.sk-title em { font-style: italic; color: var(--tinta); }
.sk-sub { color: var(--muted); font-size: 0.92rem; max-width: 52ch; }

/* ---- section rule, built like the letter's own K H U S U S divider ----- */
.sk-rule { display: flex; align-items: center; gap: 0.75rem; margin: 1.9rem 0 0.7rem; }
.sk-rule::after { content: ""; flex: 1; height: 0; border-top: 1px dashed var(--rule); }
.sk-rule span {
  font-size: 0.72rem; letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--muted); white-space: nowrap;
}

/* ---- inputs: the blanko's dotted fill-in line -------------------------- */
div[data-baseweb="input"], div[data-baseweb="base-input"],
div[data-baseweb="textarea"] {
  background: transparent !important; border: 0 !important;
  border-bottom: 1px dashed var(--rule) !important; border-radius: 0 !important;
  transition: border-color .18s ease;
}
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within {
  border-bottom: 1.5px solid var(--tinta) !important;
}
.stTextInput input, .stTextArea textarea, .stDateInput input {
  background: transparent !important; padding-left: 0 !important;
  font-size: 0.95rem;
}
.stTextInput label, .stTextArea label, .stDateInput label, .stSelectbox label,
.stMultiSelect label, .stSlider label, .stRadio label, .stFileUploader label {
  font-size: 0.72rem !important; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--muted) !important; font-weight: 500 !important;
}

/* ---- buttons ----------------------------------------------------------- */
.stButton button, .stDownloadButton button {
  border-radius: 3px; font-weight: 500; border: 1px solid var(--rule);
  transition: transform .12s ease, background .18s ease, border-color .18s ease;
}
.stButton button[kind="primary"] { background: var(--tinta); border-color: var(--tinta); color: #fff; }
.stButton button:hover, .stDownloadButton button:hover {
  transform: translateY(-1px); border-color: var(--tinta);
}

/* ---- expanders & chips ------------------------------------------------- */
[data-testid="stExpander"] {
  border: 1px solid var(--rule); border-radius: 4px; background: var(--raised);
}
[data-baseweb="tag"] { border-radius: 2px !important; font-size: 0.8rem !important; }
[data-testid="stCode"], code { font-family: 'IBM Plex Mono', monospace !important; }

/* ---- the preview column sticks; the page scrolls as one ---------------- */
[data-testid="stHorizontalBlock"] { align-items: flex-start; }
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child,
[data-testid="stHorizontalBlock"] > [data-testid="column"]:last-child {
  position: sticky; top: 1rem; align-self: flex-start;
}

/* ---- the sheet: the only paper in the interface ------------------------ */
/* Kept shorter than the viewport so the whole column can stick; the full
   page is one click away in the fullscreen dialog. */
.sk-sheet img {
  border-radius: 2px;
  box-shadow: 0 18px 36px -16px rgba(20,26,35,.28), 0 1px 3px rgba(20,26,35,.14);
  outline: 1px solid rgba(20,26,35,.12);
  max-height: calc(100vh - 24rem);
  width: auto !important;
  margin: 0 auto;
  display: block;
}
[data-testid="stDialog"] .sk-sheet img { max-height: none; width: 100% !important; }
.sk-note {
  font-size: 0.8rem; color: var(--muted); margin: 0.3rem 0 0;
}
.sk-note b { color: var(--cap); font-weight: 500; }

/* ---- legal wording: typewriter, the way a filing reads ----------------- */
.stTextArea textarea {
  font-family: 'Courier New', 'IBM Plex Mono', monospace !important;
  font-size: 0.86rem !important; line-height: 1.5;
}

/* ---- one-line facts; the detail hides behind the (i) ------------------- */
.sk-line {
  font-size: 0.92rem; color: #1C2430; margin: 0 0 .5rem;
  display: flex; align-items: baseline; gap: .4rem;
}
.sk-line b { font-weight: 500; }
.sk-info {
  position: relative; display: inline-flex; align-items: center;
  justify-content: center; width: 1.15em; height: 1.15em; border-radius: 50%;
  border: 1px solid var(--rule); color: var(--muted);
  font-size: .72rem; font-style: italic; cursor: help; flex: none;
  outline: none;
}
.sk-info:hover, .sk-info:focus { border-color: var(--tinta); color: var(--tinta); }

/* The panel itself: instant, readable, and reachable by tap or keyboard. */
.sk-info::after {
  content: attr(data-tip);
  position: absolute; bottom: calc(100% + 8px); left: 50%;
  transform: translateX(-50%) translateY(4px);
  width: max-content; max-width: 280px;
  padding: .55rem .7rem; border-radius: 4px;
  background: #141A23; color: #F2F5F9;
  font-size: .78rem; font-style: normal; line-height: 1.45; text-align: left;
  box-shadow: 0 10px 24px -10px rgba(20,26,35,.5);
  opacity: 0; visibility: hidden; pointer-events: none; z-index: 999;
  transition: opacity .12s ease, transform .12s ease;
}
.sk-info:hover::after, .sk-info:focus::after {
  opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0);
}
/* Streamlit clips its blocks, so let the panel out. */
.sk-line, [data-testid="stMarkdownContainer"] { overflow: visible !important; }

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
  .stButton button:hover, .stDownloadButton button:hover { transform: none; }
}
</style>
"""


def line(text: str, tip: str = "") -> None:
    """One short line; anything longer belongs behind the (i)."""
    safe = tip.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    mark = (f'<span class="sk-info" tabindex="0" data-tip="{safe}">i</span>'
            if tip else "")
    st.markdown(f'<p class="sk-line">{text}{mark}</p>', unsafe_allow_html=True)


def rule(label: str) -> None:
    """Section divider in the letter's own idiom: a label, then a dashed rule."""
    st.markdown(f'<div class="sk-rule"><span>{label}</span></div>',
                unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Storage: the browser, or a file you keep. Never the server.
# --------------------------------------------------------------------------- #

# Per-letter values are deliberately left out: a letter number and a fixed date
# belong to one document, not to your setup.
REMEMBERED_DOCUMENT = ("type", "place", "substitution_right", "valid_until",
                       "footnote")
REMEMBERED_LAYOUT = ("paper", "font_size", "fit_one_page",
                     "font", "font_bold")
COOKIE_LIMIT = 3500  # browsers cap a cookie at about 4 KB, headers and all


def _device_settings(cfg: dict) -> dict:
    """Everything worth carrying to the next visit.

    Both parties, where you sign, how the materai is placed, the e-sign
    switches (anchors, .fields.json, AcroForm fields) and the page setup. The
    clause text is skipped: it belongs to one letter type and would crowd out
    the cookie.
    """
    document = cfg.get("document", {})
    return {
        "principal": cfg.get("principal", {}),
        "agent": cfg.get("agent", {}),
        "document": {
            **{k: document.get(k) for k in REMEMBERED_DOCUMENT if document.get(k) not in (None, "")},
            "stamp": document.get("stamp", {}),
            "header": document.get("header", {}),
            "footer": document.get("footer", {}),
        },
        "esign": cfg.get("esign", {}),
        "layout": {k: cfg.get("layout", {}).get(k)
                   for k in REMEMBERED_LAYOUT if cfg.get("layout", {}).get(k) is not None},
    }


def _pack(settings: dict) -> str:
    return base64.b64encode(
        zlib.compress(dump_toml(settings).encode("utf-8"), 9)
    ).decode("ascii")


def remember_on_device(cfg: dict) -> None:
    """Keep your setup in a cookie on this device (compressed, ~1 year).

    Streamlit already carries whatever you type to its own process, so this
    adds no new exposure - and it means the form fills itself next time. The
    cookie lives on the device; nothing is written to a database or a disk.
    """
    settings = _device_settings(cfg)
    payload = _pack(settings)
    if len(payload) > COOKIE_LIMIT:
        # Too much to carry: keep who you are, drop the rest.
        settings = {k: settings[k] for k in ("principal", "agent")}
        payload = _pack(settings)
        st.warning("Setelannya terlalu panjang untuk disimpan di perangkat - "
                   "hanya data pemberi & penerima kuasa yang diingat. Unduh "
                   "config.toml untuk menyimpan semuanya.")

    secure = "; Secure" if str(getattr(st.context, "url", "")).startswith("https") else ""
    components.html(
        f"""<script>
        document.cookie = "{COOKIE}=" + {json.dumps(payload)} +
          "; max-age=31536000; path=/; SameSite=Lax{secure}";
        </script>""", height=0)


def remember_template(label: str, purpose: str, powers: list[str],
                      limits: str) -> bool:
    """Keep a letter the user wrote themselves, on their own device."""
    payload = _pack({"label": label or "Template saya", "purpose": purpose,
                     "powers": powers, "limits": limits})
    if len(payload) > COOKIE_LIMIT:
        st.warning("Teks suratnya terlalu panjang untuk disimpan di perangkat. "
                   "Persingkat, atau simpan lewat config.toml.")
        return False
    secure = "; Secure" if str(getattr(st.context, "url", "")).startswith("https") else ""
    components.html(
        f"""<script>
        document.cookie = "{COOKIE_TEMPLATE}=" + {json.dumps(payload)} +
          "; max-age=31536000; path=/; SameSite=Lax{secure}";
        </script>""", height=0)
    return True


def remember_profiles(profiles: list[dict]) -> bool:
    """Keep a few saved parties on this device, each under its own name."""
    payload = _pack({"profile": profiles})
    if len(payload) > COOKIE_LIMIT:
        st.warning("Profil tersimpan sudah penuh. Hapus salah satu dulu.")
        return False
    secure = "; Secure" if str(getattr(st.context, "url", "")).startswith("https") else ""
    components.html(
        f"""<script>
        document.cookie = "{COOKIE_PROFILES}=" + {json.dumps(payload)} +
          "; max-age=31536000; path=/; SameSite=Lax{secure}";
        </script>""", height=0)
    return True


def recall_profiles() -> list[dict]:
    try:
        raw = st.context.cookies.get(COOKIE_PROFILES)
    except Exception:
        return []
    if not raw:
        return []
    try:
        data = tomllib.loads(zlib.decompress(base64.b64decode(raw)).decode("utf-8"))
        return [p for p in data.get("profile", []) if isinstance(p, dict)]
    except Exception:
        return []


def recall_template() -> dict | None:
    try:
        raw = st.context.cookies.get(COOKIE_TEMPLATE)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return tomllib.loads(zlib.decompress(base64.b64decode(raw)).decode("utf-8"))
    except Exception:
        return None


def forget_on_device() -> None:
    components.html(
        f"""<script>
        document.cookie = "{COOKIE}=; max-age=0; path=/; SameSite=Lax";
        document.cookie = "{COOKIE_TEMPLATE}=; max-age=0; path=/; SameSite=Lax";
        document.cookie = "{COOKIE_PROFILES}=; max-age=0; path=/; SameSite=Lax";
        </script>""", height=0)


def recall_from_device() -> dict | None:
    """Read back what this device remembers, if anything."""
    raw = None
    try:
        raw = st.context.cookies.get(COOKIE)
    except Exception:
        return None
    if not raw:
        return None
    try:
        text = zlib.decompress(base64.b64decode(raw)).decode("utf-8")
        return tomllib.loads(text)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Shareable setup link
#
# The link carries the setup only: which letter, where it is signed, materai
# side, e-sign switches, page setup. Never a name, a NIK or an address - a URL
# ends up in chat logs, browser history and link previews, and those belong to
# the person filling the form, not to whoever gets the link.
# --------------------------------------------------------------------------- #

SHARE_LIMIT = 10_000      # characters of setup we are willing to put in a link
QR_BYTE_LIMIT = 2_900     # a single QR tops out here; the standard says so

# Setup that may travel in a link. Personal fields are absent by design; only
# the blank flags come along, since they describe the form, not a person.
SHARE_DOCUMENT = ("type", "place", "substitution_right", "valid_until",
                  "footnote", "clause_label", "purpose", "powers", "limits")
SHARE_LAYOUT = ("paper", "font", "font_bold", "font_size", "fit_one_page")


def _share_payload(types: list[str], cfg: dict) -> dict:
    document = cfg.get("document", {})
    payload = {
        "types": types,
        "document": {k: document[k] for k in SHARE_DOCUMENT
                     if document.get(k) not in (None, "", [])},
        "layout": {k: cfg["layout"][k] for k in SHARE_LAYOUT
                   if cfg.get("layout", {}).get(k) is not None},
        "esign": cfg.get("esign", {}),
        "blank": [role for role in ("principal", "agent")
                  if cfg.get(role, {}).get("blank")],
    }
    payload["document"]["stamp"] = document.get("stamp", {})
    for section in ("header", "footer"):
        block = document.get(section, {})
        if any(str(v).strip() for v in block.values() if not isinstance(v, bool)):
            payload["document"][section] = block
    return payload


def build_share_link(types: list[str], cfg: dict) -> str:
    """One compressed parameter: whatever the setup happens to be, it fits.

    Spelling every field out as its own query parameter got unwieldy once the
    clause text, the kop and the footer could travel too. Compressed TOML in a
    single `c` parameter is shorter than the readable form for anything but the
    smallest setup, and it round-trips exactly.
    """
    raw = dump_toml(_share_payload(types, cfg)).encode("utf-8")
    packed = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")
    base = str(getattr(st.context, "url", "")) or "/"
    base = base.split("?")[0].split("#")[0]
    return f"{base}?c={packed}"


def setup_from_link() -> dict | None:
    """Turn ?c=... back into a config overlay, or None when absent."""
    try:
        q = dict(st.query_params)
    except Exception:
        return None
    packed = q.get("c")
    if not packed:
        return None
    try:
        raw = zlib.decompress(base64.urlsafe_b64decode(packed)).decode("utf-8")
        payload = tomllib.loads(raw)
    except Exception:
        st.warning("Tautan setelan tidak terbaca; mungkin terpotong saat "
                   "dikirim. Minta tautannya sekali lagi.")
        return None

    types = [t for t in payload.get("types", []) if t in TEMPLATES]
    if not types:
        return None

    document = {k: v for k, v in payload.get("document", {}).items()
                if k in SHARE_DOCUMENT or k in ("stamp", "header", "footer")}
    layout = {k: v for k, v in payload.get("layout", {}).items()
              if k in SHARE_LAYOUT}
    overlay: dict = {"document": document, "layout": layout,
                     "esign": payload.get("esign", {})}
    for role in payload.get("blank", []):
        if role in ("principal", "agent"):
            overlay.setdefault(role, {})["blank"] = True
    overlay["_types"] = types
    return overlay


def qr_png(url: str, scale: int = 9, quiet: int = 4) -> bytes | None:
    """Render the link as a QR code, so it can be saved as a picture.

    reportlab already ships a QR encoder and Pillow comes with it, so this
    needs nothing beyond what the letters themselves use. Long links get the
    lower correction level, which buys capacity; past that a QR is the wrong
    carrier and this returns None.
    """
    from PIL import Image, ImageDraw
    from reportlab.graphics.barcode import qr

    if len(url.encode("utf-8")) > QR_BYTE_LIMIT:
        return None
    code = None
    for level in ("M", "L"):
        try:
            widget = qr.QrCodeWidget(url, barLevel=level)
            widget.draw()
            code = widget.qr
            break
        except Exception:
            continue
    if code is None:
        return None
    n = code.getModuleCount()

    scale = max(3, min(scale, 700 // (n + quiet * 2)))
    size = (n + quiet * 2) * scale
    image = Image.new("RGB", (size, size), "white")
    pen = ImageDraw.Draw(image)
    for row in range(n):
        for col in range(n):
            if code.isDark(row, col):
                x, y = (col + quiet) * scale, (row + quiet) * scale
                pen.rectangle([x, y, x + scale - 1, y + scale - 1], fill="black")

    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def setup_from_link() -> dict | None:
    """Turn ?t=skck&pa=F4&... into a config overlay, or None when absent."""
    try:
        q = dict(st.query_params)
    except Exception:
        return None
    if not q.get("t"):
        return None

    types = [t for t in q["t"].split(",") if t in TEMPLATES]
    if not types:
        return None

    overlay: dict = {"document": {"type": types[0]}, "layout": {}, "esign": {}}
    if q.get("p"):
        overlay["document"]["place"] = q["p"]
    if q.get("st"):
        overlay["document"]["stamp"] = ({"enabled": False} if q["st"] == "none"
                                        else {"enabled": True, "on": q["st"]})
    if q.get("pa") in PAGE_SIZES:
        overlay["layout"]["paper"] = q["pa"]
    try:
        if q.get("fs"):
            overlay["layout"]["font_size"] = float(q["fs"])
    except ValueError:
        pass
    bits = q.get("es", "")
    overlay["esign"] = {"anchors": "a" in bits, "fields_json": "j" in bits,
                        "signature_fields": "f" in bits}
    for role in q.get("bl", "").split(","):
        if role in ("principal", "agent"):
            overlay.setdefault(role, {})["blank"] = True
    overlay["_types"] = types
    return overlay


def deep_merge(base: dict, overlay: dict) -> dict:
    """Overlay wins, but nested tables merge instead of replacing wholesale."""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def apply_base(cfg: dict, note: str) -> None:
    """Load a config into the form, bumping widget keys so values refresh."""
    st.session_state["base"] = cfg
    st.session_state["form_rev"] = st.session_state.get("form_rev", 0) + 1
    st.session_state["base_note"] = note


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #

@st.cache_data(show_spinner=False)
def preset_configs() -> dict[str, dict]:
    """Config files shipped with the repo, used to prefill the form."""
    presets = {}
    for path in find_configs(Path("config.toml")):
        try:
            presets[str(path)] = load_config(path)
        except (Exception, SystemExit):
            # Unreadable config (broken, or YAML without PyYAML) is skipped;
            # load_config exits the process on the CLI, hence SystemExit too.
            continue
    return presets


def clean_nik(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def party_form(role: str, title: str, data: dict, rev: int,
               copy_from: dict | None = None,
               profiles: list[dict] | None = None) -> dict:
    """Render the inputs for one party and return what the user typed."""
    rule(title)
    k = lambda field: f"{role}_{field}_{rev}"  # noqa: E731

    profiles = profiles or []

    blank = st.checkbox("Kosongkan - diisi tangan nanti",
                        value=bool(data.get("blank")), key=k("blank"),
                        help="Data jadi garis titik-titik, termasuk nama di "
                             "atas tanda tangan.")
    out: dict = {"blank": blank}
    if blank:
        out["blank_fields"] = st.multiselect(
            "Baris tambahan pada blanko", BLANK_EXTRA,
            default=[f for f in (data.get("blank_fields") or []) if f in BLANK_EXTRA],
            format_func=lambda f: PARTY_LABELS[f], key=k("blank_fields"),
            help="Nama, Alamat, Kelurahan/Kecamatan, Kota/Provinsi dan NIK "
                 "selalu ada.")
        return out

    same_address = False
    if copy_from is not None:
        same_address = st.checkbox("Alamat sama dengan pemberi kuasa",
                                   value=bool(data.get("same_address")),
                                   key=k("same_address"))

    fields = ("name", "nik", "birth", "occupation", "position", "address",
              "rt_rw", "village", "district", "city", "province", "phone")
    cols = st.columns(2)
    for i, field in enumerate(fields):
        if same_address and field in SHARED_ADDRESS:
            out[field] = copy_from.get(field, "")
            continue
        with cols[i % 2]:
            out[field] = st.text_input(PARTY_LABELS[field],
                                       value=str(data.get(field, "") or ""),
                                       key=k(field))
    if same_address:
        st.markdown(
            f'<p class="sk-note">Alamat mengikuti pemberi kuasa: '
            f'{copy_from.get("address", "-")}, {copy_from.get("city", "-")}</p>',
            unsafe_allow_html=True)

    out["nik"] = clean_nik(out.get("nik", ""))
    digits = re.sub(r"\D", "", out["nik"])
    if out["nik"] and len(digits) != 16:
        st.markdown(f'<p class="sk-note"><b>NIK {len(digits)} digit</b> - '
                    'NIK Indonesia 16 digit.</p>', unsafe_allow_html=True)

    out["same_address"] = same_address
    out["attach_id_copy"] = st.checkbox(
        "Tulis \"(fotokopi KTP terlampir)\" di baris NIK",
        value=bool(data.get("attach_id_copy", True)), key=k("attach"))
    out["show_nik_on_signature"] = st.checkbox(
        "Tulis NIK di bawah nama pada tanda tangan",
        value=bool(data.get("show_nik_on_signature", False)), key=k("niksig"))

    names = [p.get("label", "") for p in profiles if p.get("label")]
    n1, n2, n3 = st.columns([3, 1.4, 1.4])
    with n1:
        label = st.selectbox(
            "Profil di perangkat ini", names, index=None,
            key=k("profile_name"), accept_new_options=True,
            placeholder="Pilih profil, atau ketik nama baru",
            help="Pilih yang tersimpan lalu Pakai untuk mengisi form ini. "
                 "Ketik nama baru lalu Simpan untuk menambah; nama yang sama "
                 "akan ditimpa.")
    named = (label or "").strip()
    with n2:
        st.markdown("<div style='height:1.55rem'></div>", unsafe_allow_html=True)
        if st.button("Pakai", key=k("profile_use"), use_container_width=True,
                     disabled=named not in names):
            st.session_state["load_profile"] = (role, names.index(named))
            st.rerun()
    with n3:
        st.markdown("<div style='height:1.55rem'></div>", unsafe_allow_html=True)
        if st.button("Simpan", key=k("profile_save"), use_container_width=True,
                     disabled=not named):
            st.session_state["save_profile"] = (named, dict(out))
            st.rerun()
    return out


def build_documents(cfg: dict, types: list[str], want_json: bool,
                    want_fields: bool) -> list[tuple[str, bytes]]:
    """Render every requested letter into a temp dir; return (name, bytes)."""
    files: list[tuple[str, bytes]] = []

    with tempfile.TemporaryDirectory() as tmp:
        pattern = str(Path(tmp) / "surat-kuasa-{type}.pdf")
        for doc_type in types:
            cfg["document"]["type"] = doc_type
            path = output_path(pattern, doc_type, many=len(types) > 1, cfg=cfg)
            builder = LetterBuilder(cfg)
            builder.build(path)

            if want_json:
                esign.write_fields_json(
                    path, builder.areas, builder.page_size,
                    extra={"type": doc_type, "label": TEMPLATES[doc_type]["label"]},
                )
            if want_fields and esign.have_pyhanko():
                esign.add_signature_fields(path, builder.areas)

            files.append((path.name, path.read_bytes()))
            sidecar = esign.sidecar_path(path)
            if want_json and sidecar.is_file():
                files.append((sidecar.name, sidecar.read_bytes()))

    return files


@st.cache_data(show_spinner=False, max_entries=12)
def preview_image(cfg_toml: str, doc_type: str, scale: int = 2) -> bytes | None:
    """Render one letter and return its first page as PNG.

    Keyed on the config as TOML, so an unchanged form costs nothing.
    """
    try:
        import pypdfium2
    except ImportError:
        return None

    cfg = tomllib.loads(cfg_toml)
    cfg["document"]["type"] = doc_type
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "preview.pdf"
        LetterBuilder(cfg).build(path)
        pdf = pypdfium2.PdfDocument(path.read_bytes())
        image = pdf[0].render(scale=scale).to_pil()

    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def stash_upload(upload, name: str) -> str:
    """Keep an uploaded file on disk for as long as this session lasts."""
    if upload is None:
        return ""
    folder = st.session_state.get("upload_dir")
    if not folder:
        folder = tempfile.mkdtemp(prefix="sk-upload-")
        st.session_state["upload_dir"] = folder
    path = Path(folder) / f"{name}-{upload.name}"
    if not path.exists():
        path.write_bytes(upload.getvalue())
    return str(path)


def zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Masthead
# --------------------------------------------------------------------------- #

st.markdown(CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="sk-eyebrow">Surat kuasa · perorangan</div>'
    '<h1 class="sk-title">Pilih suratnya, isi datanya, <em>unduh</em>.</h1>'
    '<p class="sk-sub">Format resmi, satu halaman.'
    '<span class="sk-info" tabindex="0" data-tip="Enam belas jenis keperluan '
    'administrasi. Data kamu disimpan di perangkat sendiri; server ini tidak '
    'menyimpan apa pun dan tidak memakai basis data.">i</span></p>',
    unsafe_allow_html=True,
)

presets = preset_configs()

if "base" not in st.session_state:  # shipped example until the browser answers
    apply_base(dict(next(iter(presets.values()), {})), "contoh bawaan")

remembered = recall_from_device()
my_template = recall_template()
profiles = recall_profiles()

pending = st.session_state.pop("save_profile", None)
if pending:
    label, party = pending
    party = {k: v for k, v in party.items() if k != "same_address"}
    party["label"] = label
    profiles = [p for p in profiles if p.get("label") != label] + [party]
    if remember_profiles(profiles):
        st.toast(f"Profil \"{label}\" tersimpan di perangkat ini.")

loading = st.session_state.pop("load_profile", None)

if loading:
    role, index = loading
    if 0 <= index < len(profiles):
        party = {k: v for k, v in profiles[index].items() if k != "label"}
        apply_base(deep_merge(st.session_state["base"], {role: party}),
                   f'profil {profiles[index].get("label", "")}')

shared = setup_from_link()
if shared and not st.session_state.get("link_applied"):
    st.session_state["link_applied"] = True
    link_types = shared.pop("_types")
    st.session_state["types_from_link"] = link_types
    apply_base(deep_merge(st.session_state["base"], shared),
               "setelan dari tautan")
if remembered and not st.session_state.get("restored"):
    st.session_state["restored"] = True
    apply_base(deep_merge(st.session_state["base"], remembered),
               "tersimpan di perangkat ini")

with st.sidebar:
    st.markdown('<div class="sk-eyebrow">Data kamu</div>', unsafe_allow_html=True)
    st.markdown(f'<p class="sk-note">Terisi dari: {st.session_state["base_note"]}</p>',
                unsafe_allow_html=True)
    if remembered:
        line("Tersimpan di perangkat ini.",
             "Data diri, materai, e-sign dan tata letak terisi sendiri saat "
             "kamu kembali. Disimpan sebagai cookie di browser ini, bukan di "
             "server.")
        if st.button("Lupakan data di perangkat ini", use_container_width=True):
            forget_on_device()
            st.session_state.pop("restored", None)
            st.session_state.pop("base", None)
            st.success("Dilupakan. Muat ulang halaman untuk memastikan.")

    uploaded = st.file_uploader("Buka data tersimpan", type=["toml"],
                                help="Berkas .toml yang pernah kamu unduh dari "
                                     "sini, atau yang dipakai versi terminal.")
    if uploaded is not None and st.session_state.get("uploaded_name") != uploaded.name:
        try:
            apply_base(tomllib.loads(uploaded.getvalue().decode("utf-8")),
                       f"berkas {uploaded.name}")
            st.session_state["uploaded_name"] = uploaded.name
            st.rerun()
        except tomllib.TOMLDecodeError:
            st.error("File itu bukan config.toml yang valid.")

    if presets:
        pick = st.selectbox("Mulai dari contoh", ["-"] + list(presets))
        if pick != "-" and st.button("Pakai contoh ini", use_container_width=True):
            apply_base(dict(presets[pick]), f"contoh {pick}")
            st.rerun()

    line("Ada juga versi terminal.",
         "python generate.py memakai config yang sama, bisa membuat banyak "
         "surat sekaligus dan menandatangani PDF dengan sertifikat sendiri.")

base = st.session_state["base"]
rev = st.session_state["form_rev"]
document = dict(base.get("document", {}))
stamp = dict(document.get("stamp", {}))
header_cfg = dict(document.get("header", {}))
footer_cfg = dict(document.get("footer", {}))
esign_cfg = dict(base.get("esign", {}))
layout = dict(base.get("layout", {}))

form_col, preview_col = st.columns([1, 1], gap="large")

# --------------------------------------------------------------------------- #
# Left: the form. The page scrolls normally; nothing traps the scroll.
# --------------------------------------------------------------------------- #

with form_col:
    rule("Keperluan")
    type_keys = sorted(TEMPLATES)
    default_types = st.session_state.get("types_from_link") or [
        document.get("type") if document.get("type") in TEMPLATES else "umum"]
    types = st.multiselect(
        "Jenis surat kuasa", type_keys, default=default_types,
        format_func=lambda k: f"{TEMPLATES[k]['label']}  ({k})",
        key=f"types_{rev}",
        help="Pilih lebih dari satu untuk membuat beberapa surat sekaligus.")

    principal = party_form("principal", "Pemberi kuasa",
                           base.get("principal", {}), rev, profiles=profiles)
    agent = party_form("agent", "Penerima kuasa", base.get("agent", {}), rev,
                       copy_from=principal, profiles=profiles)

    rule("Tempat & tanggal")
    c1, c2 = st.columns(2)
    with c1:
        place = st.text_input("Tempat penandatanganan",
                              value=str(document.get("place", "")
                                        or principal.get("city", "")),
                              key=f"place_{rev}")
        number = st.text_input("Nomor surat (opsional)",
                               value=str(document.get("number", "") or ""),
                               key=f"number_{rev}")
    with c2:
        use_today = st.checkbox("Pakai tanggal hari ini", value=True,
                                key=f"today_{rev}")
        picked = st.date_input("Tanggal", value=dt.date.today(),
                               disabled=use_today, format="YYYY-MM-DD",
                               key=f"date_{rev}")

    rule("Rincian")
    with st.expander("Isi & ketentuan surat"):
        substitution = st.checkbox(
            "Boleh dilimpahkan lagi (hak substitusi)",
            value=bool(document.get("substitution_right", False)),
            key=f"subst_{rev}")
        valid_until = st.text_input(
            "Masa berlaku (opsional)",
            value=str(document.get("valid_until", "") or ""),
            placeholder="Surat kuasa ini berlaku sampai dengan …",
            key=f"valid_{rev}")
        footnote = st.text_input("Catatan kaki (opsional)",
                                 value=str(document.get("footnote", "") or ""),
                                 placeholder="Lampiran: fotokopi KTP …",
                                 key=f"foot_{rev}")
        if len(types) == 1:
            tpl = dict(TEMPLATES[types[0]])
            # A letter you wrote yourself starts from your saved version.
            if types[0] == "custom" and my_template:
                tpl.update({k: my_template[k] for k in ("purpose", "powers",
                                                        "limits")
                            if my_template.get(k)})
            purpose = st.text_area("Maksud kuasa",
                                   value=str(document.get("purpose")
                                             or tpl["purpose"]), height=90,
                                   key=f"purpose_{rev}_{types[0]}")
            powers_text = st.text_area(
                "Rincian wewenang - satu per baris",
                value="\n".join(document.get("powers") or tpl.get("powers", [])),
                height=160, key=f"powers_{rev}_{types[0]}")
            limits = st.text_area(
                "Pembatasan",
                value=str(document.get("limits") or tpl.get("limits", "")),
                height=90, key=f"limits_{rev}_{types[0]}")

            t1, t2 = st.columns([3, 2])
            with t1:
                tpl_label = st.text_input(
                    "Nama template", value=str((my_template or {}).get("label")
                                               or "Template saya"),
                    key=f"tpl_label_{rev}")
            with t2:
                st.markdown("<div style='height:1.55rem'></div>",
                            unsafe_allow_html=True)
                if st.button("Simpan teks ini di perangkat",
                             use_container_width=True):
                    saved = remember_template(
                        tpl_label, purpose,
                        [p.strip() for p in powers_text.splitlines() if p.strip()],
                        limits)
                    if saved:
                        st.success(f"Tersimpan. Pilih jenis \"Custom\" untuk "
                                   f"memakai \"{tpl_label}\" lain kali.")
            if my_template:
                line(f'Tersimpan: {my_template.get("label", "Template saya")}.',
                     'Teks ini terisi sendiri setiap kali jenis "Custom" '
                     'dipilih di perangkat ini.')
        else:
            purpose = powers_text = limits = None
            st.info("Beberapa jenis dipilih, jadi tiap surat memakai teks "
                    "templatenya masing-masing. Pilih satu jenis saja kalau "
                    "mau menulis isinya sendiri.")

    with st.expander("Materai, e-sign & tata letak"):
        stamp_enabled = st.checkbox("Sisakan ruang materai",
                                    value=bool(stamp.get("enabled", True)),
                                    key=f"stamp_on_{rev}")
        stamp_on = st.radio("Materai di sisi", ["principal", "agent", "both"],
                            index=["principal", "agent", "both"].index(
                                str(stamp.get("on", "principal"))),
                            format_func={"principal": "Pemberi kuasa",
                                         "agent": "Penerima kuasa",
                                         "both": "Keduanya"}.get,
                            horizontal=True, disabled=not stamp_enabled,
                            key=f"stamp_side_{rev}")
        s1, s2 = st.columns(2)
        with s1:
            paper = st.selectbox("Ukuran kertas", list(PAGE_SIZES),
                                 index=list(PAGE_SIZES).index(
                                     str(layout.get("paper", "A4")).upper()),
                                 key=f"paper_{rev}")
            font_face = st.selectbox(
                "Huruf surat", list(LETTER_FONTS),
                index=list(LETTER_FONTS).index(
                    str(layout.get("font", "Times-Roman"))
                    if layout.get("font") in LETTER_FONTS else "Times-Roman"),
                format_func=lambda f: LETTER_FONTS[f][0], key=f"face_{rev}",
                help="Surat dinas Indonesia lazimnya Times New Roman atau "
                     "Arial. Courier meniru mesin tik dan dipakai di berkas "
                     "pengadilan Amerika, jadi terlihat tidak biasa di loket "
                     "sini, tapi tersedia kalau memang diminta.")
        with s2:
            font_size = st.slider("Ukuran font", 9.0, 13.0,
                                  float(layout.get("font_size", 11)), step=0.5,
                                  key=f"font_{rev}")
        fit_one_page = st.checkbox("Paksa muat satu halaman",
                                   value=bool(layout.get("fit_one_page", True)),
                                   key=f"fit_{rev}")

        font_file = st.file_uploader("Font sendiri (.ttf)", type=["ttf"],
                                     key=f"ttf_{rev}",
                                     help="Menimpa pilihan huruf di atas. "
                                          "Fontnya ikut tertanam di PDF, jadi "
                                          "surat terlihat sama di mana pun.")
        font_bold_file = None
        if font_file is not None:
            font_bold_file = st.file_uploader("Font tebal (.ttf, opsional)",
                                              type=["ttf"], key=f"ttfb_{rev}")

        st.markdown('<div class="sk-eyebrow" style="margin-top:.8rem">'
                    'Kop &amp; footer</div>', unsafe_allow_html=True)
        header_text = st.text_area(
            "Kop surat (opsional)", value=str(header_cfg.get("text", "") or ""),
            height=80, key=f"head_{rev}",
            placeholder="Baris pertama jadi judul kop\nAlamat, telepon, dst.")
        header_rule = st.checkbox("Garis di bawah kop",
                                  value=bool(header_cfg.get("rule", True)),
                                  key=f"headrule_{rev}",
                                  disabled=not header_text.strip())
        footer_text = st.text_input(
            "Footer halaman (opsional)",
            value=str(footer_cfg.get("text", "") or ""), key=f"foot_p_{rev}")
        page_numbers = st.checkbox("Nomor halaman",
                                   value=bool(footer_cfg.get("page_numbers", False)),
                                   key=f"pagenum_{rev}")

        st.markdown('<div class="sk-eyebrow" style="margin-top:.8rem">'
                    'Tanda tangan elektronik</div>', unsafe_allow_html=True)
        anchors = st.checkbox(
            "Anchor tak terlihat", value=bool(esign_cfg.get("anchors", True)),
            key=f"anch_{rev}",
            help=f"Menyisipkan {DEFAULT_ANCHORS['principal']} dan "
                 f"{DEFAULT_ANCHORS['agent']} supaya DocuSign/Adobe Sign "
                 "menaruh field-nya sendiri.")
        want_json = st.checkbox(
            "Koordinat tanda tangan (.fields.json)",
            value=bool(esign_cfg.get("fields_json", False)), key=f"json_{rev}",
            help="Posisi tiap area tanda tangan, untuk dipakai lewat API.")
        want_fields = st.checkbox(
            "Signature field kosong (AcroForm)",
            value=bool(esign_cfg.get("signature_fields", False)),
            key=f"acro_{rev}", disabled=not esign.have_pyhanko(),
            help="Butuh pyhanko terpasang di server." if not esign.have_pyhanko()
                 else "Kotak klik-untuk-tanda-tangan di Acrobat.")

    rule("Tanda tangan & materai")
    st.markdown('<div class="sk-eyebrow">Tanda tangan elektronik</div>',
                unsafe_allow_html=True)
    line("<b>Privy</b> - unggah PDF, taruh kotak tanda tangan.",
         "Masuk ke akun Privy, unggah PDF-nya, seret kotak tanda tangan ke "
         "ruang kosong di atas nama, lalu undang penerima kuasa lewat email "
         "atau nomor HP-nya untuk ikut menandatangani.")
    line("<b>DocuSign / Adobe Sign</b> - anchor otomatis.",
         "Aktifkan Anchor tak terlihat sebelum membuat surat. Pakai anchor "
         "string /ttd_pemberi/ dan /ttd_penerima/; field tanda tangan menempel "
         "sendiri di posisi yang benar tanpa menyeret apa pun.")
    line("<b>Lewat API</b> - koordinat siap pakai.",
         "Aktifkan Koordinat tanda tangan. Berkas .fields.json memuat halaman "
         "dan kotak tiap area dalam dua sistem koordinat, siap dipakai untuk "
         "DocuSign tabs atau endpoint sejenis.")

    st.markdown('<div class="sk-eyebrow" style="margin-top:1rem">e-Meterai</div>',
                unsafe_allow_html=True)
    line("Ruang materai dibiarkan kosong tanpa garis.",
         "Karena kosong, e-meterai bisa ditempel persis di situ tanpa menimpa "
         "apa pun; kalau dicetak, materai tempel dibubuhkan di tempat yang sama.")
    line("Harga nominal Rp10.000, beda hanya biaya layanan.",
         "Nominal meterai elektronik ditetapkan pemerintah. Sebagian "
         "distributor menambah sekitar Rp2.500 per keping. Menawar di bawah "
         "Rp10.000 bukan penghematan: DJP menyebut meterai di bawah nominal "
         "patut dicurigai palsu.")
    line("Termurah: beli di distributor resmi Peruri.",
         "Bandingkan biaya layanan antar distributor resmi, ambil paket banyak "
         "keping kalau sering dipakai, lalu bubuhkan sendiri lewat portal "
         "distributor tersebut.")
    line("Kadang tidak wajib.",
         "Meterai hanya wajib untuk dokumen yang dipakai sebagai alat bukti "
         "perdata. Banyak loket administrasi menerima surat kuasa tanpa "
         "meterai; tanyakan dulu ke instansi tujuan sebelum membeli.")

    st.markdown(
        '<p class="sk-note" style="margin-top:1.6rem">Template, bukan nasihat '
        'hukum.<span class="sk-info" tabindex="0" data-tip="Sebagian instansi '
        'mewajibkan formulir kuasa versi mereka sendiri, jadi cek dulu ke loket '
        'tujuan. Dokumen dibuat sementara di memori server lalu dihapus.">i'
        '</span></p>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Assemble the config from the form
# --------------------------------------------------------------------------- #

cfg = {
    "document": {
        "type": types[0] if types else "umum",
        "number": number,
        "place": place,
        "date": "auto" if use_today else picked.isoformat(),
        "substitution_right": substitution,
        "valid_until": valid_until,
        "footnote": footnote,
        "stamp": {"enabled": stamp_enabled, "on": stamp_on,
                  "width_cm": float(stamp.get("width_cm", 3.0)),
                  "height_cm": float(stamp.get("height_cm", 2.0))},
        "header": {"text": header_text, "rule": header_rule,
                   "align": str(header_cfg.get("align", "center"))},
        "footer": {"text": footer_text, "page_numbers": page_numbers},
    },
    "principal": principal,
    "agent": agent,
    "esign": {"anchors": anchors, "fields_json": want_json,
              "signature_fields": want_fields},
    "layout": {"paper": paper, "font_size": font_size,
               "fit_one_page": fit_one_page,
               "font": font_face, "font_bold": LETTER_FONTS[font_face][1],
               "font_file": stash_upload(font_file, "regular"),
               "font_bold_file": stash_upload(font_bold_file, "bold")},
}
if len(types) == 1 and purpose is not None:
    cfg["document"]["purpose"] = purpose
    cfg["document"]["powers"] = [p.strip() for p in powers_text.splitlines()
                                 if p.strip()]
    cfg["document"]["limits"] = limits

missing = [role for role, party in (("pemberi kuasa", principal),
                                    ("penerima kuasa", agent))
           if not party.get("name") and not party.get("blank")]
ready = bool(types) and not missing
cfg_toml = dump_toml(cfg)


@st.dialog("Bagikan setelan", width="large")
def show_share(types: list[str], cfg: dict, rev: int) -> None:
    line("Tautan setelan, tanpa data pribadi.",
         "Yang dibawa: jenis surat, tempat, materai, teks kuasa, kop, footer, "
         "e-sign dan tata letak. Nama, NIK dan alamat tidak ikut, karena "
         "tautan mengendap di riwayat chat dan browser.")
    share_url = build_share_link(types, cfg)
    png = qr_png(share_url)

    if png:
        q1, q2 = st.columns([1, 1])
        with q1:
            st.image(png, width=220)
        with q2:
            line("Pindai atau simpan QR ini.",
                 "Memindainya membuka app dengan setelan yang sama, tanpa data "
                 "pribadi.")
            st.download_button("Unduh QR (PNG)", png,
                               file_name="surat-kuasa-setelan.png",
                               mime="image/png", use_container_width=True,
                               key=f"qr_dl_{rev}")
    else:
        line(f"Setelan ini terlalu panjang untuk satu QR "
             f"({len(share_url)} karakter).",
             "Satu QR menampung sekitar 2.900 byte menurut standarnya, bukan "
             "batasan app ini. Tautannya tetap bisa disalin, atau kirim berkas "
             "config.toml.")

    if st.checkbox("Lihat tautannya", key=f"show_link_{rev}"):
        st.code(share_url, language=None)
        line(f"Panjang {len(share_url)} karakter.",
             "Setelan dipadatkan dulu sebelum masuk tautan, jadi teks kuasa, "
             "kop dan footer pun ikut tanpa membuat tautannya meledak.")

    line("Surat jadi: kirim PDF. Data lengkap: kirim config.toml.",
         "Berkas lebih aman daripada tautan untuk data pribadi, karena tidak "
         "tertinggal di riwayat chat atau browser.")


@st.dialog("Pratinjau", width="large")
def show_fullscreen(toml_text: str, doc_type: str) -> None:
    png = preview_image(toml_text, doc_type, scale=4)
    if png:
        st.markdown('<div class="sk-sheet">', unsafe_allow_html=True)
        st.image(png, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption("Gambar bisa diperbesar lewat ikon di pojok gambar.")


# --------------------------------------------------------------------------- #
# Right: actions first, then the sheet. The column sticks, so the actions stay
# reachable no matter how far the form is scrolled.
# --------------------------------------------------------------------------- #

with preview_col:
    head, share_btn = st.columns([3, 2])
    with head:
        st.markdown('<div class="sk-eyebrow" style="padding-top:.45rem">'
                    'Pratinjau langsung</div>', unsafe_allow_html=True)
    with share_btn:
        if st.button("Bagikan setelan", use_container_width=True,
                     disabled=not types):
            show_share(types, cfg, rev)

    def draw_preview(doc_type: str) -> None:
        png = preview_image(cfg_toml, doc_type)
        if not png:
            st.markdown('<p class="sk-note">Pratinjau butuh pypdfium2 '
                        '(<code>pip install pypdfium2</code>).</p>',
                        unsafe_allow_html=True)
            return
        st.markdown('<div class="sk-sheet">', unsafe_allow_html=True)
        st.image(png, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(f'<p class="sk-note">{TEMPLATES[doc_type]["label"]} - '
                    'halaman 1</p>', unsafe_allow_html=True)
        if st.button("Layar penuh", use_container_width=True,
                     key=f"full_{rev}_{doc_type}"):
            show_fullscreen(cfg_toml, doc_type)

    if not ready:
        st.markdown('<p class="sk-note">Pratinjau muncul setelah nama '
                    'terisi.</p>', unsafe_allow_html=True)
    elif len(types) == 1:
        draw_preview(types[0])
    elif len(types) <= 5:
        # A tab per letter: every one is visible without hunting for it.
        for tab, doc_type in zip(st.tabs(types), types):
            with tab:
                draw_preview(doc_type)
    else:
        # Past a handful, rendering them all on every keystroke is wasteful.
        shown = st.selectbox("Lihat pratinjau", types, key=f"pv_{rev}",
                             format_func=lambda t: TEMPLATES[t]["label"],
                             label_visibility="collapsed")
        draw_preview(shown)
        st.markdown(f'<p class="sk-note">{len(types)} jenis dipilih; semuanya '
                    'ikut dibuat saat kamu menekan Buat surat.</p>',
                    unsafe_allow_html=True)

    rule("Buat surat")
    if missing:
        st.warning(f"Isi nama {' dan '.join(missing)}, atau centang "
                   "\"Kosongkan\" untuk mencetak blanko.")
    elif not types:
        st.warning("Pilih dulu jenis suratnya.")

    if st.button("Buat surat", type="primary", use_container_width=True,
                 disabled=not ready):
        with st.spinner("Membuat dokumen..."):
            st.session_state["files"] = build_documents(
                dict(cfg), types, want_json, want_fields)
        if st.session_state.get(f"remember_{rev}", True):
            remember_on_device(cfg)  # so the form fills itself next time

    st.checkbox("Ingat data ini di perangkat ini", value=True,
                key=f"remember_{rev}",
                help="Disimpan sebagai cookie di browser ini, bukan di server. "
                     "Bisa dihapus lewat sidebar.")

    files = st.session_state.get("files")
    if files:
        d1, d2 = st.columns(2)
        with d1:
            if len(files) == 1:
                st.download_button("Unduh PDF", files[0][1],
                                   file_name=files[0][0],
                                   mime="application/pdf",
                                   use_container_width=True)
            else:
                st.download_button("Unduh semua (ZIP)", zip_bytes(files),
                                   file_name="surat-kuasa.zip",
                                   mime="application/zip",
                                   use_container_width=True)
        with d2:
            st.download_button(
                "Simpan config.toml", cfg_toml, file_name="config.toml",
                mime="text/plain", use_container_width=True,
                help="Simpan di perangkatmu; muat lagi lewat sidebar, atau "
                     "pakai: python generate.py -c config.toml")
        if len(files) > 1:
            with st.expander(f"{len(files)} berkas dalam paket"):
                for name, data in files:
                    st.markdown(f'<p class="sk-note">{name} - '
                                f'{len(data) / 1024:.1f} KB</p>',
                                unsafe_allow_html=True)
