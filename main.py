"""ZooBase — учёт племенных овец (Арашан, Ала-Тоо). Запуск: python main.py"""
import logging
import os

from kivy.config import Config

Config.set("kivy", "exit_on_escape", "0")

from kivy.core.window import Window  # noqa: E402
from kivy.lang import Builder  # noqa: E402
from kivy.metrics import dp  # noqa: E402
from kivy.properties import ListProperty, StringProperty  # noqa: E402
from kivymd.app import MDApp  # noqa: E402
from kivymd.uix.label import MDLabel  # noqa: E402
from kivymd.uix.screenmanager import MDScreenManager  # noqa: E402
from kivymd.uix.snackbar import MDSnackbar  # noqa: E402

from zoobase.config import DB_FILENAME  # noqa: E402
from zoobase.controllers import (AnimalController, FarmController, HealthController,  # noqa: E402
                                 ReproController, SettingsController, TaskController)
from zoobase.i18n import tr  # noqa: E402
from zoobase.models import init_db  # noqa: E402
from zoobase.views.screens import (DetailScreen, FormScreen, HealthScreen, HomeScreen,  # noqa: E402
                                   RegisterScreen, ReproScreen, TaskScreen)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zoobase")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
Window.softinput_mode = "below_target"  # клавиатура не перекрывает поля ввода


class ZooBaseApp(MDApp):
    lang = StringProperty("ru")
    canvas_color = ListProperty([0.96, 0.97, 0.94, 1])
    surface_color = ListProperty([1, 1, 1, 1])
    brand_color = ListProperty([0.08, 0.31, 0.22, 1])
    brand_text_color = ListProperty([1, 1, 1, 1])
    accent_color = ListProperty([0.96, 0.69, 0.19, 1])
    accent_text_color = ListProperty([0.20, 0.14, 0.05, 1])
    ink_color = ListProperty([0.12, 0.17, 0.14, 1])
    muted_color = ListProperty([0.40, 0.47, 0.42, 1])

    def build(self):
        self.title = "ZooBase"
        init_db(os.path.join(self.user_data_dir, DB_FILENAME))
        self.settings, self.farms, self.animals = SettingsController(), FarmController(), AnimalController()
        self.health, self.tasks, self.repro = HealthController(), TaskController(), ReproController()
        self.animals.photo_dir = os.path.join(self.user_data_dir, "photos")
        self.lang = self.settings.get("lang", "ru")
        self.theme_cls.theme_style = self.settings.get("theme", "Light")
        self.theme_cls.primary_palette = "Green"
        self.theme_cls.primary_hue = "800"
        self.theme_cls.accent_palette = "Amber"
        self.theme_cls.accent_hue = "A700"
        self._set_theme_colors(self.theme_cls.theme_style == "Dark")
        self.farm = self.farms.current()
        self.history = []

        Builder.load_file(os.path.join(BASE_DIR, "zoobase", "views", "zoobase.kv"))
        self.sm = MDScreenManager()
        self.register = RegisterScreen(name="register")
        self.home = HomeScreen(name="home")
        self.form = FormScreen(name="form")
        self.detail = DetailScreen(name="detail")
        self.health_screen = HealthScreen(name="health")
        self.repro_screen = ReproScreen(name="repro")
        self.task_screen = TaskScreen(name="task")
        for s in (self.register, self.home, self.form, self.detail, self.health_screen, self.repro_screen, self.task_screen):
            self.sm.add_widget(s)
        self.sm.current = "home" if self.farm else "register"
        Window.bind(on_keyboard=self.on_key)
        return self.sm

    # ---- локализация и тема ----
    def t(self, key, lang=None):
        return tr(key, lang or self.lang)

    def set_lang(self, code):
        self.lang = code
        self.settings.set("lang", code)
        if self.farm:
            self.home.refresh_all()

    def set_dark(self, active):
        self.theme_cls.theme_style = "Dark" if active else "Light"
        self._set_theme_colors(active)
        self.settings.set("theme", self.theme_cls.theme_style)

    def _set_theme_colors(self, dark):
        """Keep neutral surfaces dominant in both themes; green and amber stay intentional."""
        if dark:
            self.canvas_color = [0.055, 0.085, 0.07, 1]
            self.surface_color = [0.10, 0.145, 0.12, 1]
            self.brand_color = [0.09, 0.32, 0.23, 1]
            self.accent_color = [0.98, 0.72, 0.24, 1]
            self.accent_text_color = [0.20, 0.14, 0.05, 1]
            self.ink_color = [0.94, 0.96, 0.93, 1]
            self.muted_color = [0.68, 0.75, 0.70, 1]
        else:
            self.canvas_color = [0.96, 0.97, 0.94, 1]
            self.surface_color = [1, 1, 1, 1]
            self.brand_color = [0.08, 0.31, 0.22, 1]
            self.accent_color = [0.96, 0.69, 0.19, 1]
            self.accent_text_color = [0.20, 0.14, 0.05, 1]
            self.ink_color = [0.12, 0.17, 0.14, 1]
            self.muted_color = [0.40, 0.47, 0.42, 1]

    def toast(self, key):
        try:
            MDSnackbar(MDLabel(text=self.t(key), theme_text_color="Custom", text_color="white"),
                       y=dp(24), pos_hint={"center_x": .5}, size_hint_x=.9).open()
        except Exception:  # noqa: BLE001
            log.exception("snackbar")

    # ---- навигация ----
    def go(self, name):
        self.history.append(self.sm.current)
        self.sm.transition.direction = "left"
        self.sm.current = name

    def go_home(self, reset=True):
        if reset:
            self.history = []
        else:
            self.history = [h for h in self.history if h == "home"][:1]
        self.sm.transition.direction = "right"
        self.sm.current = "home"

    def open_animal(self, animal_id):
        if self.sm.current == "detail":
            self.detail.push(animal_id)
        else:
            self.detail.open(animal_id)
            self.go("detail")

    def open_form(self, animal_id):
        self.form.load(animal_id)
        self.go("form")

    def open_health(self, animal_id):
        self.health_screen.load(animal_id)
        self.go("health")

    def open_task(self):
        self.task_screen.load()
        self.go("task")

    def open_repro(self, animal_id, kind):
        self.repro_screen.load(animal_id, kind)
        self.go("repro")

    def back(self):
        if self.sm.current == "detail" and len(self.detail.trail) > 1:
            self.detail.trail.pop()
            self.detail.render()
            return True
        if self.history:
            self.sm.transition.direction = "right"
            self.sm.current = self.history.pop()
            return True
        return False

    def on_key(self, window, key, *args):
        if key == 27:  # кнопка «Назад» на Android
            return self.back()
        return False


if __name__ == "__main__":
    ZooBaseApp().run()
