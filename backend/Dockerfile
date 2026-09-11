FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY backend ./backend
COPY data/plans ./data/plans
RUN mkdir -p /app/data/uploads

COPY infra/docker/api-entrypoint.sh /api-entrypoint.sh
RUN sed -i 's/\r$//' /api-entrypoint.sh && chmod +x /api-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/api-entrypoint.sh"]
