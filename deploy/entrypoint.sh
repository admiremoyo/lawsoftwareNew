#!/bin/sh
set -e
# Wait for the database, apply migrations, then start the app.
python - <<'PY'
import os, time, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lawpractice.settings")
django.setup()
from django.db import connection
for attempt in range(30):
    try:
        connection.ensure_connection()
        break
    except Exception as exc:
        print(f"Waiting for database ({exc.__class__.__name__})…", flush=True)
        time.sleep(2)
else:
    raise SystemExit("Database not reachable")
PY
python manage.py migrate --noinput
exec "$@"
