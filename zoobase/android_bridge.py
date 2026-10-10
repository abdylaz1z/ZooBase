"""Android document picker and local reminders, imported lazily on desktop."""
import os
from kivy.clock import Clock


class Documents:
    def __init__(self, cache_dir):
        from android import activity
        self.cache_dir = cache_dir
        self.pending = None
        activity.bind(on_activity_result=self._result)

    def open(self, mime, callback):
        self._launch(False, mime, callback)

    def save(self, path, mime, callback):
        self._launch(True, mime, callback, path)

    def _launch(self, saving, mime, callback, path=None):
        from jnius import autoclass
        from android.runnable import run_on_ui_thread
        if self.pending:
            return
        Intent = autoclass("android.content.Intent")
        intent = Intent(Intent.ACTION_CREATE_DOCUMENT if saving else Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(mime)
        if saving:
            autoclass("kg.zoobase.platform.FileBridge").setDocumentTitle(intent, os.path.basename(path))
        self.pending = (saving, path, callback)

        @run_on_ui_thread
        def launch():
            autoclass("org.kivy.android.PythonActivity").mActivity.startActivityForResult(intent, 812)
        launch()

    def _result(self, request, result, intent):
        if request != 812 or self.pending is None:
            return
        saving, path, callback = self.pending
        self.pending = None
        if result != -1 or intent is None:
            return
        uri = intent.getData().toString()

        def finish(_dt):
            from jnius import autoclass
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            bridge = autoclass("kg.zoobase.platform.FileBridge")
            try:
                if saving:
                    bridge.write(activity, path, uri)
                else:
                    path_in = os.path.join(self.cache_dir, "selected-document")
                    bridge.read(activity, uri, path_in, 512 * 1024 * 1024)
                callback(path if saving else path_in)
            except Exception:
                import logging
                logging.getLogger("zoobase").exception("document transfer")
                callback(None)
        Clock.schedule_once(finish)


def configure_reminders(database_path, language, enabled, request=False):
    from jnius import autoclass
    from android.permissions import request_permissions
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    if request and enabled and autoclass("android.os.Build$VERSION").SDK_INT >= 33:
        request_permissions(["android.permission.POST_NOTIFICATIONS"])
    autoclass("kg.zoobase.platform.ReminderReceiver").configure(activity, database_path, language, enabled)
