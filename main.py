import tkinter as tk
from tkinter import filedialog, messagebox, ttk
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
import science_utils
import spectrum_simulator

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

POLL_OPTIONS = {"1 s": 1, "2 s": 2, "5 s": 5, "10 s": 10}
MAX_PTS = 200

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GC-01 Rad Pro — Monitor de Radiación")
        self.geometry("1500x860")
        self.minsize(1150, 700)
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

        # Variables de estado para física y análisis avanzado
        self.poisson_mode_var = ctk.StringVar(value="Discreto (Intervalo)")
        
        self.decay_range_var = ctk.StringVar(value="Desde el Máximo")
        self.decay_bg_check_var = ctk.BooleanVar(value=False)
        self.decay_bg_val_var = ctk.StringVar(value="25.0")
        
        self.dt_preset_var = ctk.StringVar(value="J305")
        self.dt_val_var = ctk.StringVar(value="180")
        
        self.act_dist_var = ctk.StringVar(value="10.0")
        self.act_tube_var = ctk.StringVar(value="J305")
        self.act_area_var = ctk.StringVar(value="9.0")
        self.act_eff_var = ctk.StringVar(value="1.0")
        
        self.sh_mat_var = ctk.StringVar(value="Plomo")
        self.sh_nrg_var = ctk.StringVar(value="Cs-137 (662 keV)")
        self.sh_thick_var = ctk.StringVar(value="1.0")
        self.sh_i0_var = ctk.StringVar(value="1000.0")
        self.sh_i_var = ctk.StringVar(value="500.0")

        # Variables para simulador de espectroscopía
        self.spec_iso_var = ctk.StringVar(value="Cs-137")
        self.spec_res_var = ctk.DoubleVar(value=7.0)
        self.spec_det_preset_var = ctk.StringVar(value="NaI(Tl) (Centellador estándar)")

        # Variables para Datalog Flash
        self.datalog_sessions = []
        self.selected_datalog_session_idx = -1

        # Variables para Calibración de 2 Fuentes
        self.cal_bg_var = ctk.StringVar(value="25.0")
        self.cal_r1_var = ctk.StringVar(value="500.0")
        self.cal_r2_var = ctk.StringVar(value="600.0")
        self.cal_r12_var = ctk.StringVar(value="1050.0")
        self.cal_status_var = ctk.StringVar(value="Listos para calibrar")
        self.cal_progress_var = ctk.DoubleVar(value=0.0)
        self._temp_cal_dt = None

        # Variables para Atenuación Multi-espesor
        self.sh_points = []
        self.sh_point_thick_var = ctk.StringVar(value="0.1")
        self.sh_point_cpm_var = ctk.StringVar(value="100.0")
        self.sh_res_i0_var = ctk.StringVar(value="—")
        self.sh_res_mu_var = ctk.StringVar(value="—")
        self.sh_res_hvl_var = ctk.StringVar(value="—")
        self.sh_res_tvl_var = ctk.StringVar(value="—")
        self.sh_res_r2_var = ctk.StringVar(value="—")
        self.sh_res_isotope_var = ctk.StringVar(value="—")
        self._sh_fit_I0 = None
        self._sh_fit_mu = None
        self._sh_fit_B = None

        # Variables para telemetría y ajuste de alta tensión (HV)
        self.hv_freq_var = ctk.StringVar(value="—")
        self.hv_duty_var = ctk.StringVar(value="—")
        self.hv_set_freq_var = ctk.StringVar(value="16000")


        self._build()
        self._update_spec_chart()
        self.after(500, self._tick)

    # ── UI BUILD ──────────────────────────────────────────────────────────────
    def _build(self):
        # 3-column layout: sidebar | live metrics | analysis tabs
        self.grid_columnconfigure(0, weight=0, minsize=280)
        self.grid_columnconfigure(1, weight=0, minsize=300)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sidebar()
        self._live_panel()
        self._main_area()

    def _sidebar(self):
        # ── Sidebar contenedor externo ──────────────────────────────────────
        sb_outer = ctk.CTkFrame(self, width=280, fg_color=CARD, corner_radius=0)
        sb_outer.grid(row=0, column=0, sticky="nsew")
        sb_outer.grid_propagate(False)
        sb_outer.grid_rowconfigure(0, weight=0)   # header fijo
        sb_outer.grid_rowconfigure(1, weight=1)   # scroll
        sb_outer.grid_columnconfigure(0, weight=1)

        # ── Header fijo (logo + título) ─────────────────────────────────────
        hdr = ctk.CTkFrame(sb_outer, fg_color="#0b1120", corner_radius=0, height=72)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="☢", font=("Segoe UI", 34),
                     text_color=GREEN).grid(row=0, column=0, padx=(16, 10), pady=14)
        tf = ctk.CTkFrame(hdr, fg_color="transparent")
        tf.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(tf, text="GC-01 Rad Pro",
                     font=("Outfit", 15, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(tf, text="Monitor de Radiación Avanzado",
                     font=("Outfit", 9), text_color=MUTED).pack(anchor="w")

        # ── Área scrollable ─────────────────────────────────────────────────
        sb = ctk.CTkScrollableFrame(sb_outer, fg_color=CARD, corner_radius=0,
                                    scrollbar_button_color=BORDER,
                                    scrollbar_button_hover_color=CARD2)
        sb.grid(row=1, column=0, sticky="nsew")
        sb.grid_columnconfigure(0, weight=1)

        def section_label(parent, text):
            """Etiqueta de sección estilo dashboard."""
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", padx=14, pady=(12, 4))
            ctk.CTkFrame(f, height=1, fg_color=BORDER).pack(fill="x", pady=(0, 4))
            ctk.CTkLabel(f, text=text, font=("Outfit", 8, "bold"),
                         text_color=MUTED).pack(anchor="w")

        def info_row(parent, label, value_text="—", val_font=("JetBrains Mono", 10),
                     val_color=TEXT):
            """Fila clave-valor para tarjetas de información."""
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(r, text=label, font=("Outfit", 10),
                         text_color=MUTED).pack(side="left")
            v = ctk.CTkLabel(r, text=value_text, font=val_font, text_color=val_color)
            v.pack(side="right")
            return v

        # ── SECCIÓN: CONEXIÓN ───────────────────────────────────────────────
        section_label(sb, "CONEXIÓN")

        pf = ctk.CTkFrame(sb, fg_color="transparent")
        pf.pack(fill="x", padx=14, pady=(0, 4))
        pf.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(pf, text="Puerto COM", font=("Outfit", 11),
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(pf, text="↺", width=28, height=24, font=("Outfit", 13),
                      fg_color=CARD2, hover_color=BORDER,
                      command=self._refresh_ports).grid(row=0, column=1)

        self.port_var = ctk.StringVar(value="Seleccionar…")
        self.port_menu = ctk.CTkOptionMenu(sb, variable=self.port_var,
                                           values=SerialManager.list_ports(),
                                           fg_color=CARD2, button_color="#238636",
                                           button_hover_color="#2ea043",
                                           font=("JetBrains Mono", 11))
        self.port_menu.pack(fill="x", padx=14, pady=(0, 6))

        self.btn_conn = ctk.CTkButton(sb, text="⚡  Conectar",
                                      font=("Outfit", 13, "bold"),
                                      fg_color="#238636", hover_color="#2ea043",
                                      command=self._toggle_connect)
        self.btn_conn.pack(fill="x", padx=14, pady=(0, 6))

        # Estado + LED heartbeat
        st_frame = ctk.CTkFrame(sb, fg_color=CARD2, corner_radius=8)
        st_frame.pack(fill="x", padx=14, pady=(0, 4))
        inner_st = ctk.CTkFrame(st_frame, fg_color="transparent")
        inner_st.pack(fill="x", padx=10, pady=8)
        self.status_lbl = ctk.CTkLabel(inner_st, text="● Desconectado",
                                       font=("Outfit", 11, "bold"), text_color=RED)
        self.status_lbl.pack(side="left")
        self.led_indicator = ctk.CTkLabel(inner_st, text="●",
                                           font=("Segoe UI", 14), text_color="#222222")
        self.led_indicator.pack(side="right")

        self.btn_sync_time = ctk.CTkButton(sb, text="⏱  Sincronizar Reloj",
                                           font=("Outfit", 11),
                                           fg_color=CARD2, hover_color=BORDER,
                                           state="disabled", command=self._sync_time)
        self.btn_sync_time.pack(fill="x", padx=14, pady=(0, 4))

        # ── SECCIÓN: DISPOSITIVO ────────────────────────────────────────────
        section_label(sb, "DISPOSITIVO")
        dev_card = ctk.CTkFrame(sb, fg_color=CARD2, corner_radius=8)
        dev_card.pack(fill="x", padx=14, pady=(0, 4))
        self.dev_lbl = {}
        for k, d in [("hardware", "Hardware"), ("firmware", "Firmware"),
                     ("tube", "Tubo"), ("sensitivity", "Sensibilidad"),
                     ("dead_time", "Tiempo Muerto"), ("hv_freq", "Freq. HV"),
                     ("bg_comp", "Comp. de Fondo")]:
            self.dev_lbl[k] = info_row(dev_card, d)

        # ── SECCIÓN: BATERÍA ────────────────────────────────────────────────
        section_label(sb, "BATERÍA")
        bc = ctk.CTkFrame(sb, fg_color=CARD2, corner_radius=8)
        bc.pack(fill="x", padx=14, pady=(0, 4))
        batt_inner = ctk.CTkFrame(bc, fg_color="transparent")
        batt_inner.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(batt_inner, text="Voltaje",
                     font=("Outfit", 10), text_color=MUTED).pack(side="left")
        self.batt_lbl = ctk.CTkLabel(batt_inner, text="— V",
                                     font=("JetBrains Mono", 16, "bold"),
                                     text_color=GREEN)
        self.batt_lbl.pack(side="right")
        self.batt_bar = ctk.CTkProgressBar(bc, height=6, fg_color=BORDER,
                                           progress_color=GREEN)
        self.batt_bar.set(0)
        self.batt_bar.pack(fill="x", padx=10, pady=(0, 10))

        # ── SECCIÓN: SESIÓN ─────────────────────────────────────────────────
        section_label(sb, "CONTROL DE SESIÓN")

        btn_row = ctk.CTkFrame(sb, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 4))
        btn_row.grid_columnconfigure((0, 1), weight=1)
        self.btn_start = ctk.CTkButton(btn_row, text="▶  Iniciar",
                                       font=("Outfit", 12, "bold"),
                                       fg_color="#1f6feb", hover_color="#388bfd",
                                       state="disabled", command=self._start)
        self.btn_start.grid(row=0, column=0, padx=(0, 3), sticky="ew")
        self.btn_stop = ctk.CTkButton(btn_row, text="⏸  Pausar",
                                      font=("Outfit", 12),
                                      fg_color=CARD2, hover_color=BORDER,
                                      state="disabled", command=self._stop)
        self.btn_stop.grid(row=0, column=1, padx=(3, 0), sticky="ew")

        ivf = ctk.CTkFrame(sb, fg_color="transparent")
        ivf.pack(fill="x", padx=14, pady=(0, 4))
        ivf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ivf, text="Intervalo", font=("Outfit", 10),
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.iv_var = ctk.StringVar(value="2 s")
        ctk.CTkOptionMenu(ivf, variable=self.iv_var, values=list(POLL_OPTIONS.keys()),
                          width=80, height=26, fg_color=CARD2, button_color=CARD2,
                          font=("Outfit", 10),
                          command=lambda v: setattr(self, "_poll_iv", POLL_OPTIONS[v])
                          ).grid(row=0, column=1, sticky="e")

        sc = ctk.CTkFrame(sb, fg_color=CARD2, corner_radius=8)
        sc.pack(fill="x", padx=14, pady=(0, 4))
        self.sess_lbl = {}
        for k, d in [("dur", "Duración"), ("n", "Muestras")]:
            self.sess_lbl[k] = info_row(sc, d)

        # ── SECCIÓN: EXPORTACIÓN ────────────────────────────────────────────
        section_label(sb, "DATOS")
        self.btn_exp = ctk.CTkButton(sb, text="⬇  Exportar CSV",
                                     font=("Outfit", 11),
                                     fg_color=CARD2, hover_color=BORDER,
                                     state="disabled", command=self._export)
        self.btn_exp.pack(fill="x", padx=14, pady=(0, 4))
        self.btn_clr = ctk.CTkButton(sb, text="🗑  Limpiar datos",
                                     font=("Outfit", 11),
                                     fg_color="#3d1a1a", hover_color="#5a2020",
                                     text_color="#ff6b6b",
                                     state="disabled", command=self._clear)
        self.btn_clr.pack(fill="x", padx=14, pady=(0, 16))

    def _live_panel(self):
        """Columna central — gauges en tiempo real + estadísticas de sesión."""
        lp = ctk.CTkFrame(self, width=300, fg_color="#0b1120", corner_radius=0)
        lp.grid(row=0, column=1, sticky="nsew", padx=(1, 1))
        lp.grid_propagate(False)
        lp.grid_columnconfigure(0, weight=1)
        lp.grid_rowconfigure(5, weight=1)  # spacer

        def panel_title(parent, text, icon=""):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", padx=14, pady=(14, 4))
            ctk.CTkFrame(f, height=1, fg_color=BORDER).pack(fill="x", pady=(0, 5))
            row = ctk.CTkFrame(f, fg_color="transparent")
            row.pack(fill="x")
            if icon:
                ctk.CTkLabel(row, text=icon, font=("Segoe UI", 11),
                             text_color=MUTED).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(row, text=text, font=("Outfit", 8, "bold"),
                         text_color=MUTED).pack(side="left")

        # ── GAUGE CPM ──────────────────────────────────────────────────────
        panel_title(lp, "TASA DE CONTEO", "📡")
        cpm_card = ctk.CTkFrame(lp, fg_color=CARD, corner_radius=10)
        cpm_card.pack(fill="x", padx=14, pady=(0, 4))
        self.cpm_gauge = ArcGauge(cpm_card, max_val=1000, unit="CPM",
                                  label="Counts Per Minute", width=220, height=170)
        self.cpm_gauge.pack(fill="x", padx=6, pady=(8, 0))
        # Valor numérico grande + nivel
        cpm_val_row = ctk.CTkFrame(cpm_card, fg_color="transparent")
        cpm_val_row.pack(fill="x", padx=12, pady=(0, 10))
        self.cpm_big_lbl = ctk.CTkLabel(cpm_val_row, text="—",
                                        font=("JetBrains Mono", 22, "bold"),
                                        text_color=GREEN)
        self.cpm_big_lbl.pack(side="left")
        self.cpm_lv = ctk.CTkLabel(cpm_val_row, text="Sin datos",
                                    font=("Outfit", 10), text_color=MUTED)
        self.cpm_lv.pack(side="right")

        # ── GAUGE DOSIS ───────────────────────────────────────────────────
        panel_title(lp, "TASA DE DOSIS", "☢")
        dose_card = ctk.CTkFrame(lp, fg_color=CARD, corner_radius=10)
        dose_card.pack(fill="x", padx=14, pady=(0, 4))
        self.dose_gauge = ArcGauge(dose_card, max_val=10, unit="µSv/h",
                                   label="Microsievert / hora", width=220, height=170)
        self.dose_gauge.pack(fill="x", padx=6, pady=(8, 0))
        dose_val_row = ctk.CTkFrame(dose_card, fg_color="transparent")
        dose_val_row.pack(fill="x", padx=12, pady=(0, 10))
        self.dose_big_lbl = ctk.CTkLabel(dose_val_row, text="— µSv/h",
                                         font=("JetBrains Mono", 14, "bold"),
                                         text_color=CYAN)
        self.dose_big_lbl.pack(side="left")
        self.dose_lbl = ctk.CTkLabel(dose_val_row, text="Acum: — µSv",
                                     font=("Outfit", 9), text_color=MUTED)
        self.dose_lbl.pack(side="right")

        # ── ESTADÍSTICAS ──────────────────────────────────────────────────
        panel_title(lp, "ESTADÍSTICAS DE SESIÓN", "📊")
        stats_card = ctk.CTkFrame(lp, fg_color=CARD, corner_radius=10)
        stats_card.pack(fill="x", padx=14, pady=(0, 4))
        self.stat_lbl = {}
        stats_def = [
            ("avg",      "CPM Promedio",        TEXT,   "—"),
            ("max",      "CPM Máximo",           RED,    "—"),
            ("dose_acc", "Dosis Acumulada",      CYAN,   "— µSv"),
            ("dose_yr",  "Proyección Anual",     ORANGE, "— mSv/y"),
            ("sigma",    "Incertidumbre ±σ",     TEXT,   "—"),
            ("pulses",   "Pulsos Totales",       MUTED,  "—"),
        ]
        for k, d, c, default in stats_def:
            f = ctk.CTkFrame(stats_card, fg_color="transparent")
            f.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(f, text=d, font=("Outfit", 9),
                         text_color=MUTED).pack(side="left", padx=(2, 0))
            v = ctk.CTkLabel(f, text=default,
                             font=("JetBrains Mono", 10, "bold"), text_color=c)
            v.pack(side="right", padx=(0, 2))
            self.stat_lbl[k] = v
        # spacer
        ctk.CTkFrame(stats_card, height=4, fg_color="transparent").pack()

    def _main_area(self):
        """Columna derecha — tabview de análisis ocupa todo el espacio."""
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=2, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=4)   # tabview principal
        main.grid_rowconfigure(1, weight=1)   # log de datos

        self.tabview = ctk.CTkTabview(main, fg_color=CARD, corner_radius=12,
                                      segmented_button_selected_color="#1f6feb",
                                      segmented_button_selected_hover_color="#388bfd",
                                      segmented_button_unselected_color=CARD2,
                                      text_color=TEXT)
        self.tabview.grid(row=0, column=0, padx=(4, 10), pady=(10, 4), sticky="nsew")

        self.tabview.add("📈 Tendencia")
        self.tabview.add("📊 Poisson")
        self.tabview.add("⏳ Decaimiento")
        self.tabview.add("⚛ Física")
        self.tabview.add("🌟 Espectro")
        self.tabview.add("💾 Datalog")

        tab_sma     = self.tabview.tab("📈 Tendencia")
        tab_poisson = self.tabview.tab("📊 Poisson")
        tab_decay   = self.tabview.tab("⏳ Decaimiento")
        tab_phys    = self.tabview.tab("⚛ Física")
        tab_spec    = self.tabview.tab("🌟 Espectro")
        tab_flash   = self.tabview.tab("💾 Datalog")

        # --- Gráfico de tendencia (Tab 1) ---
        self.fig = Figure(figsize=(1,1), facecolor=CARD)
        self.ax  = self.fig.add_subplot(111)
        self._style_chart()
        self.chart_canvas = FigureCanvasTkAgg(self.fig, master=tab_sma)
        self.chart_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(4,10))

        # --- Gráfico de Poisson con selector (Tab 2) ---
        tab_poisson.grid_columnconfigure(0, weight=3)
        tab_poisson.grid_columnconfigure(1, weight=1)
        tab_poisson.grid_rowconfigure(1, weight=1)

        pois_ctrl = ctk.CTkFrame(tab_poisson, fg_color="transparent", height=32)
        pois_ctrl.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(pois_ctrl, text="Modo de Visualización:", font=("Outfit", 11), text_color=MUTED).pack(side="left", padx=5)
        self.poisson_mode_menu = ctk.CTkOptionMenu(pois_ctrl, variable=self.poisson_mode_var,
                          values=["Discreto (Intervalo)", "Continuo (CPM)"],
                          width=165, height=24, fg_color=CARD2, button_color=CARD2,
                          font=("Outfit", 11), command=lambda _: self._update_hist_chart()
                          )
        self.poisson_mode_menu.pack(side="left", padx=10)

        self.fig_hist = Figure(figsize=(1,1), facecolor=CARD)
        self.ax_hist  = self.fig_hist.add_subplot(111)
        self._style_hist_chart()
        self.hist_canvas = FigureCanvasTkAgg(self.fig_hist, master=tab_poisson)
        self.hist_canvas.get_tk_widget().grid(row=1, column=0, padx=10, pady=(4,10), sticky="nsew")

        self.pois_chi_frame = ctk.CTkScrollableFrame(tab_poisson, fg_color=CARD2, corner_radius=8, label_text="Prueba Chi-Cuadrado (χ²)", label_font=("Outfit", 12, "bold"))
        self.pois_chi_frame.grid(row=1, column=1, padx=(0,10), pady=(4,10), sticky="nsew")
        self.pois_chi_lbl = ctk.CTkLabel(self.pois_chi_frame, text="Esperando acumular más muestras (mín. 10)...", font=("Outfit", 11), justify="left", wraplength=220, text_color=MUTED)
        self.pois_chi_lbl.pack(fill="both", expand=True, padx=8, pady=8)


        # --- Tab 3: Decaimiento Radiactivo ---
        tab_decay.grid_columnconfigure(0, weight=1)
        tab_decay.grid_columnconfigure(1, weight=3)
        tab_decay.grid_rowconfigure(0, weight=1)
        
        dec_left = ctk.CTkFrame(tab_decay, fg_color=CARD2, corner_radius=8, width=280)
        dec_left.grid(row=0, column=0, padx=(10,5), pady=10, sticky="nsew")
        dec_left.grid_propagate(False)
        
        dec_right = ctk.CTkFrame(tab_decay, fg_color=CARD2, corner_radius=8)
        dec_right.grid(row=0, column=1, padx=(5,10), pady=10, sticky="nsew")
        
        ctk.CTkLabel(dec_left, text="Ajuste de Decaimiento", font=("Outfit", 12, "bold"), text_color=TEXT).pack(pady=(12, 6), padx=12, anchor="w")
        
        r_frame = ctk.CTkFrame(dec_left, fg_color="transparent")
        r_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(r_frame, text="Rango:", font=("Outfit", 10), text_color=MUTED).pack(side="left")
        self.decay_range_menu = ctk.CTkOptionMenu(r_frame, variable=self.decay_range_var,
                                                  values=["Desde el Máximo", "Toda la sesión", "Últimos 2 min", "Últimos 5 min", "Últimos 10 min"],
                                                  width=130, height=24, fg_color=CARD, button_color=CARD, font=("Outfit", 10))
        self.decay_range_menu.pack(side="right")
        
        bg_frame = ctk.CTkFrame(dec_left, fg_color="transparent")
        bg_frame.pack(fill="x", padx=12, pady=4)
        self.decay_bg_check = ctk.CTkCheckBox(bg_frame, text="Fijar Fondo (CPM):", font=("Outfit", 10),
                                              variable=self.decay_bg_check_var, text_color=MUTED,
                                              checkbox_width=16, checkbox_height=16,
                                              command=self._toggle_decay_bg_input)
        self.decay_bg_check.pack(side="left")
        self.decay_bg_entry = ctk.CTkEntry(bg_frame, textvariable=self.decay_bg_val_var,
                                           width=60, height=22, font=("JetBrains Mono", 10),
                                           state="disabled", border_color=BORDER, fg_color=CARD)
        self.decay_bg_entry.pack(side="right")
        
        self.btn_fit = ctk.CTkButton(dec_left, text="🧪 Ejecutar Ajuste", font=("Outfit", 11, "bold"),
                                     fg_color="#1f6feb", hover_color="#388bfd",
                                     command=self._run_decay_fit)
        self.btn_fit.pack(fill="x", padx=12, pady=10)
        
        res_frame = ctk.CTkScrollableFrame(dec_left, fg_color=CARD, corner_radius=6, height=160)
        res_frame.pack(fill="both", expand=True, padx=12, pady=(0,12))
        
        self.dec_res_lbls = {}
        for k, name, color in [
            ("t_half", "Vida Media (T_1/2)", CYAN),
            ("lambda", "Const. Decaimiento (λ)", TEXT),
            ("n0", "Actividad Inicial (N0)", TEXT),
            ("bg", "Fondo (B)", MUTED),
            ("r2", "Coef. Det. (R²)", GREEN),
            ("chi2", "Chi² Reducido (χ²_red)", YELLOW),
            ("isotope", "Identificación", GREEN)
        ]:
            rf = ctk.CTkFrame(res_frame, fg_color="transparent")
            rf.pack(fill="x", pady=2)
            ctk.CTkLabel(rf, text=name, font=("Outfit", 9), text_color=MUTED).pack(side="left", padx=4)
            v = ctk.CTkLabel(rf, text="—", font=("JetBrains Mono", 10, "bold"), text_color=color)
            v.pack(side="right", padx=4)
            self.dec_res_lbls[k] = v

        # Gráfico de decaimiento en dec_right
        self.fig_decay = Figure(figsize=(1,1), facecolor=CARD)
        self.ax_decay = self.fig_decay.add_subplot(111)
        self._style_decay_chart()
        self.decay_canvas = FigureCanvasTkAgg(self.fig_decay, master=dec_right)
        self.decay_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
            
        # --- Tab 4: Herramientas de Física (Rediseño con Sub-Tabs) ---
        self.phys_tabview = ctk.CTkTabview(tab_phys, fg_color="transparent",
                                           segmented_button_selected_color="#1f6feb",
                                           segmented_button_selected_hover_color="#388bfd",
                                           segmented_button_unselected_color=CARD,
                                           text_color=TEXT)
        self.phys_tabview.pack(fill="both", expand=True, padx=2, pady=2)
        
        self.phys_tabview.add("Tiempo Muerto y Calibración")
        self.phys_tabview.add("Estimador de Actividad")
        self.phys_tabview.add("Atenuación de Blindaje")
        self.phys_tabview.add("Diagnóstico de Alta Tensión (HV)")
        
        sub_dt = self.phys_tabview.tab("Tiempo Muerto y Calibración")
        sub_act = self.phys_tabview.tab("Estimador de Actividad")
        sub_att = self.phys_tabview.tab("Atenuación de Blindaje")
        sub_hv = self.phys_tabview.tab("Diagnóstico de Alta Tensión (HV)")

        # ── SUB-TAB 1: Tiempo Muerto y Calibración ───────────────────────────
        sub_dt.grid_columnconfigure((0, 1), weight=1)
        sub_dt.grid_rowconfigure(0, weight=1)

        # Izquierda: Compensación de Tiempo Muerto (Monitor Live)
        dt_live_frame = ctk.CTkFrame(sub_dt, fg_color=CARD2, corner_radius=10)
        dt_live_frame.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        
        ctk.CTkLabel(dt_live_frame, text="⚡ Compensación de Tiempo Muerto", font=("Outfit", 12, "bold"), text_color=TEXT).pack(pady=(12, 8), padx=12, anchor="w")
        
        row_preset = ctk.CTkFrame(dt_live_frame, fg_color="transparent")
        row_preset.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(row_preset, text="Modelo de Tubo:", font=("Outfit", 10), text_color=MUTED).pack(side="left")
        self.dt_preset_menu = ctk.CTkOptionMenu(row_preset, variable=self.dt_preset_var,
                                                values=list(science_utils.TUBE_PRESETS.keys()),
                                                width=100, height=24, fg_color=CARD, button_color=CARD, font=("Outfit", 10),
                                                command=self._on_dt_preset_change)
        self.dt_preset_menu.pack(side="right")
        
        row_dt = ctk.CTkFrame(dt_live_frame, fg_color="transparent")
        row_dt.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(row_dt, text="Tiempo Muerto (µs):", font=("Outfit", 10), text_color=MUTED).pack(side="left")
        self.dt_entry = ctk.CTkEntry(row_dt, textvariable=self.dt_val_var, width=60, height=22, font=("JetBrains Mono", 10), border_color=BORDER, fg_color=CARD)
        self.dt_entry.pack(side="right")
        self.dt_val_var.trace_add("write", lambda *args: self._update_physics_calculations())
        
        ctk.CTkFrame(dt_live_frame, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=8)
        
        self.dt_out_lbls = {}
        for k, name, color in [
            ("measured", "CPM Medido:", TEXT),
            ("corrected", "CPM Corregido:", CYAN),
            ("loss", "Pérdida por Coincidencia:", RED),
            ("sat", "Límite Sat. Teórico:", YELLOW)
        ]:
            rf = ctk.CTkFrame(dt_live_frame, fg_color="transparent")
            rf.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(rf, text=name, font=("Outfit", 10), text_color=MUTED).pack(side="left")
            v = ctk.CTkLabel(rf, text="—", font=("JetBrains Mono", 11, "bold"), text_color=color)
            v.pack(side="right")
            self.dt_out_lbls[k] = v

        # Derecha: Calibrador de dos fuentes
        dt_cal_frame = ctk.CTkFrame(sub_dt, fg_color=CARD2, corner_radius=10)
        dt_cal_frame.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        
        ctk.CTkLabel(dt_cal_frame, text="🧪 Calibración del Tiempo de Resolución", font=("Outfit", 12, "bold"), text_color=TEXT).pack(pady=(12, 6), padx=12, anchor="w")
        ctk.CTkLabel(dt_cal_frame, text="Método de las Dos Fuentes (Modelo No Paralizable)", font=("Outfit", 9), text_color=MUTED).pack(padx=12, anchor="w")

        # Campos de entrada con botón de captura rápida
        for k, name, var in [
            ("bg", "Fondo Rb (CPM):", self.cal_bg_var),
            ("r1", "Fuente 1 R1 (CPM):", self.cal_r1_var),
            ("r2", "Fuente 2 R2 (CPM):", self.cal_r2_var),
            ("r12", "Ambas R12 (CPM):", self.cal_r12_var)
        ]:
            row = ctk.CTkFrame(dt_cal_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(row, text=name, font=("Outfit", 10), text_color=TEXT).pack(side="left")
            
            entry = ctk.CTkEntry(row, textvariable=var, width=60, height=22, font=("JetBrains Mono", 10), border_color=BORDER, fg_color=CARD)
            entry.pack(side="right", padx=(5, 0))
            
            # Botón capturar en vivo
            btn = ctk.CTkButton(row, text="Capturar en vivo", font=("Outfit", 9), width=85, height=20, fg_color=CARD, hover_color=BORDER)
            btn.pack(side="right")
            # Configurar comando closure
            btn.configure(command=lambda s=name[:-7], v=var, b=btn: self._start_two_source_capture(s, v, b))

        # Progreso y Estado
        self.cal_progress_bar = ctk.CTkProgressBar(dt_cal_frame, height=5, fg_color=BORDER, progress_color=CYAN, variable=self.cal_progress_var)
        self.cal_progress_bar.pack(fill="x", padx=12, pady=(10, 4))
        
        self.cal_lbl_status = ctk.CTkLabel(dt_cal_frame, textvariable=self.cal_status_var, font=("Outfit", 10), text_color=YELLOW, justify="left")
        self.cal_lbl_status.pack(pady=4, padx=12, anchor="w")
        
        btn_calc = ctk.CTkButton(dt_cal_frame, text="🧪 Calcular Tiempo Muerto (τ)", font=("Outfit", 11, "bold"), fg_color="#1f6feb", hover_color="#388bfd", command=self._calculate_two_source_dead_time)
        btn_calc.pack(fill="x", padx=12, pady=4)
        
        self.btn_apply_cal_dt = ctk.CTkButton(dt_cal_frame, text="💾 Aplicar al Monitor Live", font=("Outfit", 11, "bold"), fg_color="#238636", hover_color="#2ea043", state="disabled", command=self._apply_calibrated_dead_time)
        self.btn_apply_cal_dt.pack(fill="x", padx=12, pady=4)


        # ── SUB-TAB 2: Estimación de Actividad ───────────────────────────────
        sub_act.grid_columnconfigure((0, 1), weight=1)
        sub_act.grid_rowconfigure(0, weight=1)
        
        act_left = ctk.CTkFrame(sub_act, fg_color=CARD2, corner_radius=10)
        act_left.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        
        ctk.CTkLabel(act_left, text="🔮 Estimador de Actividad Absoluta", font=("Outfit", 12, "bold"), text_color=TEXT).pack(pady=(12, 8), padx=12, anchor="w")
        
        for name, var, desc in [
            ("Distancia a Fuente (cm):", self.act_dist_var, "Distancia de la fuente puntual al detector"),
            ("Geometría del Tubo:", self.act_tube_var, "Selector de dimensiones geométricas"),
            ("Área de la Ventana (cm²):", self.act_area_var, "Área de detección geométrica"),
            ("Eficiencia del Tubo (%):", self.act_eff_var, "Eficiencia intrínseca del detector para la radiación dada")
        ]:
            row = ctk.CTkFrame(act_left, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(row, text=name, font=("Outfit", 10), text_color=MUTED).pack(side="left")
            if var == self.act_tube_var:
                menu = ctk.CTkOptionMenu(row, variable=var, values=list(science_utils.TUBE_PRESETS.keys()), width=100, height=24, fg_color=CARD, button_color=CARD, font=("Outfit", 10), command=self._on_act_tube_change)
                menu.pack(side="right")
            else:
                entry = ctk.CTkEntry(row, textvariable=var, width=60, height=22, font=("JetBrains Mono", 10), border_color=BORDER, fg_color=CARD)
                entry.pack(side="right")
                if var == self.act_area_var:
                    self.act_area_entry = entry
                var.trace_add("write", lambda *args: self._update_physics_calculations())

        ctk.CTkFrame(act_left, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=8)
        
        self.act_out_lbls = {}
        for k, name, color in [
            ("solid_angle", "Ángulo Sólido (sr):", TEXT),
            ("act_bq", "Actividad Estimada (Bq):", CYAN),
            ("act_uci", "Actividad Estimada (µCi):", GREEN)
        ]:
            rf = ctk.CTkFrame(act_left, fg_color="transparent")
            rf.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(rf, text=name, font=("Outfit", 10), text_color=MUTED).pack(side="left")
            v = ctk.CTkLabel(rf, text="—", font=("JetBrains Mono", 11, "bold"), text_color=color)
            v.pack(side="right")
            self.act_out_lbls[k] = v

        act_right = ctk.CTkFrame(sub_act, fg_color=CARD2, corner_radius=10)
        act_right.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(act_right, text="📖 Teoría Física y Geometría", font=("Outfit", 11, "bold"), text_color=TEXT).pack(pady=(12, 6), padx=12, anchor="w")
        
        th_lbl = ctk.CTkLabel(act_right, text=(
            "La tasa de conteo neta (CPM - Fondo) observada por un detector es proporcional a la actividad absoluta de la fuente corregida por factores geométricos e intrínsecos:\n\n"
            "1. Ángulo Sólido Fraccional (Ω):\n"
            "Representa la fracción de fotones emitidos isotrópicamente que intersectan el volumen del detector. Para una ventana circular a distancia d:\n"
            "   Ω ≈ Área_Ventana / (4 * π * d²)\n\n"
            "2. Eficiencia Intrínseca (ε):\n"
            "Es la probabilidad de que un fotón que incide sobre la ventana del tubo sea detectado y genere una avalancha.\n\n"
            "Fórmula de Actividad:\n"
            "   Actividad (Bq) = Net_CPS / (Ω * ε_frac)"
        ), font=("Outfit", 9.5), text_color=MUTED, justify="left", wraplength=420)
        th_lbl.pack(padx=12, pady=6, fill="both", expand=True)


        # ── SUB-TAB 3: Atenuación de Blindaje (Multi-espesor) ────────────────
        sub_att.grid_columnconfigure(0, weight=1)
        sub_att.grid_columnconfigure(1, weight=1)
        sub_att.grid_columnconfigure(2, weight=2)
        sub_att.grid_rowconfigure(0, weight=1)
        
        att_left = ctk.CTkFrame(sub_att, fg_color=CARD2, corner_radius=10)
        att_left.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        
        ctk.CTkLabel(att_left, text="🛡️ Atenuación y Curva Multi-espesor", font=("Outfit", 11, "bold"), text_color=TEXT).pack(pady=(10, 4), padx=10, anchor="w")

        # Selectores principales de blindaje
        sh_sel_f = ctk.CTkFrame(att_left, fg_color="transparent")
        sh_sel_f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(sh_sel_f, text="Material:", font=("Outfit", 9), text_color=MUTED).pack(side="left")
        self.sh_mat_menu = ctk.CTkOptionMenu(sh_sel_f, variable=self.sh_mat_var, values=list(science_utils.SHIELDING_DATA.keys()), width=80, height=20, font=("Outfit", 9), dropdown_font=("Outfit", 9), command=self._on_shield_change)
        self.sh_mat_menu.pack(side="right")

        sh_nrg_f = ctk.CTkFrame(att_left, fg_color="transparent")
        sh_nrg_f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(sh_nrg_f, text="Energía:", font=("Outfit", 9), text_color=MUTED).pack(side="left")
        self.sh_nrg_menu = ctk.CTkOptionMenu(sh_nrg_f, variable=self.sh_nrg_var, values=["Cs-137 (662 keV)", "Co-60 (1.25 MeV)", "Am-241 (59 keV)"], width=130, height=20, font=("Outfit", 9), dropdown_font=("Outfit", 9), command=self._on_shield_change)
        self.sh_nrg_menu.pack(side="right")

        ctk.CTkFrame(att_left, height=1, fg_color=BORDER).pack(fill="x", padx=10, pady=4)

        # Entrada de puntos experimentales
        ctk.CTkLabel(att_left, text="Puntos de Calibración de Espesor", font=("Outfit", 10, "bold"), text_color=TEXT).pack(pady=2, padx=10, anchor="w")
        
        pt_in_f = ctk.CTkFrame(att_left, fg_color="transparent")
        pt_in_f.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(pt_in_f, text="x (cm):", font=("Outfit", 9), text_color=MUTED).pack(side="left")
        self.sh_x_entry = ctk.CTkEntry(pt_in_f, textvariable=self.sh_point_thick_var, width=50, height=20, font=("JetBrains Mono", 9))
        self.sh_x_entry.pack(side="left", padx=2)
        
        ctk.CTkLabel(pt_in_f, text="CPM:", font=("Outfit", 9), text_color=MUTED).pack(side="left", padx=(4, 0))
        self.sh_y_entry = ctk.CTkEntry(pt_in_f, textvariable=self.sh_point_cpm_var, width=65, height=20, font=("JetBrains Mono", 9))
        self.sh_y_entry.pack(side="left", padx=2)
        
        btn_add_pt = ctk.CTkButton(pt_in_f, text="+", font=("Outfit", 11, "bold"), width=24, height=20, fg_color="#238636", hover_color="#2ea043", command=self._add_shielding_point)
        btn_add_pt.pack(side="left", padx=2)
        btn_del_pt = ctk.CTkButton(pt_in_f, text="-", font=("Outfit", 11, "bold"), width=24, height=20, fg_color="#6e1818", hover_color="#8b2020", command=self._delete_shielding_point)
        btn_del_pt.pack(side="left", padx=2)

        # Tabla de puntos experimentales
        self.sh_tree_frame = ctk.CTkFrame(att_left, fg_color="transparent", height=90)
        self.sh_tree_frame.pack(fill="x", padx=10, pady=2)
        self.sh_tree_frame.pack_propagate(False)
        
        self.sh_tree = ttk.Treeview(self.sh_tree_frame, columns=("thick", "cpm"), show="headings", style="Custom.Treeview")
        self.sh_tree.heading("thick", text="Espesor (cm)")
        self.sh_tree.heading("cpm", text="CPM")
        self.sh_tree.column("thick", width=100, anchor="center")
        self.sh_tree.column("cpm", width=120, anchor="center")
        self.sh_tree.pack(fill="both", expand=True)
        
        self.sh_tree.tag_configure("even", background=CARD)
        self.sh_tree.tag_configure("odd", background=CARD2)

        btn_fit_sh = ctk.CTkButton(att_left, text="📊 Ajustar Exponencial", font=("Outfit", 10, "bold"), fg_color="#1f6feb", hover_color="#388bfd", command=self._run_shielding_fit)
        btn_fit_sh.pack(fill="x", padx=10, pady=4)

        # Resultados del ajuste
        self.sh_res_scroll = ctk.CTkScrollableFrame(att_left, fg_color=CARD, corner_radius=6, height=130)
        self.sh_res_scroll.pack(fill="both", expand=True, padx=10, pady=(2, 6))

        self.sh_res_lbls = {}
        for k, label_text, clr in [
            ("mu", "Coef. Lineal (μ):", TEXT),
            ("hvl", "HVL exp (cm):", CYAN),
            ("tvl", "TVL exp (cm):", TEXT),
            ("i0", "Intensidad I0 (CPM):", TEXT),
            ("r2", "R² del ajuste:", GREEN),
            ("isotope", "Isótopo propuesto:", GREEN)
        ]:
            rf = ctk.CTkFrame(self.sh_res_scroll, fg_color="transparent")
            rf.pack(fill="x", pady=1)
            ctk.CTkLabel(rf, text=label_text, font=("Outfit", 9), text_color=MUTED).pack(side="left")
            v = ctk.CTkLabel(rf, text="—", font=("JetBrains Mono", 10, "bold"), text_color=clr)
            v.pack(side="right"); self.sh_res_lbls[k] = v

        # Centro: Calculadora de Blindaje Único y ID
        att_mid = ctk.CTkFrame(sub_att, fg_color=CARD2, corner_radius=10)
        att_mid.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        
        ctk.CTkLabel(att_mid, text="🛡️ Calculadora de Blindaje Único", font=("Outfit", 11, "bold"), text_color=TEXT).pack(pady=(10, 4), padx=10, anchor="w")
        
        # Entrada de Espesor Único
        thick_row = ctk.CTkFrame(att_mid, fg_color="transparent")
        thick_row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(thick_row, text="Espesor del Blindaje (cm):", font=("Outfit", 10), text_color=MUTED).pack(side="left")
        self.sh_thick_entry = ctk.CTkEntry(thick_row, textvariable=self.sh_thick_var, width=60, height=22, font=("JetBrains Mono", 10), border_color=BORDER, fg_color=CARD)
        self.sh_thick_entry.pack(side="right")
        self.sh_thick_var.trace_add("write", lambda *args: self._update_physics_calculations())
        
        ctk.CTkFrame(att_mid, height=1, fg_color=BORDER).pack(fill="x", padx=10, pady=6)
        
        # Resultados de cálculo de blindaje único
        self.sh_out_lbls = {}
        for k, name, color in [
            ("hvl", "HVL Teórico:", TEXT),
            ("tvl", "TVL Teórico:", TEXT),
            ("trans", "Transmisión (I/I₀):", CYAN),
            ("att", "Atenuación (%):", GREEN),
            ("shield_dose", "Dosis Blindada:", YELLOW)
        ]:
            rf = ctk.CTkFrame(att_mid, fg_color="transparent")
            rf.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(rf, text=name, font=("Outfit", 10), text_color=MUTED).pack(side="left")
            v = ctk.CTkLabel(rf, text="—", font=("JetBrains Mono", 11, "bold"), text_color=color)
            v.pack(side="right")
            self.sh_out_lbls[k] = v
            
        ctk.CTkFrame(att_mid, height=1, fg_color=BORDER).pack(fill="x", padx=10, pady=6)
        
        # Identificación de isótopo
        ctk.CTkLabel(att_mid, text="🆔 Identificación de Isótopo (Atenuación)", font=("Outfit", 11, "bold"), text_color=TEXT).pack(pady=4, padx=10, anchor="w")
        
        for name, var in [
            ("Intensidad Inicial I₀ (CPM):", self.sh_i0_var),
            ("Intensidad Blindada I (CPM):", self.sh_i_var)
        ]:
            rf = ctk.CTkFrame(att_mid, fg_color="transparent")
            rf.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(rf, text=name, font=("Outfit", 10), text_color=MUTED).pack(side="left")
            entry = ctk.CTkEntry(rf, textvariable=var, width=60, height=22, font=("JetBrains Mono", 10), border_color=BORDER, fg_color=CARD)
            entry.pack(side="right")
            var.trace_add("write", lambda *args: self._update_physics_calculations())
            
        rf_iso = ctk.CTkFrame(att_mid, fg_color=CARD, corner_radius=6)
        rf_iso.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(rf_iso, text="Isótopo Propuesto:", font=("Outfit", 10), text_color=MUTED).pack(side="left", padx=10, pady=8)
        self.sh_iso_lbl = ctk.CTkLabel(rf_iso, text="—", font=("Outfit", 11, "bold"), text_color=GREEN)
        self.sh_iso_lbl.pack(side="right", padx=10)

        # Derecha: Gráfico de Atenuación
        att_right = ctk.CTkFrame(sub_att, fg_color=CARD2, corner_radius=10)
        att_right.grid(row=0, column=2, padx=8, pady=8, sticky="nsew")
        
        self.fig_phys = Figure(figsize=(1,1), facecolor=CARD)
        self.ax_phys = self.fig_phys.add_subplot(111)
        self._style_phys_chart()
        self.phys_canvas = FigureCanvasTkAgg(self.fig_phys, master=att_right)
        self.phys_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        # ── SUB-TAB 4: Diagnóstico de Alta Tensión (HV) ──────────────────────
        sub_hv.grid_columnconfigure((0, 1), weight=1)
        sub_hv.grid_rowconfigure(0, weight=1)
        
        hv_left = ctk.CTkFrame(sub_hv, fg_color=CARD2, corner_radius=10)
        hv_left.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        
        ctk.CTkLabel(hv_left, text="🔄 Telemetría de Alta Tensión", font=("Outfit", 12, "bold"), text_color=TEXT).pack(pady=(12, 8), padx=12, anchor="w")
        ctk.CTkLabel(hv_left, text="Lectura de oscilación de la placa base:", font=("Outfit", 9), text_color=MUTED).pack(padx=12, anchor="w")

        for name, var in [
            ("Frecuencia del Oscilador HV:", self.hv_freq_var),
            ("Ciclo de Trabajo PWM (Duty):", self.hv_duty_var)
        ]:
            row = ctk.CTkFrame(hv_left, fg_color=CARD, corner_radius=6)
            row.pack(fill="x", padx=12, pady=6)
            ctk.CTkLabel(row, text=name, font=("Outfit", 10), text_color=MUTED).pack(side="left", padx=10, pady=8)
            v = ctk.CTkLabel(row, textvariable=var, font=("JetBrains Mono", 12, "bold"), text_color=CYAN)
            v.pack(side="right", padx=10)

        btn_read_hv = ctk.CTkButton(hv_left, text="🔄 Leer Valores del GC-01", font=("Outfit", 11, "bold"), fg_color=CARD, hover_color=BORDER, command=self._refresh_hv_telemetry)
        btn_read_hv.pack(fill="x", padx=12, pady=12)

        hv_right = ctk.CTkFrame(sub_hv, fg_color=CARD2, corner_radius=10)
        hv_right.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        
        ctk.CTkLabel(hv_right, text="⚙️ Ajuste de Frecuencia de HV", font=("Outfit", 12, "bold"), text_color=TEXT).pack(pady=(12, 6), padx=12, anchor="w")
        
        warn_box = ctk.CTkFrame(hv_right, fg_color="#3d1a1a", border_width=1, border_color="#5a2020", corner_radius=6)
        warn_box.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(warn_box, text="⚠️ ADVERTENCIA DE SEGURIDAD:\nModificar la frecuencia de conmutación influye directamente en el transformador elevador de la placa y en la tensión del tubo Geiger. Un valor inadecuado puede dañar el tubo GM (J305/M4011 toleran ~400V) o sobrecalentar los MOSFET. Proceda bajo su responsabilidad.", font=("Outfit", 8.5), text_color="#ff6b6b", justify="left", wraplength=380).pack(padx=10, pady=10)
        
        set_row = ctk.CTkFrame(hv_right, fg_color="transparent")
        set_row.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(set_row, text="Frecuencia PWM (Hz):", font=("Outfit", 10), text_color=TEXT).pack(side="left")
        self.hv_entry = ctk.CTkEntry(set_row, textvariable=self.hv_set_freq_var, width=100, height=24, font=("JetBrains Mono", 10), border_color=BORDER, fg_color=CARD)
        self.hv_entry.pack(side="right")
        
        btn_set_hv = ctk.CTkButton(hv_right, text="💾 Aplicar Frecuencia (SET)", font=("Outfit", 11, "bold"), fg_color="#6e1818", hover_color="#8b2020", command=self._apply_hv_frequency)
        btn_set_hv.pack(fill="x", padx=12, pady=12)


        # ── PESTAÑA 6: Datalog de Flash ──────────────────────────────────────
        tab_flash.grid_columnconfigure(0, weight=1)
        tab_flash.grid_columnconfigure(1, weight=3)
        tab_flash.grid_rowconfigure(0, weight=1)

        # Panel izquierdo: Controles e historial
        flash_left = ctk.CTkFrame(tab_flash, fg_color=CARD2, corner_radius=8, width=280)
        flash_left.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        flash_left.grid_propagate(False)

        ctk.CTkLabel(flash_left, text="Datalog en Memoria Flash", font=("Outfit", 12, "bold"), text_color=TEXT).pack(pady=(12, 6), padx=12, anchor="w")
        
        flash_lbl_desc = ctk.CTkLabel(flash_left, text="Rad Pro guarda registros de radiación de manera autónoma cuando el equipo está encendido sin PC.", font=("Outfit", 9), text_color=MUTED, justify="left", wraplength=240)
        flash_lbl_desc.pack(padx=12, anchor="w")

        self.btn_download_flash = ctk.CTkButton(flash_left, text="📥 Descargar Datalog", font=("Outfit", 11, "bold"), fg_color="#1f6feb", hover_color="#388bfd", command=self._download_flash_datalog)
        self.btn_download_flash.pack(fill="x", padx=12, pady=(10, 4))
        
        btn_exp_flash = ctk.CTkButton(flash_left, text="📊 Exportar CSV de Sesión", font=("Outfit", 11), fg_color=CARD, hover_color=BORDER, command=self._export_flash_datalog)
        btn_exp_flash.pack(fill="x", padx=12, pady=2)
        
        btn_reset_flash = ctk.CTkButton(flash_left, text="🗑️ Borrar Memoria Flash", font=("Outfit", 11), fg_color="#3d1a1a", hover_color="#5a2020", text_color="#ff6b6b", command=self._clear_flash_datalog)
        btn_reset_flash.pack(fill="x", padx=12, pady=2)

        ctk.CTkFrame(flash_left, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(flash_left, text="Sesiones de Registro:", font=("Outfit", 10, "bold"), text_color=TEXT).pack(padx=12, anchor="w")

        self.flash_sess_frame = ctk.CTkFrame(flash_left, fg_color="transparent", height=180)
        self.flash_sess_frame.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        
        self.flash_sess_tree = ttk.Treeview(self.flash_sess_frame, columns=("id", "date", "pts"), show="headings", style="Custom.Treeview")
        self.flash_sess_tree.heading("id", text="ID")
        self.flash_sess_tree.heading("date", text="Fecha Inicio")
        self.flash_sess_tree.heading("pts", text="Muestras")
        self.flash_sess_tree.column("id", width=30, anchor="center")
        self.flash_sess_tree.column("date", width=130, anchor="center")
        self.flash_sess_tree.column("pts", width=65, anchor="center")
        self.flash_sess_tree.pack(fill="both", expand=True)
        self.flash_sess_tree.bind("<<TreeviewSelect>>", self._on_flash_session_selected)

        self.flash_sess_tree.tag_configure("even", background=CARD)
        self.flash_sess_tree.tag_configure("odd", background=CARD2)

        # Panel derecho: Gráfico y Tabla
        flash_right = ctk.CTkFrame(tab_flash, fg_color=CARD2, corner_radius=8)
        flash_right.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        flash_right.grid_columnconfigure(0, weight=1)
        flash_right.grid_rowconfigure(0, weight=3) # gráfico
        flash_right.grid_rowconfigure(1, weight=2) # tabla de registros

        # Gráfico superior
        self.fig_flash = Figure(figsize=(1,1), facecolor=CARD)
        self.ax_flash = self.fig_flash.add_subplot(111)
        self._style_flash_chart()
        self.flash_canvas = FigureCanvasTkAgg(self.fig_flash, master=flash_right)
        self.flash_canvas.get_tk_widget().grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Tabla inferior
        self.flash_table_frame = ctk.CTkFrame(flash_right, fg_color="transparent")
        self.flash_table_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
        flash_vsb = ttk.Scrollbar(self.flash_table_frame, orient="vertical")
        flash_vsb.pack(side="right", fill="y")
        
        self.flash_tree = ttk.Treeview(self.flash_table_frame, columns=("date", "cpm", "pulses", "interval", "delta"), show="headings", style="Custom.Treeview", yscrollcommand=flash_vsb.set)
        flash_vsb.config(command=self.flash_tree.yview)
        
        self.flash_tree.heading("date", text="Fecha/Hora Local")
        self.flash_tree.heading("cpm", text="CPM")
        self.flash_tree.heading("pulses", text="Pulsos Acum.")
        self.flash_tree.heading("interval", text="Intervalo dt (s)")
        self.flash_tree.heading("delta", text="Delta Pulsos")
        
        for c in ("date", "cpm", "pulses", "interval", "delta"):
            self.flash_tree.column(c, anchor="center", width=120)
            
        self.flash_tree.pack(fill="both", expand=True)
        self.flash_tree.tag_configure("even", background=CARD)
        self.flash_tree.tag_configure("odd", background=CARD2)


        # --- Tab 5: Espectroscopía Gamma (Simulación) ---
        tab_spec.grid_columnconfigure(0, weight=1)
        tab_spec.grid_columnconfigure(1, weight=3)
        tab_spec.grid_rowconfigure(0, weight=1)

        
        # Left side control panel
        spec_left = ctk.CTkFrame(tab_spec, fg_color=CARD2, corner_radius=8, width=280)
        spec_left.grid(row=0, column=0, padx=(10,5), pady=10, sticky="nsew")
        spec_left.grid_propagate(False)
        
        # Right side chart panel
        spec_right = ctk.CTkFrame(tab_spec, fg_color=CARD2, corner_radius=8)
        spec_right.grid(row=0, column=1, padx=(5,10), pady=10, sticky="nsew")
        
        # Title
        ctk.CTkLabel(spec_left, text="Espectroscopía Gamma", font=("Outfit", 12, "bold"), text_color=TEXT).pack(pady=(12, 6), padx=12, anchor="w")
        
        # Explanation disclaimer
        disc_frame = ctk.CTkFrame(spec_left, fg_color=CARD, corner_radius=6)
        disc_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(disc_frame, text="ℹ️ Nota Física: Los tubos GM no diferencian energías. Este panel simula el espectro obtenido con un detector de centelleo (NaI) o semiconductor (HPGe) real para fines comparativos.",
                     font=("Outfit", 9), text_color=MUTED, wraplength=230, justify="left").pack(padx=8, pady=8)
        
        # Isotope dropdown
        iso_row = ctk.CTkFrame(spec_left, fg_color="transparent")
        iso_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(iso_row, text="Isótopo:", font=("Outfit", 10), text_color=MUTED).pack(side="left")
        self.spec_iso_menu = ctk.CTkOptionMenu(iso_row, variable=self.spec_iso_var,
                                               values=["Cs-137", "Co-60", "Am-241", "Ba-137m", "Fondo Natural"],
                                               width=140, height=24, fg_color=CARD, button_color=CARD, font=("Outfit", 10),
                                               command=self._on_spec_change)
        self.spec_iso_menu.pack(side="right")
        
        # Detector preset dropdown
        det_row = ctk.CTkFrame(spec_left, fg_color="transparent")
        det_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(det_row, text="Detector:", font=("Outfit", 10), text_color=MUTED).pack(side="left")
        self.spec_det_menu = ctk.CTkOptionMenu(det_row, variable=self.spec_det_preset_var,
                                               values=["NaI(Tl) (Centellador estándar)", "HPGe (Alta resolución)", "BGO (Baja resolución)", "Personalizado"],
                                               width=140, height=24, fg_color=CARD, button_color=CARD, font=("Outfit", 10),
                                               command=self._on_spec_preset_change)
        self.spec_det_menu.pack(side="right")
        
        # FWHM Resolution slider
        res_row = ctk.CTkFrame(spec_left, fg_color="transparent")
        res_row.pack(fill="x", padx=12, pady=(8,4))
        ctk.CTkLabel(res_row, text="Resolución (FWHM @ 662 keV):", font=("Outfit", 10), text_color=MUTED).pack(anchor="w")
        
        self.res_lbl = ctk.CTkLabel(spec_left, text="7.0%", font=("JetBrains Mono", 12, "bold"), text_color=CYAN)
        self.res_lbl.pack(pady=2)
        
        self.spec_res_slider = ctk.CTkSlider(spec_left, from_=0.1, to=15.0, number_of_steps=149,
                                             variable=self.spec_res_var, height=16,
                                             command=self._on_spec_slider_move)
        self.spec_res_slider.pack(fill="x", padx=12, pady=4)
        
        # Matplotlib plot for spectrum (Right side)
        self.fig_spec = Figure(figsize=(1,1), facecolor=CARD)
        self.ax_spec = self.fig_spec.add_subplot(111)
        self._style_spec_chart()
        self.spec_canvas = FigureCanvasTkAgg(self.fig_spec, master=spec_right)
        self.spec_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)


        lf = ctk.CTkFrame(main, fg_color=CARD, corner_radius=12)
        lf.grid(row=1, column=0, padx=(4, 10), pady=(0, 10), sticky="nsew")
        lhdr = ctk.CTkFrame(lf, fg_color="transparent"); lhdr.pack(fill="x", padx=14, pady=(10,4))
        ctk.CTkLabel(lhdr, text="Registro de datos", font=("Outfit",13,"bold"), text_color=TEXT).pack(side="left")
        self.log_count_lbl = ctk.CTkLabel(lhdr, text="0 entradas",
                                           font=("Outfit",11), text_color=MUTED)
        self.log_count_lbl.pack(side="right")

        cols = ("hora","cpm","usvh","pulsos","bateria","nivel")
        heads = ("Hora","CPM","µSv/h","Pulsos","Batería (V)","Nivel")
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

        # Solución de compatibilidad para habilitar colores de tags en Treeview (Zebra Striping)
        def fixed_map(option):
            return [elm for elm in style.map("Treeview", query_opt=option)
                    if elm[:2] != ("!disabled", "!selected")]
        style.map("Custom.Treeview",
                  foreground=fixed_map("foreground"),
                  background=fixed_map("background"))


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

        # Configuración de tags para zebra striping (filas de colores alternados)
        self.tree.tag_configure("even", background=CARD)
        self.tree.tag_configure("odd", background=CARD2)


    # ── Histogram style & updates ─────────────────────────────────────────────
    def _style_hist_chart(self):
        self.ax_hist.set_facecolor(CARD2)
        self.fig_hist.patch.set_facecolor(CARD)
        self.ax_hist.tick_params(colors=MUTED, labelsize=9)
        for spine in self.ax_hist.spines.values():
            spine.set_color(BORDER)
        self.ax_hist.set_xlabel("Tasa de Conteo (CPM)", color=MUTED, fontsize=10)
        self.ax_hist.set_ylabel("Densidad de Probabilidad", color=MUTED, fontsize=10)
        self.ax_hist.grid(color=BORDER, linestyle=":", linewidth=0.5, alpha=0.5)
        self.fig_hist.subplots_adjust(bottom=0.2, left=0.1, right=0.98, top=0.92)

    def _update_hist_chart(self):
        self.ax_hist.clear()
        self._style_hist_chart()
        
        if len(self.cpm_hist) > 5:
            ys = np.array(list(self.cpm_hist))
            mean_cpm = np.mean(ys)
            std_obs = np.std(ys)
            tau = self._poll_iv / 60.0  # intervalo en minutos
            
            # Desviación teórica para un proceso de Poisson con tasa de conteo media (cpm)
            std_theo = math.sqrt(mean_cpm / tau) if mean_cpm > 0 else 0.0
            
            # Chi-cuadrado reducido (X2/dof)
            if std_theo > 0:
                chi2_red = (std_obs ** 2) / (std_theo ** 2)
            else:
                chi2_red = 0.0
                
            # Diagnóstico del ajuste
            if chi2_red == 0:
                status = "Sin radiación registrada"
            elif 0.7 <= chi2_red <= 1.3:
                status = "Decaimiento Estocástico de Poisson Puro"
            elif chi2_red > 1.3:
                status = "Fluctuación Activa de Campo / Variabilidad de Tasa"
            else:
                status = "Varianza Sub-Poissoniana (Suavizado Artificial)"
                
            mode = self.poisson_mode_var.get()
            counts_in_iv = np.round(ys * self._poll_iv / 60.0).astype(int)
            lambda_pois = np.mean(counts_in_iv)
            
            if mode == "Discreto (Intervalo)":
                # Convertimos CPM a conteos reales en el intervalo
                unique_counts, freq = np.unique(counts_in_iv, return_counts=True)
                freq_pct = freq / len(counts_in_iv)
                
                # Graficamos el histograma discreto observado
                self.ax_hist.bar(unique_counts, freq_pct, color=GREEN, alpha=0.35, edgecolor=BORDER, width=0.6, label="Hist. Observado")
                
                # Curva teórica de Poisson usando log-gamma para estabilidad numérica
                if len(unique_counts) > 0:
                    max_k = max(unique_counts)
                    k_axis = np.arange(0, max_k + 2)
                    pmf = []
                    for k in k_axis:
                        if lambda_pois > 0:
                            if k > 0:
                                ln_p = k * math.log(lambda_pois) - lambda_pois - math.lgamma(k + 1)
                                p_val = math.exp(ln_p)
                            else:
                                p_val = math.exp(-lambda_pois)
                        else:
                            p_val = 1.0 if k == 0 else 0.0
                        pmf.append(p_val)
                    
                    self.ax_hist.step(k_axis, pmf, where='mid', color=CYAN, linewidth=2.0, marker='o', label=f"Teoría Poisson (λ={lambda_pois:.3f})")
                
                self.ax_hist.set_xlabel(f"Número de Pulsos en {self._poll_iv} s (k)", color=MUTED, fontsize=10)
                self.ax_hist.set_ylabel("Frecuencia Relativa (Probabilidad)", color=MUTED, fontsize=10)
                
                info_text = (
                    f"Estadística del Intervalo ({self._poll_iv} s):\n"
                    f" Media de Conteo (λ): {lambda_pois:.3f} pulsos\n"
                    f" Desv. Est. Obs: {np.std(counts_in_iv):.3f} pulsos\n"
                    f" Desv. Est. Teo (√λ): {math.sqrt(lambda_pois):.3f} pulsos\n"
                    f" Chi-Cuadrado Red. (χ²_red): {chi2_red:.3f}\n"
                    f" Diagnóstico: {status}"
                )
            else:
                # Modo Continuo (CPM)
                counts, bins, _ = self.ax_hist.hist(ys, bins="auto", density=True, color=GREEN, alpha=0.35, edgecolor=BORDER, label="Hist. Observado")
                
                if std_theo > 0:
                    xmin, xmax = self.ax_hist.get_xlim()
                    x_axis = np.linspace(xmin, xmax, 300)
                    y_axis = (1.0 / (std_theo * math.sqrt(2 * math.pi))) * np.exp(-0.5 * ((x_axis - mean_cpm) / std_theo) ** 2)
                    self.ax_hist.plot(x_axis, y_axis, color=CYAN, linewidth=2.0, label="Curva Teórica de Poisson")
                
                self.ax_hist.set_xlabel("Tasa de Conteo (CPM)", color=MUTED, fontsize=10)
                self.ax_hist.set_ylabel("Densidad de Probabilidad", color=MUTED, fontsize=10)
                
                info_text = (
                    f"Análisis Estocástico:\n"
                    f" Promedio (μ): {mean_cpm:.2f} CPM\n"
                    f" Desv. Est. Obs. (s): {std_obs:.2f} CPM\n"
                    f" Desv. Est. Teo. (σ): {std_theo:.2f} CPM\n"
                    f" Chi-Cuadrado Red. (χ²_red): {chi2_red:.3f}\n"
                    f" Diagnóstico: {status}"
                )
                
            self.ax_hist.text(0.03, 0.95, info_text, transform=self.ax_hist.transAxes,
                               fontsize=8.5, color=TEXT, va='top', ha='left',
                               bbox=dict(boxstyle="round,pad=0.5", facecolor=CARD, edgecolor=BORDER, alpha=0.85))
            
            self.ax_hist.legend(loc="upper right", facecolor=CARD, edgecolor=BORDER, fontsize=8, labelcolor=TEXT)

            # Ejecutar prueba de bondad de ajuste Chi-Cuadrado de Poisson formal
            res_test = science_utils.poisson_chi2_test(counts_in_iv)
            if res_test:
                res_str = (
                    f"📊 PRUEBA DE HIPÓTESIS:\n"
                    f"• Media de Conteo (λ): {res_test['mean']:.3f} pul/int\n"
                    f"• Estadístico χ²: {res_test['chi2']:.3f}\n"
                    f"• Grados de Libertad: {res_test['dof']}\n"
                    f"• p-valor calculado: {res_test['p_value']:.5f}\n\n"
                    f"📢 CONCLUSIÓN:\n"
                )
                if res_test['passed']:
                    res_str += "✅ APTO: Los datos siguen una distribución de Poisson pura (H₀ aceptada al 95% de confianza). Las fluctuaciones son puramente estadísticas y aleatorias.\n\n"
                else:
                    res_str += "❌ RECHAZADO: Se rechaza la hipótesis de Poisson (H₀ rechazada al 95% de confianza). Existe una modulación temporal activa de la radiación o un suavizado/filtro artificial en el tubo.\n\n"
                
                res_str += "📊 BINS AGRUPADOS (Obs | Exp):\n"
                for label, o, e in res_test['bins']:
                    res_str += f"  - k={label}: {int(o)} | {e:.1f}\n"
                self.pois_chi_lbl.configure(text=res_str, text_color=GREEN if res_test['passed'] else YELLOW)
            else:
                self.pois_chi_lbl.configure(text="Mediciones insuficientes o demasiados ceros para realizar la prueba Chi-Cuadrado (requiere más variación).", text_color=MUTED)
        else:
            self.ax_hist.text(0.5, 0.5, "Esperando acumular más muestras en la sesión\npara realizar el análisis estadístico (mín. 6)...",
                               color=MUTED, fontsize=10, ha='center', va='center')
            self.pois_chi_lbl.configure(text="Esperando acumular al menos 6 muestras para habilitar el panel de análisis Chi-Cuadrado...", text_color=MUTED)
        
        self.hist_canvas.draw_idle()

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
            self.ax.plot(xs, ys, color=GREEN, linewidth=2.0, alpha=0.45, label="Lectura Cruda (Ruido)")
            
            # 2. Análisis Estadístico (Filtro SMA y Poisson)
            window = min(10, len(ys)) # Ventana de promediado de 10 muestras
            if window > 1:
                # Convolución para la media móvil
                sma = np.convolve(ys, np.ones(window)/window, mode='valid')
                xs_sma = xs[window-1:]
                
                # Incertidumbre estadística (Desviación de Poisson = raíz de la media)
                sigma = np.sqrt(sma)
                
                # Dibujamos la media (Tendencia Real)
                self.ax.plot(xs_sma, sma, color=CYAN, linewidth=3.5, solid_capstyle="round", label=f"Tendencia Real (SMA n={window})")
                
                # Dibujamos la franja de incertidumbre ±1σ
                self.ax.fill_between(xs_sma, sma - sigma, sma + sigma, color=CYAN, alpha=0.15, label="Incertidumbre Poisson (±1σ)")
                
                # Relleno translúcido Sci-Fi bajo la tendencia real (SMA)
                self.ax.fill_between(xs_sma, 0, sma, color=CYAN, alpha=0.06, label="Dosis Relativa")
            
            # 3. Líneas de alerta radiológica con etiquetas de texto integradas (sin emojis para evitar errores de fuentes en Matplotlib)
            self.ax.axhline(y=100, color=YELLOW, linewidth=1.0, linestyle="--", alpha=0.5)
            self.ax.text(0.98, 108, " Umbral Elevado (100 CPM)", color=YELLOW, fontsize=8, alpha=0.7, va='bottom', ha='right', transform=self.ax.get_yaxis_transform())

            self.ax.axhline(y=500, color=RED,    linewidth=1.0, linestyle="--", alpha=0.5)
            self.ax.text(0.98, 508, " Umbral Peligroso (500 CPM)", color=RED, fontsize=8, alpha=0.7, va='bottom', ha='right', transform=self.ax.get_yaxis_transform())
            
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
        self.led_indicator.configure(text_color="#103020") # Verde tenue (modo espera)
        self.btn_start.configure(state="normal")
        self.btn_sync_time.configure(state="normal")

    def _set_disconnected(self):
        self.btn_conn.configure(text="⚡  Conectar", fg_color="#238636", hover_color="#2ea043")
        self.status_lbl.configure(text="● Desconectado", text_color=RED)
        self.led_indicator.configure(text_color="#222222") # Apagado
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

            # Telemetría avanzada para el físico
            dt = self.serial.get_tube_dead_time()
            if dt is not None:
                self.dev_lbl["dead_time"].configure(text=f"{dt * 1e6:.1f} µs" if dt < 1.0 else f"{dt:.2f} s")
            else:
                self.dev_lbl["dead_time"].configure(text="Desactivado")

            bg = self.serial.get_tube_background()
            if bg is not None:
                self.dev_lbl["bg_comp"].configure(text=f"{bg:.1f} CPM")
            else:
                self.dev_lbl["bg_comp"].configure(text="0.0 CPM")

            hvf = self.serial.get_tube_hv_frequency()
            if hvf is not None:
                self.dev_lbl["hv_freq"].configure(text=f"{hvf} Hz")
            else:
                self.dev_lbl["hv_freq"].configure(text="—")
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
        self.cpm_lv.configure(text=level, text_color=color)
        self.cpm_big_lbl.configure(text=f"{cpm:.1f}", text_color=color)
        self.dose_gauge.set_value(dose)
        self.dose_big_lbl.configure(text=f"{dose:.4f} µSv/h", text_color=CYAN)
        self.dose_lbl.configure(text=f"Acum: {self.dose_acc:.4f} µSv")

        # Flashear el indicador LED de actividad (Heartbeat)
        self.led_indicator.configure(text_color=GREEN)
        self.after(150, lambda: self.led_indicator.configure(text_color="#103020" if self.serial.connected else "#222222"))

        if volt is not None:
            pct = max(0, min(1, (volt - 2.7) / (4.2 - 2.7)))
            self.batt_bar.set(pct)
            bc = GREEN if pct > 0.5 else (YELLOW if pct > 0.2 else RED)
            self.batt_bar.configure(progress_color=bc)
            self.batt_lbl.configure(text=f"{volt:.3f} V", text_color=bc)

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

        # Insertar con zebra striping
        tag = "even" if len(self.log_rows) % 2 == 0 else "odd"
        self.tree.insert("", 0, values=tuple(row.values()), tags=(tag,))
        self.log_count_lbl.configure(text=f"{len(self.log_rows)} entradas")
        self._update_chart()
        self._update_hist_chart()
        self._update_physics_calculations(cpm, dose)

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
        self._update_hist_chart()
        self._update_physics_calculations(0.0, 0.0)
        
        # Limpiar ajuste de decaimiento
        self.ax_decay.clear()
        self._style_decay_chart()
        self.decay_canvas.draw_idle()
        for k in self.dec_res_lbls:
            self.dec_res_lbls[k].configure(text="—")

    # ── Métodos de Física y Utilidades de Ajuste ─────────────────────────────────
    def _style_decay_chart(self):
        self.ax_decay.set_facecolor(CARD2)
        self.fig_decay.patch.set_facecolor(CARD)
        self.ax_decay.tick_params(colors=MUTED, labelsize=9)
        for spine in self.ax_decay.spines.values():
            spine.set_color(BORDER)
        self.ax_decay.set_xlabel("Tiempo relativo (s)", color=MUTED, fontsize=10)
        self.ax_decay.set_ylabel("Tasa de Conteo (CPM)", color=MUTED, fontsize=10)
        self.ax_decay.grid(color=BORDER, linestyle="--", linewidth=0.5, alpha=0.5)
        self.fig_decay.subplots_adjust(bottom=0.18, left=0.1, right=0.98, top=0.92)

    def _toggle_decay_bg_input(self):
        if self.decay_bg_check_var.get():
            self.decay_bg_entry.configure(state="normal")
        else:
            self.decay_bg_entry.configure(state="disabled")

    def _run_decay_fit(self):
        if len(self.cpm_hist) < 5:
            messagebox.showwarning("Ajuste de Decaimiento", "Se necesitan al menos 5 muestras registradas para realizar el ajuste.")
            return
            
        times = list(self.time_hist)
        cpms = list(self.cpm_hist)
        
        t_sec = np.array([(t - times[0]).total_seconds() for t in times])
        y_val = np.array(cpms)
        
        rng = self.decay_range_var.get()
        start_idx = 0
        
        if rng == "Desde el Máximo":
            start_idx = np.argmax(y_val)
        elif rng == "Últimos 2 min":
            limit = t_sec[-1] - 120
            start_idx = np.searchsorted(t_sec, limit)
        elif rng == "Últimos 5 min":
            limit = t_sec[-1] - 300
            start_idx = np.searchsorted(t_sec, limit)
        elif rng == "Últimos 10 min":
            limit = t_sec[-1] - 600
            start_idx = np.searchsorted(t_sec, limit)
            
        t_fit = t_sec[start_idx:]
        y_fit = y_val[start_idx:]
        
        if len(t_fit) < 5:
            messagebox.showwarning("Ajuste de Decaimiento", "El rango seleccionado no contiene suficientes puntos (mínimo 5).")
            return
            
        t0 = t_fit[0]
        t_rel = t_fit - t0
        
        bg_fixed = None
        if self.decay_bg_check_var.get():
            try:
                bg_fixed = float(self.decay_bg_val_var.get())
                if bg_fixed < 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Error de Fondo", "Por favor introduce un valor numérico de fondo válido (>= 0).")
                return
                
        try:
            A, err_A, lam, err_lam, B, err_B, r2, chi2_red = science_utils.fit_exponential_decay(t_rel, y_fit, bg_fixed)
            
            if lam > 0:
                t_half = math.log(2) / lam
                err_t_half = t_half * (err_lam / lam) if lam > 0 else 0
                
                if t_half < 60:
                    t_half_str = f"{t_half:.2f} ± {err_t_half:.2f} s"
                elif t_half < 3600:
                    t_half_str = f"{t_half/60:.2f} ± {err_t_half/60:.2f} min"
                else:
                    t_half_str = f"{t_half/3600:.2f} ± {err_t_half/3600:.2f} h"
                
                matches = science_utils.identify_isotope_by_half_life(t_half)
                if matches:
                    best = matches[0]
                    iso_str = f"{best['name']} (err {best['error_pct']:.1f}%)"
                else:
                    iso_str = "No coincide (desconocido)"
            else:
                t_half_str = "Infinito (Sin decaimiento)"
                iso_str = "N/A"
                
            self.dec_res_lbls["t_half"].configure(text=t_half_str)
            self.dec_res_lbls["lambda"].configure(text=f"{lam:.6f} ± {err_lam:.6f} s⁻¹")
            self.dec_res_lbls["n0"].configure(text=f"{A:.2f} ± {err_A:.2f} CPM")
            self.dec_res_lbls["bg"].configure(text=f"{B:.2f} ± {err_B:.2f} CPM" if bg_fixed is None else f"{B:.1f} CPM (Fijo)")
            self.dec_res_lbls["r2"].configure(text=f"{r2:.4f}")
            self.dec_res_lbls["chi2"].configure(text=f"{chi2_red:.3f}")
            self.dec_res_lbls["isotope"].configure(text=iso_str)
            
            self.ax_decay.clear()
            self._style_decay_chart()
            
            self.ax_decay.scatter(t_rel, y_fit, color=GREEN, s=15, alpha=0.7, label="Observado")
            
            t_curve = np.linspace(0, t_rel[-1], 300)
            y_curve = A * np.exp(-lam * t_curve) + B
            self.ax_decay.plot(t_curve, y_curve, color=CYAN, linewidth=2.5, label="Ajuste Exponencial")
            self.ax_decay.axhline(y=B, color=RED, linestyle="--", linewidth=1.0, alpha=0.5, label=f"Fondo ({B:.1f} CPM)")
            
            self.ax_decay.legend(loc="upper right", facecolor=CARD, edgecolor=BORDER, fontsize=8, labelcolor=TEXT)
            self.decay_canvas.draw_idle()
            
        except Exception as e:
            messagebox.showerror("Error de Ajuste", f"El ajuste falló debido a problemas de convergencia matemática:\n{e}")

    def _on_dt_preset_change(self, preset):
        if preset in science_utils.TUBE_PRESETS:
            _, dt = science_utils.TUBE_PRESETS[preset]
            if preset == "Personalizado":
                self.dt_entry.configure(state="normal")
            else:
                self.dt_entry.configure(state="normal")
                self.dt_val_var.set(f"{dt:.0f}")
        self._update_physics_calculations()

    def _on_act_tube_change(self, preset):
        if preset in science_utils.TUBE_PRESETS:
            area, _ = science_utils.TUBE_PRESETS[preset]
            if preset == "Personalizado":
                self.act_area_entry.configure(state="normal")
            else:
                self.act_area_entry.configure(state="normal")
                self.act_area_var.set(f"{area:.1f}")
        self._update_physics_calculations()

    def _on_shield_change(self, _v):
        self._update_physics_calculations()

    def _update_physics_calculations(self, live_cpm=None, live_dose=None):
        if live_cpm is None:
            if len(self.cpm_hist) > 0:
                live_cpm = self.cpm_hist[-1]
            else:
                live_cpm = 0.0
        if live_dose is None:
            if live_cpm > 0:
                live_dose = live_cpm / self.sensitivity
            else:
                live_dose = 0.0
                
        # 1. Tiempo muerto
        try:
            dt_us = float(self.dt_val_var.get())
            if dt_us < 0:
                raise ValueError()
        except ValueError:
            dt_us = 0.0
            
        corr_cpm, loss = science_utils.correct_dead_time(live_cpm, dt_us)
        sat_limit = science_utils.get_saturation_limit(dt_us)
        
        self.dt_out_lbls["measured"].configure(text=f"{live_cpm:.1f} CPM")
        self.dt_out_lbls["corrected"].configure(text=f"{corr_cpm:.1f} CPM")
        self.dt_out_lbls["loss"].configure(text=f"{loss:.2f}%")
        self.dt_out_lbls["sat"].configure(text=f"{sat_limit:.0f} CPM" if sat_limit < float("inf") else "Infinito")
        
        # 2. Actividad de fuente
        try:
            dist = float(self.act_dist_var.get())
            area = float(self.act_area_var.get())
            eff = float(self.act_eff_var.get())
            if dist < 0 or area < 0 or eff < 0:
                raise ValueError()
        except ValueError:
            dist = area = eff = 0.0
            
        bg_cpm = 25.0
        if self.decay_bg_check_var.get():
            try:
                bg_cpm = float(self.decay_bg_val_var.get())
            except ValueError:
                pass
                
        act_bq, act_uci = science_utils.estimate_source_activity(live_cpm, bg_cpm, dist, area, eff)
        
        if dist > 0:
            solid_angle = area / (4.0 * math.pi * (dist ** 2))
        else:
            solid_angle = 0.0
            
        self.act_out_lbls["solid_angle"].configure(text=f"{solid_angle:.5f} sr")
        self.act_out_lbls["act_bq"].configure(text=f"{act_bq:.1f} Bq")
        self.act_out_lbls["act_uci"].configure(text=f"{act_uci:.4f} µCi")
        
        # 3. Blindaje
        mat = self.sh_mat_var.get()
        nrg = self.sh_nrg_var.get()
        
        try:
            thick = float(self.sh_thick_var.get())
            if thick < 0:
                raise ValueError()
        except ValueError:
            thick = 0.0
            
        hvl = science_utils.get_shielding_hvl(mat, nrg)
        tvl = hvl * math.log(10) / math.log(2)
        
        trans, att = science_utils.calculate_transmission(thick, hvl)
        sh_dose = live_dose * trans
        
        self.sh_out_lbls["hvl"].configure(text=f"{hvl:.3f} cm")
        self.sh_out_lbls["tvl"].configure(text=f"{tvl:.3f} cm")
        self.sh_out_lbls["trans"].configure(text=f"{trans:.5f} (I/I₀)")
        self.sh_out_lbls["att"].configure(text=f"{att:.2f}%")
        self.sh_out_lbls["shield_dose"].configure(text=f"{sh_dose:.4f} µSv/h")
        
        # 4. Identificación por atenuación de blindaje
        try:
            i0 = float(self.sh_i0_var.get())
            i_val = float(self.sh_i_var.get())
            if i0 <= 0 or i_val <= 0 or i_val >= i0 or thick <= 0:
                raise ValueError()
            sh_matches = science_utils.identify_isotope_by_shielding(mat, thick, i0, i_val)
            if sh_matches:
                best = sh_matches[0]
                self.sh_iso_lbl.configure(text=f"{best['energy']} (err {best['error_pct']:.1f}%)", text_color=GREEN)
            else:
                self.sh_iso_lbl.configure(text="No coincide", text_color=RED)
        except ValueError:
            self.sh_iso_lbl.configure(text="Datos inv./Falta blindar", text_color=MUTED)

        # Actualizar gráfico de blindaje
        self._update_phys_chart(mat, nrg, thick, trans)

    def _style_phys_chart(self):
        self.ax_phys.set_facecolor(CARD2)
        self.fig_phys.patch.set_facecolor(CARD)
        self.ax_phys.tick_params(colors=MUTED, labelsize=9)
        for spine in self.ax_phys.spines.values():
            spine.set_color(BORDER)
        self.ax_phys.set_xlabel("Espesor del blindaje (cm)", color=MUTED, fontsize=10)
        self.ax_phys.set_ylabel("Transmisión (I/I₀)", color=MUTED, fontsize=10)
        self.ax_phys.grid(color=BORDER, linestyle=":", linewidth=0.5, alpha=0.5)
        self.fig_phys.subplots_adjust(bottom=0.2, left=0.08, right=0.98, top=0.9)

    def _update_phys_chart(self, mat, nrg, thick, trans):
        self.ax_phys.clear()
        self._style_phys_chart()
        
        hvl = science_utils.get_shielding_hvl(mat, nrg)
        if hvl <= 0:
            return
            
        x_max = max(thick * 1.5, hvl * 5.0)
        
        # Ajustar límites del gráfico si hay datos experimentales
        if self.sh_points:
            xs = [p[0] for p in self.sh_points]
            x_max = max(x_max, max(xs) * 1.2)
            
        x_max = max(x_max, 1.0)
        x_axis = np.linspace(0, x_max, 300)
        y_axis = np.power(2, -x_axis / hvl)
        
        # 1. Trazar curva de atenuación teórica de referencia
        self.ax_phys.plot(x_axis, y_axis, color=CYAN, linewidth=2.0, label=f"Teórico ({mat}, {nrg})")
        self.ax_phys.fill_between(x_axis, 0, y_axis, color=CYAN, alpha=0.04)
        
        # 2. Trazar el espesor de blindaje actual
        self.ax_phys.axvline(x=thick, color="#8b949e", linestyle=":", alpha=0.6)
        self.ax_phys.scatter([thick], [trans], color=CYAN, s=40, zorder=5, label=f"Espesor Act: {thick:.2f} cm ({trans*100.0:.1f}%)")
        
        # 3. Trazar puntos experimentales y ajuste si existen
        if self.sh_points:
            xs = np.array([p[0] for p in self.sh_points])
            ys = np.array([p[1] for p in self.sh_points])
            
            # Normalizar los CPM respecto a I0 para comparar con transmisión (0 a 1)
            i0_norm = ys[np.argmin(xs)] if len(xs) > 0 else 1.0
            if self._sh_fit_I0 is not None:
                i0_norm = self._sh_fit_I0
                
            ys_norm = ys / i0_norm
            self.ax_phys.scatter(xs, ys_norm, color=GREEN, s=35, zorder=6, label="Exp. Medido (Normalizado)")
            
            if self._sh_fit_mu is not None and self._sh_fit_B is not None:
                # Curva ajustada de Beer-Lambert con offset de fondo
                y_fit_curve = (self._sh_fit_I0 * np.exp(-self._sh_fit_mu * x_axis) + self._sh_fit_B) / i0_norm
                self.ax_phys.plot(x_axis, y_fit_curve, color=ORANGE, linewidth=2.0, linestyle="--", label="Ajuste Beer-Lambert")
                
        self.ax_phys.legend(loc="upper right", facecolor=CARD, edgecolor=BORDER, fontsize=8, labelcolor=TEXT)
        self.phys_canvas.draw_idle()

    # ── Métodos de Espectroscopía Gamma ──────────────────────────────────────────
    def _style_spec_chart(self):
        self.ax_spec.set_facecolor(CARD2)
        self.fig_spec.patch.set_facecolor(CARD)
        self.ax_spec.tick_params(colors=MUTED, labelsize=9)
        for spine in self.ax_spec.spines.values():
            spine.set_color(BORDER)
        self.ax_spec.set_xlabel("Energía (keV)", color=MUTED, fontsize=10)
        self.ax_spec.set_ylabel("Cuentas / Canal (Intensidad normalizada)", color=MUTED, fontsize=10)
        self.ax_spec.grid(color=BORDER, linestyle=":", linewidth=0.5, alpha=0.5)
        self.fig_spec.subplots_adjust(bottom=0.18, left=0.08, right=0.98, top=0.92)

    def _update_spec_chart(self):
        self.ax_spec.clear()
        self._style_spec_chart()
        
        iso = self.spec_iso_var.get()
        res = self.spec_res_var.get()
        
        energias, intensidad = spectrum_simulator.generate_gamma_spectrum(iso, res)
        
        self.ax_spec.plot(energias, intensidad, color=GREEN, linewidth=2.0, label=f"Espectro {iso}")
        self.ax_spec.fill_between(energias, 0, intensidad, color=GREEN, alpha=0.08)
        
        peaks = spectrum_simulator.ISOTOPE_PEAKS.get(iso, [])
        for ep, i_rel in peaks:
            idx = np.argmin(np.abs(energias - ep))
            y_val = intensidad[idx]
            self.ax_spec.annotate(f"{ep:.1f} keV",
                                 xy=(ep, y_val),
                                 xytext=(ep + 45, y_val + 0.05),
                                 fontsize=8.5,
                                 color=TEXT,
                                 arrowprops=dict(arrowstyle="->", color=CYAN, lw=1.0, connectionstyle="arc3,rad=.15"),
                                 bbox=dict(boxstyle="round,pad=0.2", facecolor=CARD, edgecolor=BORDER, alpha=0.85))
                                 
        self.ax_spec.set_ylim(0, 1.25)
        self.ax_spec.legend(loc="upper right", facecolor=CARD, edgecolor=BORDER, fontsize=8, labelcolor=TEXT)
        self.spec_canvas.draw_idle()

    def _on_spec_change(self, val):
        self._update_spec_chart()

    def _on_spec_preset_change(self, preset):
        if preset == "NaI(Tl) (Centellador estándar)":
            self.spec_res_var.set(7.0)
            self.spec_res_slider.configure(state="normal")
        elif preset == "HPGe (Alta resolución)":
            self.spec_res_var.set(0.2)
            self.spec_res_slider.configure(state="normal")
        elif preset == "BGO (Baja resolución)":
            self.spec_res_var.set(11.0)
            self.spec_res_slider.configure(state="normal")
        elif preset == "Personalizado":
            self.spec_res_slider.configure(state="normal")
            
        self.res_lbl.configure(text=f"{self.spec_res_var.get():.1f}%")
        self._update_spec_chart()

    def _on_spec_slider_move(self, val):
        self.res_lbl.configure(text=f"{float(val):.1f}%")
        self.spec_det_preset_var.set("Personalizado")
        self._update_spec_chart()

    # ── MÉTODOS DE DATALOG DE FLASH ──────────────────────────────────────────

    def _style_flash_chart(self):
        self.ax_flash.set_facecolor(CARD2)
        self.fig_flash.patch.set_facecolor(CARD)
        self.ax_flash.tick_params(colors=MUTED, labelsize=9)
        for spine in self.ax_flash.spines.values():
            spine.set_color(BORDER)
        self.ax_flash.set_ylabel("Tasa (CPM)", color=MUTED, fontsize=10)
        self.ax_flash.grid(color=BORDER, linestyle="--", linewidth=0.5, alpha=0.5)
        self.ax_flash.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
        self.ax_flash.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))
        self.ax_flash.tick_params(axis='x', rotation=12)
        self.fig_flash.subplots_adjust(bottom=0.2, left=0.08, right=0.98, top=0.92)

    def _download_flash_datalog(self):
        if not self.serial.connected:
            messagebox.showwarning("Conexión", "El detector debe estar conectado para descargar el datalog.")
            return

        self.cal_status_var.set("Descargando datalog de Flash...")
        self.pois_chi_lbl.configure(text="Descargando registros de flash. Por favor espere...", text_color=YELLOW)
        
        # Desactivar botones temporalmente
        self.btn_download_flash.configure(state="disabled", text="⏱️ Descargando...")

        def run_dl():
            try:
                # Descarga de Rad Pro
                raw = self.serial.send("GET datalog 0")
                if not raw:
                    self.after(0, lambda: messagebox.showinfo("Datalog Vacío", "No se encontraron registros en la memoria flash del dispositivo."))
                    self.after(0, self._finalize_download, [])
                    return
                
                sessions = science_utils.parse_datalog_sessions(raw)
                self.after(0, self._finalize_download, sessions)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error de descarga", f"Falló la comunicación: {e}"))
                self.after(0, self._finalize_download, [])

        threading.Thread(target=run_dl, daemon=True).start()

    def _finalize_download(self, sessions):
        self.datalog_sessions = sessions
        
        # Re-habilitar botón
        self.btn_download_flash.configure(state="normal", text="📥 Descargar Datalog")
        
        # Limpiar
        for row in self.flash_sess_tree.get_children():
            self.flash_sess_tree.delete(row)
        for row in self.flash_tree.get_children():
            self.flash_tree.delete(row)
        self.ax_flash.clear()
        self._style_flash_chart()
        self.flash_canvas.draw_idle()

        if not sessions:
            self.cal_status_var.set("No se obtuvieron registros de datalog.")
            return

        # Llenar árbol de sesiones
        for i, sess in enumerate(sessions):
            if sess:
                ts = sess[0]["time"]
                dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                pts = len(sess)
                tag = "even" if i % 2 == 0 else "odd"
                self.flash_sess_tree.insert("", "end", iid=str(i), values=(i+1, dt_str, pts), tags=(tag,))
        
        self.cal_status_var.set(f"Datalog descargado: {len(sessions)} sesiones encontradas.")
        messagebox.showinfo("Descarga Exitosa", f"Se descargaron {len(sessions)} sesiones de registro de la memoria flash.")

    def _on_flash_session_selected(self, event):
        sel = self.flash_sess_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.selected_datalog_session_idx = idx
        sess = self.datalog_sessions[idx]

        # Limpiar tabla
        for row in self.flash_tree.get_children():
            self.flash_tree.delete(row)

        # Llenar tabla e histórico
        times = []
        cpms = []
        for i, rec in enumerate(sess):
            dt_str = datetime.fromtimestamp(rec["time"]).strftime("%Y-%m-%d %H:%M:%S")
            tag = "even" if i % 2 == 0 else "odd"
            self.flash_tree.insert("", "end", values=(dt_str, f"{rec['cpm']:.1f}", rec["pulseCount"], rec["dt"], rec["dp"]), tags=(tag,))
            
            times.append(datetime.fromtimestamp(rec["time"]))
            cpms.append(rec["cpm"])

        # Graficar
        self.ax_flash.clear()
        self._style_flash_chart()
        if len(times) > 0:
            self.ax_flash.plot(times, cpms, color=CYAN, linewidth=2.0, label=f"Sesión {idx+1}")
            self.ax_flash.fill_between(times, 0, cpms, color=CYAN, alpha=0.08)
            self.ax_flash.legend(loc="upper right", facecolor=CARD, edgecolor=BORDER, labelcolor=TEXT)
        self.flash_canvas.draw_idle()

    def _clear_flash_datalog(self):
        if not self.serial.connected:
            messagebox.showwarning("Conexión", "El detector debe estar conectado.")
            return
        if not messagebox.askyesno("Borrar Flash", "⚠️ ¿Está seguro de borrar permanentemente el datalog guardado en la memoria flash del GC-01?\n\nEsta operación no se puede deshacer."):
            return
            
        success = self.serial.reset_datalog()
        if success:
            self.datalog_sessions = []
            self.selected_datalog_session_idx = -1
            for row in self.flash_sess_tree.get_children():
                self.flash_sess_tree.delete(row)
            for row in self.flash_tree.get_children():
                self.flash_tree.delete(row)
            self.ax_flash.clear()
            self._style_flash_chart()
            self.flash_canvas.draw_idle()
            messagebox.showinfo("Flash Borrada", "La memoria flash del dispositivo se ha borrado con éxito.")
        else:
            messagebox.showerror("Error", "No se pudo borrar el datalog de la flash (dispositivo no respondió).")

    def _export_flash_datalog(self):
        if self.selected_datalog_session_idx == -1:
            messagebox.showwarning("Exportar", "Por favor seleccione una sesión descargada de la lista.")
            return
        sess = self.datalog_sessions[self.selected_datalog_session_idx]
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV","*.csv")],
            initialfile=f"gc01_flash_sess_{self.selected_datalog_session_idx + 1}_{datetime.now():%Y%m%d_%H%M%S}.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Timestamp_UNIX", "Fecha_Hora_Local", "CPM", "Pulsos_Acumulados", "Intervalo_dt_s", "Delta_Pulsos"])
            for rec in sess:
                dt_str = datetime.fromtimestamp(rec["time"]).strftime("%Y-%m-%d %H:%M:%S")
                w.writerow([rec["time"], dt_str, f"{rec['cpm']:.2f}", rec["pulseCount"], rec["dt"], rec["dp"]])
        messagebox.showinfo("Exportado", f"Sesión guardada en:\n{path}")


    # ── MÉTODOS DE CALIBRACIÓN DE TIEMPO MUERTO (2 FUENTES) ─────────────────

    def _start_two_source_capture(self, step_name: str, entry_var: ctk.StringVar, button: ctk.CTkButton):
        if not self.serial.connected:
            messagebox.showwarning("Conexión", "El detector debe estar conectado para capturar datos en vivo.")
            return
            
        button.configure(state="disabled", text="⏱️ Mediendo...")
        self.cal_status_var.set(f"Capturando {step_name} por 10 segundos...")
        self.cal_progress_var.set(0.0)
        
        def run_capture():
            samples = []
            dur = 10.0
            steps = 10
            for i in range(steps):
                time.sleep(dur / steps)
                cpm = self.serial.get_tube_rate()
                if cpm is not None:
                    samples.append(cpm)
                
                self.after(0, self.cal_progress_var.set, (i + 1) / steps)
                
            avg_cpm = np.mean(samples) if samples else 0.0
            
            def finalize():
                entry_var.set(f"{avg_cpm:.1f}")
                button.configure(state="normal", text="Capturar en vivo")
                self.cal_status_var.set(f"Captura de {step_name} completa.")
                self._calculate_two_source_dead_time()
                
            self.after(0, finalize)
            
        threading.Thread(target=run_capture, daemon=True).start()

    def _calculate_two_source_dead_time(self):
        try:
            rb = float(self.cal_bg_var.get())
            r1 = float(self.cal_r1_var.get())
            r2 = float(self.cal_r2_var.get())
            r12 = float(self.cal_r12_var.get())
        except ValueError:
            self.cal_status_var.set("Error: Ingrese valores numéricos válidos.")
            return
            
        tau, msg = science_utils.calculate_two_source_dead_time(rb, r1, r2, r12)
        tau_us = tau * 1e6
        
        self.cal_status_var.set(f"Resultado: τ = {tau_us:.2f} µs\n({msg})")
        
        if tau > 0 and "Advertencia" not in msg:
            self.btn_apply_cal_dt.configure(state="normal")
            self._temp_cal_dt = tau_us
        else:
            self.btn_apply_cal_dt.configure(state="disabled")
            self._temp_cal_dt = None

    def _apply_calibrated_dead_time(self):
        if self._temp_cal_dt is not None:
            self.dt_val_var.set(f"{self._temp_cal_dt:.1f}")
            self.dt_preset_var.set("Personalizado")
            self._update_physics_calculations()
            messagebox.showinfo("Compensación de Tiempo Muerto", f"Se aplicó el tiempo muerto experimental de {self._temp_cal_dt:.2f} µs al monitor.")


    # ── MÉTODOS DE BLINDAJE MULTI-ESPESOR ──────────────────────────────────

    def _add_shielding_point(self):
        try:
            thick = float(self.sh_point_thick_var.get())
            cpm = float(self.sh_point_cpm_var.get())
            if thick < 0 or cpm < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Entrada Inválida", "Espesor y CPM deben ser números positivos.")
            return

        self.sh_points.append([thick, cpm])
        self.sh_points.sort(key=lambda x: x[0])
        self._update_shielding_table()
        self._update_physics_calculations()

    def _delete_shielding_point(self):
        sel = self.sh_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.sh_points):
            self.sh_points.pop(idx)
            self._update_shielding_table()
            # Si borramos puntos, limpiar resultados previos del gráfico y tabla
            self._sh_fit_I0 = None
            self._sh_fit_mu = None
            self._sh_fit_B = None
            self._update_physics_calculations()

    def _clear_shielding_points(self):
        self.sh_points = []
        self._sh_fit_I0 = None
        self._sh_fit_mu = None
        self._sh_fit_B = None
        self._update_shielding_table()
        self._update_physics_calculations()

    def _update_shielding_table(self):
        for row in self.sh_tree.get_children():
            self.sh_tree.delete(row)
        for i, pt in enumerate(self.sh_points):
            tag = "even" if i % 2 == 0 else "odd"
            self.sh_tree.insert("", "end", iid=str(i), values=(pt[0], f"{pt[1]:.1f}"), tags=(tag,))

    def _run_shielding_fit(self):
        if len(self.sh_points) < 4:
            messagebox.showwarning("Datos Insuficientes", "Se requieren al menos 4 puntos experimentales para ajustar la atenuación.")
            return

        xs = [p[0] for p in self.sh_points]
        ys = [p[1] for p in self.sh_points]

        bg_fixed = 25.0
        if self.decay_bg_check_var.get():
            try:
                bg_fixed = float(self.decay_bg_val_var.get())
            except ValueError:
                pass

        try:
            I0, err_I0, mu, err_mu, B, err_B, r2, chi2_red, hvl_exp, tvl_exp = science_utils.fit_multi_thickness_attenuation(xs, ys, bg_fixed)
            
            self._sh_fit_I0 = I0
            self._sh_fit_mu = mu
            self._sh_fit_B = B

            # Mostrar resultados
            self.sh_res_lbls["mu"].configure(text=f"{mu:.4f} ± {err_mu:.4f} cm⁻¹")
            self.sh_res_lbls["hvl"].configure(text=f"{hvl_exp:.3f} cm")
            self.sh_res_lbls["tvl"].configure(text=f"{tvl_exp:.3f} cm")
            self.sh_res_lbls["i0"].configure(text=f"{I0:.1f} ± {err_I0:.1f} CPM")
            self.sh_res_lbls["r2"].configure(text=f"{r2:.4f}")
            
            # Buscar isótopo
            mat = self.sh_mat_var.get()
            sh_matches = science_utils.identify_isotope_by_shielding(mat, hvl_exp, I0, I0*0.5) # dummy para re-utilizar busqueda
            
            # Búsqueda directa por HVL en base de datos
            matches = []
            if mat in science_utils.SHIELDING_DATA:
                for energy, hvl_theo in science_utils.SHIELDING_DATA[mat].items():
                    err = abs(hvl_exp - hvl_theo) / hvl_theo
                    if err <= 0.55:
                        matches.append((energy, err * 100.0))
            matches.sort(key=lambda x: x[1])
            
            if matches:
                iso_str = f"{matches[0][0]} (err {matches[0][1]:.1f}%)"
            else:
                iso_str = "Desconocido (sin coincidencia)"
            
            self.sh_res_lbls["isotope"].configure(text=iso_str)
            
            # Forzar actualización de gráficos
            self._update_physics_calculations()
            messagebox.showinfo("Ajuste Exponencial", f"Ajuste Beer-Lambert completado con R² = {r2:.4f}.\nCoeficiente lineal μ = {mu:.3f} cm⁻¹.")
        except Exception as e:
            messagebox.showerror("Error de ajuste", f"No se pudo resolver la regresión exponencial:\n{e}")


    # ── MÉTODOS DE ALTA TENSIÓN (HV) ─────────────────────────────────────────

    def _refresh_hv_telemetry(self):
        if not self.serial.connected:
            return
            
        def run_read():
            freq = self.serial.get_tube_hv_frequency()
            duty = self.serial.get_tube_hv_duty_cycle()
            
            def update_ui():
                self.hv_freq_var.set(f"{freq} Hz" if freq is not None else "Desconectado")
                self.hv_duty_var.set(f"{duty:.1f}%" if duty is not None else "—")
                if freq is not None:
                    self.hv_set_freq_var.set(str(freq))
                    
            self.after(0, update_ui)
            
        threading.Thread(target=run_read, daemon=True).start()

    def _apply_hv_frequency(self):
        if not self.serial.connected:
            messagebox.showwarning("Conexión", "El detector debe estar conectado.")
            return
            
        try:
            freq = int(self.hv_set_freq_var.get())
            if freq < 100 or freq > 100000:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Frecuencia Inválida", "La frecuencia debe ser un número entero entre 100 y 100000 Hz.")
            return
            
        if not messagebox.askyesno("Confirmar Alta Tensión",
                                   "⚠️ ADVERTENCIA: Modificar la frecuencia PWM de oscilación de la placa base cambiará la alta tensión (voltaje físico) aplicada al tubo Geiger-Müller.\n\n¿Desea continuar de todos modos?"):
            return
            
        def run_set():
            success = self.serial.set_tube_hv_frequency(freq)
            def update():
                if success:
                    messagebox.showinfo("Frecuencia Cambiada", f"Frecuencia ajustada con éxito a {freq} Hz.")
                    self._refresh_hv_telemetry()
                else:
                    messagebox.showerror("Error de Comunicación", "El dispositivo no confirmó el comando de frecuencia.")
            self.after(0, update)
            
        threading.Thread(target=run_set, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()