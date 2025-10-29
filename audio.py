import os
import threading
try:
    import pygame
except ImportError:
    pygame = None

class AudioPlayer:
    def __init__(self):
        self.ok = False
        self._lock = threading.Lock()
        if pygame is None:
            return
        try:
            pygame.mixer.pre_init(44100, -16, 2, 1024)
            pygame.mixer.init()
            pygame.mixer.music.set_volume(1.0)
            self.ok = True
        except Exception as e:
            print("Audio init failed:", e)

    def is_playing(self) -> bool:
        if not self.ok:
            return False
        try:
            return pygame.mixer.music.get_busy()
        except Exception:
            return False

    def play(self, path):
        if not self.ok:
            return False, "Audio belum aktif (install pygame)."
        if not os.path.exists(path):
            return False, "File suara tidak ditemukan."
        with self._lock:
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                return True, None
            except Exception as e:
                return False, str(e)

    def stop(self):
        if self.ok:
            with self._lock:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass
