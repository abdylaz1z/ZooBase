"""Патч ZooBase: фото животного + кнопка «Новая задача» на вкладке «Сегодня».
Запуск из папки проекта (где лежит main.py):  python patch_photo_tasks.py"""
import os
import sys


def patch(path, pairs, required=True):
    if not os.path.exists(path):
        if required:
            sys.exit("Не найден файл: " + path + " — запустите патч из папки с main.py")
        return
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        if s.count(old) != 1:
            if required:
                sys.exit("Не удалось применить патч к %s (фрагмент найден %d раз): %s" % (path, s.count(old), old[:60]))
            continue
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)


# ---------------- models ----------------
patch("zoobase/models.py", [
    ('''    notes = TextField(default="")

    class Meta:
        indexes = ((("farm", "tag"), True),)''',
     '''    notes = TextField(default="")
    photo = CharField(max_length=255, default="")

    class Meta:
        indexes = ((("farm", "tag"), True),)'''),
    ('''    db.create_tables(ALL_MODELS)''',
     '''    db.create_tables(ALL_MODELS)
    # миграция: колонка photo появилась позже первых версий базы
    cols = [row[1] for row in db.execute_sql("PRAGMA table_info(animal)").fetchall()]
    if "photo" not in cols:
        db.execute_sql("ALTER TABLE animal ADD COLUMN photo VARCHAR(255) NOT NULL DEFAULT ''")'''),
])

# ---------------- controllers ----------------
patch("zoobase/controllers.py", [
    ('''import logging
import re
''', '''import logging
import os
import re
import uuid
'''),
    ('''    def parents(self, animal):''',
     '''    photo_dir = ""  # задаётся в main.py: папка данных приложения / photos

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
            root = os.path.abspath(self.photo_dir) if self.photo_dir else None
            if path and root and os.path.abspath(path).startswith(root) and os.path.exists(path):
                os.remove(path)
        except OSError:
            log.exception("remove photo")

    def parents(self, animal):'''),
    ('''                          notes=(d.get("notes") or "").strip())''',
     '''                          notes=(d.get("notes") or "").strip(), photo=d.get("photo") or "")'''),
    ('''                    for k, v in fields.items():
                        setattr(animal, k, v)
                    animal.save()''',
     '''                    old_photo = animal.photo
                    for k, v in fields.items():
                        setattr(animal, k, v)
                    animal.save()
                    if old_photo and old_photo != fields["photo"]:
                        self.remove_photo(old_photo)'''),
    ('''    def delete(self, animal_id) -> Result:
        try:
            with db.atomic():
                Animal.delete().where(Animal.id == animal_id).execute()
            return Result(True, "deleted")''',
     '''    def delete(self, animal_id) -> Result:
        try:
            animal = Animal.get_or_none(Animal.id == animal_id)
            with db.atomic():
                Animal.delete().where(Animal.id == animal_id).execute()
            if animal and animal.photo:
                self.remove_photo(animal.photo)
            return Result(True, "deleted")'''),
    ('''    def urgency_map(self, farm) -> dict:''',
     '''    def add(self, farm, d: dict) -> Result:
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

    def urgency_map(self, farm) -> dict:'''),
])

# ---------------- i18n ----------------
patch("zoobase/i18n.py", [
    ('''    "err_number": ("Введите целое число от 0 до 9", "0дөн 9го чейин бүтүн сан киргизиңиз"),
}''',
     '''    "err_number": ("Введите целое число от 0 до 9", "0дөн 9го чейин бүтүн сан киргизиңиз"),
    "add_task": ("Новая задача", "Жаңы тапшырма"),
    "task_title": ("Что нужно сделать", "Эмне кылуу керек"),
    "task_date": ("Срок", "Мөөнөтү"),
    "task_animal": ("Животное", "Жаныбар"),
    "k_task": ("Задача", "Тапшырма"),
    "err_task_title": ("Укажите название задачи", "Тапшырманын атын жазыңыз"),
    "err_photo": ("Не удалось загрузить фото", "Сүрөттү жүктөө мүмкүн болгон жок"),
    "choose_photo": ("Добавить фото", "Сүрөт кошуу"),
    "remove_photo": ("Убрать фото", "Сүрөттү өчүрүү"),
}'''),
])

# ---------------- screens ----------------
patch("zoobase/views/screens.py", [
    ('''import logging
from datetime import date''', '''import logging
import os
from datetime import date'''),
    ('''from kivy.properties import BooleanProperty, StringProperty''',
     '''from kivy.properties import BooleanProperty, StringProperty
from kivy.utils import platform'''),
    ('''from kivymd.uix.dialog import MDDialog''',
     '''from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.fitimage import FitImage'''),
    ('''title = f"{T('k_' + t.kind)}: {t.title}" if t.title else T("k_" + t.kind)''',
     '''title = (t.title if t.kind == "task" and t.title
                         else f"{T('k_' + t.kind)}: {t.title}" if t.title else T("k_" + t.kind))'''),
    ('''class FormScreen(MDScreen):
    title_text = StringProperty("")''',
     '''class FormScreen(MDScreen):
    title_text = StringProperty("")
    has_photo = BooleanProperty(False)'''),
    ('''        self.state = {"breed": "arashan", "sex": "female", "status": "active",
                      "birth_date": None, "father_id": None, "mother_id": None}''',
     '''        self.state = {"breed": "arashan", "sex": "female", "status": "active",
                      "birth_date": None, "father_id": None, "mother_id": None, "photo": ""}'''),
    ('''        an = a.animals.get(animal_id)
        self.title_text = T("edit_animal") if an else T("add_animal")''',
     '''        an = a.animals.get(animal_id)
        self.orig_photo = an.photo if an else ""
        self.title_text = T("edit_animal") if an else T("add_animal")'''),
    ('''father_id=an.father_id, mother_id=an.mother_id)''', '''father_id=an.father_id, mother_id=an.mother_id, photo=an.photo)'''),
    ('''        i.mother_btn.text = f"{T('mother')}: {self._parent_text(s['mother_id'])}"''',
     '''        i.mother_btn.text = f"{T('mother')}: {self._parent_text(s['mother_id'])}"
        self.update_photo()'''),
    ('''    def pick_breed(self):''',
     '''    def update_photo(self):
        path = self.state.get("photo") or ""
        ok = bool(path) and os.path.exists(path)
        self.has_photo = ok
        self.ids.photo_img.source = path if ok else ""
        self.ids.photo_img.opacity = 1 if ok else 0

    def pick_photo(self):
        """Выбор фото из галереи/папки через файловый менеджер KivyMD."""
        try:
            if platform == "android":
                try:
                    from android.permissions import Permission, request_permissions
                    request_permissions([Permission.READ_EXTERNAL_STORAGE])
                except ImportError:
                    pass
                start = "/storage/emulated/0"
            else:
                start = os.path.expanduser("~")
            self.fm = MDFileManager(exit_manager=self._close_fm, select_path=self._on_photo,
                                    ext=[".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"])
            self.fm.show(start)
        except Exception:  # noqa: BLE001 — UI не должен падать из-за файлового менеджера
            log.exception("file manager")
            app().toast("err_photo")

    def _close_fm(self, *_):
        self.fm.close()

    def _on_photo(self, path):
        self.fm.close()
        res = app().animals.store_photo(path)
        if not res.ok:
            app().toast(res.message)
            return
        self._drop_new_photo()
        self.state["photo"] = res.data
        self.update_buttons()

    def _drop_new_photo(self):
        old = self.state.get("photo") or ""
        if old and old != self.orig_photo:
            app().animals.remove_photo(old)

    def remove_photo(self):
        self._drop_new_photo()
        self.state["photo"] = ""
        self.update_buttons()

    def pick_breed(self):'''),
    ('''        self.ids.toolbar.title = label_of(an)
''',
     '''        self.ids.toolbar.title = label_of(an)
        if an.photo and os.path.exists(an.photo):
            box.add_widget(FitImage(source=an.photo, size_hint_y=None, height=dp(240)))
'''),
])
open("zoobase/views/screens.py", "a", encoding="utf-8").write('''

class TaskScreen(MDScreen):
    def load(self):
        self.state = {"due_date": date.today(), "animal_id": None}
        self.ids.title.text = ""
        self.update_buttons()

    def update_buttons(self):
        s, i = self.state, self.ids
        an = app().animals.get(s["animal_id"])
        i.date_btn.text = f"{T('task_date')}: {fmt(s['due_date'])}"
        i.animal_btn.text = f"{T('task_animal')}: {label_of(an) if an else T('not_set')}"

    def _set(self, key, value):
        self.state[key] = value
        self.update_buttons()

    def pick_date(self):
        pick_date(lambda d: self._set("due_date", d), self.state["due_date"])

    def pick_animal(self):
        a = app()
        opts = [(None, T("not_set"))] + [(x.id, label_of(x)) for x in a.animals.search(a.farm)[:LIST_LIMIT]]
        choose_dialog(T("task_animal"), opts, lambda v: self._set("animal_id", v))

    def save(self):
        a = app()
        res = a.tasks.add(a.farm, dict(self.state, title=self.ids.title.text))
        a.toast(res.message)
        if res.ok:
            a.back()
''')

# ---------------- kv ----------------
patch("zoobase/views/zoobase.kv", [
    ('''            on_tab_press: root.refresh_tasks()
            MDBoxLayout:
                orientation: "vertical"
                MDTopAppBar:
                    title: app.t("tab_tasks", app.lang)
                MDScrollView:
                    MDList:
                        id: tasks_list''',
     '''            on_tab_press: root.refresh_tasks()
            MDFloatLayout:
                MDBoxLayout:
                    orientation: "vertical"
                    MDTopAppBar:
                        title: app.t("tab_tasks", app.lang)
                    MDScrollView:
                        MDList:
                            id: tasks_list
                MDFloatingActionButton:
                    icon: "plus"
                    pos_hint: {"right": .95, "y": .04}
                    on_release: app.open_task()'''),
    ('''        MDScrollView:
            FormBox:
                MDTextField:
                    id: tag''',
     '''        MDScrollView:
            FormBox:
                MDCard:
                    size_hint_y: None
                    height: dp(180)
                    radius: [dp(12)]
                    on_release: root.pick_photo()
                    MDFloatLayout:
                        MDIcon:
                            icon: "camera-plus"
                            font_size: "48sp"
                            theme_text_color: "Hint"
                            pos_hint: {"center_x": .5, "center_y": .58}
                        MDLabel:
                            text: app.t("choose_photo", app.lang)
                            halign: "center"
                            theme_text_color: "Hint"
                            pos_hint: {"center_x": .5, "center_y": .22}
                        FitImage:
                            id: photo_img
                            source: ""
                            opacity: 0
                            radius: [dp(12)]
                MDFlatButton:
                    text: app.t("remove_photo", app.lang)
                    opacity: 1 if root.has_photo else 0
                    disabled: not root.has_photo
                    on_release: root.remove_photo()
                MDTextField:
                    id: tag'''),
])
open("zoobase/views/zoobase.kv", "a", encoding="utf-8").write('''
<TaskScreen>:
    MDBoxLayout:
        orientation: "vertical"
        MDTopAppBar:
            title: app.t("add_task", app.lang)
            left_action_items: [["arrow-left", lambda x: app.back()]]
        MDScrollView:
            FormBox:
                MDTextField:
                    id: title
                    hint_text: app.t("task_title", app.lang)
                    mode: "rectangle"
                MDRectangleFlatButton:
                    id: date_btn
                    size_hint_x: 1
                    on_release: root.pick_date()
                MDRectangleFlatButton:
                    id: animal_btn
                    size_hint_x: 1
                    on_release: root.pick_animal()
                MDRaisedButton:
                    text: app.t("save", app.lang)
                    size_hint_x: 1
                    on_release: root.save()
''')

# ---------------- main ----------------
patch("main.py", [
    ("RegisterScreen, ReproScreen)", "RegisterScreen, ReproScreen, TaskScreen)"),
    ('''self.health, self.tasks, self.repro = HealthController(), TaskController(), ReproController()''',
     '''self.health, self.tasks, self.repro = HealthController(), TaskController(), ReproController()
        self.animals.photo_dir = os.path.join(self.user_data_dir, "photos")'''),
    ('''        self.repro_screen = ReproScreen(name="repro")
''', '''        self.repro_screen = ReproScreen(name="repro")
        self.task_screen = TaskScreen(name="task")
'''),
    ("self.health_screen, self.repro_screen):", "self.health_screen, self.repro_screen, self.task_screen):"),
    ('''    def open_repro(self, animal_id, kind):''',
     '''    def open_task(self):
        self.task_screen.load()
        self.go("task")

    def open_repro(self, animal_id, kind):'''),
])
patch("buildozer.spec", [("android.minapi = 26", "android.minapi = 26\nandroid.permissions = READ_EXTERNAL_STORAGE,READ_MEDIA_IMAGES")], required=False)
print("Готово: фото животного и кнопка «Новая задача» добавлены.")
