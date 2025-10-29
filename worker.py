import time
from datetime import datetime, date, timedelta
from storage import parse_days_csv

def valid_time_str(s):
    try:
        datetime.strptime(s, "%H:%M"); return True
    except:
        return False

class BellWorker:
    def __init__(self, db_conn, audio_player, on_trigger=None, poll_interval=1, is_master_on=lambda: True):
        self.db = db_conn
        self.audio = audio_player
        self.on_trigger = on_trigger
        self.poll_interval = poll_interval
        self.is_master_on = is_master_on
        self._last_fired = set()
        self._running = False

    def start(self):
        if self._running: return
        self._running = True
        import threading
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                if not self.is_master_on():
                    time.sleep(self.poll_interval); continue
                now = datetime.now()
                hhmm = now.strftime("%H:%M")
                weekday = now.weekday()
                minute_key = now.strftime("%Y-%m-%d %H:%M")
                for sid, name, time_str, days_csv, sound_path, active in self._fetch_schedules():
                    if not active: continue
                    if not valid_time_str(time_str): continue
                    if weekday not in parse_days_csv(days_csv): continue
                    if time_str != hhmm: continue
                    key = (sid, minute_key)
                    if key in self._last_fired: continue
                    ok, err = self.audio.play(sound_path)
                    self._last_fired.add(key)
                    if self.on_trigger:
                        msg = f" {name} — {time_str} (bunyi)"
                        if not ok and err: msg += f" | Gagal: {err}"
                        self.on_trigger(msg)
                if len(self._last_fired) > 2000:
                    today = date.today().strftime("%Y-%m-%d")
                    self._last_fired = {k for k in self._last_fired if today in k[1]}
            except Exception as e:
                if self.on_trigger: self.on_trigger(f"Worker error: {e}")
            time.sleep(self.poll_interval)

    def _fetch_schedules(self):
        cur = self.db.cursor()
        cur.execute("SELECT id, name, time_str, days, sound_path, active FROM schedules ORDER BY time_str ASC")
        return cur.fetchall()