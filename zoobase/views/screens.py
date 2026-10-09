"""View: экраны KivyMD. Вся логика данных — через контроллеры приложения (app.animals, app.tasks, ...)."""
import logging
import os
from datetime import date

from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.utils import platform
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivy.uix.image import Image
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.label import MDLabel
from kivymd.uix.list import (IconLeftWidget, IconRightWidget, MDList, OneLineListItem,
                             TwoLineAvatarIconListItem)
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.pickers import MDDatePicker
from kivymd.uix.screen import MDScreen

from ..config import (BREEDS, DATE_FMT, GREEN, GREY, HEALTH_KINDS, LIST_LIMIT, RED, SEXES,
                      STATUSES, YELLOW)
from ..controllers import age_parts

log = logging.getLogger("zoobase")


def app():
    return MDApp.get_running_app()


def T(key):
    return app().t(key)


def fmt(d):
    return d.strftime(DATE_FMT) if d else T("not_set")


def label_of(a):
    return f"{a.tag} · {a.name}" if a.name else a.tag


def anc_label(path):
    """Подпись предка по пути: ('f','m') -> «Мать отца» / «Атасынын энеси»."""
    if app().lang == "ky":
        return " ".join([T("anc_%s_g" % k) for k in path[:-1]] + [T("anc_" + path[-1])])
    return " ".join([T("anc_" + path[-1])] + [T("anc_%s_g" % k) for k in reversed(path[:-1])])


def choose_dialog(title, options, on_pick):
    """Диалог выбора из списка [(значение, подпись), ...]."""
    holder = {}

    def make(value, text):
        def _pick(*_):
            holder["dlg"].dismiss()
            on_pick(value)
        return OneLineListItem(text=text, on_release=_pick)

    lst = MDList()
    for v, t in options:
        lst.add_widget(make(v, t))
    box = MDScrollView(size_hint_y=None, height=min(dp(56) * len(options), dp(320)))
    box.add_widget(lst)
    dlg = MDDialog(title=title, type="custom", content_cls=box)
    holder["dlg"] = dlg
    dlg.open()


def pick_date(callback, initial=None, max_date=None):
    try:
        kw = {}
        if initial:
            kw.update(year=initial.year, month=initial.month, day=initial.day)
        if max_date:
            kw["max_date"] = max_date
        dlg = MDDatePicker(**kw)
        dlg.bind(on_save=lambda inst, value, rng: callback(value))
        dlg.open()
    except Exception:  # noqa: BLE001 — UI не должен падать из-за пикера
        log.exception("date picker")


class RegisterScreen(MDScreen):
    def submit(self):
        a, i = app(), self.ids
        res = a.farms.create(i.farm_name.text, i.region.text, i.owner.text, i.phone.text)
        if res.ok:
            a.farm = res.data
            a.go_home()
        else:
            a.toast(res.message)


class HomeScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.filters = {"breed": None, "sex": None, "status": None}

    def on_pre_enter(self, *args):
        self.refresh_all()

    def refresh_all(self):
        self.refresh_tasks()
        self.refresh_animals()
        self.refresh_profile()

    # ---- задачи ----
    def refresh_tasks(self):
        a, box = app(), self.ids.tasks_list
        box.clear_widgets()
        if not a.farm:
            return
        groups = a.tasks.grouped(a.farm)
        if not any(groups.values()):
            box.add_widget(OneLineListItem(text=T("no_tasks")))
            return
        for key, color, icon in (("overdue", RED, "alert-circle"), ("today", YELLOW, "clock-alert"),
                                 ("soon", GREEN, "calendar-clock")):
            if not groups[key]:
                continue
            box.add_widget(MDLabel(text=T(key), font_style="Subtitle1", adaptive_height=True,
                                   theme_text_color="Custom", text_color=a.brand_color,
                                   padding=(dp(16), dp(12))))
            for t in groups[key]:
                who = label_of(t.animal) if t.animal_id else ""
                title = (t.title if t.kind == "task" and t.title
                         else f"{T('k_' + t.kind)}: {t.title}" if t.title else T("k_" + t.kind))
                item = TwoLineAvatarIconListItem(
                    text=title, secondary_text=f"{who} · {fmt(t.due_date)}".strip(" ·"),
                    on_release=lambda *_, aid=t.animal_id: aid and a.open_animal(aid))
                item.add_widget(IconLeftWidget(icon=icon, theme_text_color="Custom", text_color=color))
                item.add_widget(IconRightWidget(icon="check-circle-outline",
                                                on_release=lambda *_, tid=t.id: self.complete(tid)))
                box.add_widget(item)

    def complete(self, task_id):
        res = app().tasks.complete(task_id)
        app().toast(res.message)
        self.refresh_tasks()
        self.refresh_animals()

    # ---- животные ----
    def _filter_options(self, kind):
        if kind == "breed":
            return [(b, T("breed_" + b)) for b in BREEDS]
        if kind == "sex":
            return [(s, T(s)) for s in SEXES]
        return [(s, T("st_" + s)) for s in STATUSES]

    def update_filter_buttons(self):
        for kind in ("breed", "sex", "status"):
            val = self.filters[kind]
            if val is None:
                shown = T("all")
            else:
                shown = dict(self._filter_options(kind))[val]
            self.ids["f_" + kind].text = f"{T(kind)}: {shown}"

    def pick_filter(self, kind):
        def _set(v):
            self.filters[kind] = v
            self.refresh_animals()
        choose_dialog(T(kind), [(None, T("all"))] + self._filter_options(kind), _set)

    def refresh_animals(self):
        a, lst = app(), self.ids.animals_list
        lst.clear_widgets()
        self.update_filter_buttons()
        if not a.farm:
            return
        f = self.filters
        items = a.animals.search(a.farm, self.ids.search.text, f["breed"], f["sex"], f["status"])
        urgency = a.tasks.urgency_map(a.farm)
        self.ids.count_label.text = f"{T('shown')}: {min(len(items), LIST_LIMIT)} / {len(items)}"
        if not items:
            lst.add_widget(OneLineListItem(text=T("no_animals")))
        for an in items[:LIST_LIMIT]:
            if an.status in ("sold", "culled", "dead"):
                color = GREY
            elif urgency.get(an.id) == "red":
                color = RED
            elif urgency.get(an.id) == "yellow" or an.status == "quarantine":
                color = YELLOW
            else:
                color = GREEN
            age = age_parts(an.birth_date)
            age_txt = f"{age[0]} {T('y_short')} {age[1]} {T('m_short')}" if age else ""
            sec = " · ".join(x for x in (T("breed_" + an.breed), T(an.sex), age_txt, T("st_" + an.status)) if x)
            item = TwoLineAvatarIconListItem(text=label_of(an), secondary_text=sec,
                                             on_release=lambda *_, aid=an.id: a.open_animal(aid))
            item.add_widget(IconLeftWidget(icon="sheep", theme_text_color="Custom", text_color=color))
            lst.add_widget(item)

    # ---- профиль ----
    def refresh_profile(self):
        a = app()
        if not a.farm:
            return
        owner = a.farms.owner(a.farm)
        st = a.animals.stats(a.farm)
        fert = a.repro.fertility(a.farm)
        fert = f"{fert:.2f}" if fert is not None else "—"
        self.ids.farm_title.text = a.farm.name
        self.ids.farm_meta.text = f"{T('region')}: {a.farm.region}" if a.farm.region else "—"
        owner_details = " · ".join(
            value for value in (owner.name if owner else "", owner.phone if owner else "") if value
        )
        self.ids.farm_owner.text = f"{T('owner')}: {owner_details}" if owner_details else "—"
        self.ids.total_value.text = str(st["total"])
        self.ids.male_value.text = str(st["male"])
        self.ids.female_value.text = str(st["female"])
        self.ids.fertility_value.text = fert
        self.ids.unsynced_value.text = str(a.farms.unsynced_count())
        self.ids.dark_switch.active = a.theme_cls.theme_style == "Dark"


class FormScreen(MDScreen):
    title_text = StringProperty("")
    has_photo = BooleanProperty(False)

    def load(self, animal_id=None):
        a, i = app(), self.ids
        self.animal_id = animal_id
        self.state = {"breed": "arashan", "sex": "female", "status": "active",
                      "birth_date": None, "father_id": None, "mother_id": None, "photo": ""}
        an = a.animals.get(animal_id)
        self.orig_photo = an.photo if an else ""
        self.title_text = T("edit_animal") if an else T("add_animal")
        if an:
            self.state.update(breed=an.breed, sex=an.sex, status=an.status, birth_date=an.birth_date,
                              father_id=an.father_id, mother_id=an.mother_id, photo=an.photo)
        i.tag.text, i.name.text = (an.tag, an.name) if an else ("", "")
        i.chip.text, i.notes.text = (an.chip, an.notes) if an else ("", "")
        self.update_buttons()

    def _parent_text(self, pid):
        p = app().animals.get(pid)
        return label_of(p) if p else T("not_set")

    def update_buttons(self):
        s, i = self.state, self.ids
        i.breed_btn.text = f"{T('breed')}: {T('breed_' + s['breed'])}"
        i.sex_btn.text = f"{T('sex')}: {T(s['sex'])}"
        i.birth_btn.text = f"{T('birth_date')}: {fmt(s['birth_date'])}"
        i.status_btn.text = f"{T('status')}: {T('st_' + s['status'])}"
        i.father_btn.text = f"{T('father')}: {self._parent_text(s['father_id'])}"
        i.mother_btn.text = f"{T('mother')}: {self._parent_text(s['mother_id'])}"
        self.update_photo()

    def _set(self, key, value):
        self.state[key] = value
        self.update_buttons()

    def update_photo(self):
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

    def pick_breed(self):
        choose_dialog(T("breed"), [(b, T("breed_" + b)) for b in BREEDS], lambda v: self._set("breed", v))

    def pick_sex(self):
        choose_dialog(T("sex"), [(s, T(s)) for s in SEXES], lambda v: self._set("sex", v))

    def pick_status(self):
        choose_dialog(T("status"), [(s, T("st_" + s)) for s in STATUSES], lambda v: self._set("status", v))

    def pick_birth(self):
        pick_date(lambda d: self._set("birth_date", d), self.state["birth_date"], max_date=date.today())

    def pick_parent(self, which):
        a = app()
        sex = "male" if which == "father" else "female"
        opts = [(None, T("not_set"))] + [(x.id, label_of(x))
                                          for x in a.animals.candidates(a.farm, sex, self.animal_id)]
        choose_dialog(T(which), opts, lambda v: self._set(which + "_id", v))

    def save(self):
        a, i = app(), self.ids
        data = dict(self.state, tag=i.tag.text, name=i.name.text, chip=i.chip.text, notes=i.notes.text)
        res = a.animals.save(a.farm, self.animal_id, data)
        a.toast(res.message)
        if res.ok:
            a.back()


class PhotoView(Image):
    """Фото с обрезкой по рамке и скруглёнными углами (правила в zoobase.kv)."""


class HeroCard(MDCard):
    """Большая карточка сверху: фото (или заглушка), имя, номер и цветной статус."""
    source = StringProperty("")
    title = StringProperty("")
    subtitle = StringProperty("")
    status_text = StringProperty("")
    status_color = ListProperty([1, 1, 1, 1])
    chip_w = NumericProperty(120)


class StatTile(MDCard):
    """Плитка с иконкой, значением и подписью."""
    icon = StringProperty("")
    value = StringProperty("")
    caption = StringProperty("")


class LinkRow(MDCard):
    """Строка с цветной иконкой, заголовком, подписью и меткой справа (для родословной, здоровья, репродукции)."""
    icon = StringProperty("")
    title = StringProperty("")
    caption = StringProperty("")
    tag = StringProperty("")
    tint = ListProperty([0.1, 0.3, 0.2, 1])
    tag_color = ListProperty([0.4, 0.47, 0.42, 1])


class SoftCard(MDCard):
    pass


class SectionLabel(MDLabel):
    pass


class DetailScreen(MDScreen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.trail = []  # стек просмотренных карточек (переход к родителю и назад)

    @property
    def animal_id(self):
        return self.trail[-1] if self.trail else None

    def open(self, animal_id):
        self.trail = [animal_id]

    def push(self, animal_id):
        self.trail.append(animal_id)
        self.render()

    def on_pre_enter(self, *args):
        self.render()

    def render(self):
        a, box = app(), self.ids.body
        box.clear_widgets()
        an = a.animals.get(self.animal_id)
        if not an:
            return
        self.ids.toolbar.title = label_of(an)
        tint = list(a.brand_color)

        def muted_label(text):
            return MDLabel(text=text, adaptive_height=True, padding=(dp(6), dp(2)), font_style="Body2",
                           theme_text_color="Custom", text_color=a.muted_color)

        def info(label, value):
            row = MDBoxLayout(adaptive_height=True, padding=(0, dp(6)), spacing=dp(8))
            row.add_widget(MDLabel(text=label, adaptive_height=True, size_hint_x=.55, font_style="Body2",
                                   theme_text_color="Custom", text_color=a.muted_color))
            row.add_widget(MDLabel(text=value, adaptive_height=True, halign="right", font_style="Body2",
                                   theme_text_color="Custom", text_color=a.ink_color))
            return row

        # --- большая карточка: фото, имя, статус ---
        urgency = a.tasks.urgency_map(a.farm).get(an.id)
        if an.status in ("sold", "culled", "dead"):
            color = GREY
        elif urgency == "red":
            color = RED
        elif urgency == "yellow" or an.status == "quarantine":
            color = YELLOW
        else:
            color = GREEN
        status = T("st_" + an.status)
        hero = HeroCard(source=an.photo if an.photo and os.path.exists(an.photo) else "",
                        title=an.name or an.tag,
                        subtitle=(f"{an.tag} · " if an.name else "") + T("breed_" + an.breed),
                        status_text=status, status_color=list(color), chip_w=dp(30) + len(status) * dp(8))
        hero.bind(on_release=lambda *_: self.edit())
        box.add_widget(hero)

        # --- плитки: пол, возраст, потомство ---
        age = age_parts(an.birth_date)
        age_txt = f"{age[0]} {T('y_short')} {age[1]} {T('m_short')}" if age else "—"
        tiles = MDBoxLayout(adaptive_height=True, spacing=dp(10))
        for icon, value, caption in (
                ("gender-female" if an.sex == "female" else "gender-male", T(an.sex), T("sex")),
                ("cake-variant", age_txt, T("age")),
                ("baby-face-outline", str(len(a.animals.offspring(an))), T("offspring_short"))):
            tiles.add_widget(StatTile(icon=icon, value=value, caption=caption))
        box.add_widget(tiles)

        # --- о животном ---
        about = SoftCard()
        about.add_widget(info(T("birth_date"), fmt(an.birth_date)))
        about.add_widget(info(T("chip"), an.chip or T("not_set")))
        if an.notes:
            about.add_widget(info(T("notes"), an.notes))
        box.add_widget(SectionLabel(text=T("about")))
        box.add_widget(about)

        # --- родословная: родители рядом, дальше предки ---
        box.add_widget(SectionLabel(text=T("pedigree")))
        father, mother = a.animals.parents(an)
        parents = MDBoxLayout(adaptive_height=True, spacing=dp(10))
        for which, parent, icon in (("father", father, "gender-male"), ("mother", mother, "gender-female")):
            row = LinkRow(icon=icon, title=(parent.name or parent.tag) if parent else T("not_set"),
                          caption=f"{T(which)} · {parent.tag}" if parent and parent.name else T(which), tint=tint)
            if parent:
                row.bind(on_release=lambda *_, pid=parent.id: self.push(pid))
            parents.add_widget(row)
        box.add_widget(parents)
        for path, anc in [(p, x) for p, x in a.animals.pedigree(an) if len(p) >= 2]:
            row = LinkRow(icon="family-tree", title=anc.name or anc.tag,
                          caption=f"{anc_label(path)} · {anc.tag}" if anc.name else anc_label(path),
                          tint=list(a.muted_color))
            row.bind(on_release=lambda *_, pid=anc.id: self.push(pid))
            box.add_widget(row)

        # --- репродукция (только матки) ---
        if an.sex == "female":
            box.add_widget(SectionLabel(text=T("repro")))
            expected = a.repro.expected_lambing(an)
            if expected:
                box.add_widget(LinkRow(icon="calendar-clock", title=fmt(expected), caption=T("expected"),
                                       tint=list(YELLOW)))
            events = a.repro.list_for(an)
            if not events and not expected:
                box.add_widget(muted_label(T("no_records")))
            for ev in events:
                if ev.kind == "mating":
                    partner = a.animals.get(ev.partner_id)
                    head = f"{T('ev_mating')}: {label_of(partner) if partner else T('not_set')}"
                    sub, icon, col = fmt(ev.event_date), "heart-outline", tint
                else:
                    head = f"{T('ev_lambing')}: {ev.males + ev.females}"
                    sub = (f"{fmt(ev.event_date)} · {T('males_count')} {ev.males} · "
                           f"{T('females_count')} {ev.females}")
                    icon, col = "baby-carriage", list(GREEN)
                box.add_widget(LinkRow(icon=icon, title=head, caption=sub, tint=col))

        # --- здоровье ---
        box.add_widget(SectionLabel(text=T("health")))
        records = a.health.list_for(an)
        if not records:
            box.add_widget(muted_label(T("no_records")))
        kinds = {"vaccine": ("needle", GREEN), "parasite": ("bug-outline", YELLOW),
                 "disease": ("medical-bag", RED), "note": ("note-text-outline", a.muted_color)}
        for r in records:
            icon, col = kinds.get(r.kind, kinds["note"])
            extra = " · ".join(x for x in (fmt(r.done_date), r.dose, r.performer) if x)
            overdue = bool(r.next_date) and r.next_date < date.today()
            box.add_widget(LinkRow(
                icon=icon, title=f"{T('k_' + r.kind)}: {r.title}", caption=extra, tint=list(col),
                tag=f"{T('next_short')}\n{fmt(r.next_date)}" if r.next_date else "",
                tag_color=list(RED if overdue else a.muted_color)))
        box.add_widget(Widget(size_hint_y=None, height=dp(90)))  # место под кнопку «+»

    def edit(self):
        app().open_form(self.animal_id)

    def add_record(self):
        a = app()
        an = a.animals.get(self.animal_id)
        opts = [("health", T("add_record"))]
        if an and an.sex == "female":
            opts += [("mating", T("ev_mating")), ("lambing", T("ev_lambing"))]
        choose_dialog(T("add_event"), opts,
                      lambda v: a.open_health(self.animal_id) if v == "health" else a.open_repro(self.animal_id, v))

    def confirm_delete(self):
        holder = {}

        def _do(*_):
            holder["dlg"].dismiss()
            a = app()
            res = a.animals.delete(self.animal_id)
            a.toast(res.message)
            if res.ok:
                self.trail = []
                a.go_home(reset=False)

        holder["dlg"] = MDDialog(
            text=T("confirm_delete"),
            buttons=[MDFlatButton(text=T("cancel"), on_release=lambda *_: holder["dlg"].dismiss()),
                     MDFlatButton(text=T("delete"), on_release=_do)])
        holder["dlg"].open()


class HealthScreen(MDScreen):
    def load(self, animal_id):
        i = self.ids
        self.animal_id = animal_id
        self.state = {"kind": "vaccine", "done_date": date.today(), "next_date": None}
        i.title.text = i.dose.text = i.performer.text = ""
        self.update_buttons()

    def update_buttons(self):
        s, i = self.state, self.ids
        i.kind_btn.text = f"{T('kind')}: {T('k_' + s['kind'])}"
        i.done_btn.text = f"{T('done_date')}: {fmt(s['done_date'])}"
        i.next_btn.text = f"{T('next_date')}: {fmt(s['next_date'])}"

    def _set(self, key, value):
        self.state[key] = value
        self.update_buttons()

    def pick_kind(self):
        choose_dialog(T("kind"), [(k, T("k_" + k)) for k in HEALTH_KINDS], lambda v: self._set("kind", v))

    def pick_done(self):
        pick_date(lambda d: self._set("done_date", d), self.state["done_date"])

    def pick_next(self):
        pick_date(lambda d: self._set("next_date", d), self.state["next_date"] or date.today())

    def save(self):
        a, i = app(), self.ids
        data = dict(self.state, title=i.title.text, dose=i.dose.text, performer=i.performer.text)
        res = a.health.add(self.animal_id, data)
        a.toast(res.message)
        if res.ok:
            a.back()


class ReproScreen(MDScreen):
    title_text = StringProperty("")
    is_lambing = BooleanProperty(False)

    def load(self, animal_id, kind):
        self.animal_id, self.kind = animal_id, kind
        self.state = {"event_date": date.today(), "partner_id": None}
        self.title_text = T("ev_" + kind)
        self.is_lambing = kind == "lambing"
        self.ids.males.text = self.ids.females.text = ""
        self.update_buttons()

    def update_buttons(self):
        s, i = self.state, self.ids
        partner = app().animals.get(s["partner_id"])
        i.date_btn.text = f"{T('event_date')}: {fmt(s['event_date'])}"
        i.partner_btn.text = f"{T('partner')}: {label_of(partner) if partner else T('not_set')}"

    def _set(self, key, value):
        self.state[key] = value
        self.update_buttons()

    def pick_date(self):
        pick_date(lambda d: self._set("event_date", d), self.state["event_date"], max_date=date.today())

    def pick_partner(self):
        a = app()
        opts = [(None, T("not_set"))] + [(x.id, label_of(x)) for x in a.animals.candidates(a.farm, "male")]
        choose_dialog(T("partner"), opts, lambda v: self._set("partner_id", v))

    def save(self):
        a, i = app(), self.ids
        data = dict(self.state, kind=self.kind, males=i.males.text, females=i.females.text)
        res = a.repro.add(self.animal_id, data)
        a.toast(res.message)
        if res.ok:
            a.back()


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