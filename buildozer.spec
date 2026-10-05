[app]
title = ZooBase
package.name = zoobase
package.domain = kg.zoobase
source.dir = .
source.include_exts = py,kv,png,jpg,ttf
version = 0.1.0
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,sqlite3,peewee
orientation = portrait
fullscreen = 0
android.minapi = 26
android.accept_sdk_license = True
android.permissions = READ_EXTERNAL_STORAGE,READ_MEDIA_IMAGES
android.api = 33
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
