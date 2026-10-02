"""LawPractice desktop backend.

The desktop app runs this program in the background and shows its pages in the app window.
Everything stays on this computer: the database, documents and backups live in the data folder
the app passes in (on Windows: %APPDATA%\\com.lawpractice.desktop).

    server serve  --data DIR --port N   run the web server on 127.0.0.1:N
    server backup --data DIR            write a backup zip into DIR/backups now
"""
import argparse
import io
import os
import secrets
import shutil
import sqlite3
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

KEEP_BACKUPS = 30
BACKUP_EVERY_SECONDS = 24 * 3600


def app_root():
    # Inside a PyInstaller bundle the project files live in sys._MEIPASS.
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def configure(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "media").mkdir(exist_ok=True)
    key_file = data_dir / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(64))
    os.environ.update({
        "DJANGO_SETTINGS_MODULE": "lawpractice.settings",
        "DJANGO_DEBUG": "0",
        "LAWPRACTICE_DESKTOP": "1",
        "DJANGO_SECRET_KEY": key_file.read_text().strip(),
        "DJANGO_DB_PATH": str(data_dir / "lawpractice.sqlite3"),
        "DJANGO_MEDIA_ROOT": str(data_dir / "media"),
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "DJANGO_STATIC_ROOT": str(app_root() / "staticfiles"),
    })
    sys.path.insert(0, str(app_root()))
    import django

    django.setup()


def backup(data_dir: Path) -> Path:
    """Consistent copy of the database (SQLite online backup) plus all documents, as one zip."""
    dest_dir = data_dir / "backups"
    dest_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    n = 1
    while (dest_dir / f"LawPractice-backup-{stamp}.zip").exists():  # two backups in one second
        n += 1
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{n}"
    snapshot = dest_dir / f".db-{stamp}.sqlite3"
    db_path = data_dir / "lawpractice.sqlite3"
    if db_path.exists():
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(snapshot)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    target = dest_dir / f"LawPractice-backup-{stamp}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        if snapshot.exists():
            zf.write(snapshot, "lawpractice.sqlite3")
        media = data_dir / "media"
        for path in media.rglob("*"):
            if path.is_file():
                zf.write(path, Path("media") / path.relative_to(media))
        zf.write(data_dir / "secret.key", "secret.key")
    snapshot.unlink(missing_ok=True)
    for old in sorted(dest_dir.glob("LawPractice-backup-*.zip"))[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
    return target


def restore(data_dir: Path, archive: Path):
    """Replace the database and documents with those in a backup zip (server must be stopped)."""
    # Read the chosen backup into memory first: the safety backup below writes into the same
    # folder and must never be able to touch it.
    payload = io.BytesIO(Path(archive).read_bytes())
    with zipfile.ZipFile(payload) as zf:
        names = zf.namelist()
        if "lawpractice.sqlite3" not in names:
            raise SystemExit("Not a LawPractice backup.")
        safety = backup(data_dir)  # never lose the current data
        print(f"Current data saved first to {safety}")
        shutil.rmtree(data_dir / "media", ignore_errors=True)
        for name in names:
            if name.startswith("/") or ".." in Path(name).parts:
                continue
            zf.extract(name, data_dir)
    print("Restore complete.")


def latest_backup_age(data_dir: Path):
    backups = sorted((data_dir / "backups").glob("LawPractice-backup-*.zip"))
    return time.time() - backups[-1].stat().st_mtime if backups else None


def backup_loop(data_dir: Path):
    while True:
        age = latest_backup_age(data_dir)
        if age is None or age > BACKUP_EVERY_SECONDS:
            try:
                print(f"Automatic backup: {backup(data_dir)}", flush=True)
            except Exception as exc:  # noqa: BLE001 - never let backups stop the server
                print(f"Automatic backup failed: {exc}", flush=True)
        time.sleep(3600)


def exit_with_parent():
    """The app keeps our stdin open; when it closes (the app quit or crashed) we stop too."""
    try:
        while sys.stdin.read(1):
            pass
    except Exception:  # noqa: BLE001
        pass
    os._exit(0)


def serve(data_dir: Path, port: int, watch_parent: bool):
    configure(data_dir)
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)
    threading.Thread(target=backup_loop, args=(data_dir,), daemon=True).start()
    if watch_parent:
        threading.Thread(target=exit_with_parent, daemon=True).start()

    from waitress import serve as waitress_serve

    from lawpractice.wsgi import application

    print(f"LawPractice ready on http://127.0.0.1:{port}/", flush=True)
    waitress_serve(application, host="127.0.0.1", port=port, threads=8, ident="LawPractice",
                   max_request_body_size=30 * 1024 * 1024)


def main():
    parser = argparse.ArgumentParser(prog="lawpractice-server")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--data", required=True, type=Path)
    p_serve.add_argument("--port", required=True, type=int)
    p_serve.add_argument("--watch-parent", action="store_true")
    p_backup = sub.add_parser("backup")
    p_backup.add_argument("--data", required=True, type=Path)
    p_restore = sub.add_parser("restore")
    p_restore.add_argument("--data", required=True, type=Path)
    p_restore.add_argument("archive", type=Path)
    p_manage = sub.add_parser("manage", help="run a Django management command against the desktop data")
    p_manage.add_argument("--data", required=True, type=Path)
    p_manage.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.cmd == "serve":
        serve(args.data, args.port, args.watch_parent)
    elif args.cmd == "backup":
        args.data.mkdir(parents=True, exist_ok=True)
        print(backup(args.data))
    elif args.cmd == "restore":
        restore(args.data, args.archive)
    elif args.cmd == "manage":
        configure(args.data)
        from django.core.management import execute_from_command_line

        execute_from_command_line(["manage.py", *args.args])


if __name__ == "__main__":
    main()
