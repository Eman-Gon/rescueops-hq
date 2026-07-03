# Single-image deploy: build the React frontend, then run FastAPI which serves
# both the /api JSON API and the built static frontend at /.
# Works on Railway (and any container host). Railway injects $PORT.

# ---- Stage 1: build the React frontend ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend + bundled frontend ----
FROM python:3.12-slim
WORKDIR /app

# System deps occasionally needed by crewai/litellm wheels.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source (frontend/ source is ignored via .dockerignore; we copy dist below).
COPY . .
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 8000
# Bind to 0.0.0.0 and honor the platform's $PORT (defaults to 8000 locally).
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
