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

The built-in Streamlit SDK is deprecated, so pick the **Docker** SDK; the
`Dockerfile` in this repo is all it needs.

1. Create a Space → SDK **Docker** → hardware "CPU basic (free)".
2. Push these files to the Space repo.
3. The Space's own `README.md` must start with this frontmatter (keep the
   project README underneath it):

```yaml
---
title: Surat Kuasa
emoji: 📄
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 8501
pinned: false
---
```

## Your own domain

Community Cloud only gives you a subdomain — `something.streamlit.app`. A
domain of your own means hosting the container somewhere else:

| Host | Custom domain | Cost | Trade-off |
| --- | --- | --- | --- |
| Streamlit Community Cloud | ✗ subdomain only | free | simplest, but the URL is theirs |
| **Render (free plan)** | ✓ up to 2, TLS included | free | sleeps after 15 min idle, ~1 min to wake |
| Google Cloud Run | ✓ domain mapping, TLS included | usage-based, free tier covers light traffic | needs a GCP project; fastest cold start |
| Hugging Face Spaces | ✓ CNAME to `hf.space` | needs PRO or Team plan | free tier is subdomain only |
| VPS + Caddy | ✓ | a few dollars a month | you patch the box |

Render is the shortest path to `suratkuasa.example.com` at no cost:

1. render.com → **New → Blueprint** → pick this repo. `render.yaml` sets the
   Docker runtime, the free plan, the Singapore region and the health check.
2. Once it is live: service → **Settings → Custom Domains → Add**.
3. At your DNS provider add what Render shows you — a `CNAME` for a subdomain
   (`suratkuasa` → `<service>.onrender.com`), or an `ALIAS`/`ANAME` plus the
   given `A` record for a bare domain.
4. Wait for verification; the TLS certificate is issued automatically.

Do not try to point a custom domain at a `*.streamlit.app` app through a
reverse proxy: the websocket connection and the app's own host checks make it
brittle, and it works around a limit the platform states plainly.

## Anywhere else (Fly.io, Cloud Run, a VPS)

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
