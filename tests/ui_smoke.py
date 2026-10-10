"""Exercise actual Kivy screens under Xvfb and keep screenshots for visual inspection."""
import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kivy.config import Config
Config.set("graphics", "width", "392")
Config.set("graphics", "height", "844")
from kivy.clock import Clock
from kivy.core.window import Window
from main import ZooBaseApp


class SmokeApp(ZooBaseApp):
    failure = None
    stage = 0

    def on_start(self):
        Clock.schedule_once(self.step, 5)

    def step(self, _dt):
        try:
            out = Path("ui-artifacts")
            out.mkdir(exist_ok=True)
            self.root.export_to_png(str(out / f"screen-{self.stage}.png"))
            if self.stage == 0:
                i = self.register.ids
                i.farm_name.text, i.region.text = "Арашан", "Чүй"
                i.owner.text, i.phone.text = "Айбек", "+996700123456"
                self.register.submit()
                assert self.farm is not None
                self.set_lang("ru")
                self.open_form(None)
            elif self.stage == 1:
                self.form.ids.tag.text = "KG-001"
                self.form.ids.name.text = "Ак кой"
                self.form.save()
                assert len(self.animals.search(self.farm)) == 1
                self.open_animal(self.animals.search(self.farm)[0].id)
            elif self.stage == 2:
                self.open_health(self.detail.animal_id)
                self.health_screen.ids.title.text = "Плановая обработка"
            elif self.stage == 3:
                from datetime import date, timedelta
                self.health_screen.state["next_date"] = date.today() + timedelta(days=30)
                self.health_screen.save()
                self.go_home()
                assert len(self.tasks.grouped(self.farm)["later"]) == 1
            elif self.stage == 4:
                self.home.ids.nav.switch_tab("tab_animals")
            elif self.stage == 5:
                self.home.ids.nav.switch_tab("tab_profile")
            elif self.stage == 6:
                self.set_lang("ky")
                self.set_dark(True)
            else:
                self.stop()
                return
            self.stage += 1
            Clock.schedule_once(self.step, 1.5)
        except Exception:
            self.failure = traceback.format_exc()
            print(self.failure, flush=True)
            self.stop()


with tempfile.TemporaryDirectory() as temp:
    app = SmokeApp()
    app._user_data_dir = temp
    app.run()
    if app.failure:
        sys.exit(1)
