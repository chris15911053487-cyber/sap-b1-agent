# ============================================================
# Stage 1: Build frontend (Node.js)
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ============================================================
# Stage 2: Python backend
# ============================================================
FROM python:3.11-slim-bookworm AS backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl freetds-dev freetds-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs && chmod 777 /app/data /app/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================================
# Stage 3: Nginx + frontend static files
# ============================================================
FROM nginx:alpine AS frontend

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-builder /src/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q -O /dev/null http://localhost/health || exit 1
