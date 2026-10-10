#!/usr/bin/env bash
set -euo pipefail
mkdir -p android-artifacts
adb install -r apk/*.apk
adb logcat -c
adb shell svc wifi disable
adb shell svc data disable
adb shell monkey -p kg.zoobase.zoobase -c android.intent.category.LAUNCHER 1
sleep 25
adb shell pidof kg.zoobase.zoobase
adb exec-out screencap -p > android-artifacts/01-launch-offline.png
adb logcat -d > android-artifacts/logcat.txt
if grep -E 'FATAL EXCEPTION|Traceback \(most recent call last\)' android-artifacts/logcat.txt; then exit 1; fi
adb shell am force-stop kg.zoobase.zoobase
adb shell monkey -p kg.zoobase.zoobase -c android.intent.category.LAUNCHER 1
sleep 12
adb shell pidof kg.zoobase.zoobase
adb exec-out screencap -p > android-artifacts/02-relaunch-offline.png
adb logcat -d > android-artifacts/logcat.txt
if grep -E 'FATAL EXCEPTION|Traceback \(most recent call last\)' android-artifacts/logcat.txt; then exit 1; fi
adb shell dumpsys package kg.zoobase.zoobase > android-artifacts/package.txt
