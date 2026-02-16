# Stage 1: Builder
FROM python:3.12-slim AS builder

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Create virtual environment and install dependencies using UV
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY bot/ ./bot/
COPY claude/ ./claude/
COPY prompts/ ./prompts/
COPY main.py .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Run the bot
CMD ["python", "main.py"]
