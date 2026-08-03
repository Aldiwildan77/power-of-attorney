# Generic container for hosts without a Streamlit preset (Fly.io, Render,
# Cloud Run, a VPS). Streamlit Community Cloud and Hugging Face Spaces do not
# need this file — they read requirements.txt directly.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Most platforms inject $PORT; default to Streamlit's own.
ENV PORT=8501
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/_stcore/health')"

CMD ["sh", "-c", "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0"]
