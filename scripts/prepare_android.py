"""Prepare pinned p4a with the upstream multi-architecture pip-venv repair.

See https://github.com/kivy/python-for-android/issues/3339 and PR #3360.
Native recipe versions stay unchanged; only the temporary pip environment changes.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".buildozer" / "p4a"
TAG = "v2026.05.09"
if not SOURCE.exists():
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", "--branch", TAG,
                    "https://github.com/kivy/python-for-android.git", str(SOURCE)], check=True)

target = SOURCE / "pythonforandroid" / "build.py"
text = target.read_text(encoding="utf-8")
old = "shprint(host_python, '-m', 'venv', 'venv')"
new = "shprint(host_python, '-m', 'venv', '--clear', 'venv')"
if old in text:
    text = text.replace(old, new)
elif new not in text:
    raise SystemExit("Unexpected p4a version: inspect the venv creation code before building")
old_upgrade = '''        info('Upgrade pip to latest version')
        shprint(sh.bash, '-c', (
            "source venv/bin/activate && pip install -U pip"
        ), _env=copy.copy(base_env))'''
new_upgrade = "        info('Using pip from a fresh hostpython virtualenv')"
if old_upgrade in text:
    text = text.replace(old_upgrade, new_upgrade)
elif new_upgrade not in text:
    raise SystemExit("Unexpected p4a pip setup: inspect before building")
target.write_text(text, encoding="utf-8")
print("Pinned p4a prepared with fresh per-architecture pip environments")

# Buildozer's extra_manifest_application_arguments inserts attributes inside
# the opening application tag, not child elements. Register the receiver as
# a child in the pinned SDL template, including already cached distributions.
receiver = (ROOT / "android_src" / "manifest.xml").read_text(encoding="utf-8").strip()
templates = [SOURCE / "pythonforandroid/bootstraps/_sdl_common/build/templates/AndroidManifest.tmpl.xml"]
templates.extend((ROOT / ".buildozer/android").rglob("AndroidManifest.tmpl.xml"))
for template in templates:
    manifest = template.read_text(encoding="utf-8")
    if 'kg.zoobase.platform.ReminderReceiver' not in manifest:
        if '</application>' not in manifest:
            raise SystemExit(f"Application element missing: {template}")
        template.write_text(manifest.replace('</application>', receiver + '\n    </application>'), encoding="utf-8")
print("Reminder receiver registered as an application child")
