FROM python:3.12-slim AS builder

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN python -m venv "$VIRTUAL_ENV"
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.12-slim AS runtime

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UVICORN_WORKERS=2

WORKDIR /app
RUN groupadd --gid 10001 copilot && useradd --uid 10001 --gid copilot --create-home --shell /usr/sbin/nologin copilot
COPY --from=builder /opt/venv /opt/venv
COPY --chown=copilot:copilot . .

USER copilot
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS}"]
