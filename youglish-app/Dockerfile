# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# gcc + libpq-dev: needed to build psycopg2-binary
# postgresql-client: provides pg_isready used in entrypoint.sh
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Download the German spaCy model (used at startup for phrase seeding)
RUN python -m spacy download de_core_news_sm

# Copy the backend package
COPY backend/ ./backend/

# Copy built frontend — main.py serves it as static files from ../frontend/dist
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist/

COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
