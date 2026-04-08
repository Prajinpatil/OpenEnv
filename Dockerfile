# =============================================================================
# Stage 1 — dependency builder
# =============================================================================
FROM python:3.11-slim AS builder

# Install uv
RUN pip install --no-cache-dir uv==0.4.10

WORKDIR /build

# Copy dependency files first for layer caching
COPY pyproject.toml ./

# Create a virtual environment and install all dependencies with uv
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python \
        pydantic>=2.7 \
        fastapi>=0.111 \
        "uvicorn[standard]>=0.30" \
        pyyaml>=6.0 \
        openai>=1.30 \
        requests>=2.31 \
        python-dotenv>=1.0

# =============================================================================
# Stage 2 — runtime image
# =============================================================================
FROM python:3.11-slim AS runtime

LABEL maintainer="mail_pro_env"
LABEL description="OpenEnv Mail Classification & Routing Environment"
LABEL version="1.0.0"

# Copy the pre-built venv from builder
COPY --from=builder /opt/venv /opt/venv

# Activate venv by prepending to PATH
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user for security
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

# Copy application source
COPY models.py ./
COPY openenv.yaml ./
COPY server/ ./server/
COPY baseline_inference.py ./

# Ensure server package is importable
RUN touch server/__init__.py

# Change ownership
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from server.environment import MailEnv; e = MailEnv(); e.reset(); print('OK')" \
    || exit 1

# Default command — serve via uvicorn (wire up to a FastAPI app if desired)
# For standalone inference, override with: docker run ... python baseline_inference.py
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]