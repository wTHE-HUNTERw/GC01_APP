"""
GC-01 Rad Pro — Monitor de Radiación
Módulo de Simulación de Espectroscopía Gamma.
"""
import numpy as np
import math

# Definición de picos de emisión teóricos para cada isótopo
# Estructura: "Isótopo": [ (Energía en keV, Intensidad Relativa) ]
ISOTOPE_PEAKS = {
    "Cs-137": [
        (661.7, 1.0),    # Fotopico principal de Cs-137 (hijo Ba-137m)
        (32.0, 0.15)     # Rayos X característicos de Bario
    ],
    "Co-60": [
        (1173.2, 1.0),   # Primer fotopico característico
        (1332.5, 0.95),  # Segundo fotopico característico
        (75.0, 0.08)     # Rayos X de Plomo (fluorescencia de blindaje común)
    ],
    "Am-241": [
        (59.5, 1.0),     # Fotopico principal de baja energía
        (17.5, 0.35)     # Rayos X de Neptunio (L-shell)
    ],
    "Ba-137m": [
        (661.7, 1.0),    # Fotopico puro de Bario metaestable sin rayos X
        (32.0, 0.12)
    ],
    "Fondo Natural": [
        (1460.8, 0.4),   # Potasio-40 (K-40) - omnipresente en el fondo
        (609.3, 0.3),    # Bismuto-214 (Radón)
        (352.0, 0.2),    # Plomo-214 (Radón)
        (186.0, 0.15)    # Radio-226
    ]
}

def generate_gamma_spectrum(isotope: str, resolution_pct: float, num_points: int = 1000) -> tuple[np.ndarray, np.ndarray]:
    """
    Genera un espectro de energía gamma simulado (intensidad vs energía en keV)
    basado en las interacciones de radiación con la materia.
    
    Parámetros:
        isotope: Nombre del isótopo ("Cs-137", "Co-60", etc.)
        resolution_pct: Resolución a 662 keV en porcentaje (FWHM %)
        num_points: Puntos en el eje X de energía
        
    Retorna:
        energias: array NumPy con el eje de energías (keV)
        intensidad: array NumPy con el espectro de cuentas por canal
    """
    # Eje de energías de 0 a 1600 keV (suficiente para Co-60 a 1332 keV)
    energias = np.linspace(5.0, 1600.0, num_points)
    intensidad = np.zeros(num_points)
    
    peaks = ISOTOPE_PEAKS.get(isotope, ISOTOPE_PEAKS["Cs-137"])
    
    # Ruido electrónico de baja energía y fondo cómico difuso
    noise = 0.04 * np.exp(-energias / 25.0) + 0.004
    intensidad += noise
    
    for ep, i_rel in peaks:
        # 1. Resolución Gaussiana dependiente de la energía (sigma ~ sqrt(E))
        # FWHM(E) = FWHM(662) * sqrt(662 / E)
        # sigma = FWHM / 2.355
        if ep <= 0:
            continue
        
        fwhm_at_e = (resolution_pct / 100.0) * ep * math.sqrt(662.0 / ep)
        sigma = fwhm_at_e / 2.355
        
        # Fotopico (Efecto Fotoeléctrico)
        photopeak = i_rel * np.exp(-0.5 * ((energias - ep) / sigma) ** 2)
        intensidad += photopeak
        
        # 2. Continuo Compton y Borde Compton
        # E_c = E_p / (1 + m_e c^2 / (2 * E_p)) = E_p / (1 + 255.5 / E_p)
        ec = ep / (1.0 + 255.5 / ep)
        
        # El continuo Compton sube un poco antes del borde y cae de forma Gaussiana suavizada por la resolución
        # Modelamos como una función Fermi-Dirac invertida para la caída suave del borde
        compton_continuum = i_rel * 0.45 * (1.0 - np.exp(-(energias / 45.0) ** 2))
        compton_drop = 1.0 / (1.0 + np.exp((energias - ec) / (1.5 * sigma)))
        
        # Multiplicamos el continuo por la caída en el borde
        compton = compton_continuum * compton_drop
        # Aseguramos que no dibuje continuo por encima del fotopico de forma absurda
        compton[energias > ep] = 0
        intensidad += compton
        
        # 3. Pico de Retrodispersión (Backscatter Peak)
        # Ocurre por dispersión a 180 grados: E_b = E_p / (1 + 2 * E_p / 511)
        eb = ep / (1.0 + (2.0 * ep) / 511.0)
        sigma_b = (resolution_pct / 100.0) * eb * math.sqrt(662.0 / eb) / 2.355
        
        backscatter = i_rel * 0.12 * np.exp(-0.5 * ((energias - eb) / sigma_b) ** 2)
        intensidad += backscatter
        
    # Normalizar para que el pico más alto esté en 1.0 (escalado conveniente para visualización)
    max_val = np.max(intensidad)
    if max_val > 0:
        intensidad = intensidad / max_val
        
    return energias, intensidad
