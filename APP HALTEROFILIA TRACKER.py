import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import json
import io
from datetime import date
from fpdf import FPDF

st.set_page_config(
    page_title="Tracker Halterofilia Pro", 
    page_icon="🏋️‍♂️", 
    layout="wide"
)

# -------------------------------------------------------------
# ESTILOS ANTI-SALTO Y DISEÑO MÓVIL
# -------------------------------------------------------------
st.markdown("""
    <style>
        html, body, [data-testid="stAppViewContainer"], .main {
            overscroll-behavior: none !important;
            overscroll-behavior-y: none !important;
        }
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 3rem !important;
        }
        .stButton button, .stDownloadButton button {
            width: 100%;
            height: 3rem;
            font-size: 1.05rem !important;
            font-weight: bold;
            border-radius: 8px;
        }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# BASE DE DATOS Y PERSISTENCIA
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
            observacion TEXT,
            bloque_combo TEXT,
            repeticion TEXT,
            movimiento TEXT,
            pct_pr REAL,
            jornada TEXT DEFAULT 'Sesión 1'
        )
    """)
    c.execute("PRAGMA table_info(intentos)")
    cols = [col[1] for col in c.fetchall()]
    if "jornada" not in cols:
        try:
            c.execute("ALTER TABLE intentos ADD COLUMN jornada TEXT DEFAULT 'Sesión 1'")
        except Exception:
            pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS estado_borrador (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def guardar_estado_disco(clave, valor_obj):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO estado_borrador (clave, valor) VALUES (?, ?)", (clave, json.dumps(valor_obj)))
    conn.commit()
    conn.close()

def cargar_estado_disco(clave, valor_defecto):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT valor FROM estado_borrador WHERE clave = ?", (clave,))
    fila = c.fetchone()
    conn.close()
    if fila and fila["valor"]:
        try:
            return json.loads(fila["valor"])
        except Exception:
            return valor_defecto
    return valor_defecto

# -------------------------------------------------------------
# FUNCIONES DE EXPORTACIÓN ROBUSTAS (EXCEL Y PDF)
# -------------------------------------------------------------
def generar_excel(df, titulo_hoja="Entrenamiento"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=titulo_hoja[:30], index=False)
    return output.getvalue()

def generar_pdf(df, titulo="Reporte de Entrenamiento", subtitulo=""):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, titulo, ln=True, align="C")
    if subtitulo:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, subtitulo, ln=True, align="C")
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 8)
    columnas = ["Tipo", "Serie", "Rep", "Movimiento", "Kg", "%", "Estado", "Observación"]
    anchos = [20, 14, 14, 45, 14, 14, 20, 48]
    
    for col, ancho in zip(columnas, anchos):
        pdf.cell(ancho, 7, col, border=1, align="C")
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    if isinstance(df, pd.DataFrame) and not df.empty:
        for _, fila in df.iterrows():
            tipo = str(fila.get("Tipo", fila.get("tipo_sesion", "")))[:10]
            serie = str(fila.get("Serie", fila.get("serie", "")))[:6]
            rep = str(fila.get("Rep", fila.get("repeticion", "")))[:6]
            mov = str(fila.get("Movimiento", fila.get("movimiento", "")))[:24]
            kg = str(fila.get("Carga (kg)", fila.get("peso", "")))[:6]
            pct = str(fila.get("% 1RM", fila.get("pct_pr", "")))[:6]
            res = "Válido" if str(fila.get("Válido (✔)", fila.get("resultado", ""))) in ["True", "Completado"] else "Falla"
            obs = str(fila.get("Observación Técnica", fila.get("observacion", "")))[:26]

            pdf.cell(anchos[0], 6, tipo, border=1, align="C")
            pdf.cell(anchos[1], 6, serie, border=1, align="C")
            pdf.cell(anchos[2], 6, rep, border=1, align="C")
            pdf.cell(anchos[3], 6, mov, border=1)
            pdf.cell(anchos[4], 6, kg, border=1, align="C")
            pdf.cell(anchos[5], 6, pct, border=1, align="C")
            pdf.cell(anchos[6], 6, res, border=1, align="C")
            pdf.cell(anchos[7], 6, obs, border=1)
            pdf.ln()

    # Conversión explícita a bytes para Streamlit
    out = pdf.output()
    if isinstance(out, str):
        return out.encode("latin1")
    return bytes(out)

# -------------------------------------------------------------
# MEMORIA Y ESTADOS DE SESIÓN
# -------------------------------------------------------------
if "lista_bloques" not in st.session_state:
    bloques_defecto = [
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 1, "Reps": 2, "% 1RM": 50},
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 1, "Reps": 2, "% 1RM": 60},
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 2, "Reps": 2, "% 1RM": 70},
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 4, "Reps": 1, "% 1RM": 80},
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón c/p + Clásico", "Series": 2, "Reps": 1, "% 1RM": 85},
    ]
    st.session_state["lista_bloques"] = cargar_estado_disco("lista_bloques", bloques_defecto)

if "matriz_activa" not in st.session_state:
    matriz_guardada = cargar_estado_disco("matriz_activa", [])
    st.session_state["matriz_activa"] = pd.DataFrame(matriz_guardada)

if "menu_nav" not in st.session_state:
    st.session_state["menu_nav"] = "⚙️ 1. Esquema y PRs"

# -------------------------------------------------------------
# BARRA LATERAL
# -------------------------------------------------------------
st.sidebar.title("🏋️‍♂️ Navegación")
opciones_menu = [
    "⚙️ 1. Esquema y PRs", 
    "🏋️‍♂️ 2. Registro en Vivo", 
    "🔍 Detalle Diario", 
    "📊 Dashboard Semestral"
]

menu = st.sidebar.radio(
    "Ir a:", 
    opciones_menu, 
    index=opciones_menu.index(st.session_state["menu_nav"]),
    key="menu_radio"
)
st.session_state["menu_nav"] = menu

# -------------------------------------------------------------
# MÓDULO 1: CONFIGURACIÓN Y ESQUEMA
# -------------------------------------------------------------
if menu == "⚙️ 1. Esquema y PRs":
    st.title("⚙️ Configuración del Entrenamiento")
    
    val_pr_arr = float(cargar_estado_disco("pr_arr", 70.0))
    val_pr_env = float(cargar_estado_disco("pr_env", 90.0))
    
    c1, c2, c3 = st.columns([1.2, 1.2, 1.2])
    with c1:
        st.session_state["cfg_fecha"] = st.date_input("Fecha de Sesión", date.today())
        pr_arr_in = st.number_input("PR Arranque (kg)", min_value=1.0, value=val_pr_arr, step=1.0)
        if pr_arr_in != val_pr_arr:
            guardar_estado_disco("pr_arr", pr_arr_in)
        st.session_state["cfg_pr_arr"] = pr_arr_in

    with c2:
        st.session_state["cfg_jornada"] = st.selectbox("Sesión / Turno", ["Sesión 1 (Mañana)", "Sesión 2 (Tarde)", "Sesión 3 (Extra)"], index=0)
        pr_env_in = st.number_input("PR Envión (kg)", min_value=1.0, value=val_pr_env, step=1.0)
        if pr_env_in != val_pr_env:
            guardar_estado_disco("pr_env", pr_env_in)
        st.session_state["cfg_pr_env"] = pr_env_in

    with c3:
        st.session_state["cfg_enfoque"] = st.selectbox("Enfoque General", ["Arranque + Envión", "Arranque", "Envión", "Fuerza"], index=0)

    st.divider()
    st.subheader("➕ Agregar Ejercicio o Bloque")
    
    with st.form("form_nuevo_bloque", clear_on_submit=True):
        f_tipo = st.selectbox("Tipo de Movimiento", ["Arranque", "Envión", "Fuerza"])
        f_ejercicio = st.text_input("Complejo o Ejercicios (separa combos con '+')", placeholder="Ej: Jalón c/p + Clásico")
        
        c_s, c_r, c_p = st.columns(3)
        with c_s:
            f_series = st.number_input("Series", min_value=1, max_value=20, value=2, step=1)
        with c_r:
            f_reps = st.number_input("Reps", min_value=1, max_value=20, value=1, step=1)
        with c_p:
            f_pct = st.number_input("% 1RM", min_value=10, max_value=150, value=75, step=5)
            
        btn_agregar = st.form_submit_button("➕ Agregar al Esquema")
        if btn_agregar:
            if f_ejercicio.strip():
                st.session_state["lista_bloques"].append({
                    "Tipo": f_tipo,
                    "Complejo / Ejercicios": f_ejercicio.strip(),
                    "Series": int(f_series),
                    "Reps": int(f_reps),
                    "% 1RM": float(f_pct)
                })
                guardar_estado_disco("lista_bloques", st.session_state["lista_bloques"])
                st.success(f"¡Agregado: {f_ejercicio}!")
                st.rerun()
            else:
                st.warning("Escribe el nombre del ejercicio antes de agregar.")

    st.divider()
    st.subheader("📋 Bloques Planificados para Esta Sesión")
    
    if len(st.session_state["lista_bloques"]) == 0:
        st.info("No hay bloques agregados todavía. Usa el formulario de arriba.")
    else:
        df_bloques = pd.DataFrame(st.session_state["lista_bloques"])
        
        cfg_bloques = {
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Arranque", "Envión", "Fuerza"], required=True),
            "Complejo / Ejercicios": st.column_config.TextColumn("Complejo / Ejercicios", width="large", required=True),
            "Series": st.column_config.NumberColumn("Series", min_value=1, max_value=20, default=1),
            "Reps": st.column_config.NumberColumn("Reps", min_value=1, max_value=20, default=1),
            "% 1RM": st.column_config.NumberColumn("% 1RM", min_value=10, max_value=150, default=70, format="%d%%")
        }

        bloques_editados = st.data_editor(
            df_bloques,
            num_rows="dynamic",
            use_container_width=True,
            column_config=cfg_bloques,
            key="editor_bloques_esquema"
        )
        
        st.session_state["lista_bloques"] = bloques_editados.to_dict(orient="records")
        guardar_estado_disco("lista_bloques", st.session_state["lista_bloques"])

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("🗑️ Borrar Último Bloque"):
                if st.session_state["lista_bloques"]:
                    st.session_state["lista_bloques"].pop()
                    guardar_estado_disco("lista_bloques", st.session_state["lista_bloques"])
                    st.rerun()
        with col_b2:
            if st.button("🧹 Limpiar Todo el Esquema"):
                st.session_state["lista_bloques"] = []
                guardar_estado_disco("lista_bloques", [])
                st.rerun()

        st.write("")
        if st.button("⚡ Generar Matriz y Pasar al Entrenamiento", type="primary"):
            filas = []
            pr_arr = float(st.session_state["cfg_pr_arr"])
            pr_env = float(st.session_state["cfg_pr_env"])
            
            for row in st.session_state["lista_bloques"]:
                tipo_mov = row["Tipo"]
                pr_base = pr_arr if tipo_mov == "Arranque" else pr_env
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
                                "Carga (kg)": float(peso),
                                "% 1RM": f"{int(pct)}%",
                                "Válido (✔)": True,
                                "Observación Técnica": ""
                            })
            st.session_state["matriz_activa"] = pd.DataFrame(filas)
            guardar_estado_disco("matriz_activa", filas)
            st.session_state["menu_nav"] = "🏋️‍♂️ 2. Registro en Vivo"
            st.rerun()

# -------------------------------------------------------------
# MÓDULO 2: REGISTRO EN VIVO CON ADICIÓN EN CALIENTE
# -------------------------------------------------------------
elif menu == "🏋️‍♂️ 2. Registro en Vivo":
    st.title("🏋️‍♂️ Registro de Levantamientos en Vivo")
    
    with st.expander("➕ ¿Añadieron más ejercicios a la clase? Agrégalos aquí"):
        c_ex1, c_ex2, c_ex3 = st.columns([1.5, 1, 1])
        with c_ex1:
            ex_tipo = st.selectbox("Tipo de Ejercicio Extra", ["Arranque", "Envión", "Fuerza"], key="ex_tipo_k")
            ex_nombre = st.text_input("Nombre del Ejercicio Extra", placeholder="Ej: Sentadilla Trasera", key="ex_nombre_k")
        with c_ex2:
            ex_series = st.number_input("Series Extra", min_value=1, max_value=10, value=1, step=1, key="ex_s_k")
            ex_reps = st.number_input("Reps Extra", min_value=1, max_value=10, value=1, step=1, key="ex_r_k")
        with c_ex3:
            ex_peso = st.number_input("Peso (kg)", min_value=0.0, max_value=300.0, value=60.0, step=1.0, key="ex_p_k")
            ex_pct = st.number_input("% 1RM (opcional)", min_value=0, max_value=150, value=75, step=5, key="ex_pct_k")

        if st.button("➕ Insertar a la Matriz Actual", type="secondary"):
            if ex_nombre.strip():
                movimientos_extra = [m.strip() for m in ex_nombre.split("+") if m.strip()]
                nuevas_filas = []
                for s in range(1, int(ex_series) + 1):
                    for r in range(1, int(ex_reps) + 1):
                        for mov in movimientos_extra:
                            nuevas_filas.append({
                                "Tipo": ex_tipo,
                                "Bloque": ex_nombre.strip(),
                                "Serie": f"S{s}",
                                "Rep": f"Rep {r}",
                                "Movimiento": mov,
                                "Carga (kg)": float(ex_peso),
                                "% 1RM": f"{int(ex_pct)}%",
                                "Válido (✔)": True,
                                "Observación Técnica": ""
                            })
                df_nuevas = pd.DataFrame(nuevas_filas)
                st.session_state["matriz_activa"] = pd.concat([st.session_state["matriz_activa"], df_nuevas], ignore_index=True)
                guardar_estado_disco("matriz_activa", st.session_state["matriz_activa"].to_dict(orient="records"))
                st.success(f"¡Se agregaron {len(nuevas_filas)} intentos extra al final de tu tabla!")
                st.rerun()
            else:
                st.warning("Escribe el nombre del ejercicio extra.")

    if st.session_state["matriz_activa"].empty:
        st.info("👈 Primero ve a **'1. Esquema y PRs'** en la barra lateral y presiona **'Generar Matriz'**, o añade ejercicios arriba.")
    else:
        cfg_matriz = {
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Arranque", "Envión", "Fuerza"], required=True),
            "Bloque": st.column_config.TextColumn("Bloque", width="medium"),
            "Serie": st.column_config.TextColumn("Serie", width="small"),
            "Rep": st.column_config.TextColumn("Rep", width="small"),
            "Movimiento": st.column_config.TextColumn("Movimiento", width="medium"),
            "Válido (✔)": st.column_config.CheckboxColumn("¿Válido?", default=True),
            "Carga (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, step=0.5),
            "% 1RM": st.column_config.TextColumn("% 1RM", width="small"),
            "Observación Técnica": st.column_config.TextColumn("Observación Técnica", width="large")
        }

        matriz_final = st.data_editor(
            st.session_state["matriz_activa"],
            num_rows="dynamic",
            use_container_width=True,
            column_config=cfg_matriz,
            key="editor_matriz_final"
        )
        
        st.session_state["matriz_activa"] = matriz_final
        guardar_estado_disco("matriz_activa", matriz_final.to_dict(orient="records"))

        st.write("---")
        st.write("**Exportar Planilla de Entrenamiento:**")
        col_exp1, col_exp2 = st.columns(2)
        
        fecha_act = str(st.session_state.get("cfg_fecha", date.today()))
        jornada_act = str(st.session_state.get("cfg_jornada", "Sesión 1"))

        with col_exp1:
            excel_bytes = generar_excel(matriz_final, f"Entrenamiento_{fecha_act}")
            st.download_button(
                label="📥 Descargar Planilla Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"Entrenamiento_{fecha_act}_{jornada_act}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_excel_vivo"
            )

        with col_exp2:
            pdf_bytes = generar_pdf(matriz_final, f"Planilla: {fecha_act}", f"Jornada: {jornada_act}")
            st.download_button(
                label="📄 Descargar Planilla PDF (.pdf)",
                data=pdf_bytes,
                file_name=f"Entrenamiento_{fecha_act}_{jornada_act}.pdf",
                mime="application/pdf",
                key="btn_dl_pdf_vivo"
            )

        st.write("")
        if st.button("💾 Guardar Entrenamiento Completo", type="primary"):
            conn = get_db_connection()
            c = conn.cursor()
            pr_arr_g = float(cargar_estado_disco("pr_arr", 70.0))
            pr_env_g = float(cargar_estado_disco("pr_env", 90.0))

            for _, r in matriz_final.iterrows():
                valido = bool(r["Válido (✔)"]) if pd.notna(r["Válido (✔)"]) else False
                res = "Completado" if valido else "Falla"
                tipo_actual = str(r["Tipo"]) if pd.notna(r["Tipo"]) else "Arranque"
                pr_base = pr_arr_g if tipo_actual == "Arranque" else pr_env_g
                obs = str(r["Observación Técnica"]) if pd.notna(r["Observación Técnica"]) else ""
                
                c.execute("""
                    INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion, jornada)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fecha_act, tipo_actual, float(pr_base), str(r.get("Bloque", "")),
                    str(r.get("Serie", "S1")), str(r.get("Rep", "Rep 1")), str(r.get("Movimiento", "")),
                    float(str(r.get("% 1RM", "70")).replace("%", "") if str(r.get("% 1RM", "70")).replace("%", "").isdigit() else 70.0),
                    float(r.get("Carga (kg)", 0.0)), res, obs, jornada_act
                ))
            conn.commit()
            conn.close()
            
            st.session_state["matriz_activa"] = pd.DataFrame()
            guardar_estado_disco("matriz_activa", [])
            st.success(f"✅ ¡Entrenamiento guardado ({jornada_act}) con éxito!")
            st.session_state["menu_nav"] = "🔍 Detalle Diario"
            st.rerun()

# -------------------------------------------------------------
# MÓDULO 3: DETALLE, EDICIÓN DE FECHAS Y DESCARGA HISTÓRICA
# -------------------------------------------------------------
elif menu == "🔍 Detalle Diario":
    st.title("📋 Detalle y Edición de Entrenamientos")
    conn = get_db_connection()
    df_raw = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_raw.empty:
        st.info("Aún no tienes entrenamientos registrados.")
    else:
        df_raw["jornada"] = df_raw["jornada"].fillna("Sesión 1")
        df_raw["sesion_id"] = df_raw["fecha"] + " | " + df_raw["jornada"]
        
        sesiones_disp = sorted(df_raw["sesion_id"].unique(), reverse=True)
        sesion_sel = st.selectbox("Selecciona la sesión a consultar o editar:", sesiones_disp)
        
        df_sesion = df_raw[df_raw["sesion_id"] == sesion_sel].copy()
        fecha_actual_sesion = df_sesion["fecha"].iloc[0]
        jornada_actual_sesion = df_sesion["jornada"].iloc[0]

        tot_movs = len(df_sesion)
        tot_val = len(df_sesion[df_sesion["resultado"] == "Completado"])
        tot_fal = len(df_sesion[df_sesion["resultado"] == "Falla"])
        pct_efectividad = (tot_val / tot_movs * 100) if tot_movs > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Efectividad", f"{pct_efectividad:.1f}%")
        c2.metric("Válidos", tot_val)
        c3.metric("Fallas", tot_fal)

        st.write("---")
        with st.expander("📅 Modificar la Fecha de este Entrenamiento"):
            c_f1, c_f2 = st.columns([2, 1])
            with c_f1:
                nueva_fecha = st.date_input("Nueva fecha para esta sesión:", pd.to_datetime(fecha_actual_sesion).date())
            with c_f2:
                st.write("")
                if st.button("🔄 Actualizar Fecha"):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("""
                        UPDATE intentos 
                        SET fecha = ? 
                        WHERE fecha = ? AND jornada = ?
                    """, (str(nueva_fecha), fecha_actual_sesion, jornada_actual_sesion))
                    conn.commit()
                    conn.close()
                    st.success(f"Fecha cambiada a {nueva_fecha}")
                    st.rerun()

        st.subheader("✏️ Editar Intentos de esta Sesión")
        df_sesion["Válido (✔)"] = df_sesion["resultado"] == "Completado"
        columnas_visibles = ["id", "tipo_sesion", "serie", "repeticion", "movimiento", "pct_pr", "peso", "Válido (✔)", "observacion"]
        
        cfg_edicion = {
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "tipo_sesion": st.column_config.TextColumn("Tipo", disabled=True),
            "serie": st.column_config.TextColumn("Serie", disabled=True),
            "repeticion": st.column_config.TextColumn("Rep", disabled=True),
            "movimiento": st.column_config.TextColumn("Movimiento", disabled=True),
            "pct_pr": st.column_config.NumberColumn("% 1RM", format="%d%%", disabled=True),
            "peso": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, step=0.5),
            "Válido (✔)": st.column_config.CheckboxColumn("¿Válido?"),
            "observacion": st.column_config.TextColumn("Observación Técnica", width="large")
        }

        df_editado = st.data_editor(
            df_sesion[columnas_visibles],
            num_rows="dynamic",
            use_container_width=True,
            column_config=cfg_edicion,
            key=f"editor_historial_{sesion_sel}"
        )

        col_btn_edit, col_btn_del = st.columns(2)
        with col_btn_edit:
            if st.button("💾 Guardar Modificaciones", type="primary"):
                conn = get_db_connection()
                c = conn.cursor()
                for _, r in df_editado.iterrows():
                    res = "Completado" if bool(r["Válido (✔)"]) else "Falla"
                    obs = str(r["observacion"]) if pd.notna(r["observacion"]) else ""
                    c.execute("""
                        UPDATE intentos 
                        SET peso = ?, resultado = ?, observacion = ?
                        WHERE id = ?
                    """, (float(r["peso"]), res, obs, int(r["id"])))
                conn.commit()
                conn.close()
                st.success("✅ ¡Sesión actualizada correctamente!")
                st.rerun()

        with col_btn_del:
            if st.button("🗑️ Eliminar Esta Sesión Completa"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("DELETE FROM intentos WHERE fecha = ? AND jornada = ?", (fecha_actual_sesion, jornada_actual_sesion))
                conn.commit()
                conn.close()
                st.warning(f"Sesión del día {fecha_actual_sesion} ({jornada_actual_sesion}) eliminada.")
                st.rerun()

        st.write("---")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            excel_hist = generar_excel(df_sesion[columnas_visibles], f"{fecha_actual_sesion}")
            st.download_button(
                label="📥 Descargar Sesión en Excel (.xlsx)",
                data=excel_hist,
                file_name=f"Historial_{fecha_actual_sesion}_{jornada_actual_sesion}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_excel_hist"
            )
        with col_d2:
            pdf_hist = generar_pdf(df_sesion[columnas_visibles], f"Historial: {fecha_actual_sesion}", f"Jornada: {jornada_actual_sesion}")
            st.download_button(
                label="📄 Descargar Sesión en PDF (.pdf)",
                data=pdf_hist,
                file_name=f"Historial_{fecha_actual_sesion}_{jornada_actual_sesion}.pdf",
                mime="application/pdf",
                key="btn_dl_pdf_hist"
            )

# -------------------------------------------------------------
# MÓDULO 4: DASHBOARD SEMESTRAL
# -------------------------------------------------------------
elif menu == "📊 Dashboard Semestral":
    st.title("📈 Progreso Semestral")
    conn = get_db_connection()
    df_all = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_all.empty:
        st.info("Registra más sesiones para ver las estadísticas acumuladas.")
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
            title="Curva de Efectividad Técnica: Arranque vs Envión",
            labels={"fecha": "Fecha", "% Efectividad": "% Éxito", "tipo_sesion": "Levantamiento"}
        )
        fig_line.update_yaxes(range=[0, 105])
        st.plotly_chart(fig_line, use_container_width=True)
