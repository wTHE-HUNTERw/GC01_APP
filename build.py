import os
import subprocess
import sys

def build():
    # Asegurar que las dependencias necesarias estén instaladas
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller no está instalado. Instalándolo ahora...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    try:
        import customtkinter
    except ImportError:
        print("customtkinter no está instalado. Instalándolo ahora...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter"])
        import customtkinter

    # Obtener la ruta de instalación de customtkinter para copiar sus recursos (temas, fuentes, etc.)
    ctk_path = os.path.dirname(customtkinter.__file__)
    print(f"Ruta de CustomTkinter encontrada: {ctk_path}")

    # Definir los argumentos de PyInstaller
    # - '--onefile': empaqueta todo en un único archivo executable .exe
    # - '--windowed': oculta la ventana negra de la consola detrás de la interfaz gráfica
    # - '--add-data': incluye los assets de customtkinter
    args = [
        'main.py',
        '--name=GC01_RadPro_Monitor',
        '--onefile',
        '--windowed',
        '--noconfirm',
        f'--add-data={ctk_path}{os.pathsep}customtkinter',
    ]

    print(f"Ejecutando PyInstaller con los argumentos: {args}")
    import PyInstaller.__main__
    PyInstaller.__main__.run(args)
    print("\n🎉 ¡Compilación completada con éxito!")
    print("El archivo ejecutable listo se encuentra en la carpeta: dist/GC01_RadPro_Monitor.exe")

if __name__ == "__main__":
    build()
