import os, socket, threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta

from utils import (
    APP_TITLE, ensure_dirs, now_id_strings, format_id_date,
    autostart_enabled, set_autostart, CONTROL_PORT,
    get_initial_sound_dir, remember_sound_dir
)
from storage import connect_db, parse_days_csv, days_to_label
from audio import AudioPlayer
from worker import BellWorker
from toggle import ToggleSwitch

from PIL import Image, ImageTk
from trayicon import TrayController


def valid_time_str(s: str) -> bool:
    try:
        datetime.strptime(s, "%H:%M")
        return True
    except:
        return False


class App(tk.Tk):
    def __init__(self, logo_path="logo.ico"):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x740")
        self.minsize(980, 620)

        ensure_dirs()
        self.conn = connect_db()
        self.audio = AudioPlayer()
        self._next_cache = None
        self._next_cache_ts = 0

        try:
            if not autostart_enabled():
                set_autostart(True)
        except Exception:
            pass

        self._set_window_icon(logo_path)
        self._use_theme()
        self._build_header()
        self._build_panes()
        self._build_statusbar()
        self._load_table()

        self.worker = BellWorker(
            self.conn,
            self.audio,
            on_trigger=lambda msg: (self._set_status(msg), self.after(0, self._refresh_buttons_state)),
            poll_interval=1,
            is_master_on=lambda: self.master_toggle.get()
        )
        self.worker.start()

        self._start_control_server()

        self.tray = TrayController(self, logo_path, fallback_img=None)
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        self.bind("<Unmap>", self._on_minimize)
        self._tick_clock()

    # ==== Single-instance control server ====
    def _start_control_server(self):
        def serve():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", CONTROL_PORT))
                s.listen(1)
            except OSError:
                try: s.close()
                except: pass
                return
            while True:
                try:
                    conn, _ = s.accept()
                    with conn:
                        data = conn.recv(32)
                        cmd = (data or b"").strip().upper()
                        if cmd == b"QUIT":
                            self.after(0, self._exit_app)
                            break
                        elif cmd == b"SHOW":
                            self.after(0, self.restore_from_tray)
                except Exception:
                    break
            try: s.close()
            except: pass
        threading.Thread(target=serve, daemon=True).start()

    def _set_window_icon(self, path):
        try:
            if os.path.exists(path):
                img = Image.open(path).convert("RGBA")
                self.tk_icon = ImageTk.PhotoImage(img)
                self.iconphoto(True, self.tk_icon)
        except Exception:
            pass

    def _use_theme(self):
        style = ttk.Style(self)
        for t in ("vista", "xpnative", "clam", "default"):
            try:
                style.theme_use(t); break
            except:
                continue
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        style.configure("Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Clock.TLabel", font=("Segoe UI", 34, "bold"))
        style.configure("Date.TLabel", font=("Segoe UI", 12))
        style.configure("CardTitle.TLabel", font=("Segoe UI", 11, "bold"))

    def _build_header(self):
        header = ttk.Frame(self, padding=(12, 10))
        header.pack(fill="x")

        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)
        clock_box = ttk.Frame(left)
        clock_box.pack(side="left")
        self.lbl_jam = ttk.Label(clock_box, text="00:00:00", style="Clock.TLabel")
        self.lbl_jam.grid(row=0, column=0, sticky="w")
        self.lbl_tanggal = ttk.Label(clock_box, text="Senin, 1 Januari 2000", style="Date.TLabel")
        self.lbl_tanggal.grid(row=1, column=0, sticky="w", pady=(2, 0))

        right = ttk.Frame(header)
        right.pack(side="right")
        ms_frame = ttk.Frame(right)
        ms_frame.pack(side="top", anchor="e")
        ttk.Label(ms_frame,).pack(side="left", padx=(0, 8))
        self.master_toggle = ToggleSwitch(ms_frame, on=True, command=self._on_master_toggle)
        self.master_toggle.pack(side="left")

        self.autostart_var = tk.IntVar(value=1)
        ttk.Checkbutton(
            right,
            text="Mulai aplikasi otomatis saat perangkat dihidupkan",
            variable=self.autostart_var,
            command=self._toggle_autostart,
        ).pack(side="top", anchor="e", pady=(8, 0))

        self.btn_stop = ttk.Button(right, text="Stop Suara", command=self._stop_sound)
        self.btn_stop.pack(side="top", anchor="e", pady=(6, 0))

        if not self.audio.ok:
            ttk.Label(
                right, foreground="red", text="⚠️ Audio tidak aktif. Jalankan: pip install pygame"
            ).pack(side="top", anchor="e", pady=(6, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=12, pady=(6, 6))
        card = ttk.Frame(self, padding=(12, 10))
        card.pack(fill="x")
        ttk.Label(card, text="Jadwal Berikutnya :", style="CardTitle.TLabel").pack(side="left")
        self.lbl_next = ttk.Label(card, text="-")
        self.lbl_next.pack(side="left", padx=(8, 0))

    def _on_master_toggle(self, is_on: bool):
        self._set_status("Master ON: jadwal akan dieksekusi." if is_on else "Master OFF: semua jadwal dihentikan.")
        self._invalidate_next_cache()
        self._update_next_label()
        try:
            self.tray.update_icon()
        except Exception:
            pass
        self._refresh_buttons_state()

    def _toggle_autostart(self):
        ok, err = set_autostart(bool(self.autostart_var.get()))
        if not ok:
            messagebox.showerror("Autostart", err or "Gagal mengatur autostart")
        else:
            self._set_status("Autostart diubah")

    def _build_panes(self):
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # 50%
        self.frm_left = ttk.Labelframe(panes, text="Form Jadwal", padding=12)
        panes.add(self.frm_left, weight=1)

        r = 0
        ttk.Label(self.frm_left, text="Nama Jadwal").grid(row=r, column=0, sticky="w"); r += 1
        self.ent_name = ttk.Entry(self.frm_left)
        self.ent_name.grid(row=r, column=0, sticky="we", pady=(0, 8))
        self.ent_name.bind("<KeyRelease>", lambda e: self._refresh_buttons_state()); r += 1

        ttk.Label(self.frm_left, text="Waktu (JJ:MM, 24 jam)").grid(row=r, column=0, sticky="w"); r += 1
        self.ent_time = ttk.Entry(self.frm_left, width=10)
        self.ent_time.insert(0, "07:00")
        self.ent_time.grid(row=r, column=0, sticky="w", pady=(0, 8))
        self.ent_time.bind("<KeyRelease>", lambda e: self._refresh_buttons_state()); r += 1

        ttk.Label(self.frm_left, text="Hari Berlaku").grid(row=r, column=0, sticky="w"); r += 1
        self.day_vars = []; day_frame = ttk.Frame(self.frm_left)
        day_frame.grid(row=r, column=0, sticky="w", pady=(2, 8))
        from utils import HARI_ID
        for i, nm in enumerate(HARI_ID):
            var = tk.IntVar(value=1 if i < 5 else 0)
            ttk.Checkbutton(
                day_frame, text=nm, variable=var, command=self._refresh_buttons_state
            ).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 12), pady=2)
            self.day_vars.append(var)
        r += 1

        ttk.Label(self.frm_left, text="File Suara").grid(row=r, column=0, sticky="w"); r += 1
        pick = ttk.Frame(self.frm_left); pick.grid(row=r, column=0, sticky="we", pady=(0, 6))
        self.ent_sound = ttk.Entry(pick); self.ent_sound.pack(side="left", fill="x", expand=True)
        self.ent_sound.bind("<KeyRelease>", lambda e: self._refresh_buttons_state())
        self.btn_pick = ttk.Button(pick, text="Pilih...", command=self._choose_sound); self.btn_pick.pack(side="left", padx=(6, 0))
        self.btn_test = ttk.Button(pick, text="Tes", command=self._test_sound); self.btn_test.pack(side="left", padx=(6, 0))
        r += 1

        ttk.Label(self.frm_left, text="Status").grid(row=r, column=0, sticky="w"); r += 1
        self.active_var = tk.IntVar(value=1)
        ttk.Checkbutton(
            self.frm_left, text="Aktif (bunyi sesuai jadwal)", variable=self.active_var, command=self._refresh_buttons_state
        ).grid(row=r, column=0, sticky="w"); r += 1

        btns = ttk.Frame(self.frm_left); btns.grid(row=r, column=0, sticky="we", pady=(8, 0))
        self.btn_add = ttk.Button(btns, text="Tambah", command=self._add_schedule); self.btn_add.pack(side="left")
        self.btn_update = ttk.Button(btns, text="Perbarui", command=self._update_schedule); self.btn_update.pack(side="left", padx=6)
        self.btn_delete = ttk.Button(btns, text="Hapus", command=self._delete_schedule); self.btn_delete.pack(side="left", padx=6)
        self.frm_left.columnconfigure(0, weight=1)

        # 50%
        self.frm_right = ttk.Labelframe(panes, text="Daftar Jadwal", padding=8)
        panes.add(self.frm_right, weight=3)

        tools = ttk.Frame(self.frm_right); tools.pack(fill="x", pady=(2, 6))
        ttk.Label(tools, text="Cari").pack(side="left")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(tools, textvariable=self.search_var, width=30); ent.pack(side="left", padx=(6, 0))
        self.search_var.trace_add("write", lambda *_: self._apply_filter())

        # === Tidak menampilkan ID; gunakan No (nomor urut) ===
        cols = ("no", "name", "time", "days", "status", "sound")
        self.tree = ttk.Treeview(self.frm_right, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("no", text="No", command=lambda: self._sort_by("id"))   # klik "No" → urut ID asli
        self.tree.heading("name", text="Nama", command=lambda: self._sort_by("name"))
        self.tree.heading("time", text="Waktu", command=lambda: self._sort_by("time"))
        self.tree.heading("days", text="Hari", command=lambda: self._sort_by("days"))
        self.tree.heading("status", text="Status", command=lambda: self._sort_by("status"))
        self.tree.heading("sound", text="File Suara", command=lambda: self._sort_by("sound"))
        self.tree.column("no", width=60, anchor="center", stretch=False)
        self.tree.column("name", width=180, stretch=True)
        self.tree.column("time", width=90, anchor="center", stretch=False)
        self.tree.column("days", width=260, stretch=True)
        self.tree.column("status", width=100, anchor="center", stretch=False)
        self.tree.column("sound", width=360, stretch=True)
        vsb = ttk.Scrollbar(self.frm_right, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.frm_right, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.tree.pack(side="top", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)
        self.frm_right.bind("<Configure>", lambda e: self._autosize_columns())
        self.frm_right.pack_propagate(False)

    def _autosize_columns(self):
        total_width = self.tree.winfo_width()
        fixed = self.tree.column("no", "width") + self.tree.column("time", "width") + self.tree.column("status", "width")
        pad = 20
        avail = max(0, total_width - fixed - pad)
        w_name = int(avail * 2 / 7)
        w_days = int(avail * 2 / 7)
        w_sound = max(120, avail - w_name - w_days)
        self.tree.column("name", width=w_name)
        self.tree.column("days", width=w_days)
        self.tree.column("sound", width=w_sound)

    def _build_statusbar(self):
        bar = ttk.Frame(self, padding=(12, 6)); bar.pack(fill="x")
        ttk.Label(bar, text="Log :").pack(side="left")
        self.status_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left", padx=8)

    def _set_status(self, text):
        self.status_var.set(text)

    def _tick_clock(self):
        h, t, j = now_id_strings()
        self.lbl_jam.configure(text=j)
        self.lbl_tanggal.configure(text=f"{h}, {t}")
        self._update_next_label()
        self._refresh_buttons_state()
        self.after(300, self._tick_clock)

    def _is_form_valid(self):
        name = self.ent_name.get().strip()
        time_str = self.ent_time.get().strip()
        days_idxs = [i for i, v in enumerate(self.day_vars) if v.get() == 1]
        sound = self.ent_sound.get().strip()
        return (
            bool(name)
            and valid_time_str(time_str)
            and len(days_idxs) > 0
            and bool(sound)
            and os.path.exists(sound)
        )

    def _sel_exists(self):
        return bool(self.tree.selection())

    def _refresh_buttons_state(self):
        form_valid = self._is_form_valid()
        has_sel = self._sel_exists()

        self._set_btn(self.btn_add, form_valid)
        self._set_btn(self.btn_update, form_valid and has_sel)
        self._set_btn(self.btn_delete, has_sel)

        sound_path = self.ent_sound.get().strip()
        can_test = self.audio.ok and bool(sound_path) and os.path.exists(sound_path)
        if hasattr(self, "btn_test"):
            self._set_btn(self.btn_test, can_test)

        can_stop = self.audio.ok and self.audio.is_playing()
        if hasattr(self, "btn_stop"):
            self._set_btn(self.btn_stop, can_stop)

    def _set_btn(self, btn, ok):
        btn.configure(state=("normal" if ok else "disabled"))

    def _load_table(self):
        sort_key = getattr(self, "_sort_key", None)
        sort_rev = getattr(self, "_sort_reverse", False)
        for r in self.tree.get_children(): self.tree.delete(r)
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, time_str, days, sound_path, active FROM schedules")
        rows = cur.fetchall()
        self._rows_all = [
            {
                "id": sid, "name": name, "time": tstr, "days_raw": days,
                "days": days_to_label(days), "sound": sound,
                "status": "Aktif" if active else "Nonaktif", "active": active,
            }
            for (sid, name, tstr, days, sound, active) in rows
        ]
        self._apply_filter()
        self._invalidate_next_cache()
        if sort_key:
            self._sort_by(sort_key, force_reverse=sort_rev, redraw_only=True)
        self._set_status("Data jadwal dimuat")
        self._refresh_buttons_state()
        self._autosize_columns()

    def _apply_filter(self):
        q = (self.search_var.get() if hasattr(self, "search_var") else "").lower().strip()
        if not hasattr(self, "_rows_all"): return
        if q:
            self._rows_filtered = [
                r for r in self._rows_all
                if q in r["name"].lower()
                or q in r["time"].lower()
                or q in r["days"].lower()
                or q in r["status"].lower()
                or q in r["sound"].lower()
            ]
        else:
            self._rows_filtered = list(self._rows_all)
        self._redraw_rows(self._rows_filtered)

    def _redraw_rows(self, rows):
        for r in self.tree.get_children(): self.tree.delete(r)
        # isi tabel: nomor urut (1..n), iid = ID asli
        for idx, r in enumerate(rows, start=1):
            self.tree.insert(
                "", "end",
                iid=str(r["id"]),
                values=(idx, r["name"], r["time"], r["days"], r["status"], r["sound"])
            )
        self._refresh_buttons_state()

    def _sort_by(self, key, force_reverse=None, redraw_only=False):
        if not hasattr(self, "_rows_filtered"): return
        if force_reverse is None:
            if getattr(self, "_sort_key", "") == key: self._sort_reverse = not getattr(self, "_sort_reverse", False)
            else: self._sort_reverse = False
        else:
            self._sort_reverse = bool(force_reverse)
        self._sort_key = key

        def k(row):
            if key == "id": return int(row["id"])      # klik "No" → urut ID asli
            if key == "time": return row["time"]
            if key == "days": return row["days"]
            if key == "status": return row["status"]
            if key == "sound": return row["sound"]
            return row["name"]

        self._rows_filtered = sorted(self._rows_filtered, key=k, reverse=self._sort_reverse)
        self._redraw_rows(self._rows_filtered)
        if not redraw_only: self._set_status(f"Urut {key} ({'desc' if self._sort_reverse else 'asc'})")
        self._autosize_columns()

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel: return None
        try:
            return int(sel[0])  # iid = ID asli
        except:
            item = self.tree.focus()
            return int(item) if item else None

    # ==== Ambil nama jadwal dari DB untuk pesan GUI ====
    def _get_name_by_id(self, sid: int):
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM schedules WHERE id=?", (sid,))
        row = cur.fetchone()
        return row[0] if row else None

    def _choose_sound(self):
        initialdir = get_initial_sound_dir()
        path = filedialog.askopenfilename(
            title="Pilih file suara",
            initialdir=initialdir,
            filetypes=[("Audio", "*.mp3 *.wav *.ogg"), ("Semua file", "*.*")],
        )
        if path:
            self.ent_sound.delete(0, tk.END)
            self.ent_sound.insert(0, path)
            remember_sound_dir(path)
            self._refresh_buttons_state()

    def _collect_form(self):
        name = self.ent_name.get().strip()
        time_str = self.ent_time.get().strip()
        days_idxs = [i for i, v in enumerate(self.day_vars) if v.get() == 1]
        days_csv = ",".join(str(x) for x in days_idxs)
        sound_path = self.ent_sound.get().strip()
        active = self.active_var.get()
        if not name: raise ValueError("Nama jadwal wajib diisi.")
        if not valid_time_str(time_str): raise ValueError("Format waktu tidak valid. Gunakan JJ:MM (24 jam).")
        if not days_idxs: raise ValueError("Pilih minimal satu hari.")
        if not sound_path: raise ValueError("File suara belum dipilih.")
        if not os.path.exists(sound_path): raise ValueError("File suara tidak ditemukan.")
        return name, time_str, days_csv, sound_path, int(active)

    def _add_schedule(self):
        try:
            name, time_str, days_csv, sound_path, active = self._collect_form()
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO schedules(name,time_str,days,sound_path,active) VALUES (?,?,?,?,?)",
                (name, time_str, days_csv, sound_path, active),
            )
            self.conn.commit()
            self._load_table()
            self._set_status(f"Jadwal ditambahkan: {name} @ {time_str}")
        except Exception as e:
            messagebox.showerror("Gagal", str(e))
        finally:
            self._refresh_buttons_state()

    def _update_schedule(self):
        sid = self._selected_id()
        if sid is None: return
        try:
            name, time_str, days_csv, sound_path, active = self._collect_form()
            cur = self.conn.cursor()
            cur.execute(
                "UPDATE schedules SET name=?, time_str=?, days=?, sound_path=?, active=? WHERE id=?",
                (name, time_str, days_csv, sound_path, active, sid),
            )
            self.conn.commit()
            self._load_table()
            self._set_status(f"Jadwal diperbarui: {name} @ {time_str}")
        except Exception as e:
            messagebox.showerror("Gagal", str(e))
        finally:
            self._refresh_buttons_state()

    def _delete_schedule(self):
        sid = self._selected_id()
        if sid is None: return
        nm = self._get_name_by_id(sid) or "jadwal ini"
        if not messagebox.askyesno("Konfirmasi", f"Hapus {nm}?"): return
        cur = self.conn.cursor()
        cur.execute("DELETE FROM schedules WHERE id=?", (sid,))
        self.conn.commit()
        self._load_table()
        self._set_status(f"Jadwal dihapus: {nm}")
        self._refresh_buttons_state()

    def _on_select_row(self, _evt):
        sid = self._selected_id()
        if sid is None:
            self._refresh_buttons_state(); return
        cur = self.conn.cursor()
        cur.execute("SELECT name,time_str,days,sound_path,active FROM schedules WHERE id=?", (sid,))
        row = cur.fetchone()
        if not row:
            self._refresh_buttons_state(); return
        name, time_str, days_csv, sound_path, active = row
        self.ent_name.delete(0, tk.END); self.ent_name.insert(0, name)
        self.ent_time.delete(0, tk.END); self.ent_time.insert(0, time_str)
        for v in self.day_vars: v.set(0)
        for i in parse_days_csv(days_csv):
            if 0 <= i < len(self.day_vars): self.day_vars[i].set(1)
        self.ent_sound.delete(0, tk.END); self.ent_sound.insert(0, sound_path)
        self.active_var.set(1 if active else 0)
        self._refresh_buttons_state()

    def _test_sound(self, *_):
        path = self.ent_sound.get().strip()
        if not path:
            messagebox.showinfo("Info", "Pilih file suara dulu."); return
        ok, err = self.audio.play(path)
        if not ok:
            messagebox.showerror("Gagal memutar", err or "Tidak diketahui")
        else:
            self._set_status("Suara diuji")
        self._refresh_buttons_state()

    def _stop_sound(self, *_):
        self.audio.stop()
        self._set_status("Suara dihentikan")
        self._refresh_buttons_state()

    def _invalidate_next_cache(self):
        self._next_cache = None
        self._next_cache_ts = 0

    def _update_next_label(self):
        if not self.master_toggle.get():
            self.lbl_next.configure(text="Semua jadwal dinonaktifkan (Master OFF)")
            return
        now = datetime.now()
        if now.timestamp() - self._next_cache_ts >= 1 or self._next_cache is None:
            self._next_cache = self._compute_next_schedule(now)
            self._next_cache_ts = now.timestamp()
        if self._next_cache is None:
            self.lbl_next.configure(text="-"); return
        sid, name, when_dt, tstr = self._next_cache
        if when_dt < now:
            self._invalidate_next_cache(); self.lbl_next.configure(text="-"); return
        delta = when_dt - now
        total = int(delta.total_seconds())
        d = total // 86400
        h = (total % 86400) // 3600
        m = (total % 3600) // 60
        s = total % 60
        when_text = f"{format_id_date(when_dt)} {tstr}"
        cd = f"dalam {d} hari {h:02d}:{m:02d}:{s:02d}" if d > 0 else f"dalam {h:02d}:{m:02d}:{s:02d}"
        self.lbl_next.configure(text=f"{name} — {when_text} ({cd})")

    def _compute_next_schedule(self, ref):
        cur = self.conn.cursor()
        cur.execute("SELECT id,name,time_str,days,active FROM schedules")
        rows = cur.fetchall()
        if not rows: return None
        best = None; best_dt = None
        for sid, name, tstr, days_csv, active in rows:
            if not active: continue
            if not valid_time_str(tstr): continue
            days = parse_days_csv(days_csv)
            if not days: continue
            try:
                hh, mm = map(int, tstr.split(":"))
            except:
                continue
            occ = None
            for add in range(0, 14):
                d = (ref + timedelta(days=add)).date()
                cand = datetime(d.year, d.month, d.day, hour=hh, minute=mm)
                if cand < ref: continue
                if cand.weekday() in days:
                    occ = cand; break
            if occ is None: continue
            if best_dt is None or occ < best_dt:
                best_dt = occ; best = (sid, name, occ, tstr)
        return best

    def minimize_to_tray(self):
        self.withdraw()
        self._set_status("Berjalan di tray.")
        try: self.tray.ensure()
        except Exception: pass

    def _on_minimize(self, event):
        if event.widget == self and self.state() == "iconic":
            self.after(0, self.minimize_to_tray)

    def restore_from_tray(self):
        self.deiconify(); self.lift(); self.focus_force()
        self._set_status("Ditampilkan kembali.")
        try: self.tray.update_icon()
        except Exception: pass

    def _exit_app(self):
        try:
            if hasattr(self, "worker") and self.worker:
                self.worker.stop()
        except Exception:
            pass
        self.destroy()
