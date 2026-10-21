FROM node:22-bookworm-slim AS assets
WORKDIR /build
COPY package*.json ./
RUN npm ci
COPY assets ./assets
COPY templates ./templates
COPY static/js ./static/js
RUN mkdir -p static/css && npm run build:css

# Official Claude Code client, so the server can read the subscription limits itself.
# The binary comes from Anthropic's signed release manifest and is checked by
# checksum; no external installer script is executed.
FROM python:3.12-slim-bookworm AS claude-client
ARG CLAUDE_CODE_VERSION=2.1.301
ARG TARGETARCH=amd64
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) platform=linux-x64 ;; \
      arm64) platform=linux-arm64 ;; \
      *) echo "Arquitectura no soportada: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    base="https://downloads.claude.ai/claude-code-releases/${CLAUDE_CODE_VERSION}"; \
    curl -fsSL "${base}/manifest.json" -o /tmp/manifest.json; \
    curl -fsSL "${base}/${platform}/claude" -o /tmp/claude; \
    expected="$(python3 -c "import json,sys; print(json.load(open('/tmp/manifest.json'))['platforms']['${platform}']['checksum'])")"; \
    actual="$(sha256sum /tmp/claude | cut -d' ' -f1)"; \
    if [ "${expected}" != "${actual}" ]; then echo "La suma del binario no coincide con el manifiesto firmado" >&2; exit 1; fi; \
    mkdir -p /opt/claude/bin && mv /tmp/claude /opt/claude/bin/claude && chmod 0755 /opt/claude/bin/claude; \
    /opt/claude/bin/claude --version

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/claude/bin:${PATH}"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 app && mkdir -p /home/app/.claude \
    && chown app:app /home/app/.claude && chmod 700 /home/app/.claude
COPY --chown=app:app . .
COPY --from=assets --chown=app:app /build/static/css/app.css ./static/css/app.css
COPY --from=claude-client --chown=app:app /opt/claude/bin/claude /opt/claude/bin/claude
RUN DJANGO_SECRET_KEY=build-only-placeholder python manage.py collectstatic --noinput
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
