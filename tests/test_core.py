import csv
import json
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path

from zoobase.backup import create_backup, restore_backup, export_animals
from zoobase.controllers import AnimalController, FarmController, HealthController, ReproController, TaskController
from zoobase.models import Animal, HealthRecord, ReproEvent, Task, db, init_db


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        init_db(str(self.root / "test.db"))
        self.farm = FarmController().create("Арашан", "Чүй", "Владелец", "+996700123456").data
        self.ac = AnimalController()
        self.ac.photo_dir = str(self.root / "photos")
        self.ac_dir = Path(self.ac.photo_dir)
        self.ac_dir.mkdir()
        self.hc, self.tc, self.rc = HealthController(), TaskController(), ReproController()

    def tearDown(self):
        db.close()
        self.temp.cleanup()

    def data(self, tag="001", **kw):
        return dict(dict(tag=tag, name="Ак кой", chip="", breed="arashan", sex="female", status="active"), **kw)

    def animal(self, tag="001", **kw):
        result = self.ac.save(self.farm, None, self.data(tag, **kw))
        self.assertTrue(result.ok, result.message)
        return result.data

    def test_registration_is_atomic(self):
        from zoobase.models import Farm, User
        self.assertFalse(FarmController().create("Test", "", "", "bad").ok)
        self.assertEqual(Farm.select().count(), 1)
        self.assertEqual(User.select().count(), 1)

    def test_500_animals_persist_and_cyrillic_search(self):
        for i in range(500):
            self.animal(f"{i:04}", name="Арашан" if i == 499 else "Кой", chip=f"CHIP{i}")
        init_db(str(self.root / "test.db"))
        self.assertEqual(len(self.ac.search(self.farm)), 500)
        self.assertEqual(self.ac.search(self.farm, "АРАШАН")[0].tag, "0499")
        self.assertEqual(self.ac.search(self.farm, "chip499")[0].tag, "0499")
        self.assertEqual(len(self.ac.search(self.farm, "0499")), 1)

    def test_unique_tag_and_chip(self):
        self.animal(chip="123")
        self.assertEqual(self.ac.save(self.farm, None, self.data()).message, "err_tag_exists")
        self.assertEqual(self.ac.save(self.farm, None, self.data("002", chip="123")).message, "err_chip_exists")

    def test_parent_cycles_rejected(self):
        father = self.animal("father", sex="male")
        child = self.animal("son", sex="male", father_id=father.id)
        result = self.ac.save(self.farm, father.id, self.data("father", sex="male", father_id=child.id))
        self.assertEqual(result.message, "err_parent_cycle")
        self.assertIsNone(self.ac.get(father.id).father_id)

    def test_parent_age_and_sex(self):
        father = self.animal("father", sex="male", birth_date=date(2020, 1, 1))
        self.assertEqual(self.ac.save(self.farm, None, self.data(birth_date=date(2019, 1, 1), father_id=father.id)).message, "err_parent_age")
        self.assertEqual(self.ac.save(self.farm, None, self.data(mother_id=father.id)).message, "err_parent_sex")

    def test_changing_parent_sex_or_age_rejected(self):
        father = self.animal("father", sex="male", birth_date=date(2020, 1, 1))
        self.animal("child", father_id=father.id, birth_date=date(2022, 1, 1))
        self.assertEqual(self.ac.save(self.farm, father.id, self.data("father", sex="female")).message, "err_parent_sex")
        self.assertEqual(self.ac.save(self.farm, father.id, self.data("father", sex="male", birth_date=date(2023, 1, 1))).message, "err_parent_age")

    def test_cross_farm_links_and_updates_rejected(self):
        other = FarmController().create("Other", "", "Owner", "+996700000000").data
        father = self.ac.save(other, None, self.data("father", sex="male")).data
        self.assertEqual(self.ac.save(self.farm, None, self.data(father_id=father.id)).message, "err_parent_farm")
        self.assertEqual(self.ac.save(self.farm, father.id, self.data("changed")).message, "err_not_found")
        ewe = self.animal()
        self.assertEqual(self.rc.add(ewe.id, dict(kind="mating", partner_id=father.id)).message, "err_parent_farm")
        self.assertFalse(self.tc.add(self.farm, dict(title="Task", animal_id=father.id)).ok)

    def test_dates_and_status(self):
        self.assertEqual(self.ac.save(self.farm, None, self.data(birth_date=date.today()+timedelta(days=1))).message, "err_future_date")
        self.assertEqual(self.ac.save(self.farm, None, self.data(sex="male", status="pregnant")).message, "err_repro_sex")
        self.assertEqual(self.ac.save(self.farm, None, self.data(birth_date=date(2022, 1, 1), arrival_date=date(2021, 1, 1))).message, "err_arrival_date")

    def test_arrival_roundtrip(self):
        animal = self.animal(arrival_date=date(2024, 1, 1))
        self.assertEqual(self.ac.get(animal.id).arrival_date, date(2024, 1, 1))

    def test_health_reminder_transaction(self):
        animal = self.animal()
        result = self.hc.add(animal.id, dict(kind="vaccine", title="Vaccine", next_date=date.today()+timedelta(days=30)))
        self.assertTrue(result.ok)
        self.assertEqual(Task.select().count(), 1)
        self.assertEqual(len(self.tc.grouped(self.farm)["later"]), 1)
        self.assertTrue(self.tc.complete(Task.get().id).ok)
        self.assertFalse(any(self.tc.grouped(self.farm).values()))
        self.assertIsNotNone(Task.get().done_at)

    def test_future_health_record_rejected(self):
        animal = self.animal()
        self.assertEqual(self.hc.add(animal.id, dict(kind="vaccine", title="V", done_date=date.today()+timedelta(days=1))).message, "err_future_date")
        self.assertEqual(HealthRecord.select().count(), 0)

    def test_reproduction_state(self):
        mother, father = self.animal(), self.animal("male", sex="male")
        self.assertTrue(self.rc.add(mother.id, dict(kind="mating", partner_id=father.id)).ok)
        self.assertEqual(self.ac.get(mother.id).status, "pregnant")
        self.assertEqual(Task.get().due_date, date.today()+timedelta(days=150))
        self.assertTrue(self.rc.add(mother.id, dict(kind="lambing", males="1", females="2")).ok)
        self.assertEqual(self.ac.get(mother.id).status, "active")
        self.assertTrue(Task.get().done)
        self.assertEqual(self.rc.fertility(self.farm), 3)

    def test_historical_repro_cannot_overwrite_current_state(self):
        animal = self.animal()
        self.rc.add(animal.id, dict(kind="mating"))
        self.assertEqual(self.rc.add(animal.id, dict(kind="mating", event_date=date.today()-timedelta(days=1))).message, "err_repro_order")
        self.assertEqual(ReproEvent.select().count(), 1)

    def test_cascade_and_parent_unlink(self):
        father = self.animal("father", sex="male")
        child = self.animal("child", father_id=father.id)
        self.hc.add(father.id, dict(kind="note", title="Note", next_date=date.today()))
        self.assertTrue(self.ac.delete(father.id).ok)
        self.assertIsNone(self.ac.get(child.id).father_id)
        self.assertEqual(HealthRecord.select().count(), 0)
        self.assertEqual(Task.select().count(), 0)

    def test_photo_delete_cannot_escape_directory(self):
        sibling = self.root / "photos-other"
        sibling.mkdir()
        outside = sibling / "keep.jpg"
        outside.write_bytes(b"keep")
        self.ac.remove_photo(str(outside))
        self.assertTrue(outside.exists())

    def test_photo_is_resized_and_kept_after_save(self):
        from PIL import Image
        source = self.root / "source.png"
        Image.new("RGBA", (1600, 1200), "green").save(source)
        result = self.ac.store_photo(str(source))
        self.assertTrue(result.ok)
        with Image.open(result.data) as image:
            self.assertEqual(image.size, (800, 600))
            self.assertEqual(image.mode, "RGB")
        self.animal(photo=result.data)
        self.assertTrue(Path(result.data).is_file())

    def test_old_database_photo_migration(self):
        self.animal()
        db.execute_sql("ALTER TABLE animal DROP COLUMN photo")
        init_db(str(self.root / "test.db"))
        self.assertEqual(Animal.get().photo, "")

    def test_photo_replacement_removes_only_old_owned_file(self):
        old = self.ac_dir / "old.jpg"
        new = self.ac_dir / "new.jpg"
        old.write_bytes(b"old")
        new.write_bytes(b"new")
        animal = self.animal(photo=str(old))
        self.assertTrue(self.ac.save(self.farm, animal.id, self.data(photo=str(new))).ok)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_backup_roundtrip_with_photo_and_wal(self):
        photo = self.ac_dir / "original.jpg"
        photo.write_bytes(b"photo")
        self.animal(photo=str(photo))
        self.tc.add(self.farm, dict(title="Check"))
        archive = create_backup(self.root / "backup.zip")
        self.animal("extra")
        restore_backup(archive, self.ac.photo_dir)
        self.assertEqual(Animal.select().count(), 1)
        self.assertEqual(Task.select().count(), 1)
        self.assertEqual(Path(Animal.get().photo).read_bytes(), b"photo")
        self.assertNotEqual(Animal.get().photo, str(photo))

    def test_invalid_backup_preserves_live_data(self):
        self.animal()
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("manifest.json", json.dumps({"format":"wrong", "version":1}))
        with self.assertRaises(ValueError):
            restore_backup(archive, self.ac.photo_dir)
        self.assertEqual(Animal.select().count(), 1)

    def test_corrupt_backup_preserves_live_data(self):
        self.animal()
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("manifest.json", json.dumps({"format":"zoobase-backup", "version":1}))
            z.writestr("zoobase.db", b"not a sqlite database")
        with self.assertRaises(Exception):
            restore_backup(archive, self.ac.photo_dir)
        self.assertEqual(Animal.select().count(), 1)

    def test_csv_formula_escape_and_cyrillic(self):
        self.animal(name="=1+1")
        target = export_animals(str(self.root / "herd.csv"), self.farm)
        with open(target, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0][0], "Номер")
        self.assertEqual(rows[1][1], "'=1+1")


if __name__ == "__main__":
    unittest.main()
