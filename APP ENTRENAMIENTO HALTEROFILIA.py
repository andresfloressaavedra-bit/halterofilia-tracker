import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from PIL import Image
import json
from datetime import date

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# Configuración visual
st.set_page_config(page_title="Tracker Halterofilia Pro", page_icon="🏋️‍♂️", layout="wide")

# Bloqueo del gesto "pull-to-refresh" en navegadores móviles táctiles
st.markdown("""
    <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            overscroll-behavior-y: contain !important;
            overscroll-behavior-x: none !important;
        }
    </style>
""", unsafe_allow_html=True)

# Tu clave de Gemini AI Studio
GEMINI_API_KEY = "TU_API_KEY_AQUI"

# -------------------------------------------------------------
# BASE DE DATOS (MIGRACIÓN AUTOMÁTICA)
# -------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect("halterofilia.db", timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Crear tabla base si no existe
    c.execute("""
        CREATE TABLE IF NOT EXISTS intentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_sesion TEXT,
            pr_base REAL,
            ejercicio TEXT,
            serie TEXT,
            intento INTEGER,
            peso REAL,
            resultado TEXT,
            observacion TEXT
        )
    """)
    
    # Auto-reparar columnas faltantes en la nube
    c.execute("PRAGMA table_info(intentos)")
    columnas_actuales = [col[1] for col in c.fetchall()]
    
    nuevas_columnas = {
        "bloque_combo": "TEXT",
        "repeticion": "TEXT",
        "movimiento": "TEXT",
        "pct_pr": "REAL"
    }
    
    for col, tipo in nuevas_columnas.items():
        if col not in columnas_actuales:
            try:
                c.execute(f"ALTER TABLE intentos ADD COLUMN {col} {tipo}")
            except Exception:
                pass
                
    conn.commit()
    conn.close()

init_db()

menu = st.sidebar.radio("Navegación", ["📷 Subir / Planificar Sesión", "🔍 Detalle Diario", "📊 Dashboard Semestral"])

# -------------------------------------------------------------
# OCR CON GEMINI
# -------------------------------------------------------------
def procesar_pizarra_con_ia(image_file, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    img = Image.open(image_file)
    
    prompt = """
    Analiza esta foto de una pizarra de halterofilia. Extrae los ejercicios planificados.
    Para cada línea identifica:
    1. "Tipo": 'Arranque', 'Envión' o 'Fuerza'.
    2. "Complejo / Ejercicios": El nombre del ejercicio o combo (separando movimientos con '+').
    3. "Series": Número de series (ej. de 2x1 es 2).
    4. "Reps": Número de repeticiones (ej. de 2x1 es 1).
    5. "% 1RM": El porcentaje de 1RM como entero (ej. 80 para 80%).

    Responde ÚNICAMENTE con un JSON válido estructurado como lista:
    [
      {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 1, "Reps": 2, "% 1RM": 50},
      {"Tipo": "Envión", "Complejo / Ejercicios": "Cargada c/p + Yerk", "Series": 2, "Reps": 1, "% 1RM": 85}
    ]
    """
    response = model.generate_content([prompt, img])
    raw_text = response.text.strip()
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].split("```")[0].strip()
    return json.loads(raw_text)

# -------------------------------------------------------------
# MÓDULO 1: SUBIDA Y PLANIFICACIÓN
# -------------------------------------------------------------
if menu == "📷 Subir / Planificar Sesión":
    st.title("🏋️‍♂️ Planificación de Sesión (Arranque / Envión)")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        fecha_sel = st.date_input("Fecha", date.today())
    with c2:
        enfoque = st.selectbox("Enfoque General", ["Arranque + Envión", "Arranque", "Envión", "Fuerza"])
    with c3:
        pr_arranque = st.number_input("PR Arranque (kg)", min_value=1.0, value=70.0, step=2.5)
    with c4:
        pr_envion = st.number_input("PR Envión (kg)", min_value=1.0, value=90.0, step=2.5)

    st.divider()
    st.subheader("1. Cargar desde Foto de Pizarra (Opcional)")
    uploaded_img = st.file_uploader("Subir foto de la pizarra", type=["png", "jpg", "jpeg"])

    if uploaded_img and GEMINI_API_KEY and GEMINI_API_KEY != "TU_API_KEY_AQUI" and HAS_GENAI:
        if st.button("🤖 Leer Pizarra Automáticamente"):
            with st.spinner("Analizando pizarra con IA..."):
                try:
                    datos_leidos = procesar_pizarra_con_ia(uploaded_img, GEMINI_API_KEY)
                    st.session_state["pizarra_datos"] = pd.DataFrame(datos_leidos)
                    st.success("¡Pizarra leída con éxito!")
                except Exception as e:
                    st.error(f"Error al procesar la imagen: {e}")

    st.divider()
    st.subheader("2. Esquema de Entrenamiento")
    
    if "pizarra_datos" not in st.session_state:
        st.session_state["pizarra_datos"] = pd.DataFrame([
            {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 1, "Reps": 2, "% 1RM": 50},
            {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 1, "Reps": 2, "% 1RM": 60},
            {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 2, "Reps": 2, "% 1RM": 70},
            {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 4, "Reps": 1, "% 1RM": 80},
            {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón c/p + Clásico", "Series": 2, "Reps": 1, "% 1RM": 85},
        ])

    pizarra_editada = st.data_editor(
        st.session_state["pizarra_datos"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Arranque", "Envión", "Fuerza"], required=True),
            "Series": st.column_config.NumberColumn(min_value=1, max
