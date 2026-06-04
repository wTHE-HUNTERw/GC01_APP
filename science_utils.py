"""
GC-01 Rad Pro — Monitor de Radiación
Módulo de Utilidades Científicas y Cálculos Físicos.
"""
import numpy as np
import math

# ── Datos de Blindaje ────────────────────────────────────────────────────────
# HVL (Half Value Layer / Capa Hemirreductora) en cm
SHIELDING_DATA = {
    "Plomo": {
        "Cs-137 (662 keV)": 0.55,
        "Co-60 (1.25 MeV)": 1.10,
        "Am-241 (59 keV)": 0.012
    },
    "Hierro": {
        "Cs-137 (662 keV)": 1.60,
        "Co-60 (1.25 MeV)": 2.00,
        "Am-241 (59 keV)": 0.08
    },
    "Hormigón": {
        "Cs-137 (662 keV)": 4.80,
        "Co-60 (1.25 MeV)": 6.20,
        "Am-241 (59 keV)": 1.50
    },
    "Agua": {
        "Cs-137 (662 keV)": 8.20,
        "Co-60 (1.25 MeV)": 11.00,
        "Am-241 (59 keV)": 3.20
    }
}

# Presets de Tubos Geiger-Müller
# Nombre: (Área geométrica en cm2, Tiempo muerto por defecto en us)
TUBE_PRESETS = {
    "J305": (9.0, 180.0),
    "M4011": (8.8, 200.0),
    "SBM-20": (13.0, 190.0),
    "SBT-9": (4.0, 100.0),
    "Personalizado": (9.0, 180.0)
}

def get_shielding_hvl(material: str, energy: str) -> float:
    """Retorna la capa hemirreductora (HVL) en cm."""
    if material in SHIELDING_DATA and energy in SHIELDING_DATA[material]:
        return SHIELDING_DATA[material][energy]
    return 1.0

def calculate_transmission(thickness_cm: float, hvl_cm: float) -> tuple[float, float]:
    """Retorna (fracción de transmisión I/I_0, atenuación porcentual)."""
    if hvl_cm <= 0:
        return 0.0, 100.0
    transmission = math.pow(2, -thickness_cm / hvl_cm)
    attenuation_pct = (1.0 - transmission) * 100.0
    return transmission, attenuation_pct

# ── Corrección de Tiempo Muerto ──────────────────────────────────────────────
def correct_dead_time(measured_cpm: float, dead_time_us: float) -> tuple[float, float]:
    """
    Corrige la tasa medida por tiempo muerto (modelo no paralizable).
    Retorna (cpm_corregido, coincidencia_loss_pct).
    """
    if dead_time_us <= 0 or measured_cpm <= 0:
        return measured_cpm, 0.0
    
    m = measured_cpm / 60.0  # Medido en CPS
    tau = dead_time_us * 1e-6  # Tiempo muerto en segundos
    
    # Evitar indeterminación o desbordamiento al acercarse a la saturación teórica (m * tau = 1)
    if m * tau >= 0.98:
        r = m / 0.02
        loss_pct = 98.0
    else:
        r = m / (1.0 - m * tau)
        loss_pct = (m * tau) * 100.0
        
    return r * 60.0, loss_pct

def get_saturation_limit(dead_time_us: float) -> float:
    """Retorna la tasa de saturación teórica en CPM."""
    if dead_time_us <= 0:
        return float("inf")
    tau = dead_time_us * 1e-6
    return (1.0 / tau) * 60.0

# ── Estimación de Actividad de Fuente ─────────────────────────────────────────
def estimate_source_activity(cpm: float, bg_cpm: float, distance_cm: float, tube_area_cm2: float, efficiency_percent: float) -> tuple[float, float]:
    """
    Estima la actividad de una fuente puntual basándose en geometría y ángulo sólido.
    Retorna (actividad_bq, actividad_uci).
    """
    net_cpm = max(0.0, cpm - bg_cpm)
    net_cps = net_cpm / 60.0
    
    if distance_cm <= 0 or tube_area_cm2 <= 0 or efficiency_percent <= 0:
        return 0.0, 0.0
        
    # Fracción de ángulo sólido F = Area_tubo / (4 * pi * d^2)
    F = tube_area_cm2 / (4.0 * math.pi * (distance_cm ** 2))
    
    eff_frac = efficiency_percent / 100.0
    
    if F * eff_frac <= 0:
        return 0.0, 0.0
        
    activity_bq = net_cps / (F * eff_frac)
    activity_uci = activity_bq / 37000.0
    
    return activity_bq, activity_uci

# ── Ajuste No Lineal de Decaimiento Radiactivo ───────────────────────────────
def fit_exponential_decay(t, y, bg_fixed=None):
    """
    Ajusta una curva exponencial N(t) = A * e^(-lambda * t) + B.
    Usa el algoritmo Levenberg-Marquardt implementado sobre NumPy.
    
    Parámetros:
        t: array de tiempos (en segundos)
        y: array de CPM medidos
        bg_fixed: si no es None, fija el fondo B a este valor.
        
    Retorna:
        A, err_A, lam, err_lam, B, err_B, r_squared, chi2_red
    """
    t = np.array(t, dtype=float)
    y = np.array(y, dtype=float)
    n = len(t)
    if n < 4:
        raise ValueError("Se requieren al menos 4 puntos para realizar el ajuste.")
        
    # 1. Estimación inicial de parámetros
    if bg_fixed is not None:
        B = float(bg_fixed)
    else:
        # Se estima como el percentil 10 para aproximar el fondo natural
        B = float(np.percentile(y, 10))
        
    dy = y - B
    mask = dy > 0.1
    if np.sum(mask) < 3:
        # Fallback si el fondo estimado es demasiado alto
        B = float(np.min(y) * 0.5)
        dy = y - B
        mask = dy > 0.1
        if np.sum(mask) < 3:
            B = 0.0
            dy = y
            mask = dy > 0
            
    t_m = t[mask]
    dy_m = dy[mask]
    
    try:
        # Ajuste lineal en espacio logarítmico: ln(y - B) = ln(A) - lambda * t
        p = np.polyfit(t_m, np.log(dy_m), 1)
        lam = -float(p[0])
        A = float(np.exp(p[1]))
    except Exception:
        A = float(np.max(y) - B)
        lam = 0.01
        
    if lam <= 0:
        lam = 1e-4
    if A <= 0:
        A = 1.0
        
    # Parámetros activos en el ajuste no lineal
    if bg_fixed is not None:
        params = np.array([A, lam], dtype=float)
    else:
        params = np.array([A, lam, B], dtype=float)
        
    max_iter = 100
    tol = 1e-6
    damping = 1e-2
    
    J = None
    
    for _ in range(max_iter):
        A_curr = params[0]
        lam_curr = params[1]
        
        if bg_fixed is not None:
            B_curr = B
            y_pred = A_curr * np.exp(-lam_curr * t) + B_curr
            r = y_pred - y
            J = np.column_stack([
                np.exp(-lam_curr * t),
                -A_curr * t * np.exp(-lam_curr * t)
            ])
        else:
            B_curr = params[2]
            y_pred = A_curr * np.exp(-lam_curr * t) + B_curr
            r = y_pred - y
            J = np.column_stack([
                np.exp(-lam_curr * t),
                -A_curr * t * np.exp(-lam_curr * t),
                np.ones_like(t)
            ])
            
        JTJ = J.T @ J
        JTJ += damping * np.eye(JTJ.shape[0]) * np.maximum(1e-5, np.diag(JTJ))
        
        try:
            delta = np.linalg.solve(JTJ, J.T @ r)
        except np.linalg.LinAlgError:
            break
            
        params_new = params - delta
        
        # Restricciones físicas básicas
        params_new[0] = max(1e-3, params_new[0]) # A > 0
        params_new[1] = max(1e-8, params_new[1]) # lambda > 0
        if bg_fixed is None:
            params_new[2] = max(0.0, params_new[2]) # B >= 0
            
        if np.linalg.norm(delta) < tol:
            params = params_new
            break
        params = params_new
        
    A = float(params[0])
    lam = float(params[1])
    if bg_fixed is None:
        B = float(params[2])
        
    # Cálculo final e incertidumbres
    y_pred = A * np.exp(-lam * t) + B
    residuals = y - y_pred
    dof = n - len(params)
    
    err_A = 0.0
    err_lam = 0.0
    err_B = 0.0
    
    if dof > 0:
        s_sq = np.sum(residuals**2) / dof
        try:
            if bg_fixed is not None:
                J_final = np.column_stack([
                    np.exp(-lam * t),
                    -A * t * np.exp(-lam * t)
                ])
            else:
                J_final = np.column_stack([
                    np.exp(-lam * t),
                    -A * t * np.exp(-lam * t),
                    np.ones_like(t)
                ])
            cov = np.linalg.inv(J_final.T @ J_final) * s_sq
            errors = np.sqrt(np.diagonal(cov))
            err_A = float(errors[0])
            err_lam = float(errors[1])
            if bg_fixed is None:
                err_B = float(errors[2])
        except np.linalg.LinAlgError:
            pass
            
    # Estadísticos del ajuste
    ss_res = np.sum(residuals**2)
    mean_y = np.mean(y)
    ss_tot = np.sum((y - mean_y)**2)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    
    # Chi-cuadrado reducido para Poisson
    chi2_red = np.sum((residuals**2) / np.maximum(y_pred, 1.0)) / dof if dof > 0 else 0.0
    
    return A, err_A, lam, err_lam, B, err_B, r_squared, chi2_red

# ── Base de Datos de Isótopos Comunes ────────────────────────────────────────
# (Nombre, Vida media teórica en segundos, Descripción científica)
DECAY_ISOTOPES = [
    ("Plata-110 (Ag-110)", 24.6, "Activación neutrónica de Plata (decay beta muy rápido)"),
    ("Aluminio-28 (Al-28)", 134.4, "Activación neutrónica de Aluminio (decay beta/gamma)"),
    ("Oxígeno-15 (O-15)", 122.2, "Isótopo PET de vida ultra corta (medicina nuclear)"),
    ("Bario-137m (Ba-137m)", 153.0, "Isómero metaestable hijo del Cs-137 (emisor gamma 662 keV)"),
    ("Plata-108 (Ag-108)", 142.2, "Activación neutrónica de Plata (vida media media)"),
    ("Polonio-218 (Po-218)", 186.0, "Cadena del Uranio-238 (primer descendiente alfa del Rn-222)"),
    ("Nitrógeno-13 (N-13)", 598.0, "Isótopo PET usado en perfusión miocárdica"),
    ("Carbono-11 (C-11)", 1218.0, "Isótopo PET de medicina nuclear (marcador orgánico)"),
    ("Bismuto-214 (Bi-214)", 1194.0, "Cadena del Uranio-238 (procedente de hijas de Radón)"),
    ("Plomo-214 (Pb-214)", 1608.0, "Cadena del Uranio-238 (descendiente beta de Radón)"),
    ("Indio-116m (In-116m)", 3252.0, "Activación neutrónica clásica de Indio (física experimental)"),
    ("Flúor-18 (F-18)", 6586.0, "Isótopo PET más común, usado en FDG para oncología"),
    ("Tecnecio-99m (Tc-99m)", 21624.0, "Isótopo médico por excelencia para gammagrafías SPECT"),
    ("Plomo-212 (Pb-212)", 38304.0, "Cadena del Torio-232 / Depósito activo de descendientes de Torón"),
    ("Potasio-42 (K-42)", 44496.0, "Decaimiento beta de alta energía usado en estudios biológicos"),
    ("Sodio-24 (Na-24)", 53820.0, "Activación de Sodio por neutrones (radiotrazador industrial)"),
    ("Yodo-131 (I-131)", 692928.0, "Tratamiento de tiroides / Fisión nuclear (vida media 8.02 días)")
]

def identify_isotope_by_half_life(t_half_seconds: float) -> list[dict]:
    """
    Compara la vida media medida con la base de datos y retorna
    los candidatos que se desvíen menos del 45%, ordenados por menor error.
    """
    matches = []
    if t_half_seconds <= 0:
        return []
    for name, t_theo, desc in DECAY_ISOTOPES:
        err = abs(t_half_seconds - t_theo) / t_theo
        if err <= 0.45:
            matches.append({
                "name": name,
                "t_theo": t_theo,
                "error_pct": err * 100.0,
                "desc": desc
            })
    matches.sort(key=lambda x: x["error_pct"])
    return matches

def identify_isotope_by_shielding(material: str, thickness_cm: float, i0: float, i: float) -> list[dict]:
    """
    Calcula el HVL experimental basándose en la atenuación de dosis medida
    y propone los isótopos emisores correspondientes.
    """
    if i0 <= 0 or i <= 0 or i >= i0 or thickness_cm <= 0:
        return []
        
    ratio = i / i0
    try:
        hvl_exp = -thickness_cm / math.log2(ratio)
    except (ValueError, ZeroDivisionError):
        return []
        
    matches = []
    if material in SHIELDING_DATA:
        for energy, hvl_theo in SHIELDING_DATA[material].items():
            err = abs(hvl_exp - hvl_theo) / hvl_theo
            if err <= 0.55:  # Margen experimental amplio para experimentos de blindaje
                matches.append({
                    "energy": energy,
                    "hvl_theo": hvl_theo,
                    "hvl_exp": hvl_exp,
                    "error_pct": err * 100.0
                })
    matches.sort(key=lambda x: x["error_pct"])
    return matches


# ── Cálculos Físicos y Estadísticos Avanzados (Añadido) ─────────────────────

def incomplete_gamma_lower(a: float, x: float) -> float:
    """
    Función Gamma incompleta regularizada inferior P(a, x) = gamma(a, x) / Gamma(a).
    Utiliza expansión en serie para x < a + 1 y fracción continua (método de Lentz) para x >= a + 1.
    """
    if x <= 0:
        return 0.0
    if x < a + 1.0:
        # Expansión en serie
        sum_val = 1.0 / a
        term = 1.0 / a
        for n in range(1, 150):
            term = term * x / (a + n)
            sum_val += term
            if abs(term) < abs(sum_val) * 1e-12:
                break
        return sum_val * math.exp(a * math.log(x) - x - math.lgamma(a))
    else:
        # Fracción continua para Q(a, x) = Gamma(a, x) / Gamma(a)
        # P(a, x) = 1.0 - Q(a, x)
        tiny = 1e-30
        b = x + 1.0 - a
        c = 1.0 / tiny
        d = 1.0 / b
        h = d
        for i in range(1, 150):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if abs(d) < tiny:
                d = tiny
            c = b + an / c
            if abs(c) < tiny:
                c = tiny
            d = 1.0 / d
            del_val = d * c
            h *= del_val
            if abs(del_val - 1.0) < 1e-12:
                break
        q = math.exp(a * math.log(x) - x - math.lgamma(a)) * h
        return max(0.0, min(1.0, 1.0 - q))

def chi2_p_value(chi2: float, dof: int) -> float:
    """Retorna el p-valor (survival function) para un estadístico Chi-Cuadrado y grados de libertad."""
    if chi2 < 0 or dof <= 0:
        return 1.0
    # p = Q(dof/2, chi2/2) = 1 - P(dof/2, chi2/2)
    p_lower = incomplete_gamma_lower(dof / 2.0, chi2 / 2.0)
    return max(0.0, min(1.0, 1.0 - p_lower))

def poisson_chi2_test(counts) -> dict | None:
    """
    Realiza una prueba de bondad de ajuste Chi-Cuadrado para verificar si
    los conteos observados siguen una distribución de Poisson.
    Combina de manera iterativa los bins adyacentes para asegurar que la frecuencia esperada E_i >= 5.0.
    
    Retorna:
        dict con:
            - 'mean': media de la distribución (lambda)
            - 'chi2': estadístico Chi-Cuadrado calculado
            - 'dof': grados de libertad
            - 'p_value': p-valor de la prueba
            - 'bins': lista de (etiqueta_rango, observado, esperado)
            - 'passed': booleano indicando si pasa el test (p-valor >= 0.05)
    """
    counts = np.array(counts, dtype=int)
    n = len(counts)
    if n < 10:  # Pocas muestras para significancia estadística
        return None
        
    mean_c = np.mean(counts)
    if mean_c <= 0:
        return None
        
    max_val = np.max(counts)
    obs_freq = np.zeros(max_val + 1)
    for c in counts:
        obs_freq[c] += 1
        
    exp_prob = np.zeros(max_val + 1)
    for k in range(max_val + 1):
        ln_p = k * math.log(mean_c) - mean_c - math.lgamma(k + 1)
        exp_prob[k] = math.exp(ln_p)
        
    # Asignar la probabilidad acumulada de la cola superior al último elemento
    tail_prob = 1.0 - np.sum(exp_prob[:-1]) if len(exp_prob) > 1 else 1.0
    exp_prob[-1] = max(exp_prob[-1], tail_prob)
    
    exp_freq = exp_prob * n
    
    # Agrupación de bins para asegurar E_i >= 5.0
    grouped_obs = []
    grouped_exp = []
    grouped_labels = []
    
    curr_obs = 0.0
    curr_exp = 0.0
    start_k = 0
    
    for k in range(max_val + 1):
        curr_obs += obs_freq[k]
        curr_exp += exp_freq[k]
        
        if curr_exp >= 5.0 or k == max_val:
            # Si es el último bin y aún es < 5, se fusiona con el anterior si existe
            if k == max_val and curr_exp < 5.0 and len(grouped_exp) > 0:
                grouped_obs[-1] += curr_obs
                grouped_exp[-1] += curr_exp
                label_prev = grouped_labels[-1]
                if "-" in label_prev:
                    label_parts = label_prev.split("-")
                    grouped_labels[-1] = f"{label_parts[0]}+"
                else:
                    grouped_labels[-1] = f"{label_prev}+"
            else:
                grouped_obs.append(curr_obs)
                grouped_exp.append(curr_exp)
                if start_k == k:
                    grouped_labels.append(f"{k}")
                else:
                    grouped_labels.append(f"{start_k}-{k}")
                
            curr_obs = 0.0
            curr_exp = 0.0
            start_k = k + 1
            
    num_bins = len(grouped_exp)
    # Grados de libertad = K - 1 - 1 = K - 2 (puesto que se estima el parámetro de la media de Poisson)
    dof = num_bins - 2
    
    if dof <= 0:
        return None
        
    chi2_stat = 0.0
    bins_info = []
    for i in range(num_bins):
        o = grouped_obs[i]
        e = grouped_exp[i]
        chi2_stat += ((o - e) ** 2) / e
        bins_info.append((grouped_labels[i], o, e))
        
    p_val = chi2_p_value(chi2_stat, dof)
    
    return {
        "mean": mean_c,
        "chi2": chi2_stat,
        "dof": dof,
        "p_value": p_val,
        "bins": bins_info,
        "passed": p_val >= 0.05
    }

def parse_datalog_sessions(raw_response: str) -> list[list[dict]]:
    """
    Parsea la respuesta serial de 'GET datalog' en una lista de sesiones.
    Cada sesión es una lista de dicts con:
    - 'time': timestamp UNIX (int)
    - 'pulseCount': conteo acumulado de pulsos (int)
    - 'dt': segundos transcurridos en el intervalo (int)
    - 'dp': pulsos acumulados en el intervalo (int)
    - 'cpm': tasa instantánea calculada en CPM (float)
    """
    if not raw_response or raw_response.strip() == "":
        return []
    
    if raw_response.startswith("OK"):
        raw_response = raw_response[2:].strip()
        
    sessions = []
    # Rad Pro separa las sesiones de datalog con ";;"
    segments = raw_response.split(";;")
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        session_records = []
        entries = segment.split(";")
        for entry in entries:
            entry = entry.strip()
            if not entry or entry.startswith("time"):
                continue
            if "," in entry:
                parts = entry.split(",")
                try:
                    t = int(parts[0])
                    p = int(parts[1])
                    session_records.append({"time": t, "pulseCount": p})
                except (ValueError, IndexError):
                    continue
        
        session_records.sort(key=lambda x: x["time"])
        
        # Calcular tasas incrementales (CPM real)
        processed_records = []
        for i, rec in enumerate(session_records):
            if i == 0:
                rec["dt"] = 0
                rec["dp"] = 0
                rec["cpm"] = 0.0
            else:
                prev = session_records[i - 1]
                dt = rec["time"] - prev["time"]
                dp = rec["pulseCount"] - prev["pulseCount"]
                rec["dt"] = dt
                rec["dp"] = dp
                if dt > 0 and dp >= 0:
                    rec["cpm"] = (dp / dt) * 60.0
                else:
                    rec["cpm"] = 0.0
            processed_records.append(rec)
            
        if len(processed_records) > 0:
            if len(processed_records) > 1:
                # Estimar el CPM del primer punto igual al del segundo punto
                processed_records[0]["cpm"] = processed_records[1]["cpm"]
            sessions.append(processed_records)
            
    return sessions

def calculate_two_source_dead_time(R_b: float, R_1: float, R_2: float, R_12: float) -> tuple[float, str]:
    """
    Calcula el tiempo de resolución (tiempo muerto) utilizando el método de las dos fuentes (modelo no paralizable).
    R_b, R_1, R_2, R_12 están en CPM.
    Retorna (tau_segundos, diagnostico_str).
    """
    # Convertir tasas de CPM a CPS
    rb = R_b / 60.0
    r1 = R_1 / 60.0
    r2 = R_2 / 60.0
    r12 = R_12 / 60.0
    
    if r1 <= 0 or r2 <= 0 or r12 <= 0:
        return 0.0, "Tasas inválidas (cero o negativas)"
        
    # Ecuación exacta
    numerator = r1 * r2 - math.sqrt(max(0.0, r1 * r2 * (r12 - rb) * (r1 + r2 - r12 - rb)))
    denominator = r1 * r2 * (r12 + rb)
    
    if denominator <= 0:
        return 0.0, "Denominador cero en el cálculo"
        
    tau = numerator / denominator
    
    # Comprobar consistencia física
    if r1 + r2 < r12:
        return 0.0, "Advertencia: R1 + R2 < R12. Imposible físicamente (ruido/fluctuación estadística)."
        
    if tau < 0:
        # Usar aproximación lineal alternativa si da negativo
        tau_approx = (r1 + r2 - r12 - rb) / (r1**2 + r2**2 - r12**2 + 1e-10)
        if tau_approx > 0:
            return tau_approx, f"Valor exacto imaginario. Estimación aprox: {tau_approx*1e6:.1f} µs"
        return 0.0, "Tiempo muerto negativo obtenido. Verifique sus estadísticas."
        
    return tau, "Cálculo completado correctamente."

def fit_multi_thickness_attenuation(thicknesses: list[float], intensities: list[float], bg_fixed: float | None = None):
    """
    Ajusta una curva de atenuación exponencial Beer-Lambert: I(x) = I_0 * e^(-mu * x) + B.
    Reutiliza el solucionador Levenberg-Marquardt de fit_exponential_decay.
    Retorna:
        I0: Intensidad inicial (CPM)
        err_I0: Incertidumbre de I0
        mu: Coeficiente de atenuación lineal (cm^-1)
        err_mu: Incertidumbre de mu
        B: Fondo (CPM)
        err_B: Incertidumbre de B
        r2: R-cuadrado
        chi2_red: Chi-cuadrado reducido
        hvl: Capa hemirreductora (cm)
        tvl: Capa decirreductora (cm)
    """
    # Llamamos a fit_exponential_decay donde t es el espesor (x) e y es la intensidad (I)
    I0, err_I0, mu, err_mu, B, err_B, r2, chi2_red = fit_exponential_decay(thicknesses, intensities, bg_fixed)
    
    hvl = math.log(2) / mu if mu > 0 else float("inf")
    tvl = math.log(10) / mu if mu > 0 else float("inf")
    
    return I0, err_I0, mu, err_mu, B, err_B, r2, chi2_red, hvl, tvl

