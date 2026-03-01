# ── Stage 1: Build the React frontend ────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + pre-built frontend ──────────────────────────────
FROM python:3.11-slim

# System deps for opencv, rembg, onnxruntime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy pre-built frontend from stage 1
COPY --from=frontend-builder /app/frontend/dist/ ./frontend/dist/

WORKDIR /app/backend

# Pre-download rembg U2-Net model so first request isn't slow
RUN python -c "from rembg import new_session; new_session('u2net')" || true

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
