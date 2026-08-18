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

# Tu API Key de Google AI Studio
GEMINI_API_KEY = "TU_API_KEY_AQUI"

# -------------------------------------------------------------
# BASE DE DATOS
# -------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect("halterofilia.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS intentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo_sesion TEXT,
            pr_base REAL,
            bloque_combo TEXT,
            serie TEXT,
            repeticion TEXT,
            movimiento TEXT,
            pct_pr REAL,
            peso REAL,
            resultado TEXT,
            observacion TEXT
        )
    """)
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
            "Series": st.column_config.NumberColumn(min_value=1, max_value=10, default=1),
            "Reps": st.column_config.NumberColumn(min_value=1, max_value=10, default=1),
            "% 1RM": st.column_config.NumberColumn(min_value=10, max_value=120, default=70, format="%d%%")
        }
    )

    if st.button("⚡ Generar Matriz de Movimientos"):
        filas_generadas = []
        for _, row in pizarra_editada.iterrows():
            tipo_mov = str(row["Tipo"])
            pr_aplicable = pr_arranque if tipo_mov == "Arranque" else pr_envion
            complejo_str = str(row["Complejo / Ejercicios"])
            movimientos = [m.strip() for m in complejo_str.split("+") if m.strip()]
            series = int(row["Series"])
            reps = int(row["Reps"])
            pct = float(row["% 1RM"])
            peso_calculado = round((pr_aplicable * (pct / 100.0)) * 2) / 2
            
            for s in range(1, series + 1):
                for r in range(1, reps + 1):
                    for mov in movimientos:
                        filas_generadas.append({
                            "Tipo": tipo_mov,
                            "Bloque": complejo_str,
                            "Serie": f"S{s}",
                            "Rep": f"Rep {r}",
                            "Movimiento": mov,
                            "Carga (kg)": peso_calculado,
                            "% 1RM": f"{int(pct)}%",
                            "Válido (✔)": True,
                            "Observación Técnica": ""
                        })
        st.session_state["matriz_activa"] = pd.DataFrame(filas_generadas)

    if "matriz_activa" in st.session_state:
        st.divider()
        st.subheader("3. Registro de Ejecución en Vivo")
        matriz_final = st.data_editor(
            st.session_state["matriz_activa"],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Válido (✔)": st.column_config.CheckboxColumn("¿Válido?", default=True),
                "Carga (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, step=0.5),
                "Observación Técnica": st.column_config.TextColumn("Observación", width="large")
            }
        )

        if st.button("💾 Guardar Entrenamiento Completo"):
            conn = get_db_connection()
            c = conn.cursor()
            for _, r in matriz_final.iterrows():
                res = "Completado" if r["Válido (✔)"] else "Falla"
                pr_guardado = pr_arranque if r["Tipo"] == "Arranque" else pr_envion
                c.execute("""
                    INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(fecha_sel), r["Tipo"], pr_guardado, r["Bloque"],
                    r["Serie"], r["Rep"], r["Movimiento"],
                    float(str(r["% 1RM"]).replace("%", "")),
                    float(r["Carga (kg)"]), res, str(r["Observación Técnica"])
                ))
            conn.commit()
            conn.close()
            st.success("¡Sesión guardada con éxito!")
            del st.session_state["matriz_activa"]

# -------------------------------------------------------------
# MÓDULO 2: DETALLE DIARIO
# -------------------------------------------------------------
elif menu == "🔍 Detalle Diario":
    st.title("📋 Resumen Diario por Movimiento")
    conn = get_db_connection()
    df_raw = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_raw.empty:
        st.info("No hay entrenamientos guardados aún.")
    else:
        fechas = sorted(df_raw["fecha"].unique(), reverse=True)
        fecha_sel = st.selectbox("Selecciona la fecha", fechas)
        df_dia = df_raw[df_raw["fecha"] == fecha_sel]

        tot_movs = len(df_dia)
        tot_val = len(df_dia[df_dia["resultado"] == "Completado"])
        tot_fal = len(df_dia[df_dia["resultado"] == "Falla"])
        pct_efectividad = (tot_val / tot_movs * 100) if tot_movs > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Efectividad Global", f"{pct_efectividad:.1f}%")
        c2.metric("Válidos", tot_val)
        c3.metric("Fallas", tot_fal)
        c4.metric("Total Movimientos", tot_movs)

        st.dataframe(
            df_dia[["tipo_sesion", "serie", "repeticion", "movimiento", "peso", "pct_pr", "resultado", "observacion"]].rename(columns={
                "tipo_sesion": "Tipo", "serie": "Serie", "repeticion": "Rep", "movimiento": "Movimiento",
                "peso": "Peso (kg)", "pct_pr": "% 1RM", "resultado": "Resultado", "observacion": "Observación Técnica"
            }),
            use_container_width=True
        )

# -------------------------------------------------------------
# MÓDULO 3: DASHBOARD SEMESTRAL
# -------------------------------------------------------------
elif menu == "📊 Dashboard Semestral":
    st.title("📈 Progreso y Diagnóstico Semestral")
    conn = get_db_connection()
    df_all = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_all.empty:
        st.info("No hay datos suficientes para graficar.")
    else:
        df_all["fecha"] = pd.to_datetime(df_all["fecha"])
        df_all["is_comp"] = df_all["resultado"] == "Completado"
        df_all["is_falla"] = df_all["resultado"] == "Falla"

        df_progreso = df_all.groupby(["fecha", "tipo_sesion"]).agg(
            Válidos=("is_comp", "sum"),
            Total=("id", "count")
        ).reset_index()
        df_progreso["% Efectividad"] = (df_progreso["Válidos"] / df_progreso["Total"]) * 100

        fig_line = px.line(
            df_progreso,
            x="fecha",
            y="% Efectividad",
            color="tipo_sesion",
            markers=True,
            title="Curva de Efectividad Técnica Semestral: Arranque vs Envión",
            labels={"fecha": "Fecha", "% Efectividad": "% Éxito", "tipo_sesion": "Levantamiento"}
        )
        fig_line.update_yaxes(range=[0, 105])
        st.plotly_chart(fig_line, use_container_width=True)
