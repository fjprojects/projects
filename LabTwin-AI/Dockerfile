FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-render.txt /app/requirements-render.txt

RUN pip install --no-cache-dir     -r /app/requirements-render.txt

COPY backend/ /app/

CMD ["sh", "-c", "python manage.py migrate && exec gunicorn backend.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 180"]


