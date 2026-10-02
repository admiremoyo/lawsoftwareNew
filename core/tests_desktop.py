import importlib.util
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase

SERVER = Path(__file__).resolve().parents[1] / "desktop" / "backend" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("lawpractice_desktop_server", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopBackupTests(SimpleTestCase):
    def setUp(self):
        self.server = load_server()
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        (self.data / "media" / "matters").mkdir(parents=True)
        (self.data / "media" / "matters" / "deed.pdf").write_bytes(b"%PDF deed")
        (self.data / "secret.key").write_text("k" * 60)
        db = sqlite3.connect(self.data / "lawpractice.sqlite3")
        db.execute("create table t (v text)")
        db.execute("insert into t values ('original')")
        db.commit()
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        db = sqlite3.connect(self.data / "lawpractice.sqlite3")
        values = [r[0] for r in db.execute("select v from t")]
        db.close()
        return values

    def test_backup_contains_database_documents_and_key(self):
        archive = self.server.backup(self.data)
        with zipfile.ZipFile(archive) as zf:
            self.assertEqual(set(zf.namelist()), {"lawpractice.sqlite3", "media/matters/deed.pdf", "secret.key"})

    def test_restore_round_trip_keeps_a_safety_copy(self):
        archive = self.server.backup(self.data)
        db = sqlite3.connect(self.data / "lawpractice.sqlite3")
        db.execute("insert into t values ('added later')")
        db.commit()
        db.close()
        (self.data / "media" / "matters" / "deed.pdf").unlink()
        self.server.restore(self.data, archive)
        self.assertEqual(self.rows(), ["original"])
        self.assertTrue((self.data / "media" / "matters" / "deed.pdf").exists())
        self.assertEqual(len(list((self.data / "backups").glob("LawPractice-backup-*.zip"))), 2)

    def test_old_backups_pruned(self):
        backups = self.data / "backups"
        backups.mkdir()
        for i in range(35):
            (backups / f"LawPractice-backup-20200101-0000{i:02d}.zip").write_bytes(b"x")
        self.server.backup(self.data)
        self.assertEqual(len(list(backups.glob("LawPractice-backup-*.zip"))), self.server.KEEP_BACKUPS)

    def test_rejects_non_backups(self):
        bad = self.data / "bad.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("hello.txt", "x")
        with self.assertRaises(SystemExit):
            self.server.restore(self.data, bad)
