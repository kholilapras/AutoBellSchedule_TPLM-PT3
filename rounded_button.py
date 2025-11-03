import tkinter as tk

class RoundedButton(tk.Canvas):
    """Button rounded seperti toggle switch"""
    def _get_bg(self, master):
        """Ambil warna latar belakang master/parent widget"""
        try:
            return master.cget("background")
        except:
            return "#ffffff"  # Fallback ke putih jika gagal
    
    def __init__(self, master, text="Button", width=92, height=34, command=None, 
                 bg_color="#4834d4", text_color="#ffffff", hover_color="#686de0"):
        # self._get_bg(master) akan mencoba mendapatkan warna latar belakang dari frame induk
        super().__init__(master, width=width, height=height, highlightthickness=0, 
                        bg=self._get_bg(master), cursor="hand2")
        self._cw, self._ch = width, height
        self._text = text
        self._cmd = command
        self._bg_color = bg_color
        self._text_color = text_color
        self._hover_color = hover_color
        self._is_hover = False
        
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        # Pastikan Canvas sudah siap sebelum menggambar
        self.after(1, self._redraw)

    def _click(self, _=None):
        if self._cmd:
            self._cmd()

    def _on_enter(self, _=None):
        self._is_hover = True
        self._redraw()

    def _on_leave(self, _=None):
        self._is_hover = False
        self._redraw()

    def _redraw(self):
        self.delete("all")
        pad = 2
        # Gunakan ukuran yang disimpan, karena winfo bisa return 1 saat pertama kali
        h = self._ch
        w = self._cw
        
        # Pilih warna berdasarkan hover state
        bg = self._hover_color if self._is_hover else self._bg_color
        
        # Draw rounded rectangle
        radius = h // 2
        self.create_oval(pad, pad, h-pad, h-pad, fill=bg, outline=bg)
        self.create_oval(w-h+pad, pad, w-pad, h-pad, fill=bg, outline=bg)
        self.create_rectangle(h//2, pad, w-h//2, h-pad, fill=bg, outline=bg)
        
        # Draw text
        self.create_text(w//2, h//2, text=self._text, fill=self._text_color, 
                        font=("Poppins", 9, "bold"))

    def configure_colors(self, bg_color=None, hover_color=None, text_color=None, parent_bg=None):
        """Update colors untuk dark mode, termasuk warna latar belakang canvas."""
        if bg_color:
            self._bg_color = bg_color
        if hover_color:
            self._hover_color = hover_color
        if text_color:
            self._text_color = text_color
        
        # PERBAIKI: Update warna latar belakang Canvas itu sendiri
        if parent_bg:
            self.configure(bg=parent_bg)
        
        # Pastikan Canvas siap sebelum menggambar
        self.update_idletasks()
        self._redraw()
