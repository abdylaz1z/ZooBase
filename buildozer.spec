[app]
title = ZooBase
package.name = zoobase
package.domain = kg.zoobase
source.dir = .
source.include_exts = py,kv,png,jpg,ttf,xml
source.exclude_dirs = tests,docs,android_src,.git,.github
source.exclude_patterns = patch_*.py,setup_ci.py,fix_ci.py
version = 0.2.0
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,sqlite3,peewee==3.17.9
orientation = portrait
fullscreen = 0
android.minapi = 26
android.accept_sdk_license = True
android.permissions = POST_NOTIFICATIONS,RECEIVE_BOOT_COMPLETED
android.api = 35
android.ndk = 28c
android.ndk_api = 26
android.archs = arm64-v8a, armeabi-v7a, x86_64
android.add_src = android_src
android.extra_manifest_application_arguments = android_src/manifest.xml
android.allow_backup = False
p4a.branch = v2026.05.09

[buildozer]
log_level = 2
