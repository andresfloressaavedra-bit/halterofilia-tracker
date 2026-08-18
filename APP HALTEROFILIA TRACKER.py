import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from datetime import date

st.set_page_config(
    page_title="Tracker Halterofilia Pro", 
    page_icon="🏋️‍♂️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# -------------------------------------------------------------
# CSS ANTI-RECARGA Y ESTILO COMPACTO MÓVIL
# -------------------------------------------------------------
st.markdown("""
    <style>
        html, body, [data-testid="stAppViewContainer"], .main {
            overscroll-behavior: none !important;
            overscroll-behavior-y: none !important;
        }
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 100% !important;
        }
        /* Botones grandes y cómodos para tocar en el celular */
        .stButton button {
            width: 100%;
            height: 3rem;
            font-size: 1.1rem !important;
            font-weight: bold;
            border-radius: 8px;
        }
    </style>
""", unsafe_allow_html=True)

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
            observacion TEXT,
            bloque_combo TEXT,
            repeticion TEXT,
            movimiento TEXT,
            pct_pr REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Inicialización de Estados de Sesión (Persistencia Total)
if "pizarra_datos" not in st.session_state:
    st.session_state["pizarra_datos"] = pd.DataFrame([
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 1, "Reps": 2, "% 1RM": 50},
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 1, "Reps": 2, "% 1RM": 60},
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 2, "Reps": 2, "% 1RM": 70},
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón Arranque c/p rodilla + Arranque c/p rodilla + Clásico", "Series": 4, "Reps": 1, "% 1RM": 80},
        {"Tipo": "Arranque", "Complejo / Ejercicios": "Jalón c/p + Clásico", "Series": 2, "Reps": 1, "% 1RM": 85},
    ])

if "matriz_activa" not in st.session_state:
    st.session_state["matriz_activa"] = pd.DataFrame()

# -------------------------------------------------------------
# NAVEGACIÓN POR PESTAÑAS SUPERIORES
# -------------------------------------------------------------
tab_esquema, tab_registro, tab_historial, tab_dashboard = st.tabs([
    "⚙️ 1. Esquema y PRs", 
    "🏋️‍♂️ 2. Registro en Vivo", 
    "🔍 3. Detalle Diario", 
    "📊 4. Dashboard"
])

# -------------------------------------------------------------
# PESTAÑA 1: ESQUEMA Y PRs
# -------------------------------------------------------------
with tab_esquema:
    st.subheader("Configuración de la Sesión")
    c1, c2 = st.columns(2)
    with c1:
        fecha_sel = st.date_input("Fecha", date.today(), key="cfg_fecha")
        pr_arranque = st.number_input("PR Arranque (kg)", min_value=1.0, value=70.0, step=2.5, key="cfg_pr_arr")
    with c2:
        enfoque = st.selectbox("Enfoque General", ["Arranque + Envión", "Arranque", "Envión", "Fuerza"], key="cfg_enfoque")
        pr_envion = st.number_input("PR Envión (kg)", min_value=1.0, value=90.0, step=2.5, key="cfg_pr_env")

    st.write("---")
    st.write("**Bloques planificados:**")

    cfg_pizarra = {
        "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Arranque", "Envión", "Fuerza"], required=True),
        "Complejo / Ejercicios": st.column_config.TextColumn("Complejo / Ejercicios", width="large", required=True),
        "Series": st.column_config.NumberColumn("Series", min_value=1, max_value=20, default=1),
        "Reps": st.column_config.NumberColumn("Reps", min_value=1, max_value=20, default=1),
        "% 1RM": st.column_config.NumberColumn("% 1RM", min_value=10, max_value=150, default=70, format="%d%%")
    }

    pizarra_editada = st.data_editor(
        st.session_state["pizarra_datos"],
        num_rows="dynamic",
        use_container_width=True,
        column_config=cfg_pizarra,
        key="editor_esquema_tab"
    )
    st.session_state["pizarra_datos"] = pizarra_editada

    if st.button("⚡ Generar Matriz y Pasar al Entrenamiento", type="primary", key="btn_crear_matriz"):
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
                            "Carga (kg)": float(peso),
                            "% 1RM": f"{int(pct)}%",
                            "Válido (✔)": True,
                            "Observación Técnica": ""
                        })
        st.session_state["matriz_activa"] = pd.DataFrame(filas)
        st.success("¡Matriz creada! Ve a la pestaña **'🏋️‍♂️ 2. Registro en Vivo'**.")

# -------------------------------------------------------------
# PESTAÑA 2: REGISTRO EN VIVO
# -------------------------------------------------------------
with tab_registro:
    st.subheader("Control de Levantamientos")
    
    if st.session_state["matriz_activa"].empty:
        st.info("👈 Primero configura tu esquema en la pestaña **'1. Esquema y PRs'** y presiona **'Generar Matriz'**.")
    else:
        cfg_matriz = {
            "Tipo": st.column_config.TextColumn("Tipo", disabled=True),
            "Bloque": st.column_config.TextColumn("Bloque", disabled=True),
            "Serie": st.column_config.TextColumn("Serie", disabled=True),
            "Rep": st.column_config.TextColumn("Rep", disabled=True),
            "Movimiento": st.column_config.TextColumn("Movimiento", disabled=True),
            "Válido (✔)": st.column_config.CheckboxColumn("¿Válido?", default=True),
            "Carga (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, step=0.5),
            "% 1RM": st.column_config.TextColumn("% 1RM", disabled=True),
            "Observación Técnica": st.column_config.TextColumn("Observación", width="medium")
        }

        matriz_final = st.data_editor(
            st.session_state["matriz_activa"],
            num_rows="fixed",
            use_container_width=True,
            column_config=cfg_matriz,
            key="editor_matriz_tab"
        )
        st.session_state["matriz_activa"] = matriz_final

        st.write("")
        if st.button("💾 Guardar Entrenamiento Completo", type="primary", key="btn_guardar_bd"):
            conn = get_db_connection()
            c = conn.cursor()
            fecha_guardar = str(st.session_state.get("cfg_fecha", date.today()))
            pr_arr_g = float(st.session_state.get("cfg_pr_arr", 70.0))
            pr_env_g = float(st.session_state.get("cfg_pr_env", 90.0))

            for _, r in matriz_final.iterrows():
                valido = bool(r["Válido (✔)"]) if pd.notna(r["Válido (✔)"]) else False
                res = "Completado" if valido else "Falla"
                pr_base = pr_arr_g if r["Tipo"] == "Arranque" else pr_env_g
                obs = str(r["Observación Técnica"]) if pd.notna(r["Observación Técnica"]) else ""
                
                c.execute("""
                    INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fecha_guardar, str(r["Tipo"]), float(pr_base), str(r["Bloque"]),
                    str(r["Serie"]), str(r["Rep"]), str(r["Movimiento"]),
                    float(str(r["% 1RM"]).replace("%", "")),
                    float(r["Carga (kg)"]), res, obs
                ))
            conn.commit()
            conn.close()
            st.success("✅ ¡Sesión guardada con éxito en tu historial!")
            st.session_state["matriz_activa"] = pd.DataFrame()
            st.rerun()

# -------------------------------------------------------------
# PESTAÑA 3: DETALLE DIARIO
# -------------------------------------------------------------
with tab_historial:
    st.subheader("Resumen de Sesiones Pasadas")
    conn = get_db_connection()
    df_raw = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_raw.empty:
        st.info("Aún no tienes entrenamientos guardados.")
    else:
        fechas = sorted(df_raw["fecha"].dropna().unique(), reverse=True)
        fecha_sel = st.selectbox("Selecciona la fecha", fechas, key="sel_fecha_historial")
        df_dia = df_raw[df_raw["fecha"] == fecha_sel]

        tot_movs = len(df_dia)
        tot_val = len(df_dia[df_dia["resultado"] == "Completado"])
        tot_fal = len(df_dia[df_dia["resultado"] == "Falla"])
        pct_efectividad = (tot_val / tot_movs * 100) if tot_movs > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Efectividad", f"{pct_efectividad:.1f}%")
        c2.metric("Válidos", tot_val)
        c3.metric("Fallas", tot_fal)

        st.dataframe(
            df_dia[["tipo_sesion", "serie", "repeticion", "movimiento", "peso", "pct_pr", "resultado", "observacion"]].rename(columns={
                "tipo_sesion": "Tipo", "serie": "Serie", "repeticion": "Rep", "movimiento": "Movimiento",
                "peso": "Kg", "pct_pr": "%", "resultado": "Estado", "observacion": "Observación"
            }),
            use_container_width=True
        )

# -------------------------------------------------------------
# PESTAÑA 4: DASHBOARD SEMESTRAL
# -------------------------------------------------------------
with tab_dashboard:
    st.subheader("Curva de Rendimiento")
    conn = get_db_connection()
    df_all = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_all.empty:
        st.info("Registra más entrenamientos para generar las curvas estadísticas.")
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
            title="Efectividad Técnica: Arranque vs Envión",
            labels={"fecha": "Fecha", "% Efectividad": "% Éxito", "tipo_sesion": "Levantamiento"}
        )
        fig_line.update_yaxes(range=[0, 105])
        st.plotly_chart(fig_line, use_container_width=True)
