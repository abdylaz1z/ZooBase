"""Заменяет workflow: сборка Buildozer напрямую на сервере GitHub, без Docker-действия."""
WORKFLOW = """name: Build APK
on:
  workflow_dispatch:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-22.04
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
      - name: System packages
        run: |
          sudo apt-get update
          sudo apt-get install -y git zip unzip autoconf automake libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev ccache
      - name: Install Buildozer
        run: pip install --upgrade buildozer "cython<3.1" virtualenv
      - name: Build APK
        run: buildozer -v android debug
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: zoobase-apk
          path: bin/*.apk
          if-no-files-found: warn
"""
open(".github/workflows/build-apk.yml", "w", encoding="utf-8").write(WORKFLOW)
print("Workflow обновлён.")
