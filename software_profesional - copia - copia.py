# software_profesional_final.py
"""
Software Profesional IPH - Versión Final Ejecutable
Guarda este archivo como software_profesional_final.py y asegúrate de tener:
 - carpeta "icons" con los iconos (512x512 png) nombrados: add.png, update.png, delete.png,
   clear.png, excel.png, pdf.png, clean.png, auditoria.png, user.png, logout.png
 - pip install tkcalendar pillow pandas reportlab openpyxl folium
"""
UPDATE users SET rol='admin' WHERE username='ERICK';
import os
import sys
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkcalendar import DateEntry
from PIL import Image, ImageTk
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
import pandas as pd
import hashlib
import datetime
import json
import webbrowser
import tempfile
import folium
import threading

# -----------------------
# Configuración global
# -----------------------
DB_NAME = "iph.db"
ICON_FOLDER = "icons"
current_user = None
MAX_DETENIDOS = 10
MAX_VEHICULOS = 10
BACKUP_DAILY = True

# -----------------------
# Helpers
# -----------------------
def resource_path(relative):
    try:
        base = sys._MEIPASS
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, relative)

def cargar_icono(nombre, size=(64,64)):
    ruta = resource_path(os.path.join(ICON_FOLDER, nombre))
    if os.path.exists(ruta):
        try:
            img = Image.open(ruta).convert("RGBA")
            img = img.resize(size, Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None
    return None

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# -----------------------
# Base de datos
# -----------------------
def conectar_db():
    conn = sqlite3.connect(resource_path(DB_NAME))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS iph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_informe TEXT UNIQUE NOT NULL,
            fecha_hechos TEXT NOT NULL,
            denunciante TEXT NOT NULL,
            tipo_hecho TEXT NOT NULL,
            tipo_delito TEXT,
            lugar TEXT,
            autoridad TEXT,
            puesta_a_disposicion TEXT,
            detenidos_json TEXT,
            vehiculos_json TEXT,
            victima TEXT,
            coordenadas TEXT,
            estado_procesal TEXT DEFAULT 'En trámite',
            observaciones TEXT,
            capturado_por TEXT,
            creado_en TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            correo TEXT UNIQUE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accion TEXT,
            numero_informe TEXT,
            usuario TEXT,
            fecha_hora TEXT,
            cambios TEXT
        )
    """)
    conn.commit()
    conn.close()

# -----------------------
# Auditoría y backup
# -----------------------
def registrar_auditoria(accion, numero, cambios=""):
    conn = sqlite3.connect(resource_path(DB_NAME))
    cur = conn.cursor()
    cur.execute("INSERT INTO auditoria (accion, numero_informe, usuario, fecha_hora, cambios) VALUES (?,?,?,?,?)",
                (accion, numero, current_user, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), cambios))
    conn.commit()
    conn.close()

def guardar_backup_excel():
    try:
        conn = sqlite3.connect(resource_path(DB_NAME))
        df = pd.read_sql_query("SELECT * FROM iph", conn)
        conn.close()
        fname = resource_path(f"backup_IPH_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        df.to_excel(fname, index=False)
        # notify user
        messagebox.showinfo("Backup", f"Backup guardado: {fname}")
    except Exception as e:
        print("Backup error:", e)
        messagebox.showerror("Backup error", str(e))

def backup_automatico_diario():
    # Simple thread that saves a daily backup at first run if enabled.
    if not BACKUP_DAILY:
        return
    try:
        today = datetime.datetime.now().strftime("%Y%m%d")
        target = resource_path(f"backup_IPH_{today}.xlsx")
        if not os.path.exists(target):
            guardar_backup_excel()
    except Exception as e:
        print("Auto-backup error:", e)

# -----------------------
# Validaciones
# -----------------------
def validar_fecha(fecha):
    try:
        datetime.datetime.strptime(fecha, "%Y-%m-%d")
        return True
    except Exception:
        return False

# -----------------------
# Export / Import
# -----------------------
def exportar_excel(path=None):
    conn = sqlite3.connect(resource_path(DB_NAME))
    df = pd.read_sql_query("SELECT * FROM iph", conn)
    conn.close()
    if df.empty:
        messagebox.showinfo("Exportar", "No hay registros para exportar.")
        return
    if not path:
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel","*.xlsx")])
        if not path:
            return
    df.to_excel(path, index=False)
    messagebox.showinfo("Exportar", f"Exportado a {path}")
    registrar_auditoria("EXPORTAR_EXCEL", "-")

def exportar_json_det_veh(path=None):
    conn = sqlite3.connect(resource_path(DB_NAME))
    df = pd.read_sql_query("SELECT id, numero_informe, detenidos_json, vehiculos_json FROM iph", conn)
    conn.close()
    if df.empty:
        messagebox.showinfo("Exportar JSON", "No hay registros para exportar.")
        return
    records = []
    for _, r in df.iterrows():
        records.append({
            "id": int(r["id"]),
            "numero_informe": r["numero_informe"],
            "detenidos": json.loads(r["detenidos_json"]) if r["detenidos_json"] else [],
            "vehiculos": json.loads(r["vehiculos_json"]) if r["vehiculos_json"] else []
        })
    if not path:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")])
        if not path: return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    messagebox.showinfo("Exportar JSON", f"Exportado a {path}")
    registrar_auditoria("EXPORTAR_JSON", "-")

def importar_json_det_veh(path=None):
    if not path:
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not path: return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        messagebox.showerror("Importar JSON", f"Error leyendo JSON: {e}"); return
    conn = sqlite3.connect(resource_path(DB_NAME)); cur = conn.cursor()
    imported = 0
    for rec in data:
        num = rec.get("numero_informe")
        if not num: continue
        # Try to update iph by numero_informe
        cur.execute("SELECT id FROM iph WHERE numero_informe=?", (num,))
        if cur.fetchone():
            cur.execute("UPDATE iph SET detenidos_json=?, vehiculos_json=? WHERE numero_informe=?",
                        (json.dumps(rec.get("detenidos",[])), json.dumps(rec.get("vehiculos",[])), num))
            imported += 1
    conn.commit(); conn.close()
    messagebox.showinfo("Importar JSON", f"Actualizados: {imported}")
    registrar_auditoria("IMPORTAR_JSON", "-")

# -----------------------
# PDF Report
# -----------------------
def generar_pdf_resumen(path=None):
    conn = sqlite3.connect(resource_path(DB_NAME))
    df = pd.read_sql_query("SELECT * FROM iph ORDER BY fecha_hechos DESC", conn)
    conn.close()
    if df.empty:
        messagebox.showinfo("PDF", "No hay datos para generar PDF.")
        return
    if not path:
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF","*.pdf")])
        if not path:
            return
    c = canvas.Canvas(path, pagesize=LETTER)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 750, "Reporte IPH - Resumen")
    c.setFont("Helvetica", 10)
    y = 730
    for i, r in df.iterrows():
        line = f"{r['numero_informe']} | {r['fecha_hechos']} | {r['denunciante']} | {r['tipo_hecho']}"
        c.drawString(40, y, line)
        y -= 14
        if y < 80:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = 750
    c.save()
    messagebox.showinfo("PDF", f"PDF generado: {path}")
    registrar_auditoria("EXPORTAR_PDF", "-")

# -----------------------
# Mapa (abre en navegador con folium)
# -----------------------
def abrir_mapa_interactivo(initial_coords=(20.0, -100.0)):
    # Creates a temporary HTML with folium map that allows clicking to show coords.
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    m = folium.Map(location=initial_coords, zoom_start=12)
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.LatLngPopup().add_to(m)  # clicking shows lat/lng popup
    m.save(tmp.name)
    webbrowser.open("file://" + tmp.name)
    messagebox.showinfo("Mapa", "Mapa abierto en el navegador. Haz clic en el punto deseado y copia las coordenadas (lat, lon) al campo Coordenadas en la app.")

# -----------------------
# GUI: ToolTip
# -----------------------
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget; self.text = text; self.tip = None
        widget.bind("<Enter>", self.show); widget.bind("<Leave>", self.hide)
    def show(self, e=None):
        if self.tip: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tip = tw = tk.Toplevel(self.widget); tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, bg="#333", fg="white", padx=6, pady=3, font=("Segoe UI",9))
        label.pack()
    def hide(self, e=None):
        if self.tip: self.tip.destroy(); self.tip = None

# -----------------------
# GUI principal
# -----------------------
def abrir_dashboard():
    global current_user
    conectar_db()
    backup_automatico_diario()

    root = tk.Tk()
    root.title("Software Profesional IPH")
    root.geometry("1400x800")
    root.configure(bg="#0b1620")

    # Sidebar
    SIDEBAR_W = 260
    sidebar = tk.Frame(root, bg="#0b1620", width=SIDEBAR_W)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    canvas_sb = tk.Canvas(sidebar, bg="#0b1620", highlightthickness=0)
    scroll_y = tk.Scrollbar(sidebar, orient="vertical", command=canvas_sb.yview)
    frame_sb = tk.Frame(canvas_sb, bg="#0b1620")
    frame_sb.bind("<Configure>", lambda e: canvas_sb.configure(scrollregion=canvas_sb.bbox("all")))
    canvas_sb.create_window((0,0), window=frame_sb, anchor="nw")
    canvas_sb.configure(yscrollcommand=scroll_y.set)
    canvas_sb.pack(side="left", fill="both", expand=True)
    scroll_y.pack(side="right", fill="y")

    # load icons
    icons = {}
    for name in ("add","update","delete","clear","excel","pdf","clean","auditoria","user","logout","map"):
        icons[name] = cargar_icono(f"{name}.png", (48,48))

    def sidebar_button(text, icon, cmd, tip_text=None):
        b = tk.Button(frame_sb, text="  "+text, image=icon, compound="left", anchor="w",
                      bg="#10232b", fg="white", relief="flat", font=("Segoe UI",10,"bold"),
                      padx=6, command=cmd)
        if icon: b.image = icon
        b.pack(fill="x", padx=12, pady=8)
        if tip_text: ToolTip(b, tip_text)
        return b

    # Actions to be linked below
    sidebar_button("Agregar IPH", icons.get("add"), lambda: abrir_formulario_registro(root), "Abrir formulario para registrar IPH")
    sidebar_button("Importar JSON (det/veh)", icons.get("update"), lambda: importar_json_det_veh(), "Importar JSON con detenidos/vehículos")
    sidebar_button("Exportar JSON (det/veh)", icons.get("update"), lambda: exportar_json_det_veh(), "Exportar JSON con detenidos/vehículos")
    sidebar_button("Exportar Excel", icons.get("excel"), lambda: exportar_excel(None), "Exportar tabla completa a Excel")
    sidebar_button("Exportar PDF", icons.get("pdf"), lambda: generar_pdf_resumen(), "Exportar reporte PDF")
    sidebar_button("Mapa (abrir)", icons.get("map"), lambda: abrir_mapa_interactivo(), "Abrir mapa interactivo en navegador")
    sidebar_button("Generar DB limpia", icons.get("clean"), lambda: generar_db_limpia(), "Borrar registros y generar backup")
    sidebar_button("Generar Auditoría", icons.get("auditoria"), lambda: generar_auditoria(), "Exportar registros de auditoría")
    sidebar_button("Backup ahora", icons.get("excel"), lambda: guardar_backup_excel(), "Forzar backup ahora")

    # Content frame (form arriba, table abajo)
    content = tk.Frame(root, bg="#14202b")
    content.pack(side="right", fill="both", expand=True)

    # --- Formulario (arriba) ---
    form = tk.Frame(content, bg="#14202b", pady=8)
    form.pack(side="top", fill="x", padx=16, pady=8)

    # Row 0
    tk.Label(form, text="Número Informe *", bg="#14202b", fg="white").grid(row=0, column=0, sticky="e", padx=6, pady=4)
    entry_num = tk.Entry(form, width=18); entry_num.grid(row=0, column=1, padx=6, pady=4)
    tk.Label(form, text="Fecha *", bg="#14202b", fg="white").grid(row=0, column=2, sticky="e", padx=6, pady=4)
    entry_fecha = DateEntry(form, date_pattern="yyyy-mm-dd"); entry_fecha.grid(row=0, column=3, padx=6, pady=4)
    tk.Label(form, text="Denunciante *", bg="#14202b", fg="white").grid(row=0, column=4, sticky="e", padx=6, pady=4)
    entry_den = tk.Entry(form, width=22); entry_den.grid(row=0, column=5, padx=6, pady=4)

    # Row 1
    tk.Label(form, text="Tipo Hecho *", bg="#14202b", fg="white").grid(row=1, column=0, sticky="e", padx=6, pady=4)
    entry_tipo = ttk.Combobox(form, values=["IP (General)","Robo","Homicidio","Fraude","Lesiones","Otro"], width=20)
    entry_tipo.grid(row=1, column=1, padx=6, pady=4)
    tk.Label(form, text="Tipo Delito", bg="#14202b", fg="white").grid(row=1, column=2, sticky="e", padx=6, pady=4)
    entry_td = tk.Entry(form, width=20); entry_td.grid(row=1, column=3, padx=6, pady=4)
    tk.Label(form, text="Lugar", bg="#14202b", fg="white").grid(row=1, column=4, sticky="e", padx=6, pady=4)
    entry_lugar = tk.Entry(form, width=22); entry_lugar.grid(row=1, column=5, padx=6, pady=4)

    # Row 2
    tk.Label(form, text="Autoridad", bg="#14202b", fg="white").grid(row=2, column=0, sticky="e", padx=6, pady=4)
    entry_aut = tk.Entry(form, width=20); entry_aut.grid(row=2, column=1, padx=6, pady=4)
    tk.Label(form, text="Puesta a disposición", bg="#14202b", fg="white").grid(row=2, column=2, sticky="e", padx=6, pady=4)
    entry_puesta = tk.Entry(form, width=20); entry_puesta.grid(row=2, column=3, padx=6, pady=4)
    tk.Label(form, text="Victima", bg="#14202b", fg="white").grid(row=2, column=4, sticky="e", padx=6, pady=4)
    entry_vict = tk.Entry(form, width=22); entry_vict.grid(row=2, column=5, padx=6, pady=4)

    # Row 3 - Coordenadas & map
    tk.Label(form, text="Coordenadas (lat,lon)", bg="#14202b", fg="white").grid(row=3, column=0, sticky="e", padx=6, pady=4)
    entry_coords = tk.Entry(form, width=30); entry_coords.grid(row=3, column=1, columnspan=2, padx=6, pady=4, sticky="w")
    btn_mapsmall = tk.Button(form, text="Abrir mapa (navegador)", command=lambda: abrir_mapa_interactivo()); btn_mapsmall.grid(row=3, column=3, padx=6, pady=4)
    ToolTip(btn_mapsmall, "Abrir mapa en tu navegador. Haz clic en el mapa y copia las coordenadas al campo.")

    # Row 4 - Detenidos dinámicos
    tk.Label(form, text="Detenidos (0-10)", bg="#14202b", fg="white").grid(row=4, column=0, sticky="e", padx=6, pady=4)
    var_num_det = tk.IntVar(value=0)
    spin_det = tk.Spinbox(form, from_=0, to=MAX_DETENIDOS, width=5, textvariable=var_num_det)
    spin_det.grid(row=4, column=1, sticky="w", padx=6, pady=4)
    frame_dets = tk.Frame(form, bg="#14202b")
    frame_dets.grid(row=5, column=0, columnspan=6, sticky="w", padx=6)

    det_widgets = []  # list of dicts {nombre:Entry, sexo:Combobox}
    def actualizar_detenidos(*args):
        for w in frame_dets.winfo_children(): w.destroy()
        det_widgets.clear()
        n = var_num_det.get()
        for i in range(n):
            tk.Label(frame_dets, text=f"{i+1}. Nombre:", bg="#14202b", fg="white").grid(row=i, column=0, padx=4, pady=2, sticky="e")
            e_nom = tk.Entry(frame_dets, width=25); e_nom.grid(row=i, column=1, padx=4, pady=2)
            tk.Label(frame_dets, text="Sexo:", bg="#14202b", fg="white").grid(row=i, column=2, padx=4, pady=2, sticky="e")
            cb_sex = ttk.Combobox(frame_dets, values=["Hombre","Mujer"], width=10); cb_sex.grid(row=i, column=3, padx=4, pady=2)
            det_widgets.append({"nombre": e_nom, "sexo": cb_sex})
    var_num_det.trace_add("write", lambda *args: actualizar_detenidos())

    # Row 6 - Vehículos dynamic
    tk.Label(form, text="Vehículos (0-10)", bg="#14202b", fg="white").grid(row=6, column=0, sticky="e", padx=6, pady=8)
    var_num_veh = tk.IntVar(value=0)
    spin_veh = tk.Spinbox(form, from_=0, to=MAX_VEHICULOS, width=5, textvariable=var_num_veh)
    spin_veh.grid(row=6, column=1, sticky="w", padx=6, pady=8)
    frame_vehs = tk.Frame(form, bg="#14202b")
    frame_vehs.grid(row=7, column=0, columnspan=6, sticky="w", padx=6)
    veh_widgets = []
    def actualizar_vehiculos(*args):
        for w in frame_vehs.winfo_children(): w.destroy()
        veh_widgets.clear()
        n = var_num_veh.get()
        for i in range(n):
            tk.Label(frame_vehs, text=f"{i+1}. Tipo:", bg="#14202b", fg="white").grid(row=i, column=0, padx=4, pady=2, sticky="e")
            cb_tipo = ttk.Combobox(frame_vehs, values=["Terrestre","Acuático","Aéreo"], width=12); cb_tipo.grid(row=i, column=1, padx=4, pady=2)
            tk.Label(frame_vehs, text="Marca:", bg="#14202b", fg="white").grid(row=i, column=2, padx=4, pady=2, sticky="e")
            e_marca = tk.Entry(frame_vehs, width=15); e_marca.grid(row=i, column=3, padx=4, pady=2)
            tk.Label(frame_vehs, text="Placa:", bg="#14202b", fg="white").grid(row=i, column=4, padx=4, pady=2, sticky="e")
            e_placa = tk.Entry(frame_vehs, width=12); e_placa.grid(row=i, column=5, padx=4, pady=2)
            tk.Label(frame_vehs, text="Serie:", bg="#14202b", fg="white").grid(row=i, column=6, padx=4, pady=2, sticky="e")
            e_serie = tk.Entry(frame_vehs, width=18); e_serie.grid(row=i, column=7, padx=4, pady=2)
            veh_widgets.append({"tipo": cb_tipo, "marca": e_marca, "placa": e_placa, "serie": e_serie})
    var_num_veh.trace_add("write", lambda *args: actualizar_vehiculos())

    # Row 8 - Observaciones & botones
    tk.Label(form, text="Observaciones", bg="#14202b", fg="white").grid(row=8, column=0, sticky="ne", padx=6, pady=8)
    txt_obs = tk.Text(form, width=80, height=4); txt_obs.grid(row=8, column=1, columnspan=5, padx=6, pady=8)

    # Buttons: Save, Clear, Export/Import quick
    def limpiar_formulario():
        entry_num.delete(0, tk.END)
        entry_fecha.set_date(datetime.date.today())
        entry_den.delete(0, tk.END)
        entry_tipo.set('')
        entry_td.delete(0, tk.END)
        entry_lugar.delete(0, tk.END)
        entry_aut.delete(0, tk.END)
        entry_puesta.delete(0, tk.END)
        entry_vict.delete(0, tk.END)
        entry_coords.delete(0, tk.END)
        var_num_det.set(0); var_num_veh.set(0)
        txt_obs.delete("1.0", tk.END)

    def recoger_detenidos():
        res = []
        for w in det_widgets:
            nombre = w["nombre"].get().strip()
            sexo = w["sexo"].get().strip()
            if nombre:
                res.append({"nombre": nombre, "sexo": sexo})
        return res

    def recoger_vehiculos():
        res = []
        for w in veh_widgets:
            tipo = w["tipo"].get().strip()
            marca = w["marca"].get().strip()
            placa = w["placa"].get().strip()
            serie = w["serie"].get().strip()
            if tipo or marca or placa or serie:
                res.append({"tipo": tipo, "marca": marca, "placa": placa, "serie": serie})
        return res

    def accion_guardar():
        datos = {
            "numero_informe": entry_num.get().strip(),
            "fecha_hechos": entry_fecha.get_date().strftime("%Y-%m-%d"),
            "denunciante": entry_den.get().strip(),
            "tipo_hecho": entry_tipo.get().strip(),
            "tipo_delito": entry_td.get().strip(),
            "lugar": entry_lugar.get().strip(),
            "autoridad": entry_aut.get().strip(),
            "puesta_a_disposicion": entry_puesta.get().strip(),
            "victima": entry_vict.get().strip(),
            "coordenadas": entry_coords.get().strip(),
            "detenidos": recoger_detenidos(),
            "vehiculos": recoger_vehiculos(),
            "observaciones": txt_obs.get("1.0", tk.END).strip(),
            "estado_procesal": "En trámite"
        }
        insertar_iph(datos)
        filtrar()  # refresh table
        limpiar_formulario()

    btn_save = tk.Button(form, text="Guardar IPH", bg="#1abc9c", fg="white", command=accion_guardar)
    btn_save.grid(row=9, column=1, padx=6, pady=10, sticky="w")
    ToolTip(btn_save, "Guarda el IPH en la base de datos (verifica duplicados)")

    btn_clear = tk.Button(form, text="Limpiar formulario", bg="#2196f3", fg="white", command=limpiar_formulario)
    btn_clear.grid(row=9, column=2, padx=6, pady=10, sticky="w")
    ToolTip(btn_clear, "Limpia todos los campos del formulario")

    # --- Tabla y filtros (abajo) ---
    panel_table = tk.Frame(content, bg="#14202b")
    panel_table.pack(side="bottom", fill="both", expand=True, padx=16, pady=8)

    # Filters row
    filter_frame = tk.Frame(panel_table, bg="#14202b")
    filter_frame.pack(side="top", fill="x", pady=6)
    tk.Label(filter_frame, text="Buscar:", bg="#14202b", fg="white").pack(side="left", padx=6)
    e_search = tk.Entry(filter_frame, width=40); e_search.pack(side="left", padx=6)
    tk.Label(filter_frame, text="Filtro Tipo:", bg="#14202b", fg="white").pack(side="left", padx=6)
    cb_filter_tipo = ttk.Combobox(filter_frame, values=["", "IP (General)","Robo","Homicidio","Fraude","Lesiones","Otro"], width=18)
    cb_filter_tipo.pack(side="left", padx=6)
    btn_clear_filters = tk.Button(filter_frame, text="Limpiar filtros", command=lambda: (e_search.delete(0,tk.END), cb_filter_tipo.set(''), filtrar()))
    btn_clear_filters.pack(side="left", padx=6)

    # Table
    cols = ("ID","Número","Fecha","Denunciante","Tipo","Delito","Lugar","Autoridad","Detenidos","Vehiculos","Victima","Coordenadas","Estado","Observaciones","Capturado_en")
    tree_frame = tk.Frame(panel_table, bg="#14202b")
    tree_frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, anchor="w", width=110)
    tree.pack(side="left", fill="both", expand=True)
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview); vsb.pack(side="right", fill="y")
    tree.configure(yscrollcommand=vsb.set)

    # Populate table
    def filtrar(event=None):
        term = e_search.get().strip().lower()
        tipo_sel = cb_filter_tipo.get().strip().lower()
        for it in tree.get_children(): tree.delete(it)
        conn = sqlite3.connect(resource_path(DB_NAME))
        df = pd.read_sql_query("SELECT * FROM iph ORDER BY fecha_hechos DESC", conn)
        conn.close()
        if df.empty: return
        for _, r in df.iterrows():
            # filter
            match = True
            if term:
                hay = False
                for f in ("numero_informe","denunciante","tipo_hecho","lugar","victima"):
                    if term in str(r.get(f,"")).lower():
                        hay = True; break
                # also search in detainees names & vehicle plates
                try:
                    dets = json.loads(r.get("detenidos_json") or "[]")
                    for d in dets:
                        if term in str(d.get("nombre","")).lower(): hay = True; break
                except Exception:
                    pass
                if not hay: match = False
            if tipo_sel:
                if tipo_sel not in str(r.get("tipo_hecho","")).lower(): match = False
            if match:
                deten_str = r.get("detenidos_json") or ""
                veh_str = r.get("vehiculos_json") or ""
                creado = r.get("creado_en") or ""
                tree.insert("", tk.END, values=(
                    r["id"], r["numero_informe"], r["fecha_hechos"], r["denunciante"], r["tipo_hecho"],
                    r.get("tipo_delito",""), r.get("lugar",""), r.get("autoridad",""),
                    deten_str, veh_str, r.get("victima",""), r.get("coordenadas",""),
                    r.get("estado_procesal",""), r.get("observaciones",""), creado
                ))
    e_search.bind("<KeyRelease>", filtrar)
    cb_filter_tipo.bind("<<ComboboxSelected>>", lambda e: filtrar())
    filtrar()

    # Right-click menu on table for actions
    def ver_detalle():
        sel = tree.selection()
        if not sel: messagebox.showwarning("Ver detalle","Selecciona un registro"); return
        item = tree.item(sel[0])["values"]
        numero = item[1]
        conn = sqlite3.connect(resource_path(DB_NAME)); cur = conn.cursor()
        cur.execute("SELECT * FROM iph WHERE numero_informe=?", (numero,))
        r = cur.fetchone(); conn.close()
        if not r: messagebox.showerror("Detalle","Registro no encontrado"); return
        # r mapping based on create table
        labels = ["ID","Número","Fecha","Denunciante","Tipo","TipoDelito","Lugar","Autoridad","Puesta a disposición",
                  "Detenidos(JSON)","Vehículos(JSON)","Victima","Coordenadas","Estado","Observaciones","Capturado_por","Creado_en"]
        txt = ""
        for i,lab in enumerate(labels):
            val = r[i] if i < len(r) else ""
            txt += f"{lab}: {val}\n"
        # show in scrolled window
        dwin = tk.Toplevel(root); dwin.title(f"Detalle: {numero}"); dwin.geometry("700x500")
        txtw = tk.Text(dwin); txtw.pack(fill="both", expand=True); txtw.insert("1.0", txt); txtw.config(state="disabled")

    def eliminar_registro():
        sel = tree.selection()
        if not sel: messagebox.showwarning("Eliminar","Selecciona un registro"); return
        item = tree.item(sel[0])["values"]
        numero = item[1]
        if not messagebox.askyesno("Confirmar", f"Eliminar registro {numero}?"): return
        conn = sqlite3.connect(resource_path(DB_NAME)); cur = conn.cursor()
        cur.execute("DELETE FROM iph WHERE numero_informe=?", (numero,))
        conn.commit(); conn.close()
        registrar_auditoria("ELIMINAR", numero)
        filtrar()
        messagebox.showinfo("Eliminar","Registro eliminado")

    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="Ver detalle", command=ver_detalle)
    menu.add_command(label="Eliminar registro", command=eliminar_registro)
    def on_right_click(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
    tree.bind("<Button-3>", on_right_click)

    # bottom status bar
    status = tk.Label(root, text="Usuario: "+(current_user or "N/A"), bg="#0b1620", fg="white", anchor="w")
    status.pack(side="bottom", fill="x")

    # start UI loop
    root.mainloop()

# -----------------------
# Formulario de registro (ventana modal)
# -----------------------
def abrir_formulario_registro(parent):
    win = tk.Toplevel(parent)
    win.title("Registrar IPH")
    win.geometry("900x700")
    win.configure(bg="#14202b")

    # Basic fields
    tk.Label(win, text="Número Informe *", bg="#14202b", fg="white").grid(row=0, column=0, padx=6, pady=6, sticky="e")
    e_num = tk.Entry(win); e_num.grid(row=0, column=1, padx=6, pady=6)
    tk.Label(win, text="Fecha *", bg="#14202b", fg="white").grid(row=0, column=2, padx=6, pady=6, sticky="e")
    e_fecha = DateEntry(win, date_pattern="yyyy-mm-dd"); e_fecha.grid(row=0, column=3, padx=6, pady=6)
    tk.Label(win, text="Denunciante *", bg="#14202b", fg="white").grid(row=1, column=0, padx=6, pady=6, sticky="e")
    e_den = tk.Entry(win); e_den.grid(row=1, column=1, padx=6, pady=6)
    tk.Label(win, text="Tipo Hecho *", bg="#14202b", fg="white").grid(row=1, column=2, padx=6, pady=6, sticky="e")
    e_tipo = ttk.Combobox(win, values=["IP (General)","Robo","Homicidio","Fraude","Lesiones","Otro"]); e_tipo.grid(row=1, column=3, padx=6, pady=6)
    tk.Label(win, text="Tipo Delito", bg="#14202b", fg="white").grid(row=2, column=0, padx=6, pady=6, sticky="e")
    e_td = tk.Entry(win); e_td.grid(row=2, column=1, padx=6, pady=6)
    tk.Label(win, text="Lugar", bg="#14202b", fg="white").grid(row=2, column=2, padx=6, pady=6, sticky="e")
    e_lugar = tk.Entry(win); e_lugar.grid(row=2, column=3, padx=6, pady=6)
    tk.Label(win, text="Autoridad", bg="#14202b", fg="white").grid(row=3, column=0, padx=6, pady=6, sticky="e")
    e_aut = tk.Entry(win); e_aut.grid(row=3, column=1, padx=6, pady=6)
    tk.Label(win, text="Puesta a disposición", bg="#14202b", fg="white").grid(row=3, column=2, padx=6, pady=6, sticky="e")
    e_puesta = tk.Entry(win); e_puesta.grid(row=3, column=3, padx=6, pady=6)
    tk.Label(win, text="Victima", bg="#14202b", fg="white").grid(row=4, column=0, padx=6, pady=6, sticky="e")
    e_vict = tk.Entry(win); e_vict.grid(row=4, column=1, padx=6, pady=6)
    tk.Label(win, text="Coordenadas (lat,lon)", bg="#14202b", fg="white").grid(row=4, column=2, padx=6, pady=6, sticky="e")
    e_coords = tk.Entry(win); e_coords.grid(row=4, column=3, padx=6, pady=6)
    btn_map = tk.Button(win, text="Abrir mapa", command=lambda: abrir_mapa_interactivo()); btn_map.grid(row=4, column=4, padx=6, pady=6)

    # Detenidos dynamic
    tk.Label(win, text="Número Detenidos (0-10)", bg="#14202b", fg="white").grid(row=5, column=0, padx=6, pady=6, sticky="e")
    var_nd = tk.IntVar(value=0); sb_nd = tk.Spinbox(win, from_=0, to=MAX_DETENIDOS, textvariable=var_nd, width=5); sb_nd.grid(row=5, column=1, padx=6, pady=6, sticky="w")
    frame_det = tk.Frame(win, bg="#14202b"); frame_det.grid(row=6, column=0, columnspan=5, sticky="w", padx=6)
    det_fields = []
    def upd_det(*args):
        for w in frame_det.winfo_children(): w.destroy()
        det_fields.clear()
        for i in range(var_nd.get()):
            tk.Label(frame_det, text=f"Det {i+1} Nombre:", bg="#14202b", fg="white").grid(row=i, column=0, padx=4, pady=2, sticky="e")
            en = tk.Entry(frame_det, width=25); en.grid(row=i, column=1, padx=4, pady=2)
            tk.Label(frame_det, text="Sexo:", bg="#14202b", fg="white").grid(row=i, column=2, padx=4, pady=2, sticky="e")
            cb = ttk.Combobox(frame_det, values=["Hombre","Mujer"], width=10); cb.grid(row=i, column=3, padx=4, pady=2)
            det_fields.append({"nombre": en, "sexo": cb})
    var_nd.trace_add("write", lambda *args: upd_det())

    # Vehículos dynamic
    tk.Label(win, text="Número Vehículos (0-10)", bg="#14202b", fg="white").grid(row=7, column=0, padx=6, pady=6, sticky="e")
    var_nv = tk.IntVar(value=0); sb_nv = tk.Spinbox(win, from_=0, to=MAX_VEHICULOS, textvariable=var_nv, width=5); sb_nv.grid(row=7, column=1, padx=6, pady=6, sticky="w")
    frame_veh = tk.Frame(win, bg="#14202b"); frame_veh.grid(row=8, column=0, columnspan=6, sticky="w", padx=6)
    veh_fields = []
    def upd_veh(*args):
        for w in frame_veh.winfo_children(): w.destroy()
        veh_fields.clear()
        for i in range(var_nv.get()):
            tk.Label(frame_veh, text=f"Veh {i+1} Tipo:", bg="#14202b", fg="white").grid(row=i, column=0, padx=4, pady=2, sticky="e")
            cbt = ttk.Combobox(frame_veh, values=["Terrestre","Acuático","Aéreo"], width=12); cbt.grid(row=i, column=1, padx=4, pady=2)
            tk.Label(frame_veh, text="Marca:", bg="#14202b", fg="white").grid(row=i, column=2, padx=4, pady=2, sticky="e")
            em = tk.Entry(frame_veh, width=15); em.grid(row=i, column=3, padx=4, pady=2)
            tk.Label(frame_veh, text="Placa:", bg="#14202b", fg="white").grid(row=i, column=4, padx=4, pady=2, sticky="e")
            ep = tk.Entry(frame_veh, width=12); ep.grid(row=i, column=5, padx=4, pady=2)
            tk.Label(frame_veh, text="Serie:", bg="#14202b", fg="white").grid(row=i, column=6, padx=4, pady=2, sticky="e")
            es = tk.Entry(frame_veh, width=18); es.grid(row=i, column=7, padx=4, pady=2)
            veh_fields.append({"tipo": cbt, "marca": em, "placa": ep, "serie": es})
    var_nv.trace_add("write", lambda *args: upd_veh())

    tk.Label(win, text="Observaciones", bg="#14202b", fg="white").grid(row=9, column=0, sticky="ne", padx=6, pady=6)
    tx_obs = tk.Text(win, width=80, height=6); tx_obs.grid(row=9, column=1, columnspan=6, padx=6, pady=6)

    def recoger_det_fields():
        out = []
        for d in det_fields:
            n = d["nombre"].get().strip()
            s = d["sexo"].get().strip()
            if n:
                out.append({"nombre": n, "sexo": s})
        return out

    def recoger_veh_fields():
        out = []
        for v in veh_fields:
            tipo = v["tipo"].get().strip()
            marca = v["marca"].get().strip()
            placa = v["placa"].get().strip()
            serie = v["serie"].get().strip()
            if tipo or marca or placa or serie:
                out.append({"tipo": tipo, "marca": marca, "placa": placa, "serie": serie})
        return out

    def guardar_desde_modal():
        datos = {
            "numero_informe": e_num.get().strip(),
            "fecha_hechos": e_fecha.get_date().strftime("%Y-%m-%d"),
            "denunciante": e_den.get().strip(),
            "tipo_hecho": e_tipo.get().strip(),
            "tipo_delito": e_td.get().strip(),
            "lugar": e_lugar.get().strip(),
            "autoridad": e_aut.get().strip(),
            "puesta_a_disposicion": e_puesta.get().strip(),
            "victima": e_vict.get().strip(),
            "coordenadas": e_coords.get().strip(),
            "detenidos": recoger_det_fields(),
            "vehiculos": recoger_veh_fields(),
            "observaciones": tx_obs.get("1.0", tk.END).strip(),
            "estado_procesal": "En trámite",
            "creado_en": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        insertar_iph(datos)
        win.destroy()

    tk.Button(win, text="Guardar IPH", bg="#1abc9c", fg="white", command=guardar_desde_modal).grid(row=10, column=1, pady=8)
    tk.Button(win, text="Cancelar", bg="#e74c3c", fg="white", command=win.destroy).grid(row=10, column=2, pady=8)

# -----------------------
# Insertar IPH helper (guarda en DB)
# -----------------------
def insertar_iph(datos):
    # basic validation
    if not datos.get("numero_informe") or not validar_fecha(datos.get("fecha_hechos","")) or not datos.get("denunciante") or not datos.get("tipo_hecho"):
        messagebox.showwarning("Validación", "Revisa campos obligatorios y formatos (fecha YYYY-MM-DD).")
        return
    conectar_db()
    conn = sqlite3.connect(resource_path(DB_NAME)); cur = conn.cursor()
    # duplicado?
    cur.execute("SELECT id FROM iph WHERE numero_informe=?", (datos["numero_informe"],))
    if cur.fetchone():
        messagebox.showerror("Duplicado", f"Número de informe {datos['numero_informe']} ya existe.")
        conn.close(); return
    try:
        cur.execute("""INSERT INTO iph
            (numero_informe, fecha_hechos, denunciante, tipo_hecho, tipo_delito, lugar, autoridad, puesta_a_disposicion,
             detenidos_json, vehiculos_json, victima, coordenadas, estado_procesal, observaciones, capturado_por, creado_en)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            datos["numero_informe"], datos["fecha_hechos"], datos["denunciante"], datos["tipo_hecho"], datos.get("tipo_delito",""),
            datos.get("lugar",""), datos.get("autoridad",""), datos.get("puesta_a_disposicion",""),
            json.dumps(datos.get("detenidos",[]), ensure_ascii=False), json.dumps(datos.get("vehiculos",[]), ensure_ascii=False),
            datos.get("victima",""), datos.get("coordenadas",""), datos.get("estado_procesal","En trámite"),
            datos.get("observaciones",""), current_user or "", datos.get("creado_en", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ))
        conn.commit()
        messagebox.showinfo("Guardado", "IPH guardado correctamente.")
        registrar_auditoria("INSERTAR", datos["numero_informe"], json.dumps(datos, ensure_ascii=False))
        # backup in background
        threading.Thread(target=guardar_backup_excel, daemon=True).start()
    except Exception as e:
        messagebox.showerror("Error guardado", str(e))
    finally:
        conn.close()

# -----------------------
# Login & Registro UI
# -----------------------
def abrir_login():
    conectar_db()
    # ensure at least one admin user exists? Not automatically for security.
    login = tk.Tk()
    login.title("Login - IPH")
    login.geometry("420x320")
    login.configure(bg="#0b1620")

    tk.Label(login, text="Usuario", bg="#0b1620", fg="white").pack(pady=8)
    e_user = tk.Entry(login); e_user.pack()
    tk.Label(login, text="Contraseña", bg="#0b1620", fg="white").pack(pady=8)
    e_pw = tk.Entry(login, show="*"); e_pw.pack()

    def intentar_login(event=None):
        global current_user
        u = e_user.get().strip(); pw = e_pw.get().strip()
        if not u or not pw:
            messagebox.showwarning("Login","Ingresa usuario y contraseña"); return
        conn = sqlite3.connect(resource_path(DB_NAME)); cur = conn.cursor()
        cur.execute("SELECT usuario FROM usuarios WHERE usuario=? AND password=?", (u, hash_password(pw)))
        if cur.fetchone():
            current_user = u
            registrar_auditoria("LOGIN", "-")
            login.destroy()
            abrir_dashboard()
        else:
            messagebox.showerror("Login", "Usuario o contraseña incorrectos")
        conn.close()

    btn_login = tk.Button(login, text="Ingresar", bg="#1abc9c", fg="white", command=intentar_login)
    btn_login.pack(pady=10)
    # allow Enter to login
    login.bind("<Return>", intentar_login)

    def abrir_registro():
        reg = tk.Toplevel(login); reg.title("Registro"); reg.geometry("420x360"); reg.configure(bg="#0b1620")
        tk.Label(reg, text="Usuario", bg="#0b1620", fg="white").pack(pady=6)
        e_ru = tk.Entry(reg); e_ru.pack()
        tk.Label(reg, text="Contraseña", bg="#0b1620", fg="white").pack(pady=6)
        e_rpw = tk.Entry(reg, show="*"); e_rpw.pack()
        tk.Label(reg, text="Correo (opcional)", bg="#0b1620", fg="white").pack(pady=6)
        e_mail = tk.Entry(reg); e_mail.pack()
        def registrar():
            if registrar_usuario(e_ru.get().strip(), e_rpw.get().strip(), e_mail.get().strip()):
                reg.destroy()
        tk.Button(reg, text="Registrar", bg="#2196f3", fg="white", command=registrar).pack(pady=10)

    def abrir_recuperar():
        rec = tk.Toplevel(login); rec.title("Recuperar"); rec.geometry("360x200"); rec.configure(bg="#0b1620")
        tk.Label(rec, text="Correo registrado", bg="#0b1620", fg="white").pack(pady=8)
        e_c = tk.Entry(rec); e_c.pack()
        tk.Button(rec, text="Recuperar (simulado)", bg="#e67e22", fg="white",
                  command=lambda: messagebox.showinfo("Recuperar", "Simulación: revisa tu correo (simulado).")).pack(pady=12)
    tk.Button(login, text="Registrar usuario", bg="#2196f3", fg="white", command=abrir_registro).pack(pady=6)
    tk.Button(login, text="Recuperar contraseña (simulado)", bg="#e67e22", fg="white", command=abrir_recuperar).pack(pady=6)

    login.mainloop()

def registrar_usuario(usuario, password, correo):
    if not usuario or not password:
        messagebox.showwarning("Registro", "Usuario y contraseña obligatorios")
        return False
    try:
        conn = sqlite3.connect(resource_path(DB_NAME)); cur = conn.cursor()
        cur.execute("INSERT INTO usuarios (usuario, password, correo) VALUES (?,?,?)",
                    (usuario, hash_password(password), correo or None))
        conn.commit(); conn.close()
        messagebox.showinfo("Registro", "Usuario registrado")
        return True
    except sqlite3.IntegrityError:
        messagebox.showerror("Registro", "Usuario o correo ya existe"); return False

# -----------------------
# Starter
# -----------------------
if __name__ == "__main__":
    abrir_login()
# ===================== MEJORAS ADICIONALES COMPLETAS =====================
# Autor: ChatGPT - GPT-5
# Fecha: Octubre 2025
# Incluye: Backup avanzado, auditoría, validación, exportación, mapa global,
# estadísticas, Panel Admin y Reportes Inteligentes.
# Todas las duplicaciones eliminadas.

import os
import sqlite3
import threading
import datetime
import traceback
import pandas as pd
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from pathlib import Path
import hashlib
import logging
import folium
import webbrowser
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
import zipfile
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

DB_NAME = "iph_database.db"
BACKUP_DIR = Path("backups")
ICON_DIR = Path("icons")
current_user = globals().get("current_user", "Sistema")

# Crear carpetas si no existen
for folder in [BACKUP_DIR, ICON_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Logging básico
logging.basicConfig(
    filename="iph_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ============================================================
# FUNCIONES DE UTILIDAD
# ============================================================

def log_event(event):
    logging.info(f"{current_user} - {event}")

def log_error(e):
    with open("logs.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now()}] ERROR: {str(e)}\n")
        f.write(traceback.format_exc() + "\n\n")

def encriptar_contraseña(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def notificacion(titulo, mensaje):
    messagebox.showinfo(titulo, mensaje)

# ============================================================
# CONEXIÓN A BASE DE DATOS
# ============================================================

def get_db_connection():
    try:
        return sqlite3.connect(DB_NAME)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo conectar a la base de datos:\n{e}")
        log_error(e)
        return None

# ============================================================
# AUDITORÍA DE ACCIONES
# ============================================================

def log_audit(accion, tabla, registro_id=0, usuario=None):
    try:
        usuario = usuario or current_user
        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        if conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS audit (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            accion TEXT, tabla TEXT,
                            registro_id INTEGER, usuario TEXT, fecha TEXT)""")
            c.execute("INSERT INTO audit (accion, tabla, registro_id, usuario, fecha) VALUES (?,?,?,?,?)",
                      (accion, tabla, registro_id, usuario, fecha))
            conn.commit()
            conn.close()
        log_event(f"Auditoría: {accion} en {tabla}")
    except Exception as e:
        log_error(e)

# ============================================================
# RESPALDO AVANZADO
# ============================================================

def backup_db_advanced():
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        today = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = BACKUP_DIR / f"backup_{today}.db"
        conn = sqlite3.connect(DB_NAME)
        bck = sqlite3.connect(backup_file)
        with bck:
            conn.backup(bck)
        bck.close()
        conn.close()
        backups = sorted(BACKUP_DIR.glob("backup_*.db"), key=os.path.getmtime, reverse=True)
        for old in backups[10:]:
            old.unlink()
        log_event(f"Backup exitoso: {backup_file}")
        log_audit("Backup", "sistema")
    except Exception as e:
        log_error(e)

def start_safe_backup_thread():
    def loop():
        while True:
            try:
                backup_db_advanced()
            except Exception as e:
                log_error(e)
            finally:
                threading.Event().wait(86400)
    threading.Thread(target=loop, daemon=True).start()

start_safe_backup_thread()

# ============================================================
# VALIDACIÓN DE FORMULARIOS
# ============================================================

def validar_campos(campos):
    errores = [f"Campo '{k}' no puede estar vacío." for k,v in campos.items() if not v or v.strip()==""]
    if errores:
        messagebox.showwarning("Validación", "\n".join(errores))
        return False
    return True

# ============================================================
# IMPORTAR / EXPORTAR DATOS
# ============================================================

def export_json():
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM iph_records", conn)
        conn.close()
        if df.empty:
            messagebox.showinfo("Exportar JSON", "No hay datos para exportar.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Archivos JSON", "*.json")])
        if filename:
            df.to_json(filename, orient="records", indent=4, force_ascii=False)
            messagebox.showinfo("Exportar JSON", f"Datos exportados correctamente a {filename}")
            log_audit("Exportar", "iph_records")
    except Exception as e:
        log_error(e)

def import_json():
    try:
        filename = filedialog.askopenfilename(filetypes=[("Archivos JSON", "*.json")])
        if not filename: return
        data = pd.read_json(filename)
        conn = get_db_connection()
        c = conn.cursor()
        for _, row in data.iterrows():
            c.execute("""INSERT INTO iph_records (fecha, detenido, vehiculo, coordenadas, usuario)
                         VALUES (?,?,?,?,?)""",
                      (row.get("fecha"), row.get("detenido"), row.get("vehiculo"),
                       row.get("coordenadas"), row.get("usuario","importado")))
        conn.commit()
        conn.close()
        messagebox.showinfo("Importar JSON", f"Datos importados correctamente desde {filename}")
        log_audit("Importar", "iph_records")
    except Exception as e:
        log_error(e)

# ============================================================
# MAPA GLOBAL
# ============================================================

def mapa_global_registros():
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT detenido, coordenadas FROM iph_records WHERE coordenadas != ''", conn)
        conn.close()
        if df.empty:
            messagebox.showinfo("Mapa Global", "No hay registros con coordenadas.")
            return
        m = folium.Map(location=[19.43, -99.13], zoom_start=6)
        for _, row in df.iterrows():
            try:
                lat, lon = map(float, row["coordenadas"].split(","))
                folium.Marker([lat, lon], popup=row["detenido"] or "Sin nombre").add_to(m)
            except: continue
        output_file = "mapa_global_registros.html"
        m.save(output_file)
        webbrowser.open(output_file)
        log_event("Mapa global generado")
    except Exception as e:
        log_error(e)

# ============================================================
# MENÚ HERRAMIENTAS AVANZADAS (SOLO ADMIN)
# ============================================================

def es_admin(usuario):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT rol FROM users WHERE username=?", (usuario,))
        rol = c.fetchone()
        conn.close()
        return rol and rol[0]=="admin"
    except:
        return False

def mostrar_menu_avanzado(menubar):
    if not es_admin(current_user): return
    menu_avanzado = tk.Menu(menubar, tearoff=0)
    menu_avanzado.add_command(label="📈 Generar estadísticas de usuarios", command=generar_estadisticas_usuarios)
    menu_avanzado.add_command(label="🗺️ Ver mapa global de registros", command=mapa_global_registros)
    menu_avanzado.add_command(label="🧹 Compactar backups antiguos", command=compactar_backups_antiguos)
    menu_avanzado.add_command(label="🧰 Diagnóstico del sistema", command=ejecutar_diagnostico)
    menu_avanzado.add_command(label="🧑‍💼 Panel de Administración", command=abrir_panel_admin)
    menu_avanzado.add_command(label="📊 Reportes Inteligentes", command=abrir_reportes_admin)
    menubar.add_cascade(label="🧠 Herramientas Avanzadas", menu=menu_avanzado)
    log_event("Menú avanzado habilitado para admin")

# ============================================================
# FUNCIONES COMPLEMENTARIAS
# ============================================================

def ejecutar_diagnostico():
    issues = []
    for folder in [ICON_DIR, BACKUP_DIR]:
        if not folder.exists(): issues.append(f"❌ Falta carpeta: {folder}")
    conn = get_db_connection()
    try:
        c = conn.cursor()
        for table in ["users","iph_records","audit"]:
            c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not c.fetchone(): issues.append(f"⚠️ Tabla faltante: {table}")
    except Exception as e:
        issues.append(f"Error en DB: {e}")
    if issues: messagebox.showwarning("Diagnóstico", "\n".join(issues))
    else: messagebox.showinfo("Diagnóstico", "✅ Todo correcto")
    log_event("Diagnóstico ejecutado")

def compactar_backups_antiguos():
    try:
        backups = sorted(BACKUP_DIR.glob("backup_*.db"), key=os.path.getmtime)
        if len(backups)<=5: return
        for archivo in backups[:-5]:
            zip_name = archivo.with_suffix(".zip")
            with zipfile.ZipFile(zip_name,"w",zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(archivo, arcname=archivo.name)
            archivo.unlink()
        log_event("Backups antiguos comprimidos")
    except Exception as e:
        log_error(e)

# ============================================================
# ESTADÍSTICAS USUARIOS
# ============================================================

def generar_estadisticas_usuarios():
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT usuario, fecha FROM iph_records", conn)
        conn.close()
        if df.empty:
            messagebox.showinfo("Estadísticas","No hay datos")
            return
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        resumen = df.groupby("usuario").agg(Total_Registros=("usuario","count"),
                                           Primer_Registro=("fecha","min"),
                                           Último_Registro=("fecha","max")).reset_index()
        output = Path.cwd() / f"estadisticas_usuarios_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        resumen.to_excel(output, index=False)
        messagebox.showinfo("Estadísticas generadas", f"Archivo: {output}")
        log_event("Estadísticas generadas")
    except Exception as e:
        log_error(e)

# ============================================================
# PANEL ADMIN
# ============================================================

def abrir_panel_admin():
    try:
        if not es_admin(current_user):
            messagebox.showwarning("Acceso denegado","Solo administradores pueden acceder.")
            return
        panel = tk.Toplevel()
        panel.title("Panel de Administración")
        panel.geometry("600x400")
        tk.Label(panel,text=f"Bienvenido {current_user} - Panel Admin", font=("Arial",14)).pack(pady=10)

        tree = ttk.Treeview(panel, columns=("Usuario","Rol"), show="headings")
        tree.heading("Usuario", text="Usuario")
        tree.heading("Rol", text="Rol")
        tree.pack(expand=True, fill="both", pady=10)

        conn = get_db_connection()
        df = pd.read_sql("SELECT username, rol FROM users", conn)
        conn.close()
        for _, row in df.iterrows():
            tree.insert("",tk.END, values=(row["username"], row["rol"]))

        tk.Button(panel, text="Cerrar", command=panel.destroy).pack(pady=5)
        log_event("Panel Admin abierto")
    except Exception as e:
        log_error(e)

# ============================================================
# REPORTES INTELIGENTES
# ============================================================

def abrir_reportes_admin():
    try:
        if not es_admin(current_user):
            messagebox.showwarning("Acceso denegado","Solo administradores pueden acceder.")
            return
        reporte = tk.Toplevel()
        reporte.title("Reportes Inteligentes")
        reporte.geometry("700x500")
        tk.Label(reporte,text="Reportes Inteligentes - IPH", font=("Arial",14)).pack(pady=10)

        conn = get_db_connection()
        df = pd.read_sql("SELECT fecha, detenido, vehiculo, usuario FROM iph_records", conn)
        conn.close()
        if df.empty:
            tk.Label(reporte,text="No hay datos para mostrar.", fg="red").pack(pady=20)
            return

        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df_count = df.groupby(df["fecha"].dt.date).size()
        fig, ax = plt.subplots(figsize=(6,3))
        df_count.plot(kind="bar", ax=ax)
        ax.set_title("Registros por día")
        ax.set_xlabel("Fecha")
        ax.set_ylabel("Cantidad")

        canvas_fig = FigureCanvasTkAgg(fig, master=reporte)
        canvas_fig.draw()
        canvas_fig.get_tk_widget().pack(expand=True, fill="both", pady=10)

        tk.Button(reporte, text="Cerrar", command=reporte.destroy).pack(pady=5)
        log_event("Reportes Inteligentes abiertos")
    except Exception as e:
        log_error(e)
# ===================== BLOQUE FINAL DE MEJORAS INTEGRADAS =====================
# Autor: ChatGPT - GPT-5
# Fecha: Octubre 2025
# Incluye: Seguridad, auditoría, backups automáticos, estadísticas en tiempo real,
# mapas interactivos, exportación a Excel/PDF, reportes gráficos, panel admin.

import os
import sqlite3
import hashlib
import threading
import datetime
import traceback
import pandas as pd
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import folium
import webbrowser
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from pathlib import Path
import zipfile

# ----------------------------
# CONFIGURACIÓN DE LOGS
# ----------------------------
logging.basicConfig(
    filename="iph_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def log_event(event):
    user = globals().get("current_user", "Sistema")
    logging.info(f"{user} - {event}")

def log_error(e):
    with open("logs.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now()}] ERROR: {str(e)}\n")
        f.write(traceback.format_exc() + "\n\n")

# ----------------------------
# SEGURIDAD
# ----------------------------
FAILED_ATTEMPTS = {}

def encriptar_contraseña(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verificar_intentos_login(username):
    intentos = FAILED_ATTEMPTS.get(username, 0)
    if intentos >= 5:
        messagebox.showerror("Bloqueo", "Demasiados intentos fallidos. Intente más tarde.")
        log_event(f"Usuario bloqueado: {username}")
        return False
    return True

def registrar_intento_fallido(username):
    FAILED_ATTEMPTS[username] = FAILED_ATTEMPTS.get(username, 0) + 1
    log_event(f"Intento fallido #{FAILED_ATTEMPTS[username]} - {username}")
    if FAILED_ATTEMPTS[username] >= 5:
        messagebox.showwarning("Seguridad", f"Usuario '{username}' bloqueado temporalmente.")

def registrar_login(username):
    try:
        log_event(f"Inicio de sesión: {username}")
    except Exception as e:
        logging.error(f"Error al registrar login: {e}")

def registrar_logout(username):
    try:
        log_event(f"Cierre de sesión: {username}")
    except Exception as e:
        logging.error(f"Error al registrar logout: {e}")

# ----------------------------
# AUDITORÍA
# ----------------------------
def registrar_auditoria(usuario, accion, detalles=""):
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    registro = f"{fecha} | {usuario} | {accion} | {detalles}\n"
    with open("auditoria.txt", "a", encoding="utf-8") as f:
        f.write(registro)

# ----------------------------
# BACKUPS AUTOMÁTICOS
# ----------------------------
BACKUP_DIR = Path("backups")
DB_NAME = "iph_database.db"

def backup_db_advanced():
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        today = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = BACKUP_DIR / f"backup_{today}.db"
        conn = sqlite3.connect(DB_NAME)
        bck = sqlite3.connect(backup_file)
        with bck:
            conn.backup(bck)
        bck.close()
        conn.close()
        backups = sorted(BACKUP_DIR.glob("backup_*.db"), key=os.path.getmtime, reverse=True)
        for old in backups[10:]:
            old.unlink()
        log_event(f"Backup avanzado creado: {backup_file}")
    except Exception as e:
        log_error(e)

def iniciar_backup_diario():
    def loop():
        while True:
            try:
                backup_db_advanced()
            except Exception as e:
                log_error(e)
            finally:
                threading.Event().wait(86400)  # 24 horas
    threading.Thread(target=loop, daemon=True).start()

iniciar_backup_diario()

def compactar_backups_antiguos():
    try:
        backups = sorted(BACKUP_DIR.glob("backup_*.db"), key=os.path.getmtime)
        if len(backups) <= 5:
            return
        antiguos = backups[:-5]
        for archivo in antiguos:
            zip_name = archivo.with_suffix(".zip")
            with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(archivo, arcname=archivo.name)
            archivo.unlink()
        log_event("Backups antiguos comprimidos correctamente.")
    except Exception as e:
        log_error(e)

# ----------------------------
# VALIDACIONES
# ----------------------------
def validar_campos(campos):
    errores = []
    for nombre, valor in campos.items():
        if valor is None or valor == "":
            errores.append(f"Campo '{nombre}' no puede estar vacío.")
    if errores:
        messagebox.showwarning("Validación", "\n".join(errores))
        return False
    return True

# ----------------------------
# EXPORTACIONES
# ----------------------------
def exportar_a_excel(df, nombre_archivo="export.xlsx"):
    try:
        df.to_excel(nombre_archivo, index=False)
        log_event(f"Exportación a Excel: {nombre_archivo}")
        messagebox.showinfo("Exportación", f"Datos exportados a {nombre_archivo}")
    except Exception as e:
        log_error(e)
        messagebox.showerror("Error", "Error exportando a Excel")

def exportar_a_pdf(df, nombre_archivo="export.pdf"):
    try:
        from reportlab.platypus import SimpleDocTemplate, Table
        doc = SimpleDocTemplate(nombre_archivo, pagesize=letter)
        data = [df.columns.tolist()] + df.values.tolist()
        table = Table(data)
        doc.build([table])
        log_event(f"Exportación a PDF: {nombre_archivo}")
        messagebox.showinfo("Exportación", f"Datos exportados a {nombre_archivo}")
    except Exception as e:
        log_error(e)
        messagebox.showerror("Error", "Error exportando a PDF")

# ----------------------------
# ESTADÍSTICAS Y MAPAS
# ----------------------------
def generar_estadisticas_realtime():
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT usuario, vehiculo FROM iph_records", conn)
        conn.close()
        if df.empty:
            messagebox.showinfo("Estadísticas", "No hay registros para generar estadísticas.")
            return
        resumen_usuario = df.groupby("usuario").size().reset_index(name="Total_Registros")
        resumen_tipo = df.groupby("vehiculo").size().reset_index(name="Total_Registros")
        file_resumen = f"estadisticas_realtime_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        with pd.ExcelWriter(file_resumen) as writer:
            resumen_usuario.to_excel(writer, sheet_name="Por Usuario", index=False)
            resumen_tipo.to_excel(writer, sheet_name="Por Tipo", index=False)
        messagebox.showinfo("Estadísticas generadas", f"Archivo generado:\n{file_resumen}")
        log_event("Estadísticas en tiempo real generadas.")
    except Exception as e:
        log_error(e)
        messagebox.showerror("Error", f"No se pudieron generar estadísticas: {e}")

def mapa_global_interactivo():
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT detenido, coordenadas FROM iph_records WHERE coordenadas != ''", conn)
        conn.close()
        if df.empty:
            messagebox.showinfo("Mapa Global", "No hay registros con coordenadas.")
            return
        latitudes = []
        longitudes = []
        for coord in df["coordenadas"]:
            try:
                lat, lon = map(float, coord.split(","))
                latitudes.append(lat)
                longitudes.append(lon)
            except:
                continue
        if not latitudes or not longitudes:
            messagebox.showinfo("Mapa Global", "No hay coordenadas válidas.")
            return
        lat_centro = sum(latitudes)/len(latitudes)
        lon_centro = sum(longitudes)/len(longitudes)
        m = folium.Map(location=[lat_centro, lon_centro], zoom_start=5, tiles="OpenStreetMap")
        for _, row in df.iterrows():
            try:
                lat, lon = map(float, row["coordenadas"].split(","))
                folium.Marker(location=[lat, lon],
                              popup=row["detenido"] or "Sin nombre",
                              icon=folium.Icon(color="red", icon="info-sign")).add_to(m)
            except:
                continue
        mapa_file = "mapa_global_interactivo.html"
        m.save(mapa_file)
        webbrowser.open(mapa_file)
        log_event("Mapa global interactivo generado.")
    except Exception as e:
        log_error(e)
        messagebox.showerror("Error", f"No se pudo generar el mapa interactivo: {e}")

def monitorear_registros(intervalo_segundos=300):
    def loop():
        while True:
            try:
                generar_estadisticas_realtime()
            except Exception as e:
                log_error(e)
            finally:
                threading.Event().wait(intervalo_segundos)
    threading.Thread(target=loop, daemon=True).start()

monitorear_registros()

# ----------------------------
# INICIALIZACIÓN DEL SISTEMA MEJORADO
# ----------------------------
def verificar_integridad():
    missing = []
    for folder in [BACKUP_DIR]:
        if not folder.exists():
            missing.append(str(folder))
    if missing:
        messagebox.showwarning("Integridad del Sistema",
                               f"Se detectaron carpetas faltantes:\n{chr(10).join(missing)}\nSe crearán automáticamente.")
        for path in missing:
            Path(path).mkdir(parents=True, exist_ok=True)

def iniciar_mejoras_finales():
    verificar_integridad()
    iniciar_backup_diario()
    print("✅ Sistema IPH mejorado e inicializado correctamente.")

iniciar_mejoras_finales()
# ===================== FIN BLOQUE FINAL DE MEJORAS =====================
# ===================== BLOQUE DE MEJORAS AVANZADAS =====================
# Autor: ChatGPT - GPT-5
# Fecha: Octubre 2025
# Este bloque amplía la funcionalidad del sistema IPH sin modificar el código original.

import threading
import datetime
import sqlite3
import pandas as pd
import tkinter as tk
from tkinter import messagebox, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import folium
import webbrowser
import logging
import hashlib
import os

# -----------------------------
# CONFIGURACIÓN DE LOGS
# -----------------------------
logging.basicConfig(
    filename="iph_advanced_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def log_event(event):
    """Registra eventos importantes del sistema."""
    user = globals().get("current_user", "Sistema")
    logging.info(f"{user} - {event}")

# -----------------------------
# 1️⃣ AUTOMATIZACIÓN DE ALERTAS Y VALIDACIONES
# -----------------------------
def alertar_supervisor(mensaje):
    """Envía alerta simple a supervisor (UI)."""
    messagebox.showwarning("Alerta Supervisión", mensaje)
    log_event(f"Alerta enviada: {mensaje}")

def validar_datos_registro(datos: dict):
    """Valida campos esenciales de un registro IPH."""
    errores = []
    for campo, valor in datos.items():
        if not valor:
            errores.append(f"Campo '{campo}' no puede estar vacío.")
    if errores:
        messagebox.showwarning("Validación de Registro", "\n".join(errores))
        return False
    return True

# -----------------------------
# 2️⃣ GESTIÓN DE DATOS Y BACKUPS AVANZADOS
# -----------------------------
BACKUP_DIR = "backups_advanced"
DB_NAME = "iph_database.db"

def backup_avanzado():
    """Backup con control de versiones, mantiene últimos 10."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = os.path.join(BACKUP_DIR, f"backup_{now}.db")
        conn = sqlite3.connect(DB_NAME)
        bck = sqlite3.connect(backup_file)
        with bck:
            conn.backup(bck)
        bck.close()
        conn.close()
        # Mantener solo últimos 10
        backups = sorted(os.listdir(BACKUP_DIR))
        for old in backups[:-10]:
            os.remove(os.path.join(BACKUP_DIR, old))
        log_event(f"Backup avanzado creado: {backup_file}")
    except Exception as e:
        logging.error(f"Error backup avanzado: {e}")

def iniciar_backup_diario():
    """Inicia backup diario en hilo separado."""
    def loop():
        while True:
            ahora = datetime.datetime.now()
            siguiente = datetime.datetime.combine(ahora.date(), datetime.time(2,0))
            if ahora > siguiente:
                siguiente += datetime.timedelta(days=1)
            segundos_espera = (siguiente - ahora).total_seconds()
            threading.Event().wait(segundos_espera)
            backup_avanzado()
    threading.Thread(target=loop, daemon=True).start()

# -----------------------------
# 3️⃣ OPTIMIZACIÓN DE INTERFAZ
# -----------------------------
def mostrar_notificacion_ui(titulo, mensaje):
    """Muestra un mensaje emergente en la UI."""
    messagebox.showinfo(titulo, mensaje)
    log_event(f"Notificación mostrada: {titulo}")

# -----------------------------
# 4️⃣ ANÁLISIS PREDICTIVO Y ESTADÍSTICAS
# -----------------------------
def estadisticas_iph_por_usuario():
    """Genera estadística de registros por usuario."""
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql("SELECT usuario, fecha FROM iph_records", conn)
        conn.close()
        if df.empty:
            mostrar_notificacion_ui("Estadísticas", "No hay registros disponibles.")
            return
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        resumen = df.groupby("usuario").agg(
            total_registros=("usuario","count"),
            primer_registro=("fecha","min"),
            ultimo_registro=("fecha","max")
        ).reset_index()
        archivo = f"estadisticas_usuarios_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        resumen.to_excel(archivo, index=False)
        mostrar_notificacion_ui("Estadísticas", f"Archivo generado: {archivo}")
        log_event("Estadísticas de usuarios generadas.")
    except Exception as e:
        logging.error(f"Error generar estadísticas: {e}")
        messagebox.showerror("Error", f"No se pudieron generar estadísticas: {e}")

# -----------------------------
# 5️⃣ VISUALIZACIÓN DE DATOS EN MAPA GLOBAL
# -----------------------------
def mapa_global_iph():
    """Genera mapa con coordenadas de registros IPH."""
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql("SELECT detenido, coordenadas FROM iph_records WHERE coordenadas != ''", conn)
        conn.close()
        if df.empty:
            mostrar_notificacion_ui("Mapa Global", "No hay registros con coordenadas.")
            return
        m = folium.Map(location=[19.43, -99.13], zoom_start=6)
        for _, row in df.iterrows():
            try:
                lat, lon = map(float, row["coordenadas"].split(","))
                folium.Marker([lat, lon], popup=row["detenido"] or "Sin nombre").add_to(m)
            except:
                continue
        archivo = "mapa_global_iph.html"
        m.save(archivo)
        webbrowser.open(archivo)
        log_event("Mapa global de registros generado.")
    except Exception as e:
        logging.error(f"Error mapa global: {e}")
        messagebox.showerror("Error", f"No se pudo generar el mapa: {e}")

# -----------------------------
# 6️⃣ SEGURIDAD AVANZADA
# -----------------------------
def encriptar_password(password):
    """Encripta contraseña usando SHA-256."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

FAILED_ATTEMPTS = {}

def verificar_intentos(usuario):
    intentos = FAILED_ATTEMPTS.get(usuario,0)
    if intentos >= 5:
        messagebox.showerror("Bloqueo", f"Usuario {usuario} bloqueado temporalmente.")
        log_event(f"Usuario bloqueado: {usuario}")
        return False
    return True

def registrar_intento_fallido(usuario):
    FAILED_ATTEMPTS[usuario] = FAILED_ATTEMPTS.get(usuario,0)+1
    log_event(f"Intento fallido #{FAILED_ATTEMPTS[usuario]} - {usuario}")

# -----------------------------
# INICIALIZACIÓN AUTOMÁTICA
# -----------------------------
def iniciar_mejoras_avanzadas():
    """Ejecuta todas las mejoras automáticamente al iniciar."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    iniciar_backup_diario()
    log_event("Sistema IPH con mejoras avanzadas iniciado.")

# Ejecutar mejoras al cargar el sistema
iniciar_mejoras_avanzadas()

# ===================== FIN BLOQUE MEJORAS AVANZADAS =====================
import mysql.connector
from mysql.connector import Error

def conectar_base_datos():
    """Establece la conexión con la base de datos MySQL."""
    try:
        conexion = mysql.connector.connect(
            host='localhost',
            database='nombre_base_datos',
            user='usuario',
            password='contraseña'
        )
        if conexion.is_connected():
            print("Conexión exitosa a la base de datos")
            return conexion
    except Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

def cerrar_conexion(conexion):
    """Cierra la conexión con la base de datos."""
    if conexion.is_connected():
        conexion.close()
        print("Conexión cerrada")

if __name__ == "__main__":
    conexion = conectar_base_datos()
    if conexion:
        # Realiza operaciones con la base de datos aquí
        cerrar_conexion(conexion)

