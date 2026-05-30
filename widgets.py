"""
GC-01 Rad Pro — Monitor de Radiación
Widgets reutilizables: ArcGauge y TablaLog.
"""
import tkinter as tk
import math

# ── Paleta ──────────────────────────────────────────────────────────────────
BG      = "#0d1117"
CARD    = "#161b22"
CARD2   = "#1c2330"
BORDER  = "#30363d"
GREEN   = "#00ff88"
CYAN    = "#00e5ff"
YELLOW  = "#ffe066"
ORANGE  = "#ff8800"
RED     = "#ff4d4d"
TEXT    = "#e6edf3"
MUTED   = "#8b949e"

# CPM umbral → (color, etiqueta física)
LEVELS = [
    (50,           GREEN,  "Fondo natural"),
    (100,          GREEN,  "Normal / UNSCEAR"),
    (500,          YELLOW, "⚠ Elevado"),
    (1000,         ORANGE, "⚠ Alto  >3 µSv/h"),
    (float("inf"), RED,    "☠ Peligroso"),
]

def level_for(cpm: float):
    for threshold, color, label in LEVELS:
        if cpm < threshold:
            return color, label
    return RED, "☠ Peligroso"

def lerp_color(t: float) -> str:
    """Verde → amarillo → rojo, t en [0, 1]."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        s = t * 2
        r = int(0x00 + s * 0xFF)
        g = int(0xFF - s * (0xFF - 0xE0))
        b = int(0x88 * (1 - s))
    else:
        s = (t - 0.5) * 2
        r = 0xFF
        g = int(0xE0 * (1 - s))
        b = 0
    return f"#{r:02x}{g:02x}{b:02x}"

# ── ArcGauge ─────────────────────────────────────────────────────────────────
class ArcGauge(tk.Canvas):
    """
    Medidor semicircular dibujado con Canvas de tkinter.
    """
    _START_DEG = -225
    _EXTENT    = 270

    def __init__(self, master, *, max_val=1000, unit="CPM",
                 label="", segments=40, **kw):
        kw.setdefault("bg", CARD)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.max_val  = max_val
        self.unit     = unit
        self.label    = label
        self.segments = segments
        self._value   = None
        self.bind("<Configure>", lambda _e: self._draw())

    def set_value(self, value: float | None):
        self._value = value
        self._draw()

    # ── Dibujo ───────────────────────────────────────────────────────────────
    def _draw(self):
        self.delete("all")
        W = self.winfo_width()
        H = self.winfo_height()
        if W < 20 or H < 20:
            return

        cx  = W / 2
        cy  = H * 0.52
        r   = min(W, H) * 0.36
        
        # CORRECCIÓN 1: Arco más delgado para que no se coma el texto
        lw  = max(6, int(r * 0.12)) 
        x0, y0 = cx - r, cy - r
        x1, y1 = cx + r, cy + r

        # ── Fondo del arco ──
        self.create_arc(x0, y0, x1, y1,
                        start=self._START_DEG, extent=self._EXTENT,
                        style="arc", outline=BORDER, width=lw)

        # ── Arco de valor (degradado) ──
        if self._value is not None:
            ratio = max(0.0, min(self._value / self.max_val, 1.0))
            n = self.segments
            for i in range(n):
                t0 = i / n
                t1 = (i + 1) / n
                if t0 >= ratio:
                    break
                frac   = min(t1, ratio)
                color  = lerp_color(t0)
                start  = self._START_DEG + self._EXTENT * t0
                extent = self._EXTENT * (frac - t0)
                self.create_arc(x0, y0, x1, y1,
                                start=start, extent=extent,
                                style="arc", outline=color, width=lw)

        # ── Tamaños de fuente ──
        fs_big = max(14, int(r * 0.44))
        fs_sm  = max(8,  int(r * 0.17))
        fs_xs  = max(7,  int(r * 0.14))

        # ── Valor central y unidad ──
        val_txt = f"{self._value:.1f}" if self._value is not None else "—"
        self.create_text(cx, cy + r * 0.05,
                         text=val_txt,
                         font=("JetBrains Mono", fs_big, "bold"),
                         fill=TEXT, anchor="center")
        self.create_text(cx, cy + r * 0.38,
                         text=self.unit,
                         font=("Outfit", fs_sm), fill=MUTED, anchor="center")

        # ── Etiqueta (encima del arco, separada) ──
        # CORRECCIÓN 2: Se alejó el texto de la etiqueta hacia arriba (1.25 en lugar de 1.05)
        self.create_text(cx, cy - r * 1.25,
                         text=self.label,
                         font=("Outfit", fs_xs), fill=MUTED, anchor="center",
                         width=int(W * 0.9)) 

        # ── Marcadores de escala (0, 50%, máx) ──
        # CORRECCIÓN 3: Expandir el radio de las etiquetas numéricas para que queden por fuera
        def arc_point(deg_tkinter, radius_frac=1.28): 
            rad = math.radians(-deg_tkinter)
            return (cx + r * radius_frac * math.cos(rad),
                    cy + r * radius_frac * math.sin(rad))

        # 0 %
        x0m, y0m = arc_point(self._START_DEG)
        self.create_text(x0m, y0m, text="0",
                         font=("Outfit", fs_xs), fill=MUTED, anchor="center")

        # 50 %
        xm, ym = arc_point(self._START_DEG + self._EXTENT * 0.5)
        mid_val = self.max_val // 2
        # CORRECCIÓN 4: Se quitó la resta manual que empujaba este número hacia el arco
        self.create_text(xm, ym, text=f"{mid_val}",
                         font=("Outfit", fs_xs), fill=MUTED, anchor="center")

        # 100 %
        x1m, y1m = arc_point(self._START_DEG + self._EXTENT)
        self.create_text(x1m, y1m, text=f"{self.max_val}",
                         font=("Outfit", fs_xs), fill=MUTED, anchor="center")