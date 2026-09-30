FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . ./
RUN WALLET_ENV=local WALLET_BUILD_STATIC=1 python manage.py collectstatic --noinput \
    && useradd --create-home --no-log-init wallet \
    && chown -R wallet:wallet /app

ENV WALLET_ENV=production
USER wallet
EXPOSE 8000

CMD ["sh", "-c", "exec gunicorn wallet_project.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 120"]
