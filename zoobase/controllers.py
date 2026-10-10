"""Controller: бизнес-логика учёта. Методы изменения данных возвращают Result (ключ сообщения для i18n)."""
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from peewee import JOIN, IntegrityError, PeeweeException

from .config import (BREEDS, GESTATION_DAYS, HEALTH_KINDS, LIVE_STATUSES, PEDIGREE_DEPTH, REPRO_KINDS,
                     SEXES, SOON_DAYS, STATUSES, WARN_DAYS)
from .models import (ALL_MODELS, Animal, AppSetting, Farm, HealthRecord, ReproEvent, Task, User, db)

log = logging.getLogger("zoobase")
PHONE_RE = re.compile(r"^\+?\d{9,13}$")


@dataclass
class Result:
    ok: bool
    message: str = ""
    data: Any = None


def age_parts(birth: Optional[date], today: Optional[date] = None):
    """Возвращает (лет, месяцев) или None."""
    if not birth:
        return None
    t = today or date.today()
    months = (t.year - birth.year) * 12 + (t.month - birth.month) - (1 if t.day < birth.day else 0)
    months = max(months, 0)
    return months // 12, months % 12


class SettingsController:
    def get(self, key: str, default: str = "") -> str:
        try:
            row = AppSetting.get_or_none(AppSetting.key == key)
            return row.value if row else default
        except PeeweeException:
            log.exception("settings get")
            return default

    def set(self, key: str, value: str) -> None:
        try:
            row = AppSetting.get_or_none(AppSetting.key == key)
            if row:
                row.value = value
                row.save()
            else:
                AppSetting.create(key=key, value=value)
        except PeeweeException:
            log.exception("settings set")


class FarmController:
    def current(self) -> Optional[Farm]:
        try:
            return Farm.select().order_by(Farm.id).first()
        except PeeweeException:
            log.exception("farm current")
            return None

    def create(self, name: str, region: str, owner: str, phone: str) -> Result:
        name, region, owner = (name or "").strip(), (region or "").strip(), (owner or "").strip()
        phone = re.sub(r"[\s\-()]", "", phone or "")
        if not name or not owner:
            return Result(False, "err_name_required")
        if not PHONE_RE.match(phone):
            return Result(False, "err_phone")
        try:
            with db.atomic():
                farm = Farm.create(name=name, region=region)
                User.create(farm=farm, name=owner, phone=phone, role="owner")
            return Result(True, "saved", farm)
        except PeeweeException:
            log.exception("farm create")
            return Result(False, "err_db")

    def owner(self, farm: Farm) -> Optional[User]:
        try:
            return User.select().where(User.farm == farm, User.role == "owner").first()
        except PeeweeException:
            return None

    def unsynced_count(self) -> int:
        try:
            return sum(m.select().where(m.synced == False).count()  # noqa: E712
                       for m in ALL_MODELS if m is not AppSetting)
        except PeeweeException:
            return 0


class AnimalController:
    def get(self, animal_id) -> Optional[Animal]:
        if not animal_id:
            return None
        try:
            return Animal.get_or_none(Animal.id == animal_id)
        except PeeweeException:
            log.exception("animal get")
            return None

    def search(self, farm, query="", breed=None, sex=None, status=None) -> list:
        try:
            q = Animal.select().where(Animal.farm == farm)
            if breed:
                q = q.where(Animal.breed == breed)
            if sex:
                q = q.where(Animal.sex == sex)
            if status:
                q = q.where(Animal.status == status)
            items = list(q.order_by(Animal.tag))
        except PeeweeException:
            log.exception("animal search")
            return []
        needle = (query or "").strip().casefold()  # casefold: корректно для кириллицы
        if needle:
            items = [a for a in items if needle in f"{a.tag} {a.name} {a.chip}".casefold()]
        return items

    def candidates(self, farm, sex: str, exclude_id=None) -> list:
        return [a for a in self.search(farm, sex=sex) if a.id != exclude_id]

    photo_dir = ""  # задаётся в main.py: папка данных приложения / photos

    def store_photo(self, src: str) -> Result:
        """Копирует выбранное фото в папку приложения: поворот по EXIF, уменьшение до 800 px (экономит место)."""
        try:
            from PIL import Image, ImageOps
            os.makedirs(self.photo_dir, exist_ok=True)
            dest = os.path.join(self.photo_dir, uuid.uuid4().hex + ".jpg")
            with Image.open(src) as raw:
                img = ImageOps.exif_transpose(raw).convert("RGB")
            img.thumbnail((800, 800))
            img.save(dest, "JPEG", quality=85)
            return Result(True, "saved", dest)
        except (OSError, ValueError, ImportError):
            log.exception("store photo")
            return Result(False, "err_photo")

    def remove_photo(self, path: str) -> None:
        """Удаляет файл фото, только если он лежит в папке приложения."""
        try:
            root = os.path.realpath(self.photo_dir) if self.photo_dir else None
            target = os.path.realpath(path) if path else None
            if target and root and os.path.commonpath([root, target]) == root and os.path.isfile(target):
                os.remove(path)
        except (OSError, ValueError):
            log.exception("remove photo")

    def parents(self, animal):
        """(отец, мать) — каждый Animal или None. Единая точка доступа для экранов."""
        try:
            return self.get(animal.father_id), self.get(animal.mother_id)
        except PeeweeException:
            log.exception("animal parents")
            return None, None

    def pedigree(self, animal, depth: int = PEDIGREE_DEPTH) -> list:
        """Предки до `depth` колен: [(путь, Animal)]. Путь ('f','m') = мать отца; ('m','f','f') и т.д."""
        result, level = [], [((), animal)]
        for _ in range(depth):
            nxt = []
            for path, an in level:
                for key, pid in (("f", an.father_id), ("m", an.mother_id)):
                    parent = self.get(pid)
                    if parent:
                        nxt.append((path + (key,), parent))
            result.extend(nxt)
            level = nxt
        return result

    def offspring(self, animal) -> list:
        try:
            return list(Animal.select().where((Animal.father == animal) | (Animal.mother == animal)))
        except PeeweeException:
            return []

    def stats(self, farm) -> dict:
        items = [a for a in self.search(farm) if a.status in LIVE_STATUSES]
        return {"total": len(items),
                "male": sum(1 for a in items if a.sex == "male"),
                "female": sum(1 for a in items if a.sex == "female")}

    def _validate(self, farm, d: dict, animal_id) -> Optional[str]:
        tag, chip = (d.get("tag") or "").strip(), (d.get("chip") or "").strip()
        if not tag:
            return "err_tag_required"
        if len(tag) > 32 or len(chip) > 40 or len(d.get("name") or "") > 60:
            return "err_too_long"
        if d.get("breed") not in BREEDS or d.get("sex") not in SEXES or d.get("status") not in STATUSES:
            return "err_choice"
        bd = d.get("birth_date")
        arrival = d.get("arrival_date")
        if (bd and bd > date.today()) or (arrival and arrival > date.today()):
            return "err_future_date"
        if bd and arrival and arrival < bd:
            return "err_arrival_date"
        if d.get("status") == "pregnant" and d.get("sex") != "female":
            return "err_repro_sex"
        if animal_id:
            existing = self.get(animal_id)
            if not existing or existing.farm_id != farm.id:
                return "err_not_found"
            children = self.offspring(existing)
            for child in children:
                expected = "male" if child.father_id == animal_id else "female"
                if d["sex"] != expected:
                    return "err_parent_sex"
                if bd and child.birth_date and bd >= child.birth_date:
                    return "err_parent_age"
        for fid, sex in ((d.get("father_id"), "male"), (d.get("mother_id"), "female")):
            if fid:
                if animal_id and fid == animal_id:
                    return "err_self_parent"
                parent = self.get(fid)
                if parent and parent.farm_id != farm.id:
                    return "err_parent_farm"
                if not parent or parent.sex != sex:
                    return "err_parent_sex"
                if bd and parent.birth_date and parent.birth_date >= bd:
                    return "err_parent_age"
                # Walk the entire ancestry, not just the three displayed generations.
                pending, seen = [parent.id], set()
                while pending:
                    pid = pending.pop()
                    if pid == animal_id:
                        return "err_parent_cycle"
                    if pid in seen:
                        continue
                    seen.add(pid)
                    ancestor = self.get(pid)
                    if ancestor:
                        pending.extend(p for p in (ancestor.father_id, ancestor.mother_id) if p)
        same_tag = Animal.select().where(Animal.farm == farm, Animal.tag == tag)
        if animal_id:
            same_tag = same_tag.where(Animal.id != animal_id)
        if same_tag.exists():
            return "err_tag_exists"
        if chip:
            same_chip = Animal.select().where(Animal.farm == farm, Animal.chip == chip)
            if animal_id:
                same_chip = same_chip.where(Animal.id != animal_id)
            if same_chip.exists():
                return "err_chip_exists"
        return None

    def save(self, farm, animal_id, d: dict) -> Result:
        """Создаёт (animal_id=None) или обновляет животное."""
        try:
            err = self._validate(farm, d, animal_id)
            if err:
                return Result(False, err)
            fields = dict(tag=d["tag"].strip(), name=(d.get("name") or "").strip(),
                          chip=(d.get("chip") or "").strip(), breed=d["breed"], sex=d["sex"],
                          birth_date=d.get("birth_date"), arrival_date=d.get("arrival_date"), status=d["status"],
                          father=d.get("father_id"), mother=d.get("mother_id"),
                          notes=(d.get("notes") or "").strip(), photo=d.get("photo") or "")
            old_photo = ""
            with db.atomic():
                if animal_id:
                    animal = Animal.get_or_none(Animal.id == animal_id)
                    if not animal:
                        return Result(False, "err_not_found")
                    old_photo = animal.photo
                    for k, v in fields.items():
                        setattr(animal, k, v)
                    animal.save()
                else:
                    animal = Animal.create(farm=farm, **fields)
            if old_photo and old_photo != fields["photo"]:
                self.remove_photo(old_photo)
            return Result(True, "saved", animal)
        except IntegrityError:
            log.exception("animal integrity")
            return Result(False, "err_tag_exists")
        except PeeweeException:
            log.exception("animal save")
            return Result(False, "err_db")

    def delete(self, animal_id) -> Result:
        try:
            animal = Animal.get_or_none(Animal.id == animal_id)
            with db.atomic():
                Animal.delete().where(Animal.id == animal_id).execute()
            if animal and animal.photo:
                self.remove_photo(animal.photo)
            return Result(True, "deleted")
        except PeeweeException:
            log.exception("animal delete")
            return Result(False, "err_db")


class HealthController:
    def list_for(self, animal) -> list:
        try:
            return list(HealthRecord.select().where(HealthRecord.animal == animal)
                        .order_by(HealthRecord.done_date.desc(), HealthRecord.id.desc()))
        except PeeweeException:
            log.exception("health list")
            return []

    def add(self, animal_id, d: dict) -> Result:
        """Добавляет запись; если указана следующая дата — автоматически создаёт задачу-напоминание."""
        try:
            animal = Animal.get_or_none(Animal.id == animal_id)
            if not animal:
                return Result(False, "err_not_found")
            title = (d.get("title") or "").strip()
            if d.get("kind") not in HEALTH_KINDS:
                return Result(False, "err_choice")
            if not title:
                return Result(False, "err_title_required")
            if len(title) > 120 or len(d.get("dose") or "") > 60 or len(d.get("performer") or "") > 80:
                return Result(False, "err_too_long")
            done_date, next_date = d.get("done_date") or date.today(), d.get("next_date")
            if done_date > date.today():
                return Result(False, "err_future_date")
            if animal.birth_date and done_date < animal.birth_date:
                return Result(False, "err_before_birth")
            if next_date and next_date < done_date:
                return Result(False, "err_date_order")
            with db.atomic():
                rec = HealthRecord.create(animal=animal, kind=d["kind"], title=title, done_date=done_date,
                                          dose=(d.get("dose") or "").strip(),
                                          performer=(d.get("performer") or "").strip(), next_date=next_date)
                if next_date:
                    Task.create(farm=animal.farm, animal=animal, record=rec, kind=d["kind"],
                                title=title, due_date=next_date)
            return Result(True, "saved", rec)
        except PeeweeException:
            log.exception("health add")
            return Result(False, "err_db")


class TaskController:
    def grouped(self, farm) -> dict:
        """{'overdue': [...], 'today': [...], 'soon': [...]} — только невыполненные задачи."""
        today = date.today()
        groups = {"overdue": [], "today": [], "soon": [], "later": []}
        try:
            q = (Task.select(Task, Animal).join(Animal, JOIN.LEFT_OUTER)
                 .where(Task.farm == farm, Task.done == False)  # noqa: E712
                 .order_by(Task.due_date, Task.id))
            for t in q:
                key = ("overdue" if t.due_date < today else "today" if t.due_date == today
                       else "soon" if t.due_date <= today + timedelta(days=SOON_DAYS) else "later")
                groups[key].append(t)
        except PeeweeException:
            log.exception("tasks grouped")
        return groups

    def complete(self, task_id) -> Result:
        try:
            task = Task.get_or_none(Task.id == task_id)
            if not task:
                return Result(False, "err_not_found")
            task.done, task.done_at = True, datetime.now()
            task.save()
            return Result(True, "done")
        except PeeweeException:
            log.exception("task complete")
            return Result(False, "err_db")

    def add(self, farm, d: dict) -> Result:
        """Ручная задача в ленту «Сегодня»: название, срок, животное (необязательно)."""
        try:
            title = (d.get("title") or "").strip()
            if not title:
                return Result(False, "err_task_title")
            if len(title) > 120:
                return Result(False, "err_too_long")
            animal_id = d.get("animal_id")
            if animal_id and not Animal.select().where(Animal.id == animal_id, Animal.farm == farm).exists():
                return Result(False, "err_not_found")
            Task.create(farm=farm, animal=animal_id, kind="task", title=title,
                        due_date=d.get("due_date") or date.today())
            return Result(True, "saved")
        except PeeweeException:
            log.exception("task add")
            return Result(False, "err_db")

    def urgency_map(self, farm) -> dict:
        """animal_id -> 'red' (просрочено) | 'yellow' (скоро)."""
        today, res = date.today(), {}
        try:
            q = Task.select().where(Task.farm == farm, Task.done == False,  # noqa: E712
                                    Task.animal.is_null(False),
                                    Task.due_date <= today + timedelta(days=WARN_DAYS))
            for t in q:
                if t.due_date < today:
                    res[t.animal_id] = "red"
                else:
                    res.setdefault(t.animal_id, "yellow")
        except PeeweeException:
            log.exception("urgency")
        return res


class ReproController:
    def list_for(self, animal) -> list:
        try:
            return list(ReproEvent.select().where(ReproEvent.animal == animal)
                        .order_by(ReproEvent.event_date.desc(), ReproEvent.id.desc()))
        except PeeweeException:
            log.exception("repro list")
            return []

    def expected_lambing(self, animal):
        """Дата ожидаемого ягнения (последняя случка + срок суягности) для суягной матки."""
        if animal.status != "pregnant":
            return None
        try:
            last = (ReproEvent.select().where(ReproEvent.animal == animal, ReproEvent.kind == "mating")
                    .order_by(ReproEvent.event_date.desc(), ReproEvent.id.desc()).first())
        except PeeweeException:
            log.exception("repro expected")
            return None
        return last.event_date + timedelta(days=GESTATION_DAYS) if last else None

    def fertility(self, farm):
        """Среднее число ягнят на одно ягнение по хозяйству или None."""
        try:
            events = list(ReproEvent.select().join(Animal, on=(ReproEvent.animal == Animal.id))
                          .where(Animal.farm == farm, ReproEvent.kind == "lambing"))
        except PeeweeException:
            log.exception("repro fertility")
            return None
        return sum(e.males + e.females for e in events) / len(events) if events else None

    def add(self, animal_id, d: dict) -> Result:
        """Случка: ставит статус «суягная» и задачу «ожидается ягнение». Ягнение: закрывает эту задачу."""
        try:
            animal = Animal.get_or_none(Animal.id == animal_id)
            if not animal:
                return Result(False, "err_not_found")
            kind = d.get("kind")
            if kind not in REPRO_KINDS:
                return Result(False, "err_choice")
            if animal.sex != "female":
                return Result(False, "err_repro_sex")
            ev_date = d.get("event_date") or date.today()
            if ev_date > date.today():
                return Result(False, "err_future_date")
            if animal.birth_date and ev_date < animal.birth_date:
                return Result(False, "err_before_birth")
            latest = (ReproEvent.select().where(ReproEvent.animal == animal)
                      .order_by(ReproEvent.event_date.desc()).first())
            if latest and ev_date < latest.event_date:
                return Result(False, "err_repro_order")
            if animal.status not in LIVE_STATUSES:
                return Result(False, "err_inactive")
            partner_id = d.get("partner_id")
            if partner_id:
                partner = Animal.get_or_none(Animal.id == partner_id)
                if partner and partner.farm_id != animal.farm_id:
                    return Result(False, "err_parent_farm")
                if not partner or partner.sex != "male":
                    return Result(False, "err_parent_sex")
            males = females = 0
            if kind == "lambing":
                try:
                    males = int(str(d.get("males") or "0").strip() or 0)
                    females = int(str(d.get("females") or "0").strip() or 0)
                except ValueError:
                    return Result(False, "err_number")
                if not (0 <= males <= 9 and 0 <= females <= 9):
                    return Result(False, "err_number")
                if males + females == 0:
                    return Result(False, "err_lambs")
            pending = (Task.animal == animal) & (Task.kind == "lambing") & (Task.done == False)  # noqa: E712
            with db.atomic():
                ev = ReproEvent.create(animal=animal, kind=kind, event_date=ev_date, partner=partner_id,
                                       males=males, females=females)
                if kind == "mating":
                    Task.delete().where(pending).execute()  # повторная случка: старый срок неактуален
                    Task.create(farm=animal.farm, animal=animal, kind="lambing", title="",
                                due_date=ev_date + timedelta(days=GESTATION_DAYS))
                    if animal.status == "active":
                        animal.status = "pregnant"
                        animal.save()
                else:
                    Task.update(done=True, done_at=datetime.now(), updated_at=datetime.now(), synced=False).where(pending).execute()
                    if animal.status == "pregnant":
                        animal.status = "active"
                        animal.save()
            return Result(True, "saved", ev)
        except PeeweeException:
            log.exception("repro add")
            return Result(False, "err_db")
