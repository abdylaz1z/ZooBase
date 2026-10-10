"""Portable, offline SQLite + photo backups. No cloud service is implied."""
import csv
import json
import os
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from .models import Animal, db, init_db

MAX_BACKUP_BYTES = 512 * 1024 * 1024
TABLES = {"farm", "user", "animal", "healthrecord", "task", "reproevent", "appsetting"}


def create_backup(destination):
    """SQLite backup API captures WAL transactions; never copy a live .db file."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        snapshot = Path(temp) / "zoobase.db"
        with sqlite3.connect(snapshot) as conn:
            db.connection().backup(conn)
            photos = conn.execute("SELECT id, photo FROM animal").fetchall()
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                for animal_id, photo in photos:
                    relative = ""
                    if photo and Path(photo).is_file():
                        relative = f"photos/{animal_id}.jpg"
                        archive.write(photo, relative)
                    conn.execute("UPDATE animal SET photo=? WHERE id=?", (relative, animal_id))
                conn.commit()
                archive.writestr("manifest.json", json.dumps({
                    "format": "zoobase-backup", "version": 1,
                    "created_at": datetime.now().isoformat(),
                }))
                archive.write(snapshot, "zoobase.db")
    return str(destination)


def restore_backup(source, photo_dir):
    """Validate everything before touching live data. SQLite backup commits atomically."""
    photo_dir = Path(photo_dir).resolve()
    photo_dir.mkdir(parents=True, exist_ok=True)
    created = []
    installed = False
    try:
        with zipfile.ZipFile(source) as archive, tempfile.TemporaryDirectory() as temp:
            infos = archive.infolist()
            if (len(infos) > 20000 or sum(i.file_size for i in infos) > MAX_BACKUP_BYTES
                    or len({i.filename for i in infos}) != len(infos)):
                raise ValueError("Invalid backup size or duplicate entries")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != "zoobase-backup" or manifest.get("version") != 1:
                raise ValueError("Unsupported backup")
            snapshot = Path(temp) / "restore.db"
            snapshot.write_bytes(archive.read("zoobase.db"))
            with sqlite3.connect(snapshot) as conn:
                conn.execute("PRAGMA trusted_schema=OFF")
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Damaged database")
                actual = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not TABLES.issubset(actual) or conn.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Invalid database schema or relationships")
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
                    raise ValueError("Unexpected executable schema")
                # Require all columns used by this application before replacement.
                for table in TABLES:
                    expected = {r[1] for r in db.execute_sql(f'PRAGMA table_info("{table}")').fetchall()}
                    found = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
                    if not expected.issubset(found):
                        raise ValueError("Incompatible schema")
                for animal_id, photo in conn.execute("SELECT id, photo FROM animal").fetchall():
                    target = ""
                    if photo:
                        if photo != f"photos/{animal_id}.jpg":
                            raise ValueError("Invalid photo reference")
                        path = photo_dir / (uuid.uuid4().hex + ".jpg")
                        path.write_bytes(archive.read(photo))
                        created.append(path)
                        target = str(path)
                    conn.execute("UPDATE animal SET photo=? WHERE id=?", (target, animal_id))
                conn.commit()
                conn.backup(db.connection())
                installed = True
        database_path = db.database
        init_db(database_path)
    finally:
        if not installed:
            for path in created:
                path.unlink(missing_ok=True)


def export_animals(destination, farm):
    """Excel-friendly UTF-8 CSV; escape spreadsheet formulas in user-entered cells."""
    def safe(value):
        text = str(value or "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

    with open(destination, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(["Номер", "Кличка", "Чип", "Порода", "Пол", "Дата рождения",
                         "Дата поступления", "Статус", "Отец (номер)", "Мать (номер)", "Заметки"])
        animals = list(Animal.select().where(Animal.farm == farm).order_by(Animal.tag))
        tags = {a.id: a.tag for a in animals}
        for a in animals:
            writer.writerow(map(safe, [a.tag, a.name, a.chip, a.breed, a.sex, a.birth_date,
                                      a.arrival_date, a.status, tags.get(a.father_id, ""),
                                      tags.get(a.mother_id, ""), a.notes]))
    return str(destination)
