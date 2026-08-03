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
SHARED_ADDRESS = ("address", "rt_rw", "village", "district", "city", "province")
COOKIE = "sk_details_v1"
COOKIE_TEMPLATE = "sk_template_v1"

st.set_page_config(page_title="Surat Kuasa", page_icon="📄", layout="wide")


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
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;1,6..72,300&family=Public+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

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

html, body, [data-testid="stAppViewContainer"] {
  font-family: 'Public Sans', system-ui, -apple-system, sans-serif;
}
[data-testid="stAppViewContainer"] .block-container {
  padding-top: 2rem; padding-bottom: 4rem; max-width: 1440px;
}

/* ---- masthead ---------------------------------------------------------- */
.sk-eyebrow {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.68rem; letter-spacing: 0.22em; text-transform: uppercase;
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
  font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem;
  letter-spacing: 0.2em; text-transform: uppercase; color: var(--muted);
  white-space: nowrap;
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
[data-baseweb="tag"] {
  border-radius: 2px !important; font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem !important;
}

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
  font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem;
  letter-spacing: 0.04em; color: var(--muted); margin: 0.35rem 0 0;
}
.sk-note b { color: var(--cap); font-weight: 500; }
.sk-step { font-size: 0.86rem; color: #2C3543; margin: 0 0 .45rem; }
.sk-step b { color: #141A23; font-weight: 600; }

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
  .stButton button:hover, .stDownloadButton button:hover { transform: none; }
}
</style>
"""


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
REMEMBERED_LAYOUT = ("paper", "font_size", "fit_one_page")
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

SHARE_KEYS = {"t": "types", "p": "place", "st": "stamp_on", "pa": "paper",
              "fs": "font_size", "es": "esign", "bl": "blank"}


def build_share_link(types: list[str], cfg: dict) -> str:
    esign_bits = "".join(flag for flag, on in
                         (("a", cfg["esign"]["anchors"]),
                          ("j", cfg["esign"]["fields_json"]),
                          ("f", cfg["esign"]["signature_fields"])) if on)
    blank = [role for role in ("principal", "agent")
             if cfg.get(role, {}).get("blank")]
    params = {
        "t": ",".join(types),
        "p": cfg["document"].get("place", ""),
        "st": cfg["document"]["stamp"]["on"] if cfg["document"]["stamp"]["enabled"] else "none",
        "pa": cfg["layout"]["paper"],
        "fs": str(cfg["layout"]["font_size"]),
    }
    if esign_bits:
        params["es"] = esign_bits
    if blank:
        params["bl"] = ",".join(blank)

    base = str(getattr(st.context, "url", "")) or "/"
    base = base.split("?")[0].split("#")[0]
    return f"{base}?{urlencode({k: v for k, v in params.items() if v})}"


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
               copy_from: dict | None = None) -> dict:
    """Render the inputs for one party and return what the user typed."""
    rule(title)
    k = lambda field: f"{role}_{field}_{rev}"  # noqa: E731

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
    '<p class="sk-sub">Lima belas keperluan administrasi, format resmi, satu '
    'halaman. Data disimpan di perangkatmu sendiri - server ini tidak menyimpan '
    'apa pun.</p>',
    unsafe_allow_html=True,
)

presets = preset_configs()

if "base" not in st.session_state:  # shipped example until the browser answers
    apply_base(dict(next(iter(presets.values()), {})), "contoh bawaan")

remembered = recall_from_device()
my_template = recall_template()

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
    st.markdown(f'<p class="sk-note">Sumber: {st.session_state["base_note"]}</p>',
                unsafe_allow_html=True)
    if remembered:
        kept = ", ".join(k for k in ("principal", "agent", "document",
                                     "esign", "layout") if k in remembered)
        st.markdown('<p class="sk-note">Diingat di perangkat ini - data diri, '
                    'materai, e-sign dan tata letak terisi sendiri saat kamu '
                    f'kembali.<br>Bagian tersimpan: {kept}.</p>',
                    unsafe_allow_html=True)
        if st.button("Lupakan data di perangkat ini", use_container_width=True):
            forget_on_device()
            st.session_state.pop("restored", None)
            st.session_state.pop("base", None)
            st.success("Dilupakan. Muat ulang halaman untuk memastikan.")

    uploaded = st.file_uploader("Muat config.toml", type=["toml"],
                                label_visibility="visible")
    if uploaded is not None and st.session_state.get("uploaded_name") != uploaded.name:
        try:
            apply_base(tomllib.loads(uploaded.getvalue().decode("utf-8")),
                       f"berkas {uploaded.name}")
            st.session_state["uploaded_name"] = uploaded.name
            st.rerun()
        except tomllib.TOMLDecodeError:
            st.error("File itu bukan config.toml yang valid.")

    if presets:
        pick = st.selectbox("Contoh bawaan", ["-"] + list(presets))
        if pick != "-" and st.button("Pakai contoh ini", use_container_width=True):
            apply_base(dict(presets[pick]), f"contoh {pick}")
            st.rerun()

    st.markdown('<p class="sk-note">Dari terminal: <code>python generate.py</code> '
                'memakai config yang sama.</p>', unsafe_allow_html=True)

base = st.session_state["base"]
rev = st.session_state["form_rev"]
document = dict(base.get("document", {}))
stamp = dict(document.get("stamp", {}))
esign_cfg = dict(base.get("esign", {}))
layout = dict(base.get("layout", {}))

form_col, preview_col = st.columns([3, 2], gap="large")

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
                           base.get("principal", {}), rev)
    agent = party_form("agent", "Penerima kuasa", base.get("agent", {}), rev,
                       copy_from=principal)

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
                st.markdown(
                    f'<p class="sk-note">Template tersimpan: '
                    f'{my_template.get("label", "Template saya")} - muncul saat '
                    'jenis "Custom" dipilih.</p>', unsafe_allow_html=True)
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
        with s2:
            font_size = st.slider("Ukuran font", 9.0, 13.0,
                                  float(layout.get("font_size", 11)), step=0.5,
                                  key=f"font_{rev}")
        fit_one_page = st.checkbox("Paksa muat satu halaman",
                                   value=bool(layout.get("fit_one_page", True)),
                                   key=f"fit_{rev}")

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
    },
    "principal": principal,
    "agent": agent,
    "esign": {"anchors": anchors, "fields_json": want_json,
              "signature_fields": want_fields},
    "layout": {"paper": paper, "font_size": font_size,
               "fit_one_page": fit_one_page},
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


@st.dialog("Pratinjau", width="large")
def show_fullscreen(toml_text: str, doc_type: str) -> None:
    png = preview_image(toml_text, doc_type, scale=3)
    if png:
        st.markdown('<div class="sk-sheet">', unsafe_allow_html=True)
        st.image(png, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Right: actions first, then the sheet. The column sticks, so the actions stay
# reachable no matter how far the form is scrolled.
# --------------------------------------------------------------------------- #

with preview_col:
    st.markdown('<div class="sk-eyebrow">Pratinjau langsung</div>',
                unsafe_allow_html=True)

    if missing:
        st.warning(f"Isi nama {' dan '.join(missing)}, atau centang "
                   "\"Kosongkan\" untuk mencetak blanko.")
    elif not types:
        st.warning("Pilih dulu jenis suratnya.")

    if st.button("Buat surat", type="primary", use_container_width=True,
                 disabled=not ready):
        with st.spinner("Membuat dokumen…"):
            st.session_state["files"] = build_documents(
                dict(cfg), types, want_json, want_fields)
        if st.session_state.get(f"remember_{rev}", True):
            remember_on_device(cfg)  # so the form fills itself next time

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

    st.checkbox("Ingat data ini di perangkat ini", value=True,
                key=f"remember_{rev}",
                help="Disimpan sebagai cookie di browser ini, bukan di server. "
                     "Bisa dihapus lewat sidebar.")

    with st.expander("Bagikan setelan ini"):
        st.markdown('<p class="sk-note">Tautan ini membawa jenis surat, tempat, '
                    'materai, e-sign dan tata letak. Nama, NIK dan alamat tidak '
                    'ikut - penerima tautan mengisi datanya sendiri.</p>',
                    unsafe_allow_html=True)
        st.code(build_share_link(types, cfg), language=None)
        st.markdown('<p class="sk-note">Mau berbagi surat yang sudah jadi? '
                    'Kirim PDF-nya langsung. Mau berbagi data lengkap dengan '
                    'orang yang kamu percaya? Kirim berkas config.toml, bukan '
                    'tautan.</p>', unsafe_allow_html=True)

    if ready:
        png = preview_image(cfg_toml, types[0])
        if png:
            st.markdown('<div class="sk-sheet">', unsafe_allow_html=True)
            st.image(png, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            note = f"{TEMPLATES[types[0]]['label']} · halaman 1"
            if len(types) > 1:
                note += f" · {len(types) - 1} jenis lain ikut dibuat"
            st.markdown(f'<p class="sk-note">{note}</p>', unsafe_allow_html=True)
            if st.button("Lihat layar penuh", use_container_width=True):
                show_fullscreen(cfg_toml, types[0])
        else:
            st.markdown('<p class="sk-note">Pratinjau butuh pypdfium2 '
                        '(<code>pip install pypdfium2</code>).</p>',
                        unsafe_allow_html=True)

    if files and len(files) > 1:
        with st.expander(f"{len(files)} berkas dalam paket"):
            for name, data in files:
                st.markdown(f'<p class="sk-note">{name} - '
                            f'{len(data) / 1024:.1f} KB</p>',
                            unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Signing and stamping: what to do with the PDF once it exists
# --------------------------------------------------------------------------- #

rule("Tanda tangan & materai")
sign_col, stamp_col = st.columns(2, gap="large")

with sign_col:
    st.markdown('<div class="sk-eyebrow">Tanda tangan elektronik</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="sk-step"><b>Privy</b> - masuk ke akun Privy, unggah PDF-nya, '
        'lalu seret kotak tanda tangan ke ruang kosong di atas nama. '
        'Undang penerima kuasa lewat email/nomor HP-nya untuk ikut tanda '
        'tangan.</p>'
        '<p class="sk-step"><b>DocuSign / Adobe Acrobat Sign</b> - aktifkan '
        '“Anchor tak terlihat” di atas sebelum membuat surat. Pada DocuSign '
        'pakai <i>anchor string</i> <code>/ttd_pemberi/</code> dan '
        '<code>/ttd_penerima/</code>; field tanda tangan menempel sendiri di '
        'posisi yang benar tanpa menyeret apa pun.</p>'
        '<p class="sk-step"><b>Lewat API</b> - aktifkan “Koordinat tanda '
        'tangan”. Berkas <code>.fields.json</code> memuat halaman dan '
        'kotak tiap area dalam dua sistem koordinat, siap dipakai untuk '
        'DocuSign tabs atau endpoint sejenis.</p>',
        unsafe_allow_html=True)

with stamp_col:
    st.markdown('<div class="sk-eyebrow">e-Meterai</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sk-step">Ruang materai di surat ini sengaja dibiarkan '
        '<b>kosong tanpa garis</b>, jadi e-meterai bisa ditempel persis di '
        'situ tanpa menimpa apa pun - atau materai tempel dibubuhkan setelah '
        'dicetak.</p>'
        '<p class="sk-step"><b>Harga</b> - nominal meterai elektronik '
        'Rp10.000 dan itu ditetapkan pemerintah; yang berbeda antar penjual '
        'hanya biaya layanannya (sebagian distributor menambah sekitar '
        'Rp2.500 per keping). Menawar di bawah Rp10.000 bukan penghematan: '
        'DJP menyebut meterai di bawah nominal patut dicurigai palsu.</p>'
        '<p class="sk-step"><b>Cara termurah</b> - beli langsung di distributor '
        'resmi Peruri (daftarnya ada di situs Peruri) dan bandingkan biaya '
        'layanannya, lalu bubuhkan sendiri lewat portal distributor tersebut. '
        'Paket banyak keping biasanya menurunkan biaya layanan per '
        'dokumen.</p>'
        '<p class="sk-step"><b>Kapan boleh dilewati</b> - meterai hanya wajib '
        'untuk dokumen yang dipakai sebagai alat bukti perdata. Banyak loket '
        'administrasi menerima surat kuasa tanpa meterai; tanyakan dulu ke '
        'instansi tujuan sebelum membeli.</p>',
        unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #

st.markdown(
    '<p class="sk-note" style="margin-top:2.5rem">Surat ini template, bukan '
    'nasihat hukum. Sebagian instansi mewajibkan formulir kuasa versi mereka '
    'sendiri - cek dulu ke loket tujuan. Dokumen dibuat sementara di memori '
    'server lalu dihapus; tidak ada basis data.</p>',
    unsafe_allow_html=True,
)
