FROM node:22-bookworm-slim AS node-runtime

FROM python:3.11-slim

# ------------------------------------------------------------
# System dependencies
# ------------------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp requires a supported JavaScript runtime for YouTube challenges.
# Keep Node explicit and modern instead of relying on Debian's nodejs package.
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
RUN ln -sf /usr/local/bin/node /usr/bin/node

# ------------------------------------------------------------
# Environment configuration
# ------------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# ------------------------------------------------------------
# Application setup
# ------------------------------------------------------------
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app ./app

# Ensure runtime directories exist
RUN mkdir -p outputs

# ------------------------------------------------------------
# Runtime
# ------------------------------------------------------------
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
