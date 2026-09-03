FROM python:3.12-slim

# WeasyPrint system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    libcairo2 \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application code
COPY app/ app/

RUN adduser --disabled-password --no-create-home appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

USER appuser

# Atrás do proxy da casa (Traefik e rewrite do Next), o IP real do visitante
# chega no X-Forwarded-For. Confiança restrita às faixas privadas da rede do
# Docker; nunca `*`, que deixaria qualquer cliente escolher o próprio IP e
# esvaziaria o rate limit (issue #349).
# `--no-access-log` porque no portal do setor e no Aceite o token E o path
# (issue #465): o access log do uvicorn tem handler proprio e escreveria o
# path CRU no mesmo stdout, ao lado da linha ja mascarada do app. A linha do
# `app.requests` cobre o que a operacao le (metodo, path mascarado, status,
# latencia, request_id e IP do cliente), mas a troca teve custo: o
# `client_addr` era exclusivo do access log e saiu junto com a flag, ate a
# issue #543 devolver o campo pelo middleware.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"]
