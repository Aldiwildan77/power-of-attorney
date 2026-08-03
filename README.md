# Surat Kuasa Generator

Generates Indonesian power-of-attorney letters (*surat kuasa*) as PDF. The
layout follows `contoh-sk-umum-perorangan.pdf` from suratkuasa.com: title,
principal and agent identities, the `K H U S U S` rule, the granted powers,
closing, and a signature block with a stamp-duty (materai) placeholder.

The letter itself is Indonesian; the CLI, config keys and docs are English.

## Install

```bash
pip install -r requirements.txt          # web UI + CLI
pip install -r requirements-cli.txt      # CLI only (just reportlab)
pip install pyhanko                      # optional: signature fields + signing
```

Python 3.11+ (uses the stdlib `tomllib`).

## Web UI

```bash
streamlit run app.py
```

The page scrolls as one and the right column sticks, so the **live preview**
and the actions stay in view while you fill the form. The preview re-renders as
you type (cached, so an unchanged form costs nothing); "Lihat layar penuh"
opens the page at full size.

- **It remembers your whole setup.** Tick "Ingat data ini di perangkat ini" and
  both parties, the place of signing, the materai side, the e-sign switches
  (anchors, `.fields.json`, AcroForm fields) and the page setup all come back
  next visit - compressed into a cookie in your own browser, never a database.
  A letter number and a fixed date are deliberately left out; they belong to one
  document, not to your setup. "Lupakan data di perangkat ini" in the sidebar
  clears everything. You can also download a `config.toml`, keep it, and load it
  again later (that same file works with the CLI).
- **Shareable setup link.** "Bagikan setelan ini" gives a URL carrying the
  letter type, place, materai side, e-sign switches and page setup, so a
  colleague opens the app already configured and fills in their own details.
  Names, NIK and addresses are never in the link: a URL survives in chat logs
  and browser history. To share a finished letter, send the PDF; to hand your
  full details to someone you trust, send the `config.toml` file instead.
- **Write your own letter.** Pick the `custom` type, write the purpose, the
  numbered powers and the limits, then "Simpan teks ini di perangkat" keeps that
  wording on your device under a name you choose. It reappears the next time you
  pick `custom`.
- **Less typing.** "Alamat sama dengan pemberi kuasa" copies the address across,
  the place of signing defaults to your city, and a NIK that isn't 16 digits is
  flagged as you type.
- **Blank forms.** "Kosongkan" turns either party into dotted lines to fill in
  by hand.
- **Signing help.** A panel at the bottom explains what to do next in Privy,
  DocuSign and Adobe Sign, and how the materai space works.

"Buat surat" produces one PDF, or a ZIP when several types are selected.
Letters are rendered in a temporary directory and deleted right after the
download is handed over; nothing is written to the server's disk and nothing is
logged.

### Deploying it for free

- **Streamlit Community Cloud** - point it at the GitHub repo, main file
  `app.py`. It reads `requirements.txt` by itself. Free tier sleeps when idle
  and wakes on the next visit.
- **Hugging Face Space** - create a Space with SDK `streamlit`, push these
  files, done. Same `requirements.txt`.

Both run the app on someone else's server, so the NIK and addresses typed into
the form travel over the network (as they already do with any Streamlit app -
widget values go to the server process). Nothing is stored there: no database,
no files, no logs of the form. For sensitive data, run `streamlit run app.py`
locally or use the CLI, and then nothing leaves the machine at all.

## The normal flow

Fill in your details once in `config.toml`, then pick a letter and generate:

```bash
python generate.py            # no arguments -> interactive menu
```

The menu asks, in order: which config holds your details (`config.toml` plus
anything in `examples/`), which letter you need (numbered 1-15; comma-separated
for several, or type `all`), whether the agent's / your own details should be
left blank, whether to edit the details (field by field, Enter keeps the
current value), place, date, and the output folder. Press Enter to accept the
value in brackets.

After editing it offers to save everything back to a config file - the same one
or a new name. Saving rewrites the file from the values, so a hand-written
config trades its comments for the new data; it asks before overwriting.

## Direct mode

```bash
python generate.py -t bank
python generate.py -t skck --date 2026-06-01 --place Bandung
python generate.py -t skck,bank,hr -d output/august
python generate.py --all --blank-agent
python generate.py --list-types
```

| Flag | Purpose |
| --- | --- |
| `-c, --config` | config file `.toml` / `.json` / `.yaml` (default `config.toml`) |
| `-t, --type` | letter type; comma-separated for several, or `all` |
| `--all` | generate every letter type |
| `-o, --output` | output path or pattern, e.g. `out/{type}.pdf` |
| `-d, --dir` | output folder (keeps the config's file pattern) |
| `--blank-agent` | agent details become dotted lines (fill-in form) |
| `--blank-principal` | principal details become dotted lines |
| `--date` | override `[document].date` |
| `--place` | override `[document].place` |
| `--esign` | anchors + `.fields.json` + empty signature fields |
| `--sign P12` | sign the PDF (PAdES) with a PKCS#12 certificate |
| `--sign-as` | which field to sign: `principal` (default) or `agent` |
| `--sign-pass` | PKCS#12 passphrase (prefer the env var, see below) |
| `-i, --interactive` | force the interactive menu |
| `--list-types` | list the letter types |

Output is always PDF; another extension is replaced with `.pdf`.

## Several letters at once

```bash
python generate.py -t skck,bank,hr -o "output/{type}.pdf"
python generate.py --all -d output/blank-forms
```

`{type}` in `-o` is replaced by the type code; `{date}`, `{principal}` and
`{agent}` work too. Without a `{type}` placeholder the type code is appended to
the file name (`sk.pdf` -> `sk-skck.pdf`, `sk-bank.pdf`, …) so nothing gets
overwritten. Custom `purpose` / `powers` / `limits` in the config are skipped
in batch runs - each letter uses its own template text - and the reason is
printed to stderr.

## Blank forms

```bash
python generate.py --blank-agent
python generate.py --all --blank-agent -d output/blank-forms
```

The blanked party's data becomes dotted lines, including the name above the
signature (`( .................... )`). Same as `blank = true` under
`[principal]` / `[agent]`.

Standard blank rows: Nama, Alamat, Kelurahan/Kecamatan, Kota/Provinsi, NIK.
Add more with `blank_fields`:

```toml
[agent]
blank = true
blank_fields = ["birth", "occupation", "phone"]
```

## E-signature (Privy, DocuSign, Adobe Sign, …)

The PDF is a plain, unencrypted file with a real text layer, so it uploads to
any e-sign platform as-is. `--esign` prepares it so you don't have to place
fields by hand:

```bash
python generate.py -t skck --esign
```

That produces three things:

- **Invisible anchor strings** on each signature area - `/ttd_pemberi/` and
  `/ttd_penerima/` by default (configurable). They are never printed (PDF text
  render mode 3) but are extractable, which is what DocuSign `anchorString` and
  Adobe Sign text tags look for.
- **`<name>.fields.json`** next to the PDF, listing every signature area with
  its page and rectangle in both coordinate systems - `rect` (origin
  bottom-left, for Acrobat/pyHanko) and `rect_top_left` (origin top-left, for
  DocuSign tabs, Privy and web viewers). Feed it to the API instead of guessing
  positions.
- **Empty AcroForm signature fields** named `PemberiKuasa` and `PenerimaKuasa`,
  so Acrobat shows a click-to-sign box. Needs `pip install pyhanko`; without it
  this step is skipped with a note and the other two still work.

### Signing it yourself (PAdES)

```bash
export PKCS12_PASSPHRASE='…'
python generate.py -t skck --esign --sign cert.p12 --sign-as principal
```

Signs with your PKCS#12 certificate; the result validates as intact and
covering the whole file. The other party's field stays empty for a
counter-signature. Passphrase resolution order: `--sign-pass`, then the
`PKCS12_PASSPHRASE` env var, then an interactive prompt - prefer the last two,
since a passphrase on the command line is visible to other processes on the
machine.

### Materai / e-meterai

The e-meterai nominal is fixed at Rp10.000 by the government; what differs
between sellers is the service fee on top (some official distributors add about
Rp2.500 per stamp). Anything cheaper than the nominal is a red flag - the tax
office warns that below-nominal meterai are likely counterfeit. So the cheapest
honest route is to buy from an official Peruri distributor with the lowest
service fee, in a bundle if you need several, and affix it yourself. Meterai is
only required for documents used as civil evidence; many counters accept a
surat kuasa without one, so ask the office first.

`[document.stamp]` only reserves blank space (`width_cm` × `height_cm`, default
3 × 2 cm) on the chosen side; nothing is drawn there. A printed copy takes a
physical stamp, an e-signed one takes the e-meterai overlay, and the reserved
rectangle shows up in `.fields.json` as the area flagged `holds_stamp`. Set
`image` to paste a stamp picture in instead.

## Letter types

`dukcapil`, `bpjs_tk`, `bpjs_kes`, `pajak`, `imigrasi`, `skck`, `kendaraan`,
`bank`, `hr`, `pendidikan`, `asuransi`, `instansi`, `utilitas`,
`ambil_dokumen`, `umum`, plus `custom` for a letter you write
yourself - the text of each lives in `templates.py`.

## Config

- `[document]` - `type`, `number`, `place`, `date`, `substitution_right`,
  `valid_until`, `clause_label`, `footnote`. `purpose` / `powers` / `limits`
  override the template text when set.
- `[document.stamp]` - `enabled`, `on` (`principal` | `agent` | `both`),
  `width_cm`, `height_cm`, `image` (optional PNG/JPG to paste in).
- `[esign]` - `anchors`, `anchor_principal`, `anchor_agent`, `fields_json`,
  `signature_fields`. `--esign` switches the three toggles on at once.
- `[principal]` and `[agent]` - identities. Optional fields (`birth`,
  `occupation`, `position`, `phone`) are skipped when empty. `attach_id_copy`
  prints "(fotokopi KTP terlampir)"; `show_nik_on_signature` prints the NIK
  under the name in the signature block; `blank` / `blank_fields` drive the
  fill-in form.
- `[output]` - defaults only: `dir` and `pattern`. `-o` and `-d` override them.
- `[layout]` - `paper` (`A4` | `F4` | `LETTER` | `LEGAL`), margins, font,
  `font_size`, `signature_space_cm`.

### Single-page auto-fit

`[layout].fit_one_page` (default `true`) first tightens the gaps between
blocks, then steps the font down to `font_size_min` (default 8.5) so the
signature block never ends up stranded on a second page. Raise `font_size_min`
if you would rather have two pages than small type, or set `fit_one_page` to
`false` to keep the spacing and font exactly as configured.

## Example configs

Everything in `examples/` uses fictional data and runs as-is:

| File | Shows |
| --- | --- |
| `skck-personal.toml` | the common case, plain template text |
| `bank-card-pickup.toml` | letter number, expiry, strict limits, NIK under the signature |
| `hr-employment-letter.toml` | hand-written `powers`, employer named |
| `vehicle-tax.toml` | F4 paper, plate number and vehicle named |
| `diploma-pickup.toml` | no stamp duty, student number named |
| `blank-agent-forms.toml` | your details filled, agent blank + `blank_fields` |
| `general-minimal.json` | JSON format, smallest possible config |
| `dukcapil.yaml` | YAML format (needs `pip install pyyaml`) |

```bash
python generate.py -c examples/bank-card-pickup.toml
python generate.py -c examples/blank-agent-forms.toml --all
```

## Layout

```
generate.py       CLI + PDF renderer (reportlab)
app.py            Streamlit web UI (same renderer)
esign.py          field coordinates, AcroForm fields, PAdES signing
templates.py      the 15 letter templates
config.toml       your details (the default config)
examples/         ready-to-run configs per scenario
output/           generated PDFs (git-ignored)
```

## Notes

- The signature area is left blank on purpose; the materai and the wet
  signature go on the printed copy, or come from the e-sign platform.
- Keep certificates out of the repo - `.gitignore` already excludes `*.p12`,
  `*.pfx`, `*.pem`, `*.key` and `.env`.
- Some offices insist on their own power-of-attorney form - check before
  relying on this one.
