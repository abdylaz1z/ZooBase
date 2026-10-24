"""Create a shareable PDF passport from an animal's existing ZooBase records."""
import os
import re
from pathlib import Path

from fpdf import FPDF


ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")


class AnimalPassportPDF(FPDF):
    def __init__(self, title, subtitle):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.passport_title = title
        self.passport_subtitle = subtitle
        self.set_margins(14, 41, 14)
        self.set_auto_page_break(auto=True, margin=18)
        self.add_font("ZooBase", "", os.path.join(ASSET_DIR, "DejaVuSans.ttf"))
        self.add_font("ZooBase", "B", os.path.join(ASSET_DIR, "DejaVuSans-Bold.ttf"))

    def header(self):
        self.set_fill_color(14, 33, 69)
        self.rect(0, 0, self.w, 34, style="F")
        self.set_xy(14, 7)
        self.set_text_color(255, 255, 255)
        self.set_font("ZooBase", "B", 16)
        self.cell(0, 9, self.passport_title, ln=1)
        self.set_x(14)
        self.set_text_color(202, 220, 242)
        self.set_font("ZooBase", "", 9)
        self.cell(0, 6, self.passport_subtitle)
        self.set_y(41)

    def footer(self):
        self.set_y(-13)
        self.set_draw_color(220, 228, 238)
        self.line(14, self.get_y(), self.w - 14, self.get_y())
        self.set_y(-11)
        self.set_text_color(110, 124, 145)
        self.set_font("ZooBase", "", 8)
        self.cell(0, 6, f"ZooBase  ·  {self.page_no()}", align="R")


def _section(pdf, title):
    pdf.ln(3)
    pdf.set_fill_color(235, 242, 250)
    pdf.set_text_color(14, 33, 69)
    pdf.set_font("ZooBase", "B", 11)
    pdf.cell(0, 8, title, fill=True, ln=1)
    pdf.ln(1)


def _field(pdf, label, value):
    pdf.set_text_color(103, 117, 137)
    pdf.set_font("ZooBase", "", 8)
    pdf.cell(0, 5, label, ln=1)
    pdf.set_text_color(25, 37, 57)
    pdf.set_font("ZooBase", "", 10)
    pdf.multi_cell(0, 5.5, str(value or "—"))
    pdf.ln(1)


def create_animal_passport(animal, sections, output_dir, photo_path=None):
    """Write an A4 PDF and return its path without modifying any records."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    safe_tag = re.sub(r"[^\w-]+", "_", animal.tag, flags=re.UNICODE).strip("_") or "animal"
    filename = f"passport_{animal.id}_{safe_tag}.pdf"
    path = os.path.join(output_dir, filename)

    pdf = AnimalPassportPDF(sections["title"], sections["subtitle"])
    pdf.add_page()
    if photo_path and os.path.isfile(photo_path):
        pdf.image(photo_path, x=14, y=43, w=44, h=44, keep_aspect_ratio=True)
        pdf.set_y(94)

    for section_title, fields in sections["identity"]:
        _section(pdf, section_title)
        for label, value in fields:
            _field(pdf, label, value)

    for section_title, records in ((sections["health_title"], sections["health"]),
                                   (sections["repro_title"], sections["repro"])):
        _section(pdf, section_title)
        if not records:
            _field(pdf, sections["empty"], "")
            continue
        for record_title, lines in records:
            pdf.set_text_color(25, 37, 57)
            pdf.set_font("ZooBase", "B", 9)
            pdf.multi_cell(0, 5, record_title)
            pdf.set_text_color(103, 117, 137)
            pdf.set_font("ZooBase", "", 8)
            for line in lines:
                pdf.multi_cell(0, 4.5, line)
            pdf.ln(1.5)

    if sections.get("notes"):
        _section(pdf, sections["notes_title"])
        pdf.set_text_color(25, 37, 57)
        pdf.set_font("ZooBase", "", 9)
        pdf.multi_cell(0, 5, sections["notes"])

    pdf.output(path)
    return path


def publish_to_android_downloads(path):
    """Copy the private file to Downloads through MediaStore (Android 10+)."""
    from jnius import autoclass
    from jnius.typedarray import array

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    ContentValues = autoclass("android.content.ContentValues")
    Downloads = autoclass("android.provider.MediaStore$Downloads")
    MediaColumns = autoclass("android.provider.MediaStore$MediaColumns")
    values = ContentValues()
    values.put(MediaColumns.DISPLAY_NAME, os.path.basename(path))
    values.put(MediaColumns.MIME_TYPE, "application/pdf")
    values.put(MediaColumns.RELATIVE_PATH, "Download/ZooBase")
    uri = activity.getContentResolver().insert(Downloads.EXTERNAL_CONTENT_URI, values)
    if uri is None:
        return False

    with open(path, "rb") as source:
        data = source.read()
    java_bytes = array("b", [byte if byte < 128 else byte - 256 for byte in data])
    stream = activity.getContentResolver().openOutputStream(uri)
    if stream is None:
        return False
    try:
        stream.write(java_bytes)
        stream.flush()
    finally:
        stream.close()
    return True


def downloads_directory():
    path = os.path.join(str(Path.home()), "Downloads", "ZooBase")
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        return ""
