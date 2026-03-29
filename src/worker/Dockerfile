FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY src/ src/

ENV PYTHONPATH=/app/src

# Default: no-op. Override CMD per K8s deployment:
#   extract:  ["uv", "run", "python", "-m", "worker.extract_runner"]
#   classify: ["uv", "run", "python", "-m", "worker.classify_runner"]
#   store:    ["uv", "run", "python", "-m", "worker.store_runner"]
CMD ["uv", "run", "python", "-m", "worker.extract_runner"]
