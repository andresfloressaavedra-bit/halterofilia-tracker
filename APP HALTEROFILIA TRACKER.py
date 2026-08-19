import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import json
from datetime import date

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
        .stButton button {
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
            pct_pr REAL
        )
    """)
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
# CARGAR ESTADOS GUARDADOS EN DISCO
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
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.session_state["cfg_fecha"] = st.date_input("Fecha", date.today())
        pr_arr_in = st.number_input("PR Arranque (kg)", min_value=1.0, value=val_pr_arr, step=1.0)
        if pr_arr_in != val_pr_arr:
            guardar_estado_disco("pr_arr", pr_arr_in)
        st.session_state["cfg_pr_arr"] = pr_arr_in

    with col_b:
        st.session_state["cfg_enfoque"] = st.selectbox("Enfoque General", ["Arranque + Envión", "Arranque", "Envión", "Fuerza"], index=0)
        pr_env_in = st.number_input("PR Envión (kg)", min_value=1.0, value=val_pr_env, step=1.0)
        if pr_env_in != val_pr_env:
            guardar_estado_disco("pr_env", pr_env_in)
        st.session_state["cfg_pr_env"] = pr_env_in

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
                st.success(f"¡Agregado y guardado: {f_ejercicio} ({f_series}x{f_reps} @ {f_pct}%)!")
                st.rerun()
            else:
                st.warning("Escribe el nombre del ejercicio antes de agregar.")

    st.divider()
    st.subheader("📋 Bloques Planificados para Hoy")
    
    if len(st.session_state["lista_bloques"]) == 0:
        st.info("No hay bloques agregados todavía. Usa el formulario de arriba.")
    else:
        df_mostrar = pd.DataFrame(st.session_state["lista_bloques"])
        st.dataframe(df_mostrar, use_container_width=True)
        
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("🗑️ Borrar Último Bloque"):
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
                complejo_str = row["Complejo / Ejercicios"]
                movimientos = [m.strip() for m in complejo_str.split("+") if m.strip()]
                series = int(row["Series"])
                reps = int(row["Reps"])
                pct = float(row["% 1RM"])
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
# MÓDULO 2: REGISTRO EN VIVO
# -------------------------------------------------------------
elif menu == "🏋️‍♂️ 2. Registro en Vivo":
    st.title("🏋️‍♂️ Registro de Levantamientos")
    
    if st.session_state["matriz_activa"].empty:
        st.info("👈 Primero ve a **'1. Esquema y PRs'** en la barra lateral y presiona **'Generar Matriz'**.")
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
            key="editor_matriz_final"
        )
        
        st.session_state["matriz_activa"] = matriz_final
        guardar_estado_disco("matriz_activa", matriz_final.to_dict(orient="records"))

        st.write("")
        if st.button("💾 Guardar Entrenamiento Completo", type="primary"):
            conn = get_db_connection()
            c = conn.cursor()
            fecha_guardar = str(st.session_state.get("cfg_fecha", date.today()))
            pr_arr_g = float(cargar_estado_disco("pr_arr", 70.0))
            pr_env_g = float(cargar_estado_disco("pr_env", 90.0))

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
            
            st.session_state["matriz_activa"] = pd.DataFrame()
            guardar_estado_disco("matriz_activa", [])
            st.success("✅ ¡Entrenamiento guardado con éxito!")
            st.session_state["menu_nav"] = "🔍 Detalle Diario"
            st.rerun()

# -------------------------------------------------------------
# MÓDULO 3: DETALLE Y EDICIÓN DE ENTRENAMIENTOS ANTERIORES
# -------------------------------------------------------------
elif menu == "🔍 Detalle Diario":
    st.title("📋 Detalle y Edición de Entrenamientos")
    conn = get_db_connection()
    df_raw = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_raw.empty:
        st.info("Aún no tienes entrenamientos registrados.")
    else:
        fechas = sorted(df_raw["fecha"].dropna().unique(), reverse=True)
        fecha_sel = st.selectbox("Selecciona la fecha a consultar o editar:", fechas)
        df_dia = df_raw[df_raw["fecha"] == fecha_sel].copy()

        # Métricas calculadas
        tot_movs = len(df_dia)
        tot_val = len(df_dia[df_dia["resultado"] == "Completado"])
        tot_fal = len(df_dia[df_dia["resultado"] == "Falla"])
        pct_efectividad = (tot_val / tot_movs * 100) if tot_movs > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Efectividad Global", f"{pct_efectividad:.1f}%")
        c2.metric("Válidos", tot_val)
        c3.metric("Fallas", tot_fal)

        st.write("---")
        st.subheader("✏️ Editar Intentos de este Día")
        st.caption("Puedes modificar los kilos, cambiar si fue válido o escribir notas técnicas directamente en la tabla.")

        df_dia["Válido (✔)"] = df_dia["resultado"] == "Completado"
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
            df_dia[columnas_visibles],
            num_rows="fixed",
            use_container_width=True,
            column_config=cfg_edicion,
            key=f"editor_historial_{fecha_sel}"
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
                st.success("✅ ¡Entrenamiento anterior actualizado correctamente!")
                st.rerun()

        with col_btn_del:
            if st.button("🗑️ Eliminar Entrenamiento de este Día"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("DELETE FROM intentos WHERE fecha = ?", (fecha_sel,))
                conn.commit()
                conn.close()
                st.warning(f"Entrenamiento del día {fecha_sel} eliminado.")
                st.rerun()

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
