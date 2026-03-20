# ── SCRIBE — Dockerfile (version open-source) ─────────────────────────────
FROM python:3.11-slim

LABEL maintainer="github.com/nocomp/scribe"
LABEL description="SCRIBE — Main courante de crise hospitalière"

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCRIBE_DATA_DIR=/data

WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY . .

# Dossier de données persistantes (base SQLite + uploads + config.js généré)
RUN mkdir -p /data/uploads /data/db && \
    ln -sf /data/uploads /app/uploads && \
    ln -sf /data/db/scribe.db /app/scribe.db 2>/dev/null || true

# Sécurisation : éviter l'exécution en tant que root
RUN addgroup --system scribe && \
    adduser --system --ingroup scribe --home /app --shell /usr/sbin/nologin scribe && \
    chown -R scribe:scribe /app /data

# Script d'entrée (COPY --chmod avoids filesystem permission issues on some hosts)
COPY --chmod=0755 docker-entrypoint.sh /docker-entrypoint.sh

# Ensure the entrypoint uses LF line endings (avoid "sh\r" shebang errors on Linux)
# Must run as root before USER directive to avoid permission issues
RUN sed -i 's/\r$//' /docker-entrypoint.sh

# Switch to non-root user for security
USER scribe

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
