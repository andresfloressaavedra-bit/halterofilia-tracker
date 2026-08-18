import streamlit as st
import pandas as pd
import plotly.express as px
from PIL import Image
import json
from datetime import date
from io import BytesIO
from streamlit_gsheets import GSheetsConnection

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

st.set_page_config(page_title="Tracker Halterofilia Pro", page_icon="🏋️‍♂️", layout="wide")
# Desactivar 'pull-to-refresh' (recarga accidental al deslizar en móviles)
st.markdown("""
    <style>
        html, body, [data-testid="stAppViewContainer"] {
            overscroll-behavior-y: contain !important;
            overscroll-behavior-x: none !important;
        }
        .main {
            overscroll-behavior: contain !important;
        }
    </style>
""", unsafe_allow_html=True)
# API Key de Gemini
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
# -------------------------------------------------------------
# CONEXIÓN CON GOOGLE SHEETS
# -------------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    try:
        df = conn.read(ttl=0)
        df = df.dropna(how="all")
        return df
    except Exception:
        return pd.DataFrame(columns=[
            "fecha", "tipo_sesion", "pr_base", "bloque_combo", "serie", 
            "repeticion", "movimiento", "pct_pr", "peso", "resultado", "observacion"
        ])

def guardar_datos(df_nuevos):
    df_existente = cargar_datos()
    df_final = pd.concat([df_existente, df_nuevos], ignore_index=True)
    conn.update(data=df_final)

menu = st.sidebar.radio("Navegación", ["📷 Subir / Planificar Sesión", "🔍 Detalle Diario", "📊 Dashboard Semestral", "📥 Exportar / Respaldo"])

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
    2. "Complejo / Ejercicios": Nombre del combo (separando movimientos con '+').
    3. "Series": Número de series.
    4. "Reps": Número de repeticiones.
    5. "% 1RM": El porcentaje de 1RM como entero.

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
            filas_para_db = []
            for _, r in matriz_final.iterrows():
                res = "Completado" if r["Válido (✔)"] else "Falla"
                pr_guardado = pr_arranque if r["Tipo"] == "Arranque" else pr_envion
                filas_para_db.append({
                    "fecha": str(fecha_sel),
                    "tipo_sesion": r["Tipo"],
                    "pr_base": pr_guardado,
                    "bloque_combo": r["Bloque"],
                    "serie": r["Serie"],
                    "repeticion": r["Rep"],
                    "movimiento": r["Movimiento"],
                    "pct_pr": float(str(r["% 1RM"]).replace("%", "")),
                    "peso": float(r["Carga (kg)"]),
                    "resultado": res,
                    "observacion": str(r["Observación Técnica"])
                })
            df_guardar = pd.DataFrame(filas_para_db)
            guardar_datos(df_guardar)
            st.success("¡Sesión guardada permanentemente en tu Google Drive!")
            del st.session_state["matriz_activa"]

# -------------------------------------------------------------
# MÓDULO 2: DETALLE DIARIO
# -------------------------------------------------------------
elif menu == "🔍 Detalle Diario":
    st.title("📋 Resumen Diario por Movimiento")
    df_raw = cargar_datos()

    if df_raw.empty:
        st.info("No hay entrenamientos registrados aún.")
    else:
        fechas = sorted(df_raw["fecha"].astype(str).unique(), reverse=True)
        fecha_sel = st.selectbox("Selecciona la fecha", fechas)
        df_dia = df_raw[df_raw["fecha"].astype(str) == fecha_sel]

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
    df_all = cargar_datos()

    if df_all.empty or len(df_all) < 2:
        st.info("Registra más entrenamientos para ver gráficos estadísticos.")
    else:
        df_all["fecha"] = pd.to_datetime(df_all["fecha"])
        df_all["is_comp"] = df_all["resultado"] == "Completado"
        df_all["is_falla"] = df_all["resultado"] == "Falla"

        df_progreso = df_all.groupby(["fecha", "tipo_sesion"]).agg(
            Válidos=("is_comp", "sum"),
            Total=("tipo_sesion", "count")
        ).reset_index()
        df_progreso["% Efectividad"] = (df_progreso["Válidos"] / df_progreso["Total"]) * 100

        fig_line = px.line(
            df_progreso, x="fecha", y="% Efectividad", color="tipo_sesion", markers=True,
            title="Curva de Efectividad Técnica Semestral: Arranque vs Envión",
            labels={"fecha": "Fecha", "% Efectividad": "% Éxito", "tipo_sesion": "Levantamiento"}
        )
        fig_line.update_yaxes(range=[0, 105])
        st.plotly_chart(fig_line, use_container_width=True)

# -------------------------------------------------------------
# MÓDULO 4: EXPORTAR / RESPALDO EXCEL
# -------------------------------------------------------------
elif menu == "📥 Exportar / Respaldo":
    st.title("📥 Descargar Historial Completo")
    df_respaldo = cargar_datos()

    if df_respaldo.empty:
        st.info("No hay datos para exportar.")
    else:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_respaldo.to_excel(writer, index=False, sheet_name='Entrenamientos')
        excel_data = output.getvalue()

        st.download_button(
            label="📊 Descargar Base de Datos Completa en Excel (.xlsx)",
            data=excel_data,
            file_name=f"halterofilia_respaldo_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
