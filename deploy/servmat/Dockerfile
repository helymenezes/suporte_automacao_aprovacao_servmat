# servmat: serviço Python próprio (padrão D-01 do fechamento-os), com as telas React já compiladas.
# Build a partir da raiz do repositório: docker compose -f deploy/servmat/docker-compose.yml build
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV TZ=America/Sao_Paulo PYTHONUNBUFFERED=1 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends tzdata curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app/servmat
COPY servmat/requirements.txt .
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0 pydantic==2.10.4
COPY servmat/servmat ./servmat
COPY servmat/config ./config
COPY --from=web /web/dist /app/web/dist
ENV SERVMAT_WEB=/app/web/dist
HEALTHCHECK --interval=60s --timeout=5s CMD curl -fsS "http://${SERVMAT_HOST:-127.0.0.1}:${SERVMAT_PORTA:-8792}/health" || exit 1
ENTRYPOINT ["python", "-m", "servmat"]
CMD ["servico"]
