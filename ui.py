import os, socket, threading, re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta

from utils import (
    APP_TITLE, APP_VERSION, ensure_dirs, now_id_strings, format_id_date,
    autostart_enabled, set_autostart, CONTROL_PORT,
    get_initial_sound_dir, remember_sound_dir
)
from storage import connect_db, parse_days_csv, days_to_label
from audio import AudioPlayer
from worker import BellWorker
from toggle import ToggleSwitch
from rounded_button import RoundedButton

from PIL import Image, ImageTk
from trayicon import TrayController


def valid_time_str(s: str) -> bool:
    """
    Validasi format waktu HH:MM (00:00 - 23:59)
    Regex: ^(?:[01]\\d|2[0-3]):[0-5]\\d$
    """
    pattern = r'^(?:[01]\d|2[0-3]):[0-5]\d$'
    return bool(re.match(pattern, s))


class App(tk.Tk):
    def __init__(self, logo_path="logo.ico"):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x800")
        self.minsize(1100, 700)
        
        # Simpan logo path untuk digunakan di header
        self.logo_path = logo_path

        # Dark mode state
        self.dark_mode = False
        
        # Color schemes
        self.light_colors = {
            'bg': '#f5f6fa',
            'primary': '#4834d4',
            'secondary': '#686de0',
            'success': '#26de81',
            'danger': '#fc5c65',
            'warning': '#fed330',
            'dark': '#2c3e50',
            'light': '#ffffff',
            'text': '#2f3542',
            'border': '#dfe4ea',
            'card_shadow': '#c8d6e5'
        }
        
        self.dark_colors = {
            'bg': '#0f0f0f',           # Background utama - lebih gelap
            'primary': '#8b5cf6',       # Primary purple - lebih terang untuk visibility
            'secondary': '#a78bfa',     # Secondary purple
            'success': '#22c55e',       # Success green - lebih terang
            'danger': '#ef4444',        # Danger red
            'warning': '#fbbf24',       # Warning yellow - lebih terang
            'dark': '#f3f4f6',          # Text gelap untuk dark mode (jadi terang)
            'light': '#1f1f1f',         # Card background - gelap tapi kontras dengan bg
            'text': '#f3f4f6',          # Text color - putih keabuan
            'border': '#404040',        # Border - abu gelap
            'card_shadow': '#000000'    # Shadow - hitam
        }
        
        # Set initial colors
        self.colors = self.light_colors.copy()
        self.configure(bg=self.colors['bg'])

        ensure_dirs()
        self.conn = connect_db()
        self.audio = AudioPlayer()
        self._next_cache = None
        self._next_cache_ts = 0
        
        # Autostart variable
        self.autostart_var = tk.IntVar(value=1)

        try:
            if not autostart_enabled():
                set_autostart(True)
        except Exception:
            pass

        self._set_window_icon(logo_path)
        self._use_theme()
        self._build_menu()
        self._build_header()
        self._build_panes()
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
        
        # Use clam theme for better color support on headers
        try:
            style.theme_use("clam")
        except:
            try:
                style.theme_use("vista")
            except:
                pass

        # Configure styles with Poppins font
        style.configure(".", 
            font=("Poppins", 10),
            background=self.colors['bg']
        )
        
        style.configure("TFrame", background=self.colors['bg'])
        style.configure("TLabel", 
            background=self.colors['bg'],
            foreground=self.colors['text'],
            font=("Poppins", 10)
        )
        
        style.configure("TButton",
            font=("Poppins", 10, "bold"),
            padding=(15, 8),
            background=self.colors['primary'],
            foreground='#ffffff',
            borderwidth=0
        )
        
        style.map("TButton",
            background=[
                ('active', self.colors['secondary']), 
                ('pressed', self.colors['secondary']),
                ('disabled', self.colors['border'])  # Redup saat disabled
            ],
            foreground=[
                ('active', '#ffffff'), 
                ('pressed', '#ffffff'),
                ('disabled', '#9ca3af')  # Text abu-abu saat disabled
            ]
        )
        
        style.configure("Primary.TButton",
            font=("Poppins", 9, "bold"),
            padding=(12, 6),
            background=self.colors['primary'],
            foreground='#ffffff',
            borderwidth=0
        )
        
        style.map("Primary.TButton",
            background=[
                ('active', self.colors['secondary']), 
                ('pressed', self.colors['secondary']),
                ('disabled', self.colors['border'])  # Redup saat disabled
            ],
            foreground=[
                ('active', '#ffffff'), 
                ('pressed', '#ffffff'),
                ('disabled', '#9ca3af')  # Text abu-abu saat disabled
            ]
        )
        
        style.configure("TEntry",
            font=("Poppins", 10),
            padding=8,
            fieldbackground=self.colors['light'],
            foreground=self.colors['text'],
            borderwidth=1,
            relief="solid"
        )
        
        style.map("TEntry",
            fieldbackground=[
                ('focus', self.colors['light']),
                ('disabled', self.colors['bg'])  # Background redup saat disabled
            ],
            foreground=[
                ('focus', self.colors['text']),
                ('disabled', '#9ca3af')  # Text abu-abu saat disabled
            ]
        )
        
        style.configure("TCheckbutton",
            background=self.colors['bg'],
            foreground=self.colors['text'],
            font=("Poppins", 9)
        )
        
        # Map checkbutton untuk indikator centang
        style.map("TCheckbutton",
            background=[
                ('active', self.colors['bg']), 
                ('!active', self.colors['bg']),
                ('disabled', self.colors['bg'])
            ],
            foreground=[
                ('active', self.colors['text']), 
                ('!active', self.colors['text']),
                ('disabled', '#9ca3af')  # Text abu-abu saat disabled
            ]
        )

        # Treeview styling
        style.configure("Treeview",
            background=self.colors['light'],
            foreground=self.colors['text'],
            fieldbackground=self.colors['light'],
            font=("Poppins", 9),
            rowheight=32,
            borderwidth=0
        )
        
        style.configure("Treeview.Heading",
            background=self.colors['primary'],
            foreground='#ffffff',  # Selalu putih untuk kontras dengan primary
            font=("Poppins", 10, "bold"),
            relief="flat"
        )
        
        style.map("Treeview.Heading",
            background=[('active', self.colors['secondary'])]
        )
        
        style.map("Treeview",
            background=[('selected', self.colors['secondary'])],
            foreground=[('selected', '#ffffff')]  # Selalu putih untuk selected row
        )

        # Custom label styles
        style.configure("Clock.TLabel",
            font=("Poppins", 42, "bold"),
            foreground=self.colors['primary'],
            background=self.colors['light']
        )
        
        style.configure("Date.TLabel",
            font=("Poppins", 13),
            foreground=self.colors['text'],
            background=self.colors['light']
        )
        
        style.configure("CardTitle.TLabel",
            font=("Poppins", 12, "bold"),
            foreground=self.colors['dark'],
            background=self.colors['light']
        )
        
        style.configure("Card.TFrame",
            background=self.colors['light']
        )
        
        style.configure("Card.TLabelframe",
            background=self.colors['light'],
            foreground=self.colors['dark'],
            font=("Poppins", 11, "bold")
        )
        
        style.configure("Card.TLabelframe.Label",
            background=self.colors['light'],
            foreground=self.colors['dark'],
            font=("Poppins", 11, "bold")
        )

    def _build_menu(self):
        """Buat menu bar"""
        menubar = tk.Menu(self, bg=self.colors['light'], fg=self.colors['text'])
        self.config(menu=menubar)
        
        # Menu Settings
        settings_menu = tk.Menu(menubar, tearoff=0, bg=self.colors['light'], fg=self.colors['text'])
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="⚙️ Preferences", command=self._open_settings)
        settings_menu.add_separator()
        settings_menu.add_command(label="🚪 Keluar", command=self.quit)
        
        # Menu Help
        help_menu = tk.Menu(menubar, tearoff=0, bg=self.colors['light'], fg=self.colors['text'])
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="ℹ️ About", command=self._show_about)
    
    def _build_header(self):
        header = ttk.Frame(self, style="Card.TFrame", padding=(20, 15))
        header.pack(fill="x", padx=15, pady=(15, 10))

        # Left side - Clock
        left = ttk.Frame(header, style="Card.TFrame")
        left.pack(side="left")
        clock_box = ttk.Frame(left, style="Card.TFrame")
        clock_box.pack(side="left")
        self.lbl_jam = ttk.Label(clock_box, text="00:00:00", style="Clock.TLabel")
        self.lbl_jam.grid(row=0, column=0, sticky="w")
        self.lbl_tanggal = ttk.Label(clock_box, text="Senin, 1 Januari 2000", style="Date.TLabel")
        self.lbl_tanggal.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Center - Logo SMP (expand untuk push ke tengah)
        center = ttk.Frame(header, style="Card.TFrame")
        center.pack(side="left", expand=True, fill="both")
        
        # Container untuk logo agar benar-benar center
        logo_container = ttk.Frame(center, style="Card.TFrame")
        logo_container.place(relx=0.5, rely=0.5, anchor="center")
        
        if hasattr(self, 'logo_path') and os.path.exists(self.logo_path):
            try:
                img = Image.open(self.logo_path)
                # Resize logo untuk header
                img = img.resize((80, 80), Image.Resampling.LANCZOS)
                self.header_logo = ImageTk.PhotoImage(img)
                
                logo_label = tk.Label(
                    logo_container,
                    image=self.header_logo,
                    bg=self.colors['light']
                )
                logo_label.pack()
            except Exception:
                pass

        # Right side - Toggle
        right = ttk.Frame(header, style="Card.TFrame")
        right.pack(side="right")
        
        # Master toggle dengan label yang lebih jelas
        ms_frame = ttk.Frame(right, style="Card.TFrame")
        ms_frame.pack(side="top", anchor="e")
        
        toggle_label_frame = ttk.Frame(ms_frame, style="Card.TFrame")
        toggle_label_frame.pack(side="left", padx=(0, 8))
        ttk.Label(
            toggle_label_frame, 
            text="Master Control:",
            font=("Poppins", 9, "bold"),
            background=self.colors['light'],
            foreground=self.colors['dark']
        ).pack(side="top", anchor="e")
        ttk.Label(
            toggle_label_frame, 
            text="(ON = Jadwal aktif, OFF = Semua jadwal berhenti)",
            font=("Poppins", 7),
            background=self.colors['light'],
            foreground=self.colors['text']
        ).pack(side="top", anchor="e")
        
        self.master_toggle = ToggleSwitch(ms_frame, on=True, command=self._on_master_toggle)
        self.master_toggle.pack(side="left")

        if not self.audio.ok:
            ttk.Label(
                right, foreground=self.colors['danger'], 
                text="⚠️ Audio tidak aktif. Jalankan: pip install pygame",
                background=self.colors['light'],
                font=("Poppins", 9)
            ).pack(side="top", anchor="e", pady=(8, 0))

        # Next schedule card dengan log activity
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=15, pady=(10, 10))
        card = ttk.Frame(self, style="Card.TFrame", padding=(20, 12))
        card.pack(fill="x", padx=15, pady=(0, 10))
        
        # Left side - Jadwal Berikutnya
        ttk.Label(card, text="📅 Jadwal Berikutnya:", background=self.colors['light'], 
                  font=("Poppins", 10), foreground=self.colors['text']).pack(side="left")
        self.lbl_next = ttk.Label(card, text="-", background=self.colors['light'], 
                                  font=("Poppins", 10, "bold"), foreground=self.colors['text'])
        self.lbl_next.pack(side="left", padx=(10, 0))
        
        # Right side - Log Activity
        self.status_var = tk.StringVar(value="Siap")
        ttk.Label(card, textvariable=self.status_var,
                  background=self.colors['light'],
                  foreground=self.colors['text'],
                  font=("Poppins", 9)).pack(side="right")
        ttk.Label(card, text="📝 Log:", 
                  font=("Poppins", 9, "bold"),
                  background=self.colors['light'],
                  foreground=self.colors['dark']).pack(side="right", padx=(20, 5))

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
    
    def _toggle_autostart_from_settings(self, is_on):
        """Toggle autostart dari dialog Settings"""
        self.autostart_var.set(1 if is_on else 0)
        ok, err = set_autostart(is_on)
        if not ok:
            messagebox.showerror("Autostart", err or "Gagal mengatur autostart")
        else:
            self._set_status("Autostart " + ("diaktifkan" if is_on else "dinonaktifkan"))

    def _build_panes(self):
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # Left panel - Form
        self.frm_left = ttk.Labelframe(panes, text="📝 Form Jadwal", padding=22, style="Card.TLabelframe")
        panes.add(self.frm_left, weight=1)

        r = 0
        ttk.Label(self.frm_left, text="Nama Jadwal", 
                  font=("Poppins", 11, "bold"), 
                  background=self.colors['light'],
                  foreground=self.colors['dark']).grid(row=r, column=0, sticky="w", pady=(0, 6)); r += 1
        self.ent_name = ttk.Entry(self.frm_left)
        self.ent_name.grid(row=r, column=0, sticky="we", pady=(0, 18))
        self.ent_name.bind("<KeyRelease>", lambda e: self._refresh_buttons_state()); r += 1

        ttk.Label(self.frm_left, text="⏰ Waktu (JJ:MM, 24 jam)",
                  font=("Poppins", 11, "bold"),
                  background=self.colors['light'],
                  foreground=self.colors['dark']).grid(row=r, column=0, sticky="w", pady=(0, 6)); r += 1
        
        # Time picker dengan spinbox
        time_frame = ttk.Frame(self.frm_left, style="Card.TFrame")
        time_frame.grid(row=r, column=0, sticky="w", pady=(0, 12))
        
        # Validasi untuk spinbox jam
        vcmd_hour = (self.register(self._validate_hour), '%P', '%S')
        
        # Spinbox untuk jam (00-23)
        self.spin_hour = tk.Spinbox(
            time_frame, 
            from_=0, 
            to=23, 
            width=3,
            font=("Poppins", 10),
            format="%02.0f",
            command=self._refresh_buttons_state,
            justify='center',
            validate='key',
            validatecommand=vcmd_hour,
            bg=self.colors['light'],
            fg=self.colors['text'],
            buttonbackground=self.colors['primary'],
            relief='solid',
            borderwidth=1
        )
        self.spin_hour.delete(0, "end")
        self.spin_hour.insert(0, "07")
        self.spin_hour.bind('<FocusOut>', lambda e: self._format_hour())
        self.spin_hour.bind('<Return>', lambda e: self._format_hour())
        self.spin_hour.pack(side="left")
        
        # Label pemisah
        ttk.Label(
            time_frame, 
            text=":", 
            font=("Poppins", 12, "bold"),
            background=self.colors['light']
        ).pack(side="left", padx=3)
        
        # Validasi untuk spinbox menit
        vcmd_minute = (self.register(self._validate_minute), '%P', '%S')
        
        # Spinbox untuk menit (00-59)
        self.spin_minute = tk.Spinbox(
            time_frame, 
            from_=0, 
            to=59, 
            width=3,
            font=("Poppins", 10),
            format="%02.0f",
            command=self._refresh_buttons_state,
            justify='center',
            validate='key',
            validatecommand=vcmd_minute,
            bg=self.colors['light'],
            fg=self.colors['text'],
            buttonbackground=self.colors['primary'],
            relief='solid',
            borderwidth=1
        )
        self.spin_minute.delete(0, "end")
        self.spin_minute.insert(0, "00")
        self.spin_minute.bind('<FocusOut>', lambda e: self._format_minute())
        self.spin_minute.bind('<Return>', lambda e: self._format_minute())
        self.spin_minute.pack(side="left")
        
        r += 1

        # Info label untuk hari berlaku
        info_frame = ttk.Frame(self.frm_left, style="Card.TFrame")
        info_frame.grid(row=r, column=0, sticky="w", pady=(8, 6))
        ttk.Label(info_frame, text="📆 Hari Berlaku",
                  font=("Poppins", 11, "bold"),
                  background=self.colors['light'],
                  foreground=self.colors['dark']).pack(side="left")
        ttk.Label(info_frame, text="(✔ Centang hari di mana jadwal ini akan aktif)",
                  font=("Poppins", 9),
                  background=self.colors['light'],
                  foreground=self.colors['text'],
                  style="TLabel").pack(side="left", padx=(8, 0))
        r += 1
        
        self.day_vars = []; day_frame = ttk.Frame(self.frm_left, style="Card.TFrame")
        day_frame.grid(row=r, column=0, sticky="w", pady=(4, 18))
        from utils import HARI_ID
        for i, nm in enumerate(HARI_ID):
            var = tk.IntVar(value=1 if i < 5 else 0)
            # Gunakan tk.Checkbutton untuk kontrol lebih baik atas tampilan
            cb = tk.Checkbutton(
                day_frame, 
                text=nm, 
                variable=var, 
                command=self._refresh_buttons_state,
                bg=self.colors['light'],
                fg=self.colors['text'],
                font=("Poppins", 10),
                activebackground=self.colors['light'],
                activeforeground=self.colors['text'],
                selectcolor=self.colors['light'],
                highlightthickness=0,
                bd=0
            )
            # Tampilkan semua dalam 1 baris (horizontal)
            cb.pack(side="left", padx=(0, 12))
            self.day_vars.append(var)
        r += 1

        ttk.Label(self.frm_left, text="🔊 File Suara",
                  font=("Poppins", 11, "bold"),
                  background=self.colors['light'],
                  foreground=self.colors['dark']).grid(row=r, column=0, sticky="w", pady=(0, 6)); r += 1
        pick = ttk.Frame(self.frm_left, style="Card.TFrame"); pick.grid(row=r, column=0, sticky="we", pady=(0, 18))
        self.ent_sound = ttk.Entry(pick); self.ent_sound.pack(side="left", fill="x", expand=True)
        self.ent_sound.bind("<KeyRelease>", lambda e: self._refresh_buttons_state())
        self.btn_pick = ttk.Button(pick, text="📁 Pilih...", command=self._choose_sound); self.btn_pick.pack(side="left", padx=(8, 0))
        self.btn_test = ttk.Button(pick, text="▶ Tes", command=self._test_sound); self.btn_test.pack(side="left", padx=(6, 0))
        self.btn_stop = ttk.Button(pick, text="⏹ Stop", command=self._stop_sound); self.btn_stop.pack(side="left", padx=(6, 0))
        r += 1

        # Info label untuk status jadwal
        status_info_frame = ttk.Frame(self.frm_left, style="Card.TFrame")
        status_info_frame.grid(row=r, column=0, sticky="w", pady=(0, 6))
        ttk.Label(status_info_frame, text="✓ Status Jadwal",
                  font=("Poppins", 11, "bold"),
                  background=self.colors['light'],
                  foreground=self.colors['dark']).pack(side="left")
        ttk.Label(status_info_frame, text="(✔ Centang untuk mengaktifkan jadwal ini)",
                  font=("Poppins", 9),
                  background=self.colors['light'],
                  foreground=self.colors['text'],
                  style="TLabel").pack(side="left", padx=(8, 0))
        r += 1
        
        self.active_var = tk.IntVar(value=1)
        # Gunakan tk.Checkbutton untuk kontrol lebih baik atas tampilan
        active_cb = tk.Checkbutton(
            self.frm_left, 
            text="Aktif", 
            variable=self.active_var, 
            command=self._refresh_buttons_state,
            bg=self.colors['light'],
            fg=self.colors['text'],
            font=("Poppins", 10),
            activebackground=self.colors['light'],
            activeforeground=self.colors['text'],
            selectcolor=self.colors['light'],
            highlightthickness=0,
            bd=0
        )
        active_cb.grid(row=r, column=0, sticky="w", pady=(0, 20))
        r += 1

        btns = ttk.Frame(self.frm_left, style="Card.TFrame"); btns.grid(row=r, column=0, sticky="we", pady=(12, 0))
        self.btn_add = ttk.Button(btns, text="➕ Tambah", command=self._add_schedule); self.btn_add.pack(side="left", padx=(0, 8))
        self.btn_update = ttk.Button(btns, text="✏ Perbarui", command=self._update_schedule); self.btn_update.pack(side="left", padx=(0, 8))
        self.btn_delete = ttk.Button(btns, text="🗑 Hapus", command=self._delete_schedule); self.btn_delete.pack(side="left")
        self.frm_left.columnconfigure(0, weight=1)

        # Right panel - Table
        self.frm_right = ttk.Labelframe(panes, text="📋 Daftar Jadwal", padding=12, style="Card.TLabelframe")
        panes.add(self.frm_right, weight=3)

        tools = ttk.Frame(self.frm_right, style="Card.TFrame"); tools.pack(fill="x", pady=(4, 10))
        ttk.Label(tools, text="🔍 Cari:",
                  font=("Poppins", 9, "bold"),
                  background=self.colors['light'],
                  foreground=self.colors['dark']).pack(side="left")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(tools, textvariable=self.search_var, width=35); ent.pack(side="left", padx=(8, 0))
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

    def _set_status(self, text):
        self.status_var.set(text)
    
    def _get_time_from_spinbox(self):
        """Mendapatkan waktu dari spinbox dalam format HH:MM"""
        try:
            hour = int(self.spin_hour.get())
            minute = int(self.spin_minute.get())
            # Pastikan dalam range yang valid
            hour = max(0, min(23, hour))
            minute = max(0, min(59, minute))
            return f"{hour:02d}:{minute:02d}"
        except:
            return "00:00"
    
    def _set_time_to_spinbox(self, time_str):
        """Set waktu ke spinbox dari format HH:MM"""
        try:
            parts = time_str.split(":")
            if len(parts) == 2:
                hour = int(parts[0])
                minute = int(parts[1])
                self.spin_hour.delete(0, "end")
                self.spin_hour.insert(0, f"{hour:02d}")
                self.spin_minute.delete(0, "end")
                self.spin_minute.insert(0, f"{minute:02d}")
        except:
            pass
    
    def _validate_hour(self, new_value, input_char):
        """
        Validasi input jam manual:
        - Hanya boleh angka
        - Maksimal 2 digit
        - Nilai maksimal 23
        """
        # Kosong diperbolehkan
        if new_value == "":
            return True
        
        # Hanya boleh angka
        if not new_value.isdigit():
            return False
        
        # Maksimal 2 digit
        if len(new_value) > 2:
            return False
        
        # Cek nilai maksimal 23
        try:
            val = int(new_value)
            if val > 23:
                return False
        except:
            return False
        
        return True
    
    def _validate_minute(self, new_value, input_char):
        """
        Validasi input menit manual:
        - Hanya boleh angka
        - Maksimal 2 digit
        - Nilai maksimal 59
        """
        # Kosong diperbolehkan
        if new_value == "":
            return True
        
        # Hanya boleh angka
        if not new_value.isdigit():
            return False
        
        # Maksimal 2 digit
        if len(new_value) > 2:
            return False
        
        # Cek nilai maksimal 59
        try:
            val = int(new_value)
            if val > 59:
                return False
        except:
            return False
        
        return True
    
    def _format_hour(self):
        """Format jam menjadi 2 digit saat focus out atau enter"""
        try:
            val = self.spin_hour.get().strip()
            if val:
                hour = int(val)
                hour = max(0, min(23, hour))  # Pastikan dalam range 0-23
                self.spin_hour.delete(0, "end")
                self.spin_hour.insert(0, f"{hour:02d}")
        except:
            self.spin_hour.delete(0, "end")
            self.spin_hour.insert(0, "00")
        self._refresh_buttons_state()
    
    def _format_minute(self):
        """Format menit menjadi 2 digit saat focus out atau enter"""
        try:
            val = self.spin_minute.get().strip()
            if val:
                minute = int(val)
                minute = max(0, min(59, minute))  # Pastikan dalam range 0-59
                self.spin_minute.delete(0, "end")
                self.spin_minute.insert(0, f"{minute:02d}")
        except:
            self.spin_minute.delete(0, "end")
            self.spin_minute.insert(0, "00")
        self._refresh_buttons_state()
    
    def _validate_time_input(self, new_value):
        """
        Validasi input waktu real-time:
        - Hanya boleh angka dan titik dua (:)
        - Maksimal 5 karakter (HH:MM)
        - Format partial selama mengetik: H, HH, HH:, HH:M, HH:MM
        """
        if new_value == "":
            return True
        
        # Hanya boleh angka dan titik dua
        if not re.match(r'^[0-9:]*$', new_value):
            return False
        
        # Maksimal 5 karakter
        if len(new_value) > 5:
            return False
        
        # Validasi format partial
        if len(new_value) <= 2:
            # Hanya jam (H atau HH)
            return new_value.isdigit()
        elif len(new_value) == 3:
            # Format HH: atau HH harus ada titik dua di posisi 2
            return new_value[2] == ':' and new_value[:2].isdigit()
        else:
            # Format HH:M atau HH:MM
            parts = new_value.split(':')
            if len(parts) != 2:
                return False
            return parts[0].isdigit() and parts[1].isdigit()

    def _tick_clock(self):
        h, t, j = now_id_strings()
        self.lbl_jam.configure(text=j)
        self.lbl_tanggal.configure(text=f"{h}, {t}")
        self._update_next_label()
        self._refresh_buttons_state()
        self.after(300, self._tick_clock)

    def _is_form_valid(self):
        name = self.ent_name.get().strip()
        time_str = self._get_time_from_spinbox()
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
        # Ubah cursor untuk visual feedback
        btn.configure(cursor=("hand2" if ok else "arrow"))

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
                "days": days_to_label(days), "sound": os.path.basename(sound),
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
        time_str = self._get_time_from_spinbox()
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
        self._set_time_to_spinbox(time_str)
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

    def _open_settings(self):
        """Buka dialog Settings"""
        dialog = tk.Toplevel(self)
        dialog.title("Settings")
        dialog.geometry("500x500")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # Configure colors
        dialog.configure(bg=self.colors['bg'])
        
        # Main container
        container = ttk.Frame(dialog, style="Card.TFrame", padding=20)
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        ttk.Label(
            container,
            text="⚙️ Settings",
            font=("Poppins", 16, "bold"),
            background=self.colors['light'],
            foreground=self.colors['text']
        ).pack(pady=(0, 20))
        
        # Dark Mode Toggle
        dark_frame = ttk.Frame(container, style="Card.TFrame", padding=10)
        dark_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(
            dark_frame,
            text="🌙 Mode Gelap (Dark Mode)",
            font=("Poppins", 11, "bold"),
            background=self.colors['light'],
            foreground=self.colors['text']
        ).pack(side="left")
        
        
        dark_toggle = ToggleSwitch(
            dark_frame,
            width=70,
            height=28,
            on=self.dark_mode,
            command=lambda on: self._toggle_dark_mode(on, dialog)
        )
        dark_toggle.pack(side="right")
        
        # Update background toggle agar sesuai dengan parent
        dark_toggle.configure(bg=self.colors['light'])
        
        # Separator
        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=10)
        
        # Autostart Setting
        autostart_frame = ttk.Frame(container, style="Card.TFrame", padding=10)
        autostart_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(
            autostart_frame,
            text="🚀 Jalankan Otomatis (Autostart)",
            font=("Poppins", 11, "bold"),
            background=self.colors['light'],
            foreground=self.colors['text']
        ).pack(side="left")
        
        autostart_toggle = ToggleSwitch(
            autostart_frame,
            width=70,
            height=28,
            on=bool(self.autostart_var.get()),
            command=lambda on: self._toggle_autostart_from_settings(on)
        )
        autostart_toggle.pack(side="right")
        # Update background toggle agar sesuai dengan parent
        autostart_toggle.configure(bg=self.colors['light'])
        
        ttk.Label(
            autostart_frame,
            font=("Poppins", 9),
            background=self.colors['light'],
            foreground=self.colors['text']
        ).pack(side="left", padx=(10, 0))
        
        # Separator
        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=10)
        
        # Volume Control
        volume_frame = ttk.Frame(container, style="Card.TFrame", padding=10)
        volume_frame.pack(fill="x", pady=(0, 10))
        
        # Volume header
        volume_header = ttk.Frame(volume_frame, style="Card.TFrame")
        volume_header.pack(fill="x", pady=(0, 10))
        
        ttk.Label(
            volume_header,
            text="🔊 Volume",
            font=("Poppins", 11, "bold"),
            background=self.colors['light'],
            foreground=self.colors['text']
        ).pack(side="left")
        ttk.Label(
    volume_frame, # Pasang label deskripsi di volume_frame, di bawah header
    text="Atur tingkat kekerasan suara bel dan pengumuman yang akan diputar oleh aplikasi. (Skala 0 hingga 100)",
    font=("Poppins", 9),
    background=self.colors['light'],
    foreground=self.colors['text'],
    wraplength=400 # Batasi panjang teks
).pack(anchor="w", pady=(2, 8))
        
        # Volume percentage label
        current_volume = int(self.audio.get_volume() * 100)
        volume_label = ttk.Label(
            volume_header,
            text=f"{current_volume}%",
            font=("Poppins", 10, "bold"),
            background=self.colors['light'],
            foreground=self.colors['primary']
        )
        volume_label.pack(side="right")
        
        # Volume slider
        volume_slider_frame = ttk.Frame(volume_frame, style="Card.TFrame")
        volume_slider_frame.pack(fill="x", pady=(0, 10))
        
        def on_volume_change(val):
            volume = float(val) / 100
            self.audio.set_volume(volume)
            volume_label.configure(text=f"{int(val)}%")
            self._set_status(f"Volume diatur ke {int(val)}%")
        
        volume_slider = tk.Scale(
            volume_slider_frame,
            from_=0,
            to=100,
            orient="horizontal",
            command=on_volume_change,
            bg=self.colors['light'],
            fg=self.colors['text'],
            highlightthickness=0,
            troughcolor=self.colors['border'],
            activebackground=self.colors['primary'],
            sliderrelief="flat",
            font=("Poppins", 9)
        )
        volume_slider.set(current_volume)
        volume_slider.pack(fill="x")
        
        # Volume icons
        volume_icons_frame = ttk.Frame(volume_frame, style="Card.TFrame")
        volume_icons_frame.pack(fill="x")
        
        ttk.Label(
            volume_icons_frame,
            text="🔈",
            font=("Poppins", 10),
            background=self.colors['light'],
            foreground=self.colors['text']
        ).pack(side="left")
        
        ttk.Label(
            volume_icons_frame,
            text="🔊",
            font=("Poppins", 10),
            background=self.colors['light'],
            foreground=self.colors['text']
        ).pack(side="right")
        
        # Separator
        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=15)
        
        # About Section
        about_frame = ttk.Frame(container, style="Card.TFrame", padding=15)
        about_frame.pack(fill="both", expand=True)
        
    
        
        info_text = f"""

        """
        
        info_label = tk.Label(
            about_frame,
            text=info_text.strip(),
            font=("Poppins", 9),
            bg=self.colors['light'],
            fg=self.colors['text'],
            justify="left"
        )
        info_label.pack(anchor="w", fill="both", expand=True)
        
        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

    def _toggle_dark_mode_menu(self):
        """Toggle dark mode dari menu"""
        self.dark_mode = not self.dark_mode
        self._apply_theme()
        self._set_status("Dark mode " + ("diaktifkan" if self.dark_mode else "dinonaktifkan"))
    
    def _toggle_autostart_menu(self):
        """Toggle autostart dari menu"""
        current = bool(self.autostart_var.get())
        new_val = not current
        self.autostart_var.set(1 if new_val else 0)
        ok, err = set_autostart(new_val)
        if not ok:
            messagebox.showerror("Autostart", err or "Gagal mengatur autostart")
        else:
            self._set_status("Autostart " + ("diaktifkan" if new_val else "dinonaktifkan"))
    
    def _show_about(self):
        """Tampilkan dialog About"""
        info_text = f"""
{APP_TITLE}
Versi: {APP_VERSION}

Dikembangkan untuk:
SMP Muhammadiyah 3 Purwokerto

Developer:
Nama: Abdul Company
Email: abdulroni0616@gmail.com

© 2025 Abdul Company. All rights reserved.
        """
        messagebox.showinfo("About", info_text.strip())
    
    def _toggle_dark_mode(self, is_on, settings_dialog=None):
        """Toggle dark mode"""
        self.dark_mode = is_on
        
        # Switch color scheme
        if is_on:
            self.colors = self.dark_colors.copy()
        else:
            self.colors = self.light_colors.copy()
        
        # Close settings dialog jika ada
        if settings_dialog:
            settings_dialog.destroy()
        
        # Refresh UI
        self._apply_theme()
        self._set_status(f"Dark mode {'diaktifkan' if is_on else 'dinonaktifkan'}")

    def _apply_theme(self):
        """Apply theme to all widgets"""
        # Update main window
        self.configure(bg=self.colors['bg'])
        
        # Re-configure ttk styles
        self._use_theme()
        
        # Refresh all widgets by rebuilding UI
        # Clear all widgets
        for widget in self.winfo_children():
            widget.destroy()
        
        # Rebuild UI
        self._build_menu()
        self._build_header()
        
        # PERBAIKAN: Setelah _build_header, perbarui ToggleSwitch
        # Warna latar belakang parent (light)
        parent_bg = self.colors['light']
        
        # Update Master Control Toggle (ToggleSwitch)
        # ToggleSwitch juga turunan tk.Canvas, harus di-update
        if hasattr(self, 'master_toggle'):
            try:
                self.master_toggle.configure(bg=parent_bg)
            except Exception:
                pass
        
        self._build_panes()
        self._load_table()
        
        # Refresh state
        self._refresh_buttons_state()
        self._update_next_label()

