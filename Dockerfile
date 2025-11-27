# Multi-stage Dockerfile: build Tailwind with Node then run the FastAPI app with Python

# --- Build stage (Node) ----------------------------------------------------
FROM node:18-alpine AS node_build
WORKDIR /app

# Copy package manifest and install node deps (tailwind)
COPY package.json package-lock.json* ./
RUN npm ci --silent

# Copy only the files needed to build CSS and run the build
COPY assets/tailwind-input.css ./assets/tailwind-input.css
COPY tailwind.config.js ./tailwind.config.js
COPY postcss.config.js ./postcss.config.js

# Build tailwind into ./static/tailwind.css
RUN npm run build:css


# --- Final stage (Python runtime) -----------------------------------------
FROM python:3.13.7-slim
WORKDIR /app

# Install system deps if needed (kept minimal). libpq-dev/gcc optional; psycopg2-binary is used but keep apt packages small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (use cached layer when requirements.txt unchanged)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy built static assets from node build stage
COPY --from=node_build /app/static ./static

# Copy the rest of the application (do not rely on .env being present in the image)
COPY . .
# Ensure a local .env isn't accidentally baked into the image
RUN rm -f .env || true

# Default port (Coolify will inject PORT or you can set it via env vars). Expose for documentation.
ENV PORT=3003
# For a very small app, default to a single worker to conserve memory.
# You can override these values in Coolify per-deployment if you need more concurrency.
ENV GUNICORN_WORKERS=1
# Graceful timeout and threads (configurable via env). Keep threads=1 by default.
ENV GUNICORN_TIMEOUT=30
ENV GUNICORN_THREADS=1
EXPOSE ${PORT}

# Healthcheck should use the selected PORT
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health || exit 1

# Run Gunicorn with Uvicorn workers; GUNICORN_WORKERS is configurable via env (default 1)
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w ${GUNICORN_WORKERS:-1} --threads ${GUNICORN_THREADS:-1} --timeout ${GUNICORN_TIMEOUT:-30} --bind 0.0.0.0:${PORT:-3001} main:app"]

