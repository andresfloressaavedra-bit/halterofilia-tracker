import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from PIL import Image
import json
from datetime import date
from fpdf import FPDF
import io

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

st.set_page_config(page_title="Tracker Halterofilia Pro", page_icon="🏋️‍♂️", layout="wide")

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

menu = st.sidebar.radio("Navegación", [
    "📷 Subir / Planificar Sesión", 
    "🔍 Detalle Diario", 
    "📊 Dashboard Semestral", 
    "📄 Exportar Informe PDF"
])

# -------------------------------------------------------------
# FUNCIÓN GENERADORA DE PDF
# -------------------------------------------------------------
class PDFReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(33, 37, 41)
        self.cell(0, 10, "INFORME DE RENDIMIENTO - HALTEROFILIA", border=False, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(108, 117, 125)
        self.cell(0, 5, f"Generado el: {date.today().strftime('%d/%m/%Y')}", border=False, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", align="C")

def generar_pdf_entrenamiento(df_datos, fecha_filtro=None):
    pdf = PDFReport(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # 1. Resumen Estadístico
    tot_movs = len(df_datos)
    tot_val = len(df_datos[df_datos["resultado"] == "Completado"])
    tot_fal = len(df_datos[df_datos["resultado"] == "Falla"])
    pct_efectividad = (tot_val / tot_movs * 100) if tot_movs > 0 else 0
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(240, 242, 246)
    pdf.cell(0, 8, f" RESUMEN GLOBAL {f'({fecha_filtro})' if fecha_filtro else '(HISTÓRICO COMPLETO)'}", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(45, 7, f"Total Levantamientos: {tot_movs}", border=1)
    pdf.cell(45, 7, f"Válidos: {tot_val}", border=1)
    pdf.cell(45, 7, f"Fallas Técnicas: {tot_fal}", border=1)
    pdf.cell(45, 7, f"Efectividad: {pct_efectividad:.1f}%", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # 2. Tabla Detallada
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, " DETALLE DE LEVANTAMIENTOS Y OBSERVACIONES", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Encabezados de tabla
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(220, 225, 230)
    col_widths = [18, 18, 12, 45, 15, 14, 18, 50]
    headers = ["Fecha", "Tipo", "Serie", "Movimiento", "Peso", "%1RM", "Estado", "Observación"]
    
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1, fill=True, align="C")
    pdf.ln()

    # Filas de datos
    pdf.set_font("Helvetica", "", 7.5)
    for _, row in df_datos.iterrows():
        # Color según resultado
        if row["resultado"] == "Falla":
            pdf.set_text_color(180, 40, 40)
        else:
            pdf.set_text_color(30, 120, 30)

        pdf.cell(col_widths[0], 6, str(row["fecha"])[:10], border=1, align="C")
        pdf.cell(col_widths[1], 6, str(row["tipo_sesion"])[:8], border=1, align="C")
        pdf.cell(col_widths[2], 6, f"{row['serie']}-{row['repeticion'][:3]}", border=1, align="C")
        
        pdf.set_text_color(0, 0, 0)
        pdf.cell(col_widths[3], 6, str(row["movimiento"])[:26], border=1)
        pdf.cell(col_widths[4], 6, f"{row['peso']} kg", border=1, align="C")
        pdf.cell(col_widths[5], 6, f"{int(row['pct_pr'])}%", border=1, align="C")
        
        # Estado
        if row["resultado"] == "Falla":
            pdf.set_text_color(180, 40, 40)
        else:
            pdf.set_text_color(30, 120, 30)
        pdf.cell(col_widths[6], 6, str(row["resultado"]), border=1, align="C")
        
        pdf.set_text_color(50, 50, 50)
        obs = str(row["observacion"]) if str(row["observacion"]) != "nan" else ""
        pdf.cell(col_widths[7], 6, obs[:30], border=1)
        pdf.ln()

    return bytes(pdf.output())

# -------------------------------------------------------------
# MÓDULO OCR CON GEMINI
# -------------------------------------------------------------
def procesar_pizarra_con_ia(image_file, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    img = Image.open(image_file)
    prompt = """Analiza esta pizarra de halterofilia y devuelve solo un JSON con:
    [{"Tipo": "Arranque", "Complejo / Ejercicios": "...", "Series": 1, "Reps": 2, "% 1RM": 70}]"""
    response = model.generate_content([prompt, img])
    raw = response.text.strip()
    if "```json" in raw: raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw: raw = raw.split("```")[1].split("```")[0].strip()
    return json.loads(raw)

# -------------------------------------------------------------
# MÓDULO 1: SUBIR / PLANIFICAR
# -------------------------------------------------------------
if menu == "📷 Subir / Planificar Sesión":
    st.title("🏋️‍♂️ Planificación de Sesión")
    c1, c2, c3, c4 = st.columns(4)
    with c1: fecha_sel = st.date_input("Fecha", date.today())
    with c2: enfoque = st.selectbox("Enfoque", ["Arranque + Envión", "Arranque", "Envión", "Fuerza"])
    with c3: pr_arranque = st.number_input("PR Arranque (kg)", min_value=1.0, value=70.0, step=2.5)
    with c4: pr_envion = st.number_input("PR Envión (kg)", min_value=1.0, value=90.0, step=2.5)

    st.divider()
    st.subheader("1. Cargar desde Foto (Opcional)")
    uploaded_img = st.file_uploader("Subir foto", type=["png", "jpg", "jpeg"])
    if uploaded_img and GEMINI_API_KEY and GEMINI_API_KEY != "TU_API_KEY_AQUI" and HAS_GENAI:
        if st.button("🤖 Leer Pizarra Automáticamente"):
            with st.spinner("Analizando pizarra..."):
                try:
                    st.session_state["pizarra_datos"] = pd.DataFrame(procesar_pizarra_con_ia(uploaded_img, GEMINI_API_KEY))
                    st.success("¡Pizarra leída!")
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()
    st.subheader("2. Esquema de Entrenamiento")
    if "pizarra_datos" not in st.session_state:
        st.session_state["pizarra_datos"] = pd.DataFrame([
            {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 1, "Reps": 2, "% 1RM": 60},
            {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón c/p + Clásico", "Series": 2, "Reps": 1, "% 1RM": 80},
            {"Tipo": "Envión", "Complejo / Ejercicios": "Cargada c/p rodilla + Yerk", "Series": 2, "Reps": 1, "% 1RM": 75}
        ])

    pizarra_editada = st.data_editor(
        st.session_state["pizarra_datos"], num_rows="dynamic", use_container_width=True,
        column_config={
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Arranque", "Envión", "Fuerza"], required=True),
            "Series": st.column_config.NumberColumn(min_value=1, max_value=10, default=1),
            "Reps": st.column_config.NumberColumn(min_value=1, max_value=10, default=1),
            "% 1RM": st.column_config.NumberColumn(min_value=10, max_value=120, default=70, format="%d%%")
        }
    )

    if st.button("⚡ Generar Matriz de Movimientos"):
        filas = []
        for _, row in pizarra_editada.iterrows():
            t = str(row["Tipo"])
            pr = pr_arranque if t == "Arranque" else pr_envion
            movs = [m.strip() for m in str(row["Complejo / Ejercicios"]).split("+") if m.strip()]
            pct = float(row["% 1RM"])
            peso = round((pr * (pct / 100.0)) * 2) / 2
            for s in range(1, int(row["Series"]) + 1):
                for r in range(1, int(row["Reps"]) + 1):
                    for mov in movs:
                        filas.append({
                            "Tipo": t, "Bloque": str(row["Complejo / Ejercicios"]),
                            "Serie": f"S{s}", "Rep": f"Rep {r}", "Movimiento": mov,
                            "Carga (kg)": peso, "% 1RM": f"{int(pct)}%",
                            "Válido (✔)": True, "Observación Técnica": ""
                        })
        st.session_state["matriz_activa"] = pd.DataFrame(filas)

    if "matriz_activa" in st.session_state:
        st.divider()
        st.subheader("3. Registro en Vivo")
        matriz_final = st.data_editor(
            st.session_state["matriz_activa"], num_rows="dynamic", use_container_width=True,
            column_config={
                "Válido (✔)": st.column_config.CheckboxColumn("¿Válido?", default=True),
                "Carga (kg)": st.column_config.NumberColumn("Peso (kg)", step=0.5),
                "Observación Técnica": st.column_config.TextColumn("Observación", width="large")
            }
        )
        if st.button("💾 Guardar Entrenamiento"):
            conn = get_db_connection()
            c = conn.cursor()
            for _, r in matriz_final.iterrows():
                res = "Completado" if r["Válido (✔)"] else "Falla"
                pr_g = pr_arranque if r["Tipo"] == "Arranque" else pr_envion
                c.execute("""
                    INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(fecha_sel), r["Tipo"], pr_g, r["Bloque"],
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
    st.title("📋 Resumen Diario")
    conn = get_db_connection()
    df_raw = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_raw.empty:
        st.info("Sin registros.")
    else:
        fechas = sorted(df_raw["fecha"].unique(), reverse=True)
        fecha_sel = st.selectbox("Fecha", fechas)
        df_dia = df_raw[df_raw["fecha"] == fecha_sel]
        
        tot_val = len(df_dia[df_dia["resultado"] == "Completado"])
        tot_fal = len(df_dia[df_dia["resultado"] == "Falla"])
        pct = (tot_val / len(df_dia) * 100) if len(df_dia) > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Efectividad", f"{pct:.1f}%")
        c2.metric("Válidos", tot_val)
        c3.metric("Fallas", tot_fal)
        c4.metric("Total", len(df_dia))

        st.dataframe(df_dia[["tipo_sesion", "serie", "repeticion", "movimiento", "peso", "pct_pr", "resultado", "observacion"]], use_container_width=True)

# -------------------------------------------------------------
# MÓDULO 3: DASHBOARD SEMESTRAL
# -------------------------------------------------------------
elif menu == "📊 Dashboard Semestral":
    st.title("📈 Progreso Semestral")
    conn = get_db_connection()
    df_all = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_all.empty:
        st.info("Sin datos para graficar.")
    else:
        df_all["fecha"] = pd.to_datetime(df_all["fecha"])
        df_all["is_comp"] = df_all["resultado"] == "Completado"
        df_progreso = df_all.groupby(["fecha", "tipo_sesion"]).agg(Válidos=("is_comp", "sum"), Total=("id", "count")).reset_index()
        df_progreso["% Efectividad"] = (df_progreso["Válidos"] / df_progreso["Total"]) * 100

        fig = px.line(df_progreso, x="fecha", y="% Efectividad", color="tipo_sesion", markers=True, title="Curva Semestral")
        st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------------------
# MÓDULO 4: EXPORTAR PDF
# -------------------------------------------------------------
elif menu == "📄 Exportar Informe PDF":
    st.title("📄 Generador de Informes Técnicos en PDF")
    conn = get_db_connection()
    df_all = pd.read_sql_query("SELECT * FROM intentos ORDER BY fecha DESC", conn)
    conn.close()

    if df_all.empty:
        st.warning("No hay datos registrados aún para generar un informe.")
    else:
        st.write("Configura el alcance de tu informe técnico:")
        tipo_informe = st.radio("Alcance del Informe", ["Sesión Específica (Día)", "Histórico Completo (Semestral)"])

        if tipo_informe == "Sesión Específica (Día)":
            fechas_disp = sorted(df_all["fecha"].unique(), reverse=True)
            dia_elegido = st.selectbox("Selecciona la fecha a exportar", fechas_disp)
            df_export = df_all[df_all["fecha"] == dia_elegido]
            nombre_archivo = f"Informe_Halterofilia_{dia_elegido}.pdf"
            fecha_label = dia_elegido
        else:
            df_export = df_all
            nombre_archivo = f"Informe_Historico_Halterofilia_{date.today()}.pdf"
            fecha_label = None

        st.divider()
        st.subheader("Vista previa de datos a exportar:")
        st.dataframe(df_export[["fecha", "tipo_sesion", "serie", "movimiento", "peso", "resultado", "observacion"]], use_container_width=True)

        pdf_bytes = generar_pdf_entrenamiento(df_export, fecha_label)

        st.download_button(
            label="📥 Descargar Informe en PDF",
            data=pdf_bytes,
            file_name=nombre_archivo,
            mime="application/pdf"
        )
            labels={"fecha": "Fecha", "% Efectividad": "% Éxito", "tipo_sesion": "Levantamiento"}
        )
        fig_line.update_yaxes(range=[0, 105])
        st.plotly_chart(fig_line, use_container_width=True)
