import os
from PIL import Image
import pystray
from utils import APP_TITLE

def load_icon_from_file(path: str, fallback: Image.Image|None=None) -> Image.Image|None:
    try:
        if os.path.exists(path):
            return Image.open(path).convert("RGBA")
    except Exception:
        pass
    return fallback

class TrayController:
    def __init__(self, app_ref, logo_path: str, fallback_img=None):
        self.app = app_ref
        self.icon_img = load_icon_from_file(logo_path, fallback_img)
        self.icon = None

    def ensure(self):
        if self.icon is not None:
            self.update_icon()
            return
        menu = pystray.Menu(
            pystray.MenuItem("Tampilkan/Sembunyikan", self._toggle_show),
            pystray.MenuItem(lambda item: "Master ON" if not self.app.master_toggle.get() else "Master OFF", self._toggle_master),
            pystray.MenuItem("Keluar", self._quit)
        )
        self.icon = pystray.Icon(APP_TITLE, self.icon_img, APP_TITLE, menu)
        import threading
        threading.Thread(target=self.icon.run, daemon=True).start()

    def update_icon(self):
        if self.icon is not None and self.icon_img is not None:
            try:
                self.icon.icon = self.icon_img
            except Exception:
                pass

    def _toggle_show(self, icon, item):
        self.app.after(0, lambda: self.app.restore_from_tray() if not self.app.winfo_viewable() else self.app.minimize_to_tray())

    def _toggle_master(self, icon, item):
        self.app.after(0, lambda: (self.app.master_toggle.set(not self.app.master_toggle.get()), self.app._on_master_toggle(self.app.master_toggle.get())))

    def _quit(self, icon, item):
        self.app.after(0, self.app._exit_app)
