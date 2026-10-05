"""Model: таблицы SQLite (Peewee ORM). Поля updated_at/synced готовят почву для синхронизации."""
from datetime import datetime

from peewee import (BooleanField, CharField, DateField, DateTimeField,
                    ForeignKeyField, IntegerField, Model, SqliteDatabase, TextField)

db = SqliteDatabase(None)


class BaseModel(Model):
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)
    synced = BooleanField(default=False)

    class Meta:
        database = db

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        self.synced = False
        return super().save(*args, **kwargs)


class Farm(BaseModel):
    name = CharField(max_length=120)
    region = CharField(max_length=120, default="")


class User(BaseModel):
    farm = ForeignKeyField(Farm, backref="users", on_delete="CASCADE")
    name = CharField(max_length=120)
    phone = CharField(max_length=20)
    role = CharField(default="owner")  # owner | zootech | vet | viewer


class Animal(BaseModel):
    farm = ForeignKeyField(Farm, backref="animals", on_delete="CASCADE")
    tag = CharField(max_length=32)
    name = CharField(max_length=60, default="")
    chip = CharField(max_length=40, default="")
    breed = CharField(default="arashan")
    sex = CharField(default="female")
    birth_date = DateField(null=True)
    arrival_date = DateField(null=True)
    status = CharField(default="active")
    father = ForeignKeyField("self", null=True, backref="sired", on_delete="SET NULL")
    mother = ForeignKeyField("self", null=True, backref="borne", on_delete="SET NULL")
    notes = TextField(default="")
    photo = CharField(max_length=255, default="")

    class Meta:
        indexes = ((("farm", "tag"), True),)


class HealthRecord(BaseModel):
    animal = ForeignKeyField(Animal, backref="records", on_delete="CASCADE")
    kind = CharField(default="vaccine")
    title = CharField(max_length=120)
    done_date = DateField()
    dose = CharField(max_length=60, default="")
    performer = CharField(max_length=80, default="")
    next_date = DateField(null=True)


class Task(BaseModel):
    farm = ForeignKeyField(Farm, backref="tasks", on_delete="CASCADE")
    animal = ForeignKeyField(Animal, null=True, backref="tasks", on_delete="CASCADE")
    record = ForeignKeyField(HealthRecord, null=True, backref="tasks", on_delete="CASCADE")
    kind = CharField(default="vaccine")
    title = CharField(max_length=120, default="")
    due_date = DateField()
    done = BooleanField(default=False)
    done_at = DateTimeField(null=True)


class ReproEvent(BaseModel):
    """Случка (mating) или ягнение (lambing) у матки."""
    animal = ForeignKeyField(Animal, backref="repro", on_delete="CASCADE")
    kind = CharField(default="mating")
    event_date = DateField()
    partner = ForeignKeyField(Animal, null=True, backref="partner_events", on_delete="SET NULL")
    males = IntegerField(default=0)
    females = IntegerField(default=0)


class AppSetting(BaseModel):
    key = CharField(primary_key=True)
    value = CharField(default="")


ALL_MODELS = [Farm, User, Animal, HealthRecord, Task, ReproEvent, AppSetting]


def init_db(path: str) -> None:
    db.init(path, pragmas={"foreign_keys": 1, "journal_mode": "wal"})
    db.connect(reuse_if_open=True)
    db.create_tables(ALL_MODELS)
    # миграция: колонка photo появилась позже первых версий базы
    cols = [row[1] for row in db.execute_sql("PRAGMA table_info(animal)").fetchall()]
    if "photo" not in cols:
        db.execute_sql("ALTER TABLE animal ADD COLUMN photo VARCHAR(255) NOT NULL DEFAULT ''")
