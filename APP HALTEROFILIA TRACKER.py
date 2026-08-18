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

st.set_page_config(page_title="Tracker Halterofilia Pro", page_icon="🏋️‍♂️", layout="wide")

GEMINI_API_KEY = "AQ.Ab8RN6I8munB4uXzOxh6dzT90Z3UNZ7iNXG27jzq8V-toHW0lw"

# -------------------------------------------------------------
# BASE DE DATOS (NUEVA TABLA LIMPIA: entrenamientos_v2)
# -------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect("halterofilia.db", timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS entrenamientos_v2 (
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
    3. "Series": Número de series (ej. 2).
    4. "Reps": Número de repeticiones (ej. 1).
    5. "% 1RM": El porcentaje de 1RM como entero (ej. 80 para 80%).

    Responde ÚNICAMENTE con un JSON válido estructurado como lista:
    [
      {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque + Arranque", "Series": 2, "Reps": 1, "% 1RM": 80},
      {"Tipo": "Envión", "Complejo / Ejercicios": "Cargada + Yerk", "Series": 3, "Reps": 1, "% 1RM": 85}
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
    st.title("🏋️‍♂️ Planificación de Sesión")
    
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
                    datos = procesar_pizarra_con_ia(uploaded_img, GEMINI_API_KEY)
                    st.session_state["pizarra_datos"] = pd.DataFrame(datos)
                    st.success("¡Pizarra leída con éxito!")
                except Exception as e:
                    st.error(f"Error al procesar: {e}")

    st.divider()
    st.subheader("2. Esquema de Entrenamiento")
    st.caption("Escribe tus ejercicios o agrega filas con '+':")

    # Tabla en blanco por defecto
    if "pizarra_datos" not in st.session_state:
        st.session_state["pizarra_datos"] = pd.DataFrame({
            "Tipo": ["Arranque"],
            "Complejo / Ejercicios": [""],
            "Series": [1],
            "Reps": [1],
            "% 1RM": [70]
        })

    pizarra_editada = st.data_editor(
        st.session_state["pizarra_datos"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Arranque", "Envión", "Fuerza"], required=True),
            "Complejo / Ejercicios": st.column_config.TextColumn("Complejo / Ejercicios", width="large"),
            "Series": st.column_config.NumberColumn("Series", min_value=1, max_value=10, default=1),
            "Reps": st.column_config.NumberColumn("Reps", min_value=1, max_value=10, default=1),
            "% 1RM": st.column_config.NumberColumn("% 1RM", min_value=10, max_value=120, default=70, format="%d%%")
        }
    )

    if st.button("⚡ Generar Matriz de Movimientos"):
        filas = []
        for _, row in pizarra_editada.iterrows():
            ejercicio_texto = str(row.get("Complejo / Ejercicios", "")).strip()
            if not ejercicio_texto or pd.isna(row.get("Complejo / Ejercicios")):
                continue
            
            tipo_mov = str(row.get("Tipo", "Arranque"))
            pr_base = pr_arranque if tipo_mov == "Arranque" else pr_envion
            movimientos = [m.strip() for m in ejercicio_texto.split("+") if m.strip()]
            series = int(row.get("Series", 1)) if pd.notna(row.get("Series")) else 1
            reps = int(row.get("Reps", 1)) if pd.notna(row.get("Reps")) else 1
            pct = float(row.get("% 1RM", 70.0)) if pd.notna(row.get("% 1RM")) else 70.0
            peso = round((pr_base * (pct / 100.0)) * 2) / 2
            
            for s in range(1, series + 1):
                for r in range(1, reps + 1):
                    for mov in movimientos:
                        filas.append({
                            "Tipo": tipo_mov,
                            "Bloque": ejercicio_texto,
                            "Serie": f"S{s}",
                            "Rep": f"Rep {r}",
                            "Movimiento": mov,
                            "Carga (kg)": peso,
                            "% 1RM": f"{int(pct)}%",
                            "Válido (✔)": True,
                            "Observación Técnica": ""
                        })
        if filas:
            st.session_state["matriz_activa"] = pd.DataFrame(filas)
        else:
            st.warning("Escribe al menos un ejercicio en la columna 'Complejo / Ejercicios' antes de generar la matriz.")

    if "matriz_activa" in st.session_state and not st.session_state["matriz_activa"].empty:
        st.divider()
        st.subheader("3. Registro de Ejecución en Vivo")
        
        matriz_final = st.data_editor(
            st.session_state["matriz_activa"],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Válido (✔)": st.column_config.CheckboxColumn("¿Válido?", default=True),
                "Carga (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, step=0.5),
                "Observación Técnica": st.column_config.TextColumn("Observación Técnica", width="large")
            }
        )

        if st.button("💾 Guardar Entrenamiento Completo"):
            conn = get_db_connection()
            c = conn.cursor()
            for _, r in matriz_final.iterrows():
                valido = bool(r.get("Válido (✔)", True)) if pd.notna(r.get("Válido (✔)")) else True
                res = "Completado" if valido else "Falla"
                tipo_reg = str(r.get("Tipo", "Arranque"))
                pr_base = pr_arranque if tipo_reg == "Arranque" else pr_envion
                bloque_val = str(r.get("Bloque", "")) if pd.notna(r.get("Bloque")) else "General"
                serie_val = str(r.get("Serie", "S1")) if pd.notna(r.get("Serie")) else "S1"
                rep_val = str(r.get("Rep", "Rep 1")) if pd.notna(r.get("Rep")) else "Rep 1"
                mov_val = str(r.get("Movimiento", "")) if pd.notna(r.get("Movimiento")) else bloque_val
                pct_val = float(str(r.get("% 1RM", "70")).replace("%", "")) if pd.notna(r.get("% 1RM")) else 70.0
                peso_val = float(r.get("Carga (kg)", 0.0)) if pd.notna(r.get("Carga (kg)")) else 0.0
                obs_val = str(r.get("Observación Técnica", "")) if pd.notna(r.get("Observación Técnica")) else ""
                
                c.execute("""
                    INSERT INTO entrenamientos_v2 (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(fecha_sel), tipo_reg, float(pr_base), bloque_val,
                    serie_val, rep_val, mov_val,
                    pct_val, peso_val, res, obs_val
                ))
            conn.commit()
            conn.close()
            st.success("¡Sesión guardada con éxito!")
            del st.session_state["matriz_activa"]
            st.rerun()

# -------------------------------------------------------------
# MÓDULO 2: DETALLE DIARIO
# -------------------------------------------------------------
elif menu == "🔍 Detalle Diario":
    st.title("📋 Resumen Diario por Movimiento")
    conn = get_db_connection()
    df_raw = pd.read_sql_query("SELECT * FROM entrenamientos_v2", conn)
    conn.close()

    if df_raw.empty:
        st.info("No hay entrenamientos guardados aún.")
    else:
        fechas = sorted(df_raw["fecha"].dropna().unique(), reverse=True)
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

        cols_mostrar = [c for c in ["tipo_sesion", "serie", "repeticion", "movimiento", "peso", "pct_pr", "resultado", "observacion"] if c in df_dia.columns]
        st.dataframe(
            df_dia[cols_mostrar].rename(columns={
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
    df_all = pd.read_sql_query("SELECT * FROM entrenamientos_v2", conn)
    conn.close()

    if df_all.empty:
        st.info("No hay datos suficientes para graficar.")
    else:
        df_all["fecha"] = pd.to_datetime(df_all["fecha"])
        df_all["is_comp"] = df_all["resultado"] == "Completado"

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
