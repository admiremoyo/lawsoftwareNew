FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_DEBUG=0 \
    DJANGO_MEDIA_ROOT=/data/media \
    DJANGO_STATIC_ROOT=/app/staticfiles

RUN useradd --create-home --uid 1000 app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# collectstatic needs a (throwaway) key at build time only.
RUN DJANGO_SECRET_KEY=build-only-build-only-build-only-build-only-key python manage.py collectstatic --noinput \
    && mkdir -p /data/media && chown -R app:app /data /app

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4).status != 200)"
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "lawpractice.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
