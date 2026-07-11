FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV INSTANCE_DIR=/var/data
ENV DATABASE_PATH=/var/data/back_to_god.sqlite3

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser \
  && mkdir -p /var/data \
  && chown -R appuser:appuser /var/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 180 --access-logfile - --error-logfile -"]
