# ☢️ GC-01 Rad Pro — Monitor de Radiación

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Firmware: Rad Pro](https://img.shields.io/badge/Firmware-Rad%20Pro-orange.svg)](https://github.com/GraveDesign/RadPro)

Una aplicación de escritorio moderna y de alto rendimiento diseñada para monitorear, registrar y analizar lecturas de radiación en tiempo real utilizando el contador Geiger **FNIRSI GC-01** flasheado con el firmware open-source **Rad Pro**.

La aplicación proporciona visualización gráfica, procesamiento estadístico avanzado con filtrado digital (SMA) e incertidumbre estocástica de Poisson, exportación de datos y sincronización horaria.

---

## 🚀 Características Principales

*   **Monitoreo en Tiempo Real**: Visualización instantánea de la tasa de conteo en CPM (Counts Per Minute) y la tasa de dosis equivalente en $\mu\text{Sv/h}$.
*   **Gauges Circulares Dinámicos**: Indicadores analógicos diseñados a medida que cambian de color de forma dinámica según el nivel de radiación (Fondo natural $\rightarrow$ Normal $\rightarrow$ Elevado $\rightarrow$ Alto $\rightarrow$ Peligroso).
*   **Análisis Estadístico Avanzado**:
    *   **Lectura Cruda**: Graficación del ruido estocástico de la radiación en tiempo real.
    *   **Media Móvil Simple (SMA)**: Filtro digital con ventana deslizante para detectar tendencias reales de radiación limpia.
    *   **Incertidumbre de Poisson ($\pm1\sigma$)**: Banda de desviación estándar proyectada matemáticamente ($\sigma = \sqrt{\text{Media}}$) en base a los eventos registrados.
    *   **Métricas detalladas**: CPM promedio, CPM máximo, dosis acumulada en $\mu\text{Sv}$, proyección de dosis anualizada ($\text{mSv/año}$), error estadístico e historial de pulsos totales.
*   **Registro de Datos (Data Logger)**: Tabla integrada y detallada con almacenamiento de cada muestra (Hora, CPM, $\mu\text{Sv/h}$, Pulsos, Voltaje de batería y Nivel de peligro).
*   **Exportación a CSV**: Guarda el historial completo de tu sesión para análisis posteriores en hojas de cálculo o herramientas externas.
*   **Sincronización Horaria**: Sincroniza en un solo clic el reloj en tiempo real (RTC) de tu FNIRSI GC-01 con la hora exacta de tu computadora.
*   **Interfaz Premium**: Diseño oscuro (Dark Mode) responsivo y estilizado, construido con fuentes modernas (`Outfit` y `JetBrains Mono`).

---

## 🛠️ Requisitos de Hardware y Configuración

Para conectar el dispositivo correctamente:

1.  **Firmware Rad Pro**: Su FNIRSI GC-01 debe estar ejecutando el firmware alternativo **Rad Pro** (disponible en GitHub). El firmware de fábrica de FNIRSI no soporta el protocolo de comunicación serial de datos en tiempo real.
2.  **Cable de Datos**: Use un cable USB-C de buena calidad que soporte transmisión de datos (algunos cables solo sirven para carga).
3.  **Drivers**: Asegúrese de tener instalado el driver para el chip serial **CH340** (común en este dispositivo). Generalmente Windows lo instala de forma automática.
4.  **Configuración del Dispositivo**:
    *   Encienda el GC-01.
    *   Vaya a **Ajustes** (Settings) $\rightarrow$ **Modo datos** (Data mode) $\rightarrow$ Seleccione **Activado** (o el modo que habilita la salida serial de Rad Pro).

---

## 💻 Requisitos de Software e Instalación

### 1. Clonar el repositorio
```bash
git clone https://github.com/wTHE-HUNTERw/GC01_APP.git
cd GC01_APP
```

### 2. Instalar dependencias
La aplicación utiliza Python 3.8 o superior. Instale las librerías necesarias ejecutando:
```bash
pip install -r requirements.txt
```

Las dependencias principales son:
*   [CustomTkinter](https://github.com/tomsimpson/CustomTkinter) - Interfaz gráfica moderna y responsiva.
*   [Matplotlib](https://matplotlib.org/) - Graficación científica en tiempo real.
*   [PySerial](https://github.com/pyserial/pyserial) - Comunicación a través del puerto COM.
*   [NumPy](https://numpy.org/) - Cálculos matemáticos y estadísticos rápidos.

---

## 🎮 Instrucciones de Uso

1.  **Ejecutar la aplicación**:
    ```bash
    python main.py
    ```
2.  **Conexión**:
    *   Haga clic en el botón de actualizar (↺) al lado de "Puerto COM" para buscar dispositivos conectados.
    *   Seleccione el puerto COM correspondiente a su CH340 / GC-01 en el menú desplegable.
    *   Haga clic en **⚡ Conectar**.
    *   Una vez conectado, la aplicación detectará automáticamente el tipo de tubo Geiger instalado, el hardware, la versión del firmware, la sensibilidad calibrada y el voltaje actual de la batería del dispositivo.
3.  **Iniciar Adquisición**:
    *   Seleccione el intervalo de muestreo deseado (1s, 2s, 5s o 10s).
    *   Presione **▶ Iniciar** para comenzar a graficar, almacenar y procesar las lecturas en tiempo real.
4.  **Sincronizar Reloj (Opcional)**:
    *   Haga clic en **⏱ Sincronizar Reloj** para ajustar la hora interna del dispositivo con la de su computadora actual.
5.  **Detener y Guardar**:
    *   Puede pausar la captura en cualquier momento presionando **⏸ Pausar**.
    *   Haga clic en **⬇ Exportar CSV** para guardar los datos recopilados en un archivo.
    *   Haga clic en **🗑 Limpiar datos** para restablecer las estadísticas y limpiar el gráfico/historial para una nueva medición.

---

## 📦 Compilación a Ejecutable (.exe)

Para crear un archivo `.exe` independiente que puedas ejecutar en cualquier computadora con Windows sin necesidad de tener Python instalado:

1.  **Ejecutar el script de compilación automática**:
    Hemos incluido el script [build.py](file:///c:/Users/erick/OneDrive/Escritorio/Aplicacion gc01/GC01_APP/build.py) que instala automáticamente `pyinstaller` (si no está presente) y compila el proyecto incluyendo correctamente todos los assets visuales y de configuración de `customtkinter`:
    ```bash
    python build.py
    ```
2.  **Resultado**:
    Una vez terminado el proceso, encontrarás el ejecutable en:
    `dist/GC01_RadPro_Monitor.exe`

---

## 🏷️ Cómo crear una Release en GitHub

Para distribuir tu archivo `.exe` compilado a otros usuarios a través de la sección de descargas de GitHub:

1.  **Sube los últimos cambios** de tu código a GitHub:
    ```bash
    git add .
    git commit -m "Agregar script de compilación y actualizar instrucciones"
    git push origin main
    ```
2.  Ingresa a la página de tu repositorio en GitHub: [https://github.com/wTHE-HUNTERw/GC01_APP](https://github.com/wTHE-HUNTERw/GC01_APP).
3.  En el panel derecho, haz clic en **Releases** $\rightarrow$ **Create a new release** (Crear nueva release).
4.  **Tag version (Etiqueta)**: Asigna una versión como por ejemplo `v1.0.0` y crea la etiqueta.
5.  **Release title (Título)**: Dale un nombre descriptivo, como por ejemplo `GC-01 Rad Pro Monitor v1.0.0`.
6.  **Description (Descripción)**: Escribe una breve descripción de las características principales de esta versión.
7.  **Adjuntar el Ejecutable**:
    Arrastra y suelta tu archivo `GC01_RadPro_Monitor.exe` (ubicado dentro de la carpeta `dist/`) en el área de carga que dice *"Attach binaries by dropping them here..."*.
8.  Haz clic en el botón verde **Publish release** (Publicar release).

¡Listo! Cualquiera podrá descargar directamente el archivo ejecutable listo para usar desde GitHub.

---

## 📁 Estructura del Código

*   `main.py`: Punto de entrada de la aplicación. Contiene el bucle de actualización, el hilo de comunicación de fondo (polling loop), la integración de la gráfica con matplotlib y la lógica de la ventana principal.
*   `serial_manager.py`: Controlador de comunicación serial. Implementa el protocolo Rad Pro usando comandos `GET` y `SET` sobre una conexión serial protegida mediante locks para evitar colisiones de hilos.
*   `widgets.py`: Componentes personalizados de la interfaz de usuario, incluyendo el control del medidor semicircular (`ArcGauge`), mapeos de color de nivel de peligro e interpolaciones dinámicas para alertas visuales.

---

## 📄 Licencia

Este proyecto está bajo la Licencia **MIT**. Consulte el archivo [LICENSE](LICENSE) para obtener más información.

---

*Desarrollado con ❤️ para la comunidad de entusiastas de la física y la radiación.*
