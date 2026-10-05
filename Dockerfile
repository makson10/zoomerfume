# ── Stage 1: install dependencies into a virtual environment ─────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv

# Compile bytecode at build time, copy (not hardlink) from the uv cache, and
# always use the image's Python instead of downloading one.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Stage 2: lean runtime image ─────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Non-root user for better security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source + the Alembic migration assets and entrypoint.
COPY backend/app/ ./app/
COPY backend/alembic/ ./alembic/
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

# Liveness probe used by Docker and docker-compose healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# The entrypoint runs `alembic upgrade head`, then execs the command below
# (CMD here in prod; the docker-compose dev override swaps in --reload).
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "--factory", "app.main:create_app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--loop", "uvloop", "--no-access-log"]
