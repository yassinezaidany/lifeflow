# LifeFlow — production image (Gunicorn + WhiteNoise). Frontend assets are prebuilt and committed,
# so no Node.js is needed here.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Collect static files at build time (a throwaway key is enough for this step).
RUN SECRET_KEY=build-only-not-secret DB_HOST=none python manage.py collectstatic --noinput \
    && chmod +x /app/docker/entrypoint.sh \
    && useradd --create-home --uid 1000 lifeflow \
    && mkdir -p /app/media /app/logs \
    && chown -R lifeflow:lifeflow /app/media /app/logs /app/staticfiles

USER lifeflow
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["web"]
