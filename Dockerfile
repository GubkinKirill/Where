# Одностадийная сборка: зависимостей мало, компилировать нечего,
# фронтенд собирать не нужно — HTMX и CSS лежат готовыми файлами.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# слой с зависимостями отдельно: правка кода не пересобирает pip install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

# приложение пишет только в /app/data — туда монтируется том
RUN useradd --create-home --uid 1000 inventory \
    && mkdir -p /app/data/photos \
    && chown -R inventory:inventory /app/data
USER inventory

EXPOSE 8000

# миграции накатываются при старте: база — файл, отдельного шага развёртывания нет
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
