[app]
title = ZooBase
icon.filename = assets/icon.png
presplash.filename = assets/icon.png
android.presplash_color = #143e2e
package.name = zoobase
package.domain = kg.zoobase
source.dir = .
source.include_exts = py,kv,png,jpg,ttf,xml
source.exclude_dirs = tests,docs,scripts,android_src,android_res,.git,.github
source.exclude_patterns = patch_*.py,setup_ci.py,fix_ci.py
version = 0.2.0
requirements = python3==3.11.17,hostpython3==3.11.17,kivy==2.3.1,kivymd==1.2.0,pillow,sqlite3,peewee==3.17.9
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
android.add_resources = android_res
android.apptheme = @style/ZooBaseTheme
android.allow_backup = False
p4a.branch = v2026.05.09
p4a.source_dir = .buildozer/p4a

[buildozer]
log_level = 2
