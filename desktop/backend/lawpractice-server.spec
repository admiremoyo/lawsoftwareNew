# PyInstaller recipe for the desktop backend.
# Build (from the repository root):
#   DJANGO_DEBUG=0 DJANGO_SECRET_KEY=<any 40+ chars> python manage.py collectstatic --noinput
#   pyinstaller --noconfirm --distpath desktop/backend/dist --workpath desktop/backend/build desktop/backend/lawpractice-server.spec
# Output: desktop/backend/dist/lawpractice-server/ (a folder the Tauri installer ships as a resource).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
APPS = ["lawpractice", "core", "accounts", "accounting", "billing", "clients", "diary", "matters", "trust"]

hiddenimports = ["waitress"]
# Our own modules are found by walking the source tree: importing them needs Django configured,
# which PyInstaller's automatic discovery can't do.
for app in APPS:
    for path in (ROOT / app).rglob("*.py"):
        parts = path.relative_to(ROOT).with_suffix("").parts
        hiddenimports.append(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
for pkg in ["django", "xhtml2pdf", "reportlab", "segno", "whitenoise", "dj_database_url"]:
    hiddenimports += collect_submodules(pkg)

datas = [
    (str(ROOT / "templates"), "templates"),
    (str(ROOT / "staticfiles"), "staticfiles"),
    (str(ROOT / "static"), "static"),
]
for pkg in ["django", "xhtml2pdf", "reportlab", "segno"]:
    datas += collect_data_files(pkg)

a = Analysis(
    [str(ROOT / "desktop" / "backend" / "server.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "psycopg", "psycopg_binary", "gunicorn", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lawpractice-server", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="lawpractice-server")
