# syntax=docker/dockerfile:1
#
# One container: nginx serves the React build and proxies /api to uvicorn.
#   docker build -t atlas-qe .
# The crypt_shared library is downloaded at build time for the build's
# architecture (linux x86_64 or aarch64), with the sha256 published by MongoDB.
# The local master key is NOT in the image: mount it at run time (see README).

FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS crypt-shared
# Optional pin, e.g. --build-arg MONGO_CRYPT_VERSION=8.2.1 (default: newest in the feed).
ARG MONGO_CRYPT_VERSION=""
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY scripts/instalar-crypt-shared.sh ./scripts/
RUN MONGO_CRYPT_VERSION="$MONGO_CRYPT_VERSION" bash scripts/instalar-crypt-shared.sh \
  && test -f backend/lib/mongo_crypt_v1.so

FROM python:3.12-slim AS runtime
RUN apt-get update \
  && apt-get install -y --no-install-recommends nginx curl \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home --uid 10001 app

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY --from=crypt-shared /build/backend/lib/mongo_crypt_v1.so /opt/mongo-crypt/mongo_crypt_v1.so
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY --from=frontend-build /build/dist ./frontend/dist
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/start.sh /start.sh
RUN chmod +x /start.sh && mkdir -p backend/secrets backend/data && chown -R app:app /app
USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/api/health/live || exit 1

CMD ["/start.sh"]
