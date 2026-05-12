# Use the official uv image for build
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# Set the working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy project files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Final runtime image
FROM python:3.13-slim-bookworm

# Set the working directory
WORKDIR /app

# Copy the environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source code
COPY . .

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PORT=8000

# Expose the port (informative)
EXPOSE 8000

# Command to run the application
# We use the PORT env var for Cloud Run compatibility
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
