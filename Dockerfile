# syntax=docker/dockerfile:1.7-labs
FROM python:3.13-slim-bookworm

# 1. Install system dependencies for building C extensions (like for some DB drivers)
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y gcc python3-dev && rm -rf /var/lib/apt/lists/*

# 2. Grab the uv binary (this is the magic part)
COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /uvx /bin/

WORKDIR /app

# 3. Optimization: Cache the uv layers
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1

# 4. Install dependencies first for better Docker layer caching
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 5. Copy your code and do the final sync
COPY . .
RUN uv sync --frozen --no-dev

# 6. Runtime config
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PORT=8080

# 7. The 'uv run' command handles the virtualenv paths for you
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]