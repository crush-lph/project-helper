# ---- Stage 1: Frontend build ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com && \
    npm config set fetch-retries 5 && \
    npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm ci
COPY frontend/ ./
ARG VITE_API_BASE=
RUN npm run build

# ---- Stage 2: Production ----
FROM python:3.11-slim AS production
WORKDIR /app

# System deps
RUN sed -i \
    -e 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' \
    -e 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' \
    /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    git curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 \
    --retries 10 \
    -r requirements.txt

# Backend source
COPY backend/app ./app
COPY backend/.env.example ./.env.example

# Frontend static files (served by nginx, but included for health check)
COPY --from=frontend-build /app/frontend/dist ./static

# Create data directory
RUN mkdir -p /app/data

ENV PROJECT_HELPER_DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
