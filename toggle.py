import tkinter as tk

class ToggleSwitch(tk.Canvas):
    def __init__(self, master, width=92, height=34, on=False, command=None):
        super().__init__(master, width=width, height=height, highlightthickness=0, bg=self._bg(master), cursor="hand2")
        self._cw, self._ch = width, height
        self._on = bool(on)
        self._cmd = command
        self.bind("<Button-1>", self._toggle)
        self.bind("<Configure>", lambda e: self._redraw())
        self._redraw()

    def _bg(self, master):
        try:
            return master.cget("background")
        except:
            return "#f0f0f0"

    def _toggle(self, _=None):
        self._on = not self._on
        self._redraw()
        if self._cmd:
            self._cmd(self._on)

    def set(self, val: bool):
        self._on = bool(val)
        self._redraw()

    def get(self):
        return self._on

    def _redraw(self):
        self.delete("all")
        pad = 2
        h = int(self.winfo_height()) or self._ch
        w = int(self.winfo_width()) or self._cw
        on_col = "#2ecc71"
        off_col = "#555555"
        track = on_col if self._on else off_col

        self.create_oval(pad, pad, h-pad, h-pad, fill=track, outline=track)
        self.create_oval(w-h+pad, pad, w-pad, h-pad, fill=track, outline=track)
        self.create_rectangle(h//2, pad, w-h//2, h-pad, fill=track, outline=track)

        # Knob
        kx = w - h + pad if self._on else pad
        self.create_oval(kx, pad, kx + h - pad*2, h - pad, fill="#ffffff", outline="#dddddd")

        if self._on:
            tx = int(h*0.55)
            label = "ON"
        else:
            tx = w - int(h*0.55)
            label = "OFF"
        self.create_text(tx, h//2, text=label, fill="white", font=("Segoe UI", 9, "bold"))