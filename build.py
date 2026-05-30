import os
import subprocess
import sys

def build():
    # Asegurar que todas las dependencias necesarias estén instaladas en este entorno de Python
    dependencies = {
        "PyInstaller": "pyinstaller",
        "customtkinter": "customtkinter",
        "matplotlib": "matplotlib",
        "serial": "pyserial",
        "numpy": "numpy"
    }

    for module_name, pip_name in dependencies.items():
        try:
            __import__(module_name)
        except ImportError:
            print(f"La dependencia '{pip_name}' no está instalada. Instalándola ahora...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
    
    import customtkinter


    # Obtener la ruta de instalación de customtkinter para copiar sus recursos (temas, fuentes, etc.)
    ctk_path = os.path.dirname(customtkinter.__file__)
    print(f"Ruta de CustomTkinter encontrada: {ctk_path}")

    # Limpiar carpeta temporal previa 'build' para forzar a PyInstaller a re-analizar todas las dependencias
    import shutil
    if os.path.exists("build"):
        print("Borrando caché de compilación previa en 'build'...")
        try:
            shutil.rmtree("build")
        except Exception as e:
            print(f"Advertencia: No se pudo borrar la carpeta 'build' ({e}). Se continuará de todos modos.")

    # Asegurar que el ejecutable anterior no esté ejecutándose y bloquear el archivo
    exe_path = os.path.join("dist", "GC01_RadPro_Monitor.exe")
    if os.path.exists(exe_path):
        print("Intentando eliminar el archivo ejecutable anterior en 'dist'...")
        try:
            os.remove(exe_path)
        except PermissionError:
            print("⚠️ El archivo ejecutable está bloqueado o en ejecución. Intentando cerrarlo...")
            if sys.platform.startswith("win"):
                try:
                    subprocess.run(["taskkill", "/F", "/IM", "GC01_RadPro_Monitor.exe"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    import time
                    time.sleep(1) # Esperar a que Windows libere el handle del archivo
                    os.remove(exe_path)
                    print("¡Ejecutable anterior cerrado y eliminado correctamente!")
                except Exception as e:
                    print(f"❌ Error crítico: No se pudo eliminar el ejecutable en 'dist' ({e}).")
                    print("Por favor, cierra la aplicación 'GC01_RadPro_Monitor.exe' desde el Administrador de Tareas y vuelve a intentarlo.")
                    sys.exit(1)
            else:
                sys.exit(1)
        except Exception as e:
            print(f"Advertencia: No se pudo verificar o eliminar el ejecutable anterior: {e}")


    # Definir los argumentos de PyInstaller
    # - '--onefile': empaqueta todo en un único archivo ejecutable .exe
    # - '--windowed': oculta la ventana negra de la consola detrás de la interfaz gráfica
    # - '--clean': limpia la caché de PyInstaller antes de compilar
    # - '--add-data': incluye los assets de customtkinter
    args = [
        'main.py',
        '--name=GC01_RadPro_Monitor',
        '--onefile',
        '--windowed',
        '--clean',
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
