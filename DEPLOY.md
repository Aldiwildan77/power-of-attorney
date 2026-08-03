# Deploying the web UI

The app is a single Streamlit process with no database and no writable state:
letters are rendered into a temp directory, streamed to the browser, and
deleted. Whatever you type is kept in your own browser (a cookie) or in a
`config.toml` you download. That makes every option below a plain "run one
process" deploy.

## Streamlit Community Cloud — free, least work

1. Push this repo to GitHub (public repo on the free tier).
2. Go to share.streamlit.io → **Create app** → pick the repo, branch, and
   `app.py` as the main file.
3. Advanced settings → Python 3.12.
4. Deploy. It installs `requirements.txt` on its own.

Free apps sleep after a period without visitors and wake on the next request,
so the first hit after idle takes a few seconds.

## Hugging Face Spaces — free, no GitHub required

1. Create a Space → SDK **Streamlit** → hardware "CPU basic (free)".
2. Push these files to the Space repo.
3. The Space's own `README.md` must start with the frontmatter below (keep the
   project README underneath it, or use a separate one):

```yaml
---
title: Surat Kuasa
emoji: 📄
colorFrom: indigo
colorTo: gray
sdk: streamlit
sdk_version: 1.60.0
app_file: app.py
pinned: false
---
```

## Anywhere else (Fly.io, Render, Cloud Run, a VPS)

The included `Dockerfile` binds to `$PORT` and ships a health check on
`/_stcore/health`.

```bash
docker build -t surat-kuasa .
docker run -p 8501:8501 surat-kuasa
```

- **Fly.io** — `fly launch --no-deploy`, keep the Dockerfile, then `fly deploy`.
- **Render / Railway** — new Web Service from the repo, Docker runtime, health
  check path `/_stcore/health`.
- **Cloud Run** — `gcloud run deploy --source .`; it honours `$PORT`.

## Before you go live

- **Put your own details in `config.toml`, or none at all.** It ships with
  placeholders ("NAMA PEMBERI KUASA"). On a public deploy it is only the
  example the form starts from, so leave it fictional.
- **Never commit certificates.** `.gitignore` already excludes `*.p12`,
  `*.pfx`, `*.pem`, `*.key`, `.env`. PAdES signing (`--sign`) is a CLI feature
  and stays off the server.
- **Signature fields need pyhanko.** Without it the app hides that checkbox and
  everything else still works. Add `pyhanko==0.36.2` to `requirements.txt` if
  you want it on the server.
- **HTTPS matters.** The "remember me" cookie is marked `Secure` only when the
  app is served over https, which every host above does by default.
- **Fonts come from Google Fonts** at page load. If you would rather no request
  leaves the visitor's browser, vendor the three families locally and replace
  the `@import` at the top of `CSS` in `app.py`.
- **Tell people what it is.** The footer already says the letter is a template,
  not legal advice, and that some offices insist on their own form.
