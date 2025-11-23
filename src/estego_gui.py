import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from PIL import Image
import os
import struct
import sys

# ==========================================
# LÓGICA CENTRAL DE ESTEGANOGRAFÍA (CORREGIDA)
# ==========================================

# CONFIGURACIÓN
# Cabecera: 'STG' (3) + Tamaño (4) + Extensión (8) = 15 bytes
HEADER_SIZE = 15 

def prepare_blob(file_path):
    """Convierte el archivo secreto a bits y añade cabecera corregida."""
    file_ext = os.path.splitext(file_path)[1].lower()
    file_size = os.path.getsize(file_path)
    
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    
    # CORRECCIÓN: Reservamos 8 bytes para la extensión en lugar de 4
    # Usamos [:8] para asegurar que no se pase y ljust para rellenar con ceros
    ext_bytes = file_ext.encode('utf-8').ljust(8, b'\x00')[:8]
    
    # Estructura: Marca (3) + Tamaño (4) + Extensión (8)
    header = b'STG' + struct.pack("I", file_size) + ext_bytes
    
    full_data = header + file_bytes
    
    bits = []
    for byte in full_data:
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)
    return bits

def embed_logic(cover_path, secret_path, output_path):
    try:
        img = Image.open(cover_path).convert('RGB')
        width, height = img.size
        pixels = img.load()
        
        data_bits = prepare_blob(secret_path)
        total_pixels = width * height
        
        # Verificación de capacidad
        if len(data_bits) > total_pixels * 3:
            return False, f"Error: Archivo muy grande. Necesitas una imagen de al menos {len(data_bits)//3 + 1} pixeles."
        
        idx = 0
        for y in range(height):
            for x in range(width):
                if idx < len(data_bits):
                    r, g, b = pixels[x, y]
                    if idx < len(data_bits): r = (r & ~1) | data_bits[idx]; idx += 1
                    if idx < len(data_bits): g = (g & ~1) | data_bits[idx]; idx += 1
                    if idx < len(data_bits): b = (b & ~1) | data_bits[idx]; idx += 1
                    pixels[x, y] = (r, g, b)
                else:
                    break
        
        img.save(output_path, "PNG")
        return True, f"¡Éxito! Archivo ocultado en:\n{output_path}"
    except Exception as e:
        return False, f"Error inesperado: {str(e)}"

def extract_logic(stego_path):
    try:
        img = Image.open(stego_path).convert('RGB')
        pixels = img.load()
        width, height = img.size
        
        extracted_bytes = bytearray()
        temp_byte = 0
        bit_count = 0
        
        reading_header = True
        data_size = 0
        ext = ""

        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                for val in [r, g, b]:
                    bit = val & 1
                    temp_byte = (temp_byte << 1) | bit
                    bit_count += 1
                    
                    if bit_count == 8:
                        extracted_bytes.append(temp_byte)
                        temp_byte = 0
                        bit_count = 0
                        
                        # Chequeo rápido de firma al inicio (3 bytes)
                        if len(extracted_bytes) == 3 and extracted_bytes != b'STG':
                            return False, "No se detectó firma 'STG'. La imagen está limpia."
                            
                        # Si completamos la lectura de la cabecera (15 bytes ahora)
                        if len(extracted_bytes) == HEADER_SIZE and reading_header:
                            # Bytes 3 al 7: Tamaño
                            data_size = struct.unpack("I", extracted_bytes[3:7])[0]
                            # Bytes 7 al 15: Extensión (CORREGIDO)
                            try:
                                ext = extracted_bytes[7:15].decode('utf-8').strip('\x00')
                            except:
                                ext = ".bin" # Fallback si falla la decodificación
                            
                            reading_header = False
                            
                        elif not reading_header and len(extracted_bytes) == HEADER_SIZE + data_size:
                            # Fin de lectura del archivo completo
                            base_name = os.path.splitext(os.path.basename(stego_path))[0]
                            # Limpieza extra del nombre para evitar errores
                            clean_ext = ext if ext.startswith('.') else '.' + ext
                            
                            output_filename = f"{base_name}_recuperado{clean_ext}"
                            output_full_path = os.path.join(os.path.dirname(stego_path), output_filename)

                            with open(output_full_path, "wb") as f:
                                # Escribimos solo los datos, ignorando los primeros 15 bytes de cabecera
                                f.write(extracted_bytes[HEADER_SIZE:])
                            
                            return True, f"¡Recuperado!\nTipo: {clean_ext}\nTamaño: {data_size} bytes\nGuardado: {output_filename}"
                            
        return False, "Análisis finalizado sin encontrar el final del archivo."

    except Exception as e:
         return False, f"Error crítico: {str(e)}"

# ==========================================
# INTERFAZ GRÁFICA (GUI) - IGUAL QUE ANTES
# ==========================================

class StegoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Esteganografía ")
        self.root.geometry("600x550")
        self.root.resizable(False, False)
        
        bg_color = "#f4f4f4"
        self.root.configure(bg=bg_color)
        
        # --- SECCIÓN 1: OCULTAR ---
        frame_hide = tk.LabelFrame(root, text=" 1. OCULTAR ", font=("Arial", 11, "bold"), bg=bg_color, padx=10, pady=10)
        frame_hide.pack(fill="x", padx=15, pady=10)

        tk.Label(frame_hide, text="Imagen Portada:", bg=bg_color).grid(row=0, column=0, sticky="w")
        self.cover_entry = tk.Entry(frame_hide, width=45)
        self.cover_entry.grid(row=1, column=0, padx=5)
        tk.Button(frame_hide, text="...", command=self.browse_cover).grid(row=1, column=1)

        tk.Label(frame_hide, text="Archivo Secreto:", bg=bg_color).grid(row=2, column=0, sticky="w", pady=(5,0))
        self.secret_entry = tk.Entry(frame_hide, width=45)
        self.secret_entry.grid(row=3, column=0, padx=5)
        tk.Button(frame_hide, text="...", command=self.browse_secret).grid(row=3, column=1)

        tk.Button(frame_hide, text="ENCRIPTAR Y GUARDAR", bg="#2ecc71", fg="white", font=("Arial", 10, "bold"), 
                  command=self.run_hide).grid(row=4, column=0, columnspan=2, pady=10, sticky="we")

        # --- SECCIÓN 2: EXTRAER ---
        frame_ext = tk.LabelFrame(root, text=" 2. RECUPERAR ", font=("Arial", 11, "bold"), bg=bg_color, padx=10, pady=10)
        frame_ext.pack(fill="x", padx=15, pady=10)

        tk.Label(frame_ext, text="Imagen con secreto:", bg=bg_color).grid(row=0, column=0, sticky="w")
        self.stego_entry = tk.Entry(frame_ext, width=45)
        self.stego_entry.grid(row=1, column=0, padx=5)
        tk.Button(frame_ext, text="...", command=self.browse_stego).grid(row=1, column=1)

        tk.Button(frame_ext, text="ANALIZAR Y EXTRAER", bg="#3498db", fg="white", font=("Arial", 10, "bold"), 
                  command=self.run_extract).grid(row=2, column=0, columnspan=2, pady=10, sticky="we")

        # --- LOG ---
        self.log = scrolledtext.ScrolledText(root, height=8, state='disabled', bg="#e8e8e8")
        self.log.pack(padx=15, pady=5, fill="both")

    def log_msg(self, msg):
        self.log.config(state='normal')
        self.log.insert(tk.END, "> " + msg + "\n")
        self.log.see(tk.END)
        self.log.config(state='disabled')

    def browse_cover(self):
        f = filedialog.askopenfilename(filetypes=[("Imágenes", "*.png *.jpg *.jpeg")])
        if f: self.cover_entry.delete(0, tk.END); self.cover_entry.insert(0, f)

    def browse_secret(self):
        f = filedialog.askopenfilename()
        if f: self.secret_entry.delete(0, tk.END); self.secret_entry.insert(0, f)

    def browse_stego(self):
        f = filedialog.askopenfilename(filetypes=[("PNG", "*.png")])
        if f: self.stego_entry.delete(0, tk.END); self.stego_entry.insert(0, f)

    def run_hide(self):
        cover, secret = self.cover_entry.get(), self.secret_entry.get()
        if not cover or not secret: return messagebox.showerror("Error", "Faltan archivos")
        
        out = os.path.splitext(cover)[0] + "_SECRETO.png"
        self.log_msg("Ocultando...")
        ok, msg = embed_logic(cover, secret, out)
        if ok: messagebox.showinfo("Éxito", msg); self.log_msg("Listo: " + out)
        else: messagebox.showerror("Error", msg); self.log_msg("Error: " + msg)

    def run_extract(self):
        stego = self.stego_entry.get()
        if not stego: return messagebox.showerror("Error", "Selecciona imagen")
        
        self.log_msg("Analizando...")
        ok, msg = extract_logic(stego)
        if ok: messagebox.showinfo("Éxito", msg); self.log_msg(msg)
        else: messagebox.showwarning("Fallo", msg); self.log_msg(msg)

if __name__ == "__main__":
    if getattr(sys, 'frozen', False): os.chdir(sys._MEIPASS)
    root = tk.Tk()
    app = StegoApp(root)
    root.mainloop()