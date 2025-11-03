import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import os


class SplashScreen(tk.Toplevel):
    def __init__(self, parent, logo_path=None, duration=3000):
        super().__init__(parent)
        self.duration = duration
        self.logo_path = logo_path
        
        # Window settings
        self.title("")
        self.overrideredirect(True)  # Remove window border
        
        # Set size - persegi panjang (landscape)
        width = 800
        height = 500
        
        # Center on screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # Modern colors
        self.colors = {
            'bg': '#4834d4',
            'primary': '#ffffff',
            'secondary': '#f5f6fa',
            'accent': '#ffd32a'
        }
        
        self.configure(bg=self.colors['bg'])
        
        self._build_ui()
        
        # Auto close after duration
        self.after(duration, self.close)
        
    def _build_ui(self):
        # Main container
        container = tk.Frame(self, bg=self.colors['bg'])
        container.place(relx=0.5, rely=0.5, anchor='center')
        
        # Logo
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                img = Image.open(self.logo_path)
                # Resize logo - lebih besar dan proporsional
                img = img.resize((150, 150), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(img)
                
                logo_label = tk.Label(
                    container,
                    image=self.logo_photo,
                    bg=self.colors['bg']
                )
                logo_label.pack(pady=(10, 25))
            except Exception:
                # If logo fails, show emoji
                logo_label = tk.Label(
                    container,
                    text="🔔",
                    font=("Segoe UI Emoji", 72),
                    bg=self.colors['bg'],
                    fg=self.colors['primary']
                )
                logo_label.pack(pady=(0, 20))
        else:
            # Default emoji logo
            logo_label = tk.Label(
                container,
                text="🔔",
                font=("Segoe UI Emoji", 72),
                bg=self.colors['bg'],
                fg=self.colors['primary']
            )
            logo_label.pack(pady=(0, 20))
        
        # School name
        school_name = tk.Label(
            container,
            text="SMP MUHAMMADIYAH 3",
            font=("Poppins", 28, "bold"),
            bg=self.colors['bg'],
            fg=self.colors['primary']
        )
        school_name.pack()
        
        school_location = tk.Label(
            container,
            text="PURWOKERTO",
            font=("Poppins", 24, "bold"),
            bg=self.colors['bg'],
            fg=self.colors['accent']
        )
        school_location.pack(pady=(5, 25))
        
        # Separator line
        separator = tk.Frame(container, bg=self.colors['primary'], height=2, width=300)
        separator.pack(pady=(0, 20))
        
        # App title
        app_title = tk.Label(
            container,
            text="Bell Scheduler System",
            font=("Poppins", 14),
            bg=self.colors['bg'],
            fg=self.colors['secondary']
        )
        app_title.pack(pady=(0, 10))
        
        # Version
        version = tk.Label(
            container,
            text="Version 1.0.0",
            font=("Poppins", 9),
            bg=self.colors['bg'],
            fg=self.colors['secondary']
        )
        version.pack()
        
        # Progress bar
        self.progress = ttk.Progressbar(
            container,
            mode='indeterminate',
            length=300
        )
        self.progress.pack(pady=(25, 0))
        self.progress.start(10)
        
        # Loading text
        loading_text = tk.Label(
            container,
            text="Memuat aplikasi...",
            font=("Poppins", 9),
            bg=self.colors['bg'],
            fg=self.colors['secondary']
        )
        loading_text.pack(pady=(10, 0))
    
    def close(self):
        """Close splash screen"""
        self.progress.stop()
        self.destroy()


def show_splash(parent, logo_path=None, duration=3000):
    """Show splash screen and wait for it to close"""
    splash = SplashScreen(parent, logo_path, duration)
    parent.wait_window(splash)
