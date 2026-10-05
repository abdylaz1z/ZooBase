"""Готовит проект к облачной сборке APK на GitHub Actions. Запуск из папки с main.py: python setup_ci.py"""
import os

WORKFLOW = """name: Build APK
on:
  workflow_dispatch:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - name: Build with Buildozer
        id: buildozer
        uses: ArtemSBulgakov/buildozer-action@v1
        with:
          command: buildozer android debug
          buildozer_version: stable
      - uses: actions/upload-artifact@v4
        with:
          name: zoobase-apk
          path: ${{ steps.buildozer.outputs.filename }}
"""
os.makedirs(".github/workflows", exist_ok=True)
open(".github/workflows/build-apk.yml", "w", encoding="utf-8").write(WORKFLOW)
open(".gitignore", "w", encoding="utf-8").write("venv/\n.buildozer/\nbin/\n__pycache__/\n*.pyc\n")
spec = open("buildozer.spec", encoding="utf-8").read()
if "android.accept_sdk_license" not in spec:
    spec = spec.replace("android.minapi = 26", "android.minapi = 26\nandroid.accept_sdk_license = True")
    open("buildozer.spec", "w", encoding="utf-8").write(spec)
print("Готово: .github/workflows/build-apk.yml, .gitignore, buildozer.spec обновлены.")
