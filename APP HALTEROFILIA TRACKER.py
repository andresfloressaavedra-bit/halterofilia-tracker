import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import json
import base64
import requests
from datetime import date

st.set_page_config(page_title="Tracker Halterofilia Pro", page_icon="🏋️‍♂️", layout="wide")

# Clave tomada de forma segura desde Streamlit Secrets
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

# -------------------------------------------------------------
# BASE DE DATOS
# -------------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect("halterofilia.db", timeout=10)
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
            ejercicio TEXT,
            serie TEXT,
            intento INTEGER,
            peso REAL,
            resultado TEXT,
            observacion TEXT
        )
    """)
    c.execute("PRAGMA table_info(intentos)")
    columnas = [col[1] for col in c.fetchall()]
    
    nuevas = {
        "bloque_combo": "TEXT",
        "repeticion": "TEXT",
        "movimiento": "TEXT",
        "pct_pr": "REAL"
    }
    for col, t in nuevas.items():
        if col not in columnas:
            try:
                c.execute(f"ALTER TABLE intentos ADD COLUMN {col} {t}")
            except Exception:
                pass
    conn.commit()
    conn.close()

init_db()

menu = st.sidebar.radio("Navegación", ["📷 Subir / Planificar Sesión", "🔍 Detalle Diario", "📊 Dashboard Semestral"])

# -------------------------------------------------------------
# OCR CON GEMINI (VÍA REST DIRECTO - COMPATIBLE CON AQ.)
# -------------------------------------------------------------
def procesar_pizarra_con_ia(image_file, api_key):
    image_bytes = image_file.getvalue()
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    mime_type = image_file.type if hasattr(image_file, "type") and image_file.type else "image/jpeg"

    prompt = """
    Analiza esta foto de una pizarra de halterofilia. Extrae los ejercicios planificados.
    Para cada ejercicio identifica:
    - "Tipo": exactamente 'Arranque', 'Envión' o 'Fuerza'.
    - "Complejo / Ejercicios": Nombre del combo (ej. 'Jalón Arranque + Arranque').
    - "Series": Número entero de series (ej. 2).
    - "Reps": Número entero de repeticiones (ej. 1).
    - "% 1RM": Número entero del porcentaje (ej. 80).

    IMPORTANTE: Responde ÚNICAMENTE con una lista JSON válida como esta:
    [
      {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque + Clásico", "Series": 2, "Reps": 1, "% 1RM": 80}
    ]
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_image
                        }
                    }
                ]
            }
        ]
    }

    response = requests.post(url, headers=headers, json=payload, timeout=40)
    if response.status_code != 200:
        raise Exception(f"Error de Google ({response.status_code}): {response.text}")

    result_json = response.json()
    raw_text = result_json["candidates"][0]["content"]["parts"][0]["text"].strip()

    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].split("```")[0].strip()

    data = json.loads(raw_text)

    if isinstance(data, dict):
        for k in data:
            if isinstance(data[k], list):
                data = data[k]
                break
        if isinstance(data, dict):
            data = [data]

    resultado_limpio = []
    for item in data:
        if isinstance(item, dict):
            tipo = item.get("Tipo", item.get("tipo", "Arranque"))
            ejercicio = item.get("Complejo / Ejercicios", item.get("Complejo", item.get("ejercicio", "Ejercicio")))
            series = int(item.get("Series", item.get("series", 1)))
            reps = int(item.get("Reps", item.get("reps", item.get("repeticiones", 1))))
            pct = float(item.get("% 1RM", item.get("pct", item.get("porcentaje", 70))))
            resultado_limpio.append({
                "Tipo": tipo if tipo in ["Arranque", "Envión", "Fuerza"] else "Arranque",
                "Complejo / Ejercicios": str(ejercicio),
                "Series": series,
                "Reps": reps,
                "% 1RM": pct
            })
    return resultado_limpio

# -------------------------------------------------------------
# MÓDULO 1: SUBIDA Y PLANIFICACIÓN
# -------------------------------------------------------------
if menu == "📷 Subir / Planificar Sesión":
    st.title("🏋️‍♂️ Planificación de Sesión (Arranque / Envión)")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        fecha_sel = st.date_input("Fecha", date.today(), key="fecha_entreno")
    with c2:
        enfoque = st.selectbox("Enfoque General", ["Arranque + Envión", "Arranque", "Envión", "Fuerza"], key="enfoque_entreno")
    with c3:
        pr_arranque = st.number_input("PR Arranque (kg)", min_value=1.0, value=70.0, step=2.5, key="pr_arr")
    with c4:
        pr_envion = st.number_input("PR Envión (kg)", min_value=1.0, value=90.0, step=2.5, key="pr_env")

    st.divider()
    st.subheader("1. Cargar desde Foto de Pizarra (Opcional)")
    uploaded_img = st.file_uploader("Subir foto de la pizarra", type=["png", "jpg", "jpeg"], key="pizarra_uploader")

    if uploaded_img and GEMINI_API_KEY:
        if st.button("🤖 Leer Pizarra Automáticamente", key="btn_leer_ia"):
            with st.spinner("Analizando pizarra con IA..."):
                try:
                    datos = procesar_pizarra_con_ia(uploaded_img, GEMINI_API_KEY)
                    st.session_state["pizarra_datos"] = pd.DataFrame(datos)
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

    cfg_pizarra = {
        "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Arranque", "Envión", "Fuerza"], required=True),
        "Series": st.column_config.NumberColumn("Series", min_value=1, max_value=10, default=1),
        "Reps": st.column_config.NumberColumn("Reps", min_value=1, max_value=10, default=1),
        "% 1RM": st.column_config.NumberColumn("% 1RM", min_value=10, max_value=120, default=70, format="%d%%")
    }

    pizarra_editada = st.data_editor(
        st.session_state["pizarra_datos"],
        num_rows="dynamic",
        use_container_width=True,
        column_config=cfg_pizarra,
        key="editor_pizarra"
    )

    if st.button("⚡ Generar Matriz de Movimientos", key="btn_generar_matriz"):
        filas = []
        for _, row in pizarra_editada.iterrows():
            tipo_mov = str(row["Tipo"])
            pr_base = pr_arranque if tipo_mov == "Arranque" else pr_envion
            complejo_str = str(row["Complejo / Ejercicios"])
            movimientos = [m.strip() for m in complejo_str.split("+") if m.strip()]
            series = int(row["Series"]) if pd.notna(row["Series"]) else 1
            reps = int(row["Reps"]) if pd.notna(row["Reps"]) else 1
            pct = float(row["% 1RM"]) if pd.notna(row["% 1RM"]) else 70.0
            peso = round((pr_base * (pct / 100.0)) * 2) / 2
            
            for s in range(1, series + 1):
                for r in range(1, reps + 1):
                    for mov in movimientos:
                        filas.append({
                            "Tipo": tipo_mov,
                            "Bloque": complejo_str,
                            "Serie": f"S{s}",
                            "Rep": f"Rep {r}",
                            "Movimiento": mov,
                            "Carga (kg)": peso,
                            "% 1RM": f"{int(pct)}%",
                            "Válido (✔)": True,
                            "Observación Técnica": ""
                        })
        st.session_state["matriz_activa"] = pd.DataFrame(filas)

    if "matriz_activa" in st.session_state:
        st.divider()
        st.subheader("3. Registro de Ejecución en Vivo")
        
        cfg_matriz = {
            "Válido (✔)": st.column_config.CheckboxColumn("¿Válido?", default=True),
            "Carga (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, step=0.5),
            "Observación Técnica": st.column_config.TextColumn("Observación", width="large")
        }

        matriz_final = st.data_editor(
            st.session_state["matriz_activa"],
            num_rows="dynamic",
            use_container_width=True,
            column_config=cfg_matriz,
            key="editor_matriz_final"
        )

        if st.button("💾 Guardar Entrenamiento Completo", key="btn_guardar_todo"):
            conn = get_db_connection()
            c = conn.cursor()
            for _, r in matriz_final.iterrows():
                valido = bool(r["Válido (✔)"]) if pd.notna(r["Válido (✔)"]) else False
                res = "Completado" if valido else "Falla"
                pr_base = pr_arranque if r["Tipo"] == "Arranque" else pr_envion
                obs = str(r["Observación Técnica"]) if pd.notna(r["Observación Técnica"]) else ""
                
                c.execute("""
                    INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(fecha_sel), str(r["Tipo"]), float(pr_base), str(r["Bloque"]),
                    str(r["Serie"]), str(r["Rep"]), str(r["Movimiento"]),
                    float(str(r["% 1RM"]).replace("%", "")),
                    float(r["Carga (kg)"]), res, obs
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
    df_raw = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_raw.empty:
        st.info("No hay entrenamientos guardados aún.")
    else:
        fechas = sorted(df_raw["fecha"].unique(), reverse=True)
        fecha_sel = st.selectbox("Selecciona la fecha", fechas, key="sel_fecha_detalle")
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
