"""Black-box Android journey using visible text and native document-picker nodes.

Run only on an empty test emulator. Never runs against a user's physical phone.
"""
import csv
import io
import re
import sqlite3
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PACKAGE = "kg.zoobase.zoobase"
OUT = Path("android-journey")
OUT.mkdir(exist_ok=True)
counter = 0


def adb(*args, check=True):
    return subprocess.run(["adb", *args], check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def shot(label):
    global counter
    counter += 1
    path = OUT / f"{counter:02}-{label}.png"
    path.write_bytes(adb("exec-out", "screencap", "-p"))
    return path


def words():
    from PIL import Image
    path = shot("screen")
    high_contrast = OUT / "ocr-input.png"
    Image.open(path).convert("L").point(lambda p: 0 if p < 205 else 255).save(high_contrast)
    records = []
    for source, mode in ((path, "11"), (high_contrast, "6")):
        output = subprocess.run(["tesseract", str(source), "stdout", "-l", "rus+eng", "--psm", mode, "tsv"],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()
        records.extend(r for r in csv.DictReader(io.StringIO(output), delimiter="\t") if r.get("text", "").strip())
    return records


def tap_text(fragment):
    records = words()
    needle = fragment.casefold()
    matches = [r for r in records if needle in r["text"].casefold()]
    if not matches:
        # Tesseract suppresses text enclosed by Kivy's outlined input fields.
        # Scan overlapping interior strips without their rectangular borders.
        from PIL import Image
        screen = Image.open(shot("field-scan")).convert("L")
        left = int(screen.width * .07)
        for top in range(0, screen.height - 64, 64):
            path = OUT / "ocr-strip.png"
            screen.crop((left, top, int(screen.width * .93), min(top + 128, screen.height))).save(path)
            output = subprocess.run(["tesseract", str(path), "stdout", "-l", "rus+eng", "--psm", "6", "tsv"],
                                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()
            for row in csv.DictReader(io.StringIO(output), delimiter="\t"):
                if needle in row.get("text", "").casefold():
                    row["left"] = str(int(row["left"]) + left)
                    row["top"] = str(int(row["top"]) + top)
                    matches.append(row)
            if matches:
                break
    if not matches:
        raise AssertionError(f"Visible text {fragment!r} not found: {[r['text'] for r in records]}")
    row = matches[-1]
    x = int(row["left"]) + int(row["width"]) // 2
    y = int(row["top"]) + int(row["height"]) // 2
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(1.5)


def fill(fragment, value):
    tap_text(fragment)
    # SDL consumes keyboard events asynchronously; type at a human cadence.
    for character in value:
        adb("shell", "input", "text", "%s" if character == " " else character)
        time.sleep(.12)
    adb("shell", "input", "keyevent", "4")  # dismiss IME
    time.sleep(1)


def tap_gold_button():
    # Find the visible amber action surface, independent of screen density.
    from PIL import Image
    image = Image.open(shot("action")).convert("RGB")
    rows = []
    for y in range(image.height // 3, image.height - 50):
        xs = [x for x in range(image.width // 2, image.width)
              if (lambda p: p[0] > 180 and 100 < p[1] < 215 and p[0] > p[1] * 1.15 and p[2] < 90)(image.getpixel((x, y)))]
        if len(xs) > 50:
            rows.append((y, xs))
    if not rows:
        raise AssertionError("Amber action button not visible")
    groups = []
    for row in rows:
        if not groups or row[0] > groups[-1][-1][0] + 1:
            groups.append([])
        groups[-1].append(row)
    group = max(groups, key=len)
    y, xs = group[len(group) // 2]
    adb("shell", "input", "tap", str((min(xs) + max(xs)) // 2), str(y))
    time.sleep(1.5)


def save_document():
    # Android's native picker exposes labels even though Kivy draws its own UI.
    for _ in range(8):
        adb("shell", "uiautomator", "dump", "/sdcard/window.xml")
        raw = adb("shell", "cat", "/sdcard/window.xml")
        (OUT / "document-picker.xml").write_bytes(raw)
        root = ET.fromstring(raw)
        for node in root.iter("node"):
            if node.attrib.get("text", "").casefold() in ("save", "сохранить"):
                bounds = list(map(int, re.findall(r"\d+", node.attrib["bounds"])))
                adb("shell", "input", "tap", str((bounds[0] + bounds[2]) // 2), str((bounds[1] + bounds[3]) // 2))
                time.sleep(3)
                return
        time.sleep(1)
    raise AssertionError("Native Save button not found")


def enable_reminders():
    from PIL import Image
    image = Image.open(shot("settings"))
    adb("shell", "input", "swipe", str(image.width // 2), str(int(image.height * .82)),
        str(image.width // 2), str(int(image.height * .50)), "500")
    time.sleep(1)
    rows = [r for r in words() if "напоминания" in r["text"].casefold()]
    assert rows, "Reminder setting not visible"
    y = int(rows[0]["top"]) + int(rows[0]["height"]) // 2
    adb("shell", "input", "tap", str(int(image.width * .895)), str(y))
    time.sleep(2)
    adb("shell", "uiautomator", "dump", "/sdcard/window.xml")
    root = ET.fromstring(adb("shell", "cat", "/sdcard/window.xml"))
    for node in root.iter("node"):
        if node.attrib.get("text", "").casefold() in ("allow", "разрешить"):
            box = list(map(int, re.findall(r"\d+", node.attrib["bounds"])))
            adb("shell", "input", "tap", str((box[0] + box[2]) // 2), str((box[1] + box[3]) // 2))
            time.sleep(2)
            break
    alarms = adb("shell", "dumpsys", "alarm")
    (OUT / "alarms.txt").write_bytes(alarms)
    assert re.search(rb"RTC_WAKEUP[^\n]*" + re.escape(PACKAGE.encode()), alarms), "Local reminder alarm was not scheduled"
    shot("reminders-enabled")


def main():
    assert adb("shell", "getprop", "ro.kernel.qemu").strip() == b"1", "Test emulator required"
    adb("shell", "settings", "put", "system", "screen_off_timeout", "1800000")
    adb("shell", "settings", "put", "global", "stay_on_while_plugged_in", "7")
    adb("shell", "pm", "clear", PACKAGE)
    adb("logcat", "-c")
    adb("shell", "svc", "wifi", "disable")
    adb("shell", "svc", "data", "disable")
    adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(20)
    tap_text("Русский")
    fill("Название", "CI Farm")
    fill("Район", "Chui")
    fill("владельца", "CI Owner")
    fill("Телефон", "+996700123456")
    tap_gold_button()
    shot("farm-created")
    print("Farm registration completed", flush=True)
    tap_text("Овцы")
    tap_gold_button()
    fill("Инвентарный", "CI-001")
    fill("Кличка", "Ovca")
    from PIL import Image
    image = Image.open(shot("animal-form"))
    for _ in range(3):
        # Use the scroll-view gutter so a drag cannot activate a form selector.
        adb("shell", "input", "swipe", str(int(image.width * .975)), str(int(image.height * .82)),
            str(int(image.width * .975)), str(int(image.height * .25)), "700")
        time.sleep(.5)
    tap_gold_button()
    time.sleep(3)  # the saved snackbar temporarily covers the bottom navigation
    shot("animal-saved")
    print("Animal form saved", flush=True)
    tap_text("Хозяйство")
    tap_gold_button()
    shot("document-picker")
    save_document()
    shot("backup-exported")
    # Verify actual exported file, not merely a success message.
    paths = adb("shell", "find", "/sdcard/Download", "-name", "ZooBase-*.zip").decode().splitlines()
    assert paths, "No exported backup in Downloads"
    adb("pull", paths[-1].strip(), str(OUT / "exported-backup.zip"))
    with zipfile.ZipFile(OUT / "exported-backup.zip") as archive:
        (OUT / "backup.db").write_bytes(archive.read("zoobase.db"))
    with sqlite3.connect(OUT / "backup.db") as conn:
        assert conn.execute("SELECT name FROM farm").fetchone()[0] == "CI Farm"
        assert conn.execute("SELECT tag FROM animal").fetchone()[0] == "CI-001"
    print("Native exported backup contents verified", flush=True)
    enable_reminders()
    print("Daily reminder alarm verified", flush=True)
    adb("shell", "am", "force-stop", PACKAGE)
    adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(15)
    tap_text("Овцы")
    shot("persisted-after-relaunch")
    database = adb("shell", "run-as", PACKAGE, "find", "files", "-name", "zoobase.db").decode().strip().splitlines()[0]
    adb("shell", "am", "force-stop", PACKAGE)
    for suffix in ("", "-wal", "-shm"):
        data = adb("exec-out", "run-as", PACKAGE, "cat", database + suffix, check=False)
        if data:
            (OUT / ("persisted.db" + suffix)).write_bytes(data)
    with sqlite3.connect(OUT / "persisted.db") as conn:
        assert conn.execute("SELECT tag FROM animal").fetchone()[0] == "CI-001"
    (OUT / "result.txt").write_text("PASS: offline registration, animal creation, native SAF backup, reminder alarm scheduled, persisted restart", encoding="utf-8")


try:
    main()
finally:
    shot("final")
    (OUT / "logcat.txt").write_bytes(adb("logcat", "-d"))
