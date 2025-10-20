import os, sys, subprocess, socket, json
from datetime import datetime
import warnings

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="pygame.pkgdata")

APP_TITLE = "AutoBellSchedule"
CONTROL_PORT = 51233

def resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    return os.path.join(base if base else os.path.abspath("."), relative_path)

def user_data_dir() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "SchoolBell")

DATA_DIR = user_data_dir()
DB_FILE = os.path.join(DATA_DIR, "bell_scheduler.db")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

HARI_ID = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]
BULAN_ID = ["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"]

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)

def now_id_strings():
    now = datetime.now()
    hari = HARI_ID[now.weekday() % 7]
    tgl = f"{now.day} {BULAN_ID[now.month-1]} {now.year}"
    jam = now.strftime("%H:%M:%S")
    return hari, tgl, jam

def format_id_date(dt):
    return f"{HARI_ID[dt.weekday()]}, {dt.day} {BULAN_ID[dt.month-1]} {dt.year}"

def platform_name():
    if sys.platform.startswith("win"): return "windows"
    if sys.platform == "darwin": return "mac"
    return "linux"

def get_script_path():
    return os.path.abspath(sys.argv[0])

def pythonw_path():
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        cand = exe[:-10] + "pythonw.exe"
        return cand if os.path.exists(cand) else exe
    return exe

def autostart_enabled():
    p = platform_name()
    script = get_script_path()
    if p == "windows":
        startup = os.path.join(os.environ.get("APPDATA",""), "Microsoft","Windows","Start Menu","Programs","Startup")
        bat = os.path.join(startup, "bell_scheduler_startup.bat")
        if not os.path.exists(bat): return False
        try:
            with open(bat, "r", encoding="utf-8", errors="ignore") as f:
                return script in f.read()
        except Exception:
            return False
    if p == "linux":
        desktop = os.path.join(os.path.expanduser("~"), ".config", "autostart", "bell_scheduler.desktop")
        return os.path.exists(desktop)
    if p == "mac":
        plist = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", "com.bell.scheduler.plist")
        return os.path.exists(plist)
    return False

def set_autostart(enabled: bool):
    p = platform_name()
    script = get_script_path()
    py = pythonw_path()
    try:
        if p == "windows":
            startup = os.path.join(os.environ.get("APPDATA",""), "Microsoft","Windows","Start Menu","Programs","Startup")
            os.makedirs(startup, exist_ok=True)
            bat = os.path.join(startup, "bell_scheduler_startup.bat")
            if enabled:
                cmd = f"\"{script}\"" if script.lower().endswith(".exe") else f"\"{py}\" \"{script}\""
                with open(bat, "w", encoding="utf-8") as f:
                    f.write("@echo off\n")
                    f.write(f"start \"\" {cmd}\n")
            else:
                if os.path.exists(bat): os.remove(bat)
            return True, None
        if p == "linux":
            aut = os.path.join(os.path.expanduser("~"), ".config", "autostart")
            os.makedirs(aut, exist_ok=True)
            desktop = os.path.join(aut, "bell_scheduler.desktop")
            if enabled:
                exec_cmd = f"\"{script}\"" if script.lower().endswith(".exe") else f"\"{py}\" \"{script}\""
                content = f"""[Desktop Entry]
Type=Application
Name={APP_TITLE}
Exec={exec_cmd}
X-GNOME-Autostart-enabled=true
"""
                with open(desktop, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                if os.path.exists(desktop): os.remove(desktop)
            return True, None
        if p == "mac":
            agents = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
            os.makedirs(agents, exist_ok=True)
            plist = os.path.join(agents, "com.bell.scheduler.plist")
            if enabled:
                prog = [pythonw_path(), get_script_path()]
                content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.bell.scheduler</string>
  <key>ProgramArguments</key>
  <array><string>{prog[0]}</string><string>{prog[1]}</string></array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>"""
                with open(plist, "w", encoding="utf-8") as f:
                    f.write(content)
                try:
                    subprocess.run(["launchctl","load", plist], check=False)
                except Exception:
                    pass
            else:
                if os.path.exists(plist):
                    try:
                        subprocess.run(["launchctl","unload", plist], check=False)
                    except Exception:
                        pass
                    os.remove(plist)
            return True, None
    except Exception as e:
        return False, str(e)
    return False, "Platform tidak dikenali"

def kill_previous_instance(timeout_sec: float = 2.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", CONTROL_PORT), timeout=0.5) as s:
            s.sendall(b"QUIT")
        import time
        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            try:
                with socket.create_connection(("127.0.0.1", CONTROL_PORT), timeout=0.2) as _:
                    pass
            except OSError:
                return True
        return True
    except OSError:
        return False

def _load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def _save_settings(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_initial_sound_dir() -> str:
    s = _load_settings()
    d = s.get("last_sound_dir")
    if d and os.path.isdir(d):
        return d
    music = os.path.join(os.path.expanduser("~"), "Music")
    if os.path.isdir(music):
        return music
    return os.path.expanduser("~")

def remember_sound_dir(path: str):
    try:
        d = os.path.dirname(path)
        if not d:
            return
        s = _load_settings()
        s["last_sound_dir"] = d
        _save_settings(s)
    except Exception:
        pass
