import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading, time, csv, math
from datetime import datetime
from collections import deque
import numpy as np  # <-- AÑADIDO PARA CÁLCULOS ESTADÍSTICOS

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

from serial_manager import SerialManager
from widgets import ArcGauge, level_for, CARD, CARD2, BORDER, GREEN, CYAN, YELLOW, ORANGE, RED, TEXT, MUTED, BG

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

POLL_OPTIONS = {"1 s": 1, "2 s": 2, "5 s": 5, "10 s": 10}
MAX_PTS = 200

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GC-01 Rad Pro — Monitor de Radiación")
        self.geometry("1350x800")
        self.minsize(1000, 660)
        self.configure(fg_color=BG)

        self.serial = SerialManager()
        self.running = False
        self._thread = None
        self._poll_iv = 2

        self.cpm_hist  = deque(maxlen=MAX_PTS)
        self.time_hist = deque(maxlen=MAX_PTS)
        self.log_rows  = []
        self.sess_start = None
        self.sensitivity = 153.8
        self.dose_acc = 0.0
        self.cpm_max = self.cpm_min = None
        self.cpm_sum = 0.0
        self.cpm_n = 0

        self._build()
        self.after(500, self._tick)

    # ── UI BUILD ──────────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sidebar()
        self._main_area()

    def _sidebar(self):
        sb = ctk.CTkFrame(self, width=260, fg_color=CARD, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)

        def label(text, font=("Outfit",10), color=MUTED):
            return ctk.CTkLabel(sb, text=text, font=font, text_color=color)
        def sep():
            ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=8)

        hdr = ctk.CTkFrame(sb, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(18,6))
        ctk.CTkLabel(hdr, text="☢", font=("Segoe UI",30), text_color=GREEN).pack(side="left", padx=(0,10))
        tf = ctk.CTkFrame(hdr, fg_color="transparent"); tf.pack(side="left")
        ctk.CTkLabel(tf, text="GC-01 Rad Pro", font=("Outfit",15,"bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(tf, text="Monitor de Radiación", font=("Outfit",10), text_color=MUTED).pack(anchor="w")

        sep()
        label("CONEXIÓN", ("Outfit",9,"bold"), MUTED).pack(anchor="w", padx=14, pady=(0,4))

        pf = ctk.CTkFrame(sb, fg_color="transparent"); pf.pack(fill="x", padx=14, pady=(0,4))
        pf.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(pf, text="Puerto COM", font=("Outfit",11), text_color=MUTED).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(pf, text="↺", width=28, height=24, font=("Outfit",13),
                      fg_color=CARD2, hover_color=BORDER, command=self._refresh_ports).grid(row=0, column=1)

        self.port_var = ctk.StringVar(value="Seleccionar…")
        self.port_menu = ctk.CTkOptionMenu(sb, variable=self.port_var,
                                           values=SerialManager.list_ports(),
                                           fg_color=CARD2, button_color="#238636",
                                           button_hover_color="#2ea043",
                                           font=("JetBrains Mono",11))
        self.port_menu.pack(fill="x", padx=14, pady=(0,6))

        self.btn_conn = ctk.CTkButton(sb, text="⚡  Conectar", font=("Outfit",13,"bold"),
                                      fg_color="#238636", hover_color="#2ea043",
                                      command=self._toggle_connect)
        self.btn_conn.pack(fill="x", padx=14, pady=(0,4))

        self.status_lbl = ctk.CTkLabel(sb, text="● Desconectado",
                                       font=("Outfit",12), text_color=RED)
        self.status_lbl.pack(anchor="w", padx=14)

        sep()
        label("DISPOSITIVO", ("Outfit",9,"bold"), MUTED).pack(anchor="w", padx=14, pady=(0,4))
        dev_card = ctk.CTkFrame(sb, fg_color=CARD2, corner_radius=8)
        dev_card.pack(fill="x", padx=14, pady=(0,4))
        self.dev_lbl = {}
        for k, d in [("hardware","Hardware"),("firmware","Firmware"),
                     ("tube","Tubo"),("sensitivity","Sensibilidad")]:
            r = ctk.CTkFrame(dev_card, fg_color="transparent"); r.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(r, text=d, font=("Outfit",10), text_color=MUTED).pack(side="left")
            v = ctk.CTkLabel(r, text="—", font=("JetBrains Mono",10), text_color=TEXT)
            v.pack(side="right"); self.dev_lbl[k] = v

        sep()
        self.btn_sync_time = ctk.CTkButton(sb, text="⏱  Sincronizar Reloj", font=("Outfit",12),
                                      fg_color=CARD2, hover_color=BORDER,
                                      state="disabled", command=self._sync_time)
        self.btn_sync_time.pack(fill="x", padx=14, pady=(0,4))

        sep()
        label("BATERÍA", ("Outfit",9,"bold"), MUTED).pack(anchor="w", padx=14, pady=(0,4))
        bc = ctk.CTkFrame(sb, fg_color=CARD2, corner_radius=8)
        bc.pack(fill="x", padx=14, pady=(0,4))
        self.batt_lbl = ctk.CTkLabel(bc, text="— V", font=("JetBrains Mono",22,"bold"), text_color=GREEN)
        self.batt_lbl.pack(padx=10, pady=(8,4), anchor="w")
        self.batt_bar = ctk.CTkProgressBar(bc, height=8, fg_color=BORDER, progress_color=GREEN)
        self.batt_bar.set(0); self.batt_bar.pack(fill="x", padx=10, pady=(0,10))

        sep()
        label("SESIÓN", ("Outfit",9,"bold"), MUTED).pack(anchor="w", padx=14, pady=(0,4))
        self.btn_start = ctk.CTkButton(sb, text="▶  Iniciar", font=("Outfit",13,"bold"),
                                       fg_color="#1f6feb", hover_color="#388bfd",
                                       state="disabled", command=self._start)
        self.btn_start.pack(fill="x", padx=14, pady=(0,4))
        self.btn_stop = ctk.CTkButton(sb, text="⏸  Pausar", font=("Outfit",13),
                                      fg_color=CARD2, hover_color=BORDER,
                                      state="disabled", command=self._stop)
        self.btn_stop.pack(fill="x", padx=14, pady=(0,4))

        ivf = ctk.CTkFrame(sb, fg_color="transparent"); ivf.pack(fill="x", padx=14, pady=(0,4))
        ivf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ivf, text="Intervalo", font=("Outfit",11), text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.iv_var = ctk.StringVar(value="2 s")
        ctk.CTkOptionMenu(ivf, variable=self.iv_var, values=list(POLL_OPTIONS.keys()),
                          width=80, height=28, fg_color=CARD2, button_color=CARD2,
                          font=("Outfit",11),
                          command=lambda v: setattr(self, "_poll_iv", POLL_OPTIONS[v])
                          ).grid(row=0, column=1, sticky="e")

        sc = ctk.CTkFrame(sb, fg_color=CARD2, corner_radius=8)
        sc.pack(fill="x", padx=14, pady=(0,4))
        self.sess_lbl = {}
        for k, d in [("dur","Duración"),("n","Muestras")]:
            r = ctk.CTkFrame(sc, fg_color="transparent"); r.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(r, text=d, font=("Outfit",10), text_color=MUTED).pack(side="left")
            v = ctk.CTkLabel(r, text="—", font=("JetBrains Mono",10), text_color=TEXT)
            v.pack(side="right"); self.sess_lbl[k] = v

        sep()
        self.btn_exp = ctk.CTkButton(sb, text="⬇  Exportar CSV", font=("Outfit",12),
                                     fg_color=CARD2, hover_color=BORDER,
                                     state="disabled", command=self._export)
        self.btn_exp.pack(fill="x", padx=14, pady=(0,4))
        self.btn_clr = ctk.CTkButton(sb, text="🗑  Limpiar datos", font=("Outfit",12),
                                     fg_color="#3d1a1a", hover_color="#5a2020",
                                     text_color="#ff6b6b",
                                     state="disabled", command=self._clear)
        self.btn_clr.pack(fill="x", padx=14, pady=(0,4))

    def _main_area(self):
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=(1,0))
        main.grid_columnconfigure((0,1,2), weight=1)
        main.grid_rowconfigure(1, weight=2)
        main.grid_rowconfigure(2, weight=3)

        gc = ctk.CTkFrame(main, fg_color=CARD, corner_radius=12)
        gc.grid(row=0, column=0, padx=(12,6), pady=(12,6), sticky="nsew")
        ctk.CTkLabel(gc, text="Tasa de conteo", font=("Outfit",12), text_color=MUTED).pack(pady=(10,0))
        self.cpm_gauge = ArcGauge(gc, max_val=1000, unit="CPM",
                                  label="Counts Per Minute", width=200, height=160)
        self.cpm_gauge.pack(fill="both", expand=True, padx=8)
        self.cpm_lv = ctk.CTkLabel(gc, text="● Sin datos", font=("Outfit",12), text_color=MUTED)
        self.cpm_lv.pack(pady=(0,10))

        dd = ctk.CTkFrame(main, fg_color=CARD, corner_radius=12)
        dd.grid(row=0, column=1, padx=6, pady=(12,6), sticky="nsew")
        ctk.CTkLabel(dd, text="Tasa de dosis", font=("Outfit",12), text_color=MUTED).pack(pady=(10,0))
        self.dose_gauge = ArcGauge(dd, max_val=10, unit="µSv/h",
                                   label="Microsievert / hora", width=200, height=160)
        self.dose_gauge.pack(fill="both", expand=True, padx=8)
        self.dose_lbl = ctk.CTkLabel(dd, text="Acum: — µSv", font=("Outfit",12), text_color=CYAN)
        self.dose_lbl.pack(pady=(0,10))

        sc = ctk.CTkFrame(main, fg_color=CARD, corner_radius=12)
        sc.grid(row=0, column=2, padx=(6,12), pady=(12,6), sticky="nsew")
        ctk.CTkLabel(sc, text="Estadísticas", font=("Outfit",13,"bold"), text_color=TEXT).pack(
            pady=(12,6), padx=14, anchor="w")
        self.stat_lbl = {}
        for k, d, c in [("avg","CPM Promedio",TEXT),
                         ("max","CPM Máximo",RED),
                         ("dose_acc","Dosis Acumulada (µSv)",CYAN),
                         ("dose_yr","Proyección Anual (mSv/y)",ORANGE),
                         ("sigma","Incertidumbre (±σ CPM)",TEXT),
                         ("pulses","Pulsos Totales",MUTED)]:
            f = ctk.CTkFrame(sc, fg_color=CARD2, corner_radius=6)
            f.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(f, text=d, font=("Outfit",10), text_color=MUTED).pack(side="left", padx=10, pady=6)
            v = ctk.CTkLabel(f, text="—", font=("JetBrains Mono",11,"bold"), text_color=c)
            v.pack(side="right", padx=10); self.stat_lbl[k] = v

        cf = ctk.CTkFrame(main, fg_color=CARD, corner_radius=12)
        cf.grid(row=1, column=0, columnspan=3, padx=12, pady=(0,6), sticky="nsew")
        hdr = ctk.CTkFrame(cf, fg_color="transparent"); hdr.pack(fill="x", padx=14, pady=(10,0))
        ctk.CTkLabel(hdr, text="Análisis Estadístico de Radiación — Estocástico vs. Tendencia",
                     font=("Outfit",13,"bold"), text_color=TEXT).pack(side="left")

        self.fig = Figure(figsize=(1,1), facecolor=CARD)
        self.ax  = self.fig.add_subplot(111)
        self._style_chart()
        self.chart_canvas = FigureCanvasTkAgg(self.fig, master=cf)
        self.chart_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(4,10))

        lf = ctk.CTkFrame(main, fg_color=CARD, corner_radius=12)
        lf.grid(row=2, column=0, columnspan=3, padx=12, pady=(0,12), sticky="nsew")
        lhdr = ctk.CTkFrame(lf, fg_color="transparent"); lhdr.pack(fill="x", padx=14, pady=(10,4))
        ctk.CTkLabel(lhdr, text="Registro de datos", font=("Outfit",13,"bold"), text_color=TEXT).pack(side="left")
        self.log_count_lbl = ctk.CTkLabel(lhdr, text="0 entradas",
                                           font=("Outfit",11), text_color=MUTED)
        self.log_count_lbl.pack(side="right")

        cols = ("hora","cpm","usvh","pulsos","bateria","nivel")
        heads = ("Hora","CPM","µSv/h","Pulsos","Batería (V)","Nivel")
        import tkinter.ttk as ttk
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.Treeview",
                        background=CARD2, foreground=TEXT,
                        fieldbackground=CARD2, borderwidth=0,
                        rowheight=26, font=("JetBrains Mono",10))
        style.configure("Custom.Treeview.Heading",
                        background=CARD, foreground=MUTED,
                        borderwidth=0, font=("Outfit",10,"bold"))
        style.map("Custom.Treeview", background=[("selected","#1f6feb")])

        frm = ctk.CTkFrame(lf, fg_color=CARD2, corner_radius=8)
        frm.pack(fill="both", expand=True, padx=10, pady=(0,10))
        vsb = ttk.Scrollbar(frm, orient="vertical")
        vsb.pack(side="right", fill="y")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings",
                                  style="Custom.Treeview",
                                  yscrollcommand=vsb.set)
        vsb.config(command=self.tree.yview)
        for c, h in zip(cols, heads):
            self.tree.heading(c, text=h)
            self.tree.column(c, anchor="center", width=120)
        self.tree.pack(fill="both", expand=True)

    # ── Chart style ──────────────────────────────────────────────────────────
    def _style_chart(self):
        self.ax.set_facecolor(CARD2)
        self.fig.patch.set_facecolor(CARD)
        self.ax.tick_params(colors=MUTED, labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_color(BORDER)
        self.ax.set_ylabel("CPM", color=MUTED, fontsize=10)
        self.ax.grid(color=BORDER, linestyle="--", linewidth=0.5, alpha=0.5)

        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        self.ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
        self.ax.tick_params(axis='x', rotation=15)
        
        # FIX DEFINITIVO EJE X: Ajustamos los márgenes interiores de la gráfica
        # bottom=0.22 asegura que haya 22% de espacio abajo para las horas inclinadas.
        self.fig.subplots_adjust(bottom=0.22, left=0.08, right=0.98, top=0.92)

    def _update_chart(self):
        self.ax.clear()
        self._style_chart()
        if len(self.time_hist) > 1:
            xs = list(self.time_hist)
            ys = np.array(list(self.cpm_hist))
            
            # 1. Trazamos los datos crudos estocásticos (suaves, al fondo)
            self.ax.plot(xs, ys, color=GREEN, linewidth=1.2, alpha=0.4, label="Lectura Cruda (Ruido)")
            
            # 2. Análisis Estadístico (Filtro SMA y Poisson)
            window = min(10, len(ys)) # Ventana de promediado de 10 muestras
            if window > 1:
                # Convolución para la media móvil
                sma = np.convolve(ys, np.ones(window)/window, mode='valid')
                xs_sma = xs[window-1:]
                
                # Incertidumbre estadística (Desviación de Poisson = raíz de la media)
                sigma = np.sqrt(sma)
                
                # Dibujamos la media (Tendencia Real)
                self.ax.plot(xs_sma, sma, color=CYAN, linewidth=2.0, solid_capstyle="round", label=f"Tendencia Real (SMA n={window})")
                
                # Dibujamos la franja de incertidumbre ±1σ
                self.ax.fill_between(xs_sma, sma - sigma, sma + sigma, color=CYAN, alpha=0.2, label="Banda Incertidumbre (±1σ)")
            
            # 3. Líneas de alerta radiológica estáticas
            self.ax.axhline(y=100, color=YELLOW, linewidth=0.8, linestyle="--", alpha=0.6, label="Umbral Elevado (100 CPM)")
            self.ax.axhline(y=500, color=RED,    linewidth=0.8, linestyle="--", alpha=0.6, label="Umbral Peligro (500 CPM)")
            
            # 4. Mostrar la leyenda para entender la gráfica
            self.ax.legend(loc="upper left", facecolor=CARD, edgecolor=BORDER, fontsize=8, labelcolor=TEXT)

        self.chart_canvas.draw_idle()

    # ── Serial & polling ─────────────────────────────────────────────────────
    def _toggle_connect(self):
        if self.serial.connected:
            self._stop()
            self.serial.disconnect()
            self._set_disconnected()
        else:
            port = self.port_var.get()
            if port in ("Seleccionar…","(ninguno)"):
                messagebox.showwarning("Puerto", "Selecciona un puerto COM primero.")
                return
            try:
                self.serial.connect(port)
                self._set_connected()
                self._load_device_info()
            except Exception as e:
                messagebox.showerror("Error de conexión",
                    f"No se pudo conectar a {port}.\n\n{e}\n\n"
                    "Verifica:\n• Cable USB de datos\n"
                    "• GC-01: Ajustes → Modo datos → Activado\n"
                    "• Driver CH340 instalado")

    def _set_connected(self):
        self.btn_conn.configure(text="✖  Desconectar", fg_color="#6e1818", hover_color="#8b2020")
        self.status_lbl.configure(text="● Conectado", text_color=GREEN)
        self.btn_start.configure(state="normal")
        self.btn_sync_time.configure(state="normal")

    def _set_disconnected(self):
        self.btn_conn.configure(text="⚡  Conectar", fg_color="#238636", hover_color="#2ea043")
        self.status_lbl.configure(text="● Desconectado", text_color=RED)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="disabled")
        self.btn_exp.configure(state="disabled")
        self.btn_clr.configure(state="disabled")
        self.btn_sync_time.configure(state="disabled")

    def _load_device_info(self):
        def run():
            info = self.serial.get_device_id()
            if info:
                self.dev_lbl["hardware"].configure(text=info["hardware"][:22])
                self.dev_lbl["firmware"].configure(text=info["firmware"][:22])
            tube = self.serial.get_tube_type()
            if tube:
                self.dev_lbl["tube"].configure(text=tube)
            sens = self.serial.get_tube_sensitivity()
            if sens:
                self.sensitivity = sens
                self.dev_lbl["sensitivity"].configure(text=f"{sens:.1f} cpm/µSv/h")
        threading.Thread(target=run, daemon=True).start()

    def _start(self):
        if not self.serial.connected:
            return
        self.running = True
        self.sess_start = datetime.now()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_exp.configure(state="normal")
        self.btn_clr.configure(state="normal")
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def _stop(self):
        self.running = False
        self.btn_start.configure(state="normal" if self.serial.connected else "disabled")
        self.btn_stop.configure(state="disabled")

    def _poll_loop(self):
        print("[POLL] Hilo de polling iniciado")
        while self.running and self.serial.connected:
            t0 = time.time()
            try:
                cpm  = self.serial.get_tube_rate()
                volt = self.serial.get_battery_voltage()
                puls = self.serial.get_tube_pulse_count()
                now  = datetime.now()

                if cpm is not None:
                    dose = cpm / self.sensitivity
                    self.cpm_hist.append(cpm)
                    self.time_hist.append(now) 
                    
                    if self.cpm_max is None or cpm > self.cpm_max: self.cpm_max = cpm
                    if self.cpm_min is None or cpm < self.cpm_min: self.cpm_min = cpm
                    self.cpm_sum += cpm
                    self.cpm_n += 1
                    
                    self.dose_acc += dose * (self._poll_iv / 3600)
                    row = {
                        "hora": now.strftime("%H:%M:%S"),
                        "cpm": f"{cpm:.1f}",
                        "usvh": f"{dose:.4f}",
                        "pulsos": str(puls) if puls is not None else "—",
                        "bateria": f"{volt:.3f}" if volt is not None else "—",
                        "nivel": level_for(cpm)[1],
                    }
                    self.log_rows.append(row)
                    self.after(0, self._update_ui, cpm, dose, volt, puls, row)
                else:
                    pass
            except Exception as ex:
                print(f"[POLL] ERROR en el hilo: {ex}")

            elapsed = time.time() - t0
            time.sleep(max(0, self._poll_iv - elapsed))
        print("[POLL] Hilo de polling terminado")

    def _update_ui(self, cpm, dose, volt, puls, row):
        color, level = level_for(cpm)
        self.cpm_gauge.set_value(cpm)
        self.cpm_lv.configure(text=f"● {level}", text_color=color)
        self.dose_gauge.set_value(dose)
        self.dose_lbl.configure(text=f"Acum: {self.dose_acc:.4f} µSv")

        if volt is not None:
            self.batt_lbl.configure(text=f"{volt:.3f} V")
            pct = max(0, min(1, (volt - 2.7) / (4.2 - 2.7)))
            self.batt_bar.set(pct)
            bc = GREEN if pct > 0.5 else (YELLOW if pct > 0.2 else RED)
            self.batt_bar.configure(progress_color=bc)
            self.batt_lbl.configure(text_color=bc)

        avg = self.cpm_sum / self.cpm_n if self.cpm_n else 0
        total_mins = (self.cpm_n * self._poll_iv) / 60.0
        sigma = math.sqrt(avg / total_mins) if total_mins > 0 else 0
        
        dose_yr = (dose * 24 * 365) / 1000  # uSv/h a mSv/año
        
        self.stat_lbl["avg"].configure(text=f"{avg:.1f}")
        self.stat_lbl["max"].configure(text=f"{self.cpm_max:.1f}" if self.cpm_max else "—")
        self.stat_lbl["dose_acc"].configure(text=f"{self.dose_acc:.4f}")
        self.stat_lbl["dose_yr"].configure(text=f"{dose_yr:.2f}")
        self.stat_lbl["sigma"].configure(text=f"±{sigma:.1f}")
        self.stat_lbl["pulses"].configure(text=str(puls) if puls else "—")

        self.tree.insert("", 0, values=tuple(row.values()))
        self.log_count_lbl.configure(text=f"{len(self.log_rows)} entradas")
        self._update_chart()

    def _tick(self):
        if self.sess_start and self.running:
            d = datetime.now() - self.sess_start
            h, r = divmod(int(d.total_seconds()), 3600)
            m, s = divmod(r, 60)
            self.sess_lbl["dur"].configure(text=f"{h:02d}:{m:02d}:{s:02d}")
            self.sess_lbl["n"].configure(text=str(self.cpm_n))
        self.after(1000, self._tick)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _sync_time(self):
        if not self.serial.connected:
            return

        def run_sync():
            try:
                import time
                offset = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
                local_ts = int(time.time()) - offset
                
                success = self.serial.set_device_time(local_ts)
                
                if success:
                    self.after(0, lambda: messagebox.showinfo(
                        "Reloj Sincronizado", 
                        "La hora del GC-01 se ha actualizado correctamente."
                    ))
                else:
                    self.after(0, lambda: messagebox.showerror(
                        "Error", 
                        "El dispositivo no confirmó la sincronización (No se recibió 'OK')."
                    ))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    "Error de comunicación", 
                    f"Ocurrió un fallo al intentar sincronizar: {e}"
                ))

        threading.Thread(target=run_sync, daemon=True).start()

    def _refresh_ports(self):
        ports = SerialManager.list_ports()
        self.port_menu.configure(values=ports)
        if ports:
            self.port_var.set(ports[0])

    def _export(self):
        if not self.log_rows:
            messagebox.showinfo("Sin datos", "No hay datos para exportar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV","*.csv")],
            initialfile=f"gc01_{datetime.now():%Y%m%d_%H%M%S}.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.log_rows[0].keys())
            w.writeheader(); w.writerows(self.log_rows)
        messagebox.showinfo("Exportado", f"Datos guardados en:\n{path}")

    def _clear(self):
        if not messagebox.askyesno("Limpiar", "¿Eliminar todos los datos de la sesión?"):
            return
        self.log_rows.clear()
        self.cpm_hist.clear(); self.time_hist.clear()
        self.cpm_max = self.cpm_min = self.cpm_sum = None
        self.cpm_n = 0; self.dose_acc = 0.0
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.log_count_lbl.configure(text="0 entradas")
        self.cpm_gauge.set_value(None)
        self.dose_gauge.set_value(None)
        for k in self.stat_lbl:
            self.stat_lbl[k].configure(text="—")
        self._update_chart()


if __name__ == "__main__":
    app = App()
    app.mainloop()