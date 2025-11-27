import os
import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2
import numpy as np


# ========= LÓGICA DE ESTEGANOGRAFÍA EN VIDEO =========

def calcular_capacidad_video(ruta_video):
    cap = cv2.VideoCapture(ruta_video)
    if not cap.isOpened():
        raise ValueError("No se pudo abrir el video de portada.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    cap.release()

    # Usamos solo 1 canal (B) y 1 bit (LSB) por píxel
    bits_totales = total_frames * width * height
    bytes_totales = bits_totales // 8
    return bytes_totales


def archivo_a_bits(ruta_archivo):
    """
    Empaqueta:
    [1 byte: len_nombre] [nombre utf-8] [4 bytes: len_datos] [datos]
    y devuelve un arreglo de bits (0/1).
    """
    with open(ruta_archivo, "rb") as f:
        datos = f.read()

    nombre = os.path.basename(ruta_archivo).encode("utf-8")
    if len(nombre) > 255:
        nombre = nombre[:255]
    len_nombre = len(nombre)
    len_datos = len(datos)

    cabecera = bytes([len_nombre]) + nombre + struct.pack("<I", len_datos)
    payload = cabecera + datos

    arr = np.frombuffer(payload, dtype=np.uint8)
    bits = np.unpackbits(arr)
    return bits


def bits_a_archivo(bits, carpeta_salida):
    """
    Reconstruye el archivo a partir de los bits extraídos del video.
    """
    bits = np.array(bits, dtype=np.uint8)
    if bits.size == 0:
        raise ValueError("No se encontraron datos en el video.")

    # A múltiplo de 8
    if bits.size % 8 != 0:
        padding = 8 - (bits.size % 8)
        bits = np.concatenate([bits, np.zeros(padding, dtype=np.uint8)])

    data = np.packbits(bits).tobytes()

    if len(data) < 1:
        raise ValueError("Datos insuficientes para leer el nombre del archivo.")

    len_nombre = data[0]
    indice = 1

    if len(data) < 1 + len_nombre + 4:
        raise ValueError("Cabecera incompleta o corrupta.")

    nombre_bytes = data[indice:indice + len_nombre]
    indice += len_nombre
    try:
        nombre_archivo = nombre_bytes.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        nombre_archivo = "archivo_recuperado.bin"
    
    if not nombre_archivo or not nombre_archivo.strip():
        nombre_archivo = "recuperado_sin_nombre.bin"
    
    nombre_archivo = "".join([c for c in nombre_archivo if c.isalnum() or c in "._- "])

    len_datos = struct.unpack("<I", data[indice:indice + 4])[0]
    indice += 4

    if len(data) < indice + len_datos:
        raise ValueError("Contenido incompleto o corrupto.")

    contenido = data[indice:indice + len_datos]

    if not os.path.isdir(carpeta_salida):
        os.makedirs(carpeta_salida, exist_ok=True)

    ruta_salida = os.path.join(carpeta_salida, nombre_archivo)
    with open(ruta_salida, "wb") as f:
        f.write(contenido)

    return ruta_salida, len_datos


def ocultar_archivo_en_video(ruta_video, ruta_archivo_secreto, ruta_video_salida, log_callback=None):
    capacidad = calcular_capacidad_video(ruta_video)
    bits = archivo_a_bits(ruta_archivo_secreto)
    num_bits = bits.size

    if num_bits > capacidad:
        raise ValueError(
            f"El archivo es demasiado grande para este video.\n"
            f"Capacidad aproximada: {capacidad} bytes\n"
            f"Archivo: {num_bits // 8} bytes"
        )

    cap = cv2.VideoCapture(ruta_video)
    if not cap.isOpened():
        raise ValueError("No se pudo abrir el video de portada.")

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"FFV1") # Codec sin pérdida
    if not ruta_video_salida.endswith(".avi"):
        ruta_video_salida = os.path.splitext(ruta_video_salida)[0] + ".avi"
    out = cv2.VideoWriter(ruta_video_salida, fourcc, fps, (width, height))

    bit_index = 0
    total_bits = num_bits

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if bit_index < total_bits:
            canal_b = frame[:, :, 0].flatten()

            espacio = canal_b.size
            bits_restantes = total_bits - bit_index
            bits_a_escribir = min(espacio, bits_restantes)

            segmento = canal_b[:bits_a_escribir]
            segmento = (segmento & ~1) | bits[bit_index:bit_index + bits_a_escribir]
            canal_b[:bits_a_escribir] = segmento

            frame[:, :, 0] = canal_b.reshape((height, width))

            bit_index += bits_a_escribir

        out.write(frame)

    cap.release()
    out.release()

    if bit_index < total_bits:
        raise RuntimeError("No se pudieron escribir todos los bits.")

    if log_callback:
        log_callback(f"> Oculto en: {ruta_video_salida}\n")


def extraer_archivo_de_video(ruta_video_estego, carpeta_salida, log_callback=None):
    cap = cv2.VideoCapture(ruta_video_estego)
    if not cap.isOpened():
        raise ValueError("No se pudo abrir el video con el secreto.")

    bits = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        canal_b = frame[:, :, 0].flatten()
        lsb = canal_b & 1
        bits.extend(lsb.tolist())

    cap.release()

    ruta, tam = bits_a_archivo(bits, carpeta_salida)
    if log_callback:
        log_callback(f"> Archivo recuperado: {ruta}\n> Tamaño: {tam} bytes\n")
    return ruta, tam


# ========= INTERFAZ GRÁFICA =========

class VideoStegoApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Esteganografía en video")
        self.geometry("720x520")
        self.resizable(False, False)

        self.style = ttk.Style(self)
        self.style.configure("TLabel", font=("SF Pro Text", 11))
        self.style.configure("TButton", font=("SF Pro Text", 11))
        self.style.configure("Title.TLabel", font=("SF Pro Text", 13, "bold"))

        self._crear_widgets()

    def _crear_widgets(self):
        # ----- Sección 1: Ocultar -----
        frame_ocultar = ttk.LabelFrame(self, text=" 1. OCULTAR ", padding=10)
        frame_ocultar.pack(fill="x", padx=15, pady=(15, 5))

        self.video_portada_var = tk.StringVar()
        self.archivo_secreto_var = tk.StringVar()
        self.video_salida_var = tk.StringVar()

        # Video portada
        ttk.Label(frame_ocultar, text="Video de portada:").grid(row=0, column=0, sticky="w")
        entry_vp = ttk.Entry(frame_ocultar, textvariable=self.video_portada_var, width=60)
        entry_vp.grid(row=0, column=1, padx=5, pady=3, sticky="we")
        ttk.Button(frame_ocultar, text="…", width=3,
                   command=self.seleccionar_video_portada).grid(row=0, column=2, padx=2)

        # Archivo secreto
        ttk.Label(frame_ocultar, text="Archivo secreto:").grid(row=1, column=0, sticky="w")
        entry_as = ttk.Entry(frame_ocultar, textvariable=self.archivo_secreto_var, width=60)
        entry_as.grid(row=1, column=1, padx=5, pady=3, sticky="we")
        ttk.Button(frame_ocultar, text="…", width=3,
                   command=self.seleccionar_archivo_secreto).grid(row=1, column=2, padx=2)

        # Video salida
        ttk.Label(frame_ocultar, text="Video de salida:").grid(row=2, column=0, sticky="w")
        entry_vs = ttk.Entry(frame_ocultar, textvariable=self.video_salida_var, width=60)
        entry_vs.grid(row=2, column=1, padx=5, pady=3, sticky="we")
        ttk.Button(frame_ocultar, text="…", width=3,
                   command=self.seleccionar_video_salida).grid(row=2, column=2, padx=2)

        # Botón ocultar
        btn_ocultar = ttk.Button(frame_ocultar, text="ENCRIPTAR Y GUARDAR",
                                 command=self.accion_ocultar)
        btn_ocultar.grid(row=3, column=0, columnspan=3, pady=(10, 0))
        for i in range(3):
            frame_ocultar.columnconfigure(i, weight=[0, 1, 0][i])

        # ----- Sección 2: Recuperar -----
        frame_recuperar = ttk.LabelFrame(self, text=" 2. RECUPERAR ", padding=10)
        frame_recuperar.pack(fill="x", padx=15, pady=5)

        self.video_estego_var = tk.StringVar()
        self.carpeta_salida_var = tk.StringVar()

        # Video con secreto
        ttk.Label(frame_recuperar, text="Video con secreto:").grid(row=0, column=0, sticky="w")
        entry_ve = ttk.Entry(frame_recuperar, textvariable=self.video_estego_var, width=60)
        entry_ve.grid(row=0, column=1, padx=5, pady=3, sticky="we")
        ttk.Button(frame_recuperar, text="…", width=3,
                   command=self.seleccionar_video_estego).grid(row=0, column=2, padx=2)

        # Carpeta salida
        ttk.Label(frame_recuperar, text="Carpeta de salida:").grid(row=1, column=0, sticky="w")
        entry_cs = ttk.Entry(frame_recuperar, textvariable=self.carpeta_salida_var, width=60)
        entry_cs.grid(row=1, column=1, padx=5, pady=3, sticky="we")
        ttk.Button(frame_recuperar, text="…", width=3,
                   command=self.seleccionar_carpeta_salida).grid(row=1, column=2, padx=2)

        # Botón recuperar
        btn_recuperar = ttk.Button(frame_recuperar, text="ANALIZAR Y EXTRAER",
                                   command=self.accion_recuperar)
        btn_recuperar.grid(row=2, column=0, columnspan=3, pady=(10, 0))
        for i in range(3):
            frame_recuperar.columnconfigure(i, weight=[0, 1, 0][i])

        # ----- Log inferior -----
        frame_log = ttk.Frame(self, padding=10)
        frame_log.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        ttk.Label(frame_log, text="Registro:", style="Title.TLabel").pack(anchor="w", pady=(0, 5))

        self.text_log = tk.Text(frame_log, height=10, state="disabled",
                                font=("SF Pro Text", 10))
        self.text_log.pack(fill="both", expand=True)

    # ===== funciones de UI =====

    def agregar_log(self, texto):
        self.text_log.configure(state="normal")
        self.text_log.insert("end", texto)
        self.text_log.see("end")
        self.text_log.configure(state="disabled")

    def seleccionar_video_portada(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar video de portada",
            filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")]
        )
        if ruta:
            self.video_portada_var.set(ruta)

    def seleccionar_archivo_secreto(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo secreto",
            filetypes=[("Todos los archivos", "*.*")]
        )
        if ruta:
            self.archivo_secreto_var.set(ruta)

    def seleccionar_video_salida(self):
        ruta = filedialog.asksaveasfilename(
            title="Nombre del video de salida",
            defaultextension=".avi",
            filetypes=[("Video AVI (Lossless)", "*.avi"), ("Todos", "*.*")]
        )
        if ruta:
            self.video_salida_var.set(ruta)

    def seleccionar_video_estego(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar video con secreto",
            filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")]
        )
        if ruta:
            self.video_estego_var.set(ruta)

    def seleccionar_carpeta_salida(self):
        ruta = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if ruta:
            self.carpeta_salida_var.set(ruta)

    def accion_ocultar(self):
        video = self.video_portada_var.get().strip()
        archivo = self.archivo_secreto_var.get().strip()
        salida = self.video_salida_var.get().strip()

        if not video or not archivo:
            messagebox.showwarning("Faltan datos", "Selecciona el video de portada y el archivo secreto.")
            return

        if not salida:
            base, ext = os.path.splitext(video)
            salida = base + "_SECRETO.mp4"
            self.video_salida_var.set(salida)

        self.agregar_log("> Ocultando...\n")
        try:
            ocultar_archivo_en_video(video, archivo, salida, log_callback=self.agregar_log)
            messagebox.showinfo("Listo", f"Video con secreto guardado en:\n{salida}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.agregar_log(f"! Error: {e}\n")

    def accion_recuperar(self):
        video_estego = self.video_estego_var.get().strip()
        carpeta = self.carpeta_salida_var.get().strip() or "recuperado"

        if not video_estego:
            messagebox.showwarning("Faltan datos", "Selecciona el video con secreto.")
            return

        self.agregar_log("> Analizando...\n")
        try:
            ruta, tam = extraer_archivo_de_video(video_estego, carpeta, log_callback=self.agregar_log)
            messagebox.showinfo("Recuperado",
                                f"Archivo recuperado:\n{ruta}\n\nTamaño: {tam} bytes")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.agregar_log(f"! Error: {e}\n")


if __name__ == "__main__":
    app = VideoStegoApp()
    app.mainloop()
