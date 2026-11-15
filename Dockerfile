FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATICFILES_STORAGE=django.contrib.staticfiles.storage.StaticFilesStorage

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod 755 /app/docker-entrypoint.sh \
    && addgroup --system lps && adduser --system --ingroup lps lps \
    && mkdir -p /var/data/assets \
    && chown -R lps:lps /app /var/data

USER lps

RUN SESSION_SECRET=build-only-key-not-used-at-runtime-123456789 \
    DATABASE_URL=sqlite:////tmp/lps-static-build.sqlite3 \
    MEDIA_ROOT=/tmp/lps-media \
    python manage.py collectstatic --noinput

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "lps.wsgi:application", "--config", "gunicorn.conf.py"]
