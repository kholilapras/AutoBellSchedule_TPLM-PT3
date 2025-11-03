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
        self._volume = 1.0  # Default volume 100%
        if pygame is None:
            return
        try:
            pygame.mixer.pre_init(44100, -16, 2, 1024)
            pygame.mixer.init()
            pygame.mixer.music.set_volume(self._volume)
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
    
    def set_volume(self, volume: float):
        """Set volume (0.0 - 1.0)"""
        self._volume = max(0.0, min(1.0, volume))
        if self.ok:
            try:
                pygame.mixer.music.set_volume(self._volume)
            except Exception:
                pass
    
    def get_volume(self) -> float:
        """Get current volume (0.0 - 1.0)"""
        return self._volume
