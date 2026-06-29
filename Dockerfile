FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ARG PUID=1000
ARG PGID=1000
RUN apt-get update && apt-get install -y fuse libfuse2 && rm -rf /var/lib/apt/lists/* \
    && echo "user_allow_other" >> /etc/fuse.conf \
    && groupadd -g ${PGID} vodlink 2>/dev/null || true \
    && useradd -u ${PUID} -g ${PGID} -s /sbin/nologin -M vodlink 2>/dev/null || true
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend-build /build/dist ./static
RUN mkdir -p /app/data
ARG VERSION=dev
ENV APP_VERSION=${VERSION}
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
