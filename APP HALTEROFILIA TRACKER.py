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
# PROCESADOR DE EXCEL PARA IMPORTACIÓN
# -------------------------------------------------------------
def generar_plantilla_excel():
    output = io.BytesIO()
    df_ejemplo = pd.DataFrame([
        {"Tipo": "Arranque", "Serie": "S1", "Rep": "Rep 1", "Movimiento": "Jalón Arranque c/p", "Kg": 50.0, "% 1RM": 70, "Estado": "Completado", "Observación": "Buena extensión"},
        {"Tipo": "Arranque", "Serie": "S1", "Rep": "Rep 2", "Movimiento": "Clásico", "Kg": 50.0, "% 1RM": 70, "Estado": "Completado", "Observación": ""},
        {"Tipo": "Envión", "Serie": "S1", "Rep": "Rep 1", "Movimiento": "Clean + Jerk", "Kg": 70.0, "% 1RM": 75, "Estado": "Completado", "Observación": "Codos rápidos"},
    ])
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_ejemplo.to_excel(writer, sheet_name="Plantilla", index=False)
    return output.getvalue()

def procesar_excel_importado(archivo_excel):
    df_in = pd.read_excel(archivo_excel)
    columnas_map = {}
    for col in df_in.columns:
        col_low = str(col).lower().strip()
        if "tipo" in col_low:
            columnas_map[col] = "Tipo"
        elif "serie" in col_low:
            columnas_map[col] = "Serie"
        elif "rep" in col_low:
            columnas_map[col] = "Rep"
        elif "mov" in col_low or "ejercicio" in col_low:
            columnas_map[col] = "Movimiento"
        elif "kg" in col_low or "peso" in col_low or "carga" in col_low:
            columnas_map[col] = "Carga (kg)"
        elif "%" in col_low or "pct" in col_low or "1rm" in col_low:
            columnas_map[col] = "% 1RM"
        elif "estado" in col_low or "result" in col_low or "valido" in col_low or "válido" in col_low:
            columnas_map[col] = "Estado"
        elif "obs" in col_low or "nota" in col_low or "coment" in col_low:
            columnas_map[col] = "Observación Técnica"
            
    df_in = df_in.rename(columns=columnas_map)
    filas_estandarizadas = []
    for _, r in df_in.iterrows():
        tipo = str(r.get("Tipo", "Arranque")).strip()
        if tipo not in ["Arranque", "Envión", "Fuerza"]:
            tipo = "Arranque"
        serie = str(r.get("Serie", "S1")).strip()
        rep = str(r.get("Rep", "Rep 1")).strip()
        mov = str(r.get("Movimiento", "Ejercicio")).strip()
        try:
            kg = float(r.get("Carga (kg)", 0.0))
        except Exception:
            kg = 0.0
        try:
            pct_raw = str(r.get("% 1RM", "70")).replace("%", "").strip()
            pct = float(pct_raw) if pct_raw else 70.0
        except Exception:
            pct = 70.0
            
        estado_raw = str(r.get("Estado", "Completado")).lower().strip()
        valido = estado_raw in ["completado", "válido", "valido", "true", "1", "si", "sí", "ok"]
        obs = str(r.get("Observación Técnica", "")) if pd.notna(r.get("Observación Técnica")) else ""
        
        filas_estandarizadas.append({
            "Tipo": tipo,
            "Serie": serie,
            "Rep": rep,
            "Movimiento": mov,
            "Carga (kg)": kg,
            "% 1RM": f"{int(pct)}%",
            "Válido (✔)": valido,
            "Observación Técnica": obs
        })
    return pd.DataFrame(filas_estandarizadas)

# -------------------------------------------------------------
# EXPORTACIONES DIARIAS Y SEMESTRALES (EXCEL Y PDF)
# -------------------------------------------------------------
def generar_dashboard_excel(df, fecha_str, jornada_str):
    output = io.BytesIO()
    tot_movs = len(df)
    tot_val = len(df[df["resultado"] == "Completado"])
    tot_fal = len(df[df["resultado"] == "Falla"])
    pct_efectividad = (tot_val / tot_movs * 100) if tot_movs > 0 else 0
    tonelaje = df[df["resultado"] == "Completado"]["peso"].sum() if "peso" in df.columns else 0.0

    df_kpis = pd.DataFrame([
        {"Métrica": "Fecha", "Valor": fecha_str},
        {"Métrica": "Jornada", "Valor": jornada_str},
        {"Métrica": "Efectividad Técnica (%)", "Valor": f"{pct_efectividad:.1f}%"},
        {"Métrica": "Levantamientos Válidos", "Valor": tot_val},
        {"Métrica": "Fallas Técnicas", "Valor": tot_fal},
        {"Métrica": "Total Movimientos", "Valor": tot_movs},
        {"Métrica": "Tonelaje Total Válido (kg)", "Valor": f"{tonelaje:.1f} kg"}
    ])

    df_temp = df.copy()
    df_temp["es_valido"] = df_temp["resultado"] == "Completado"
    df_resumen_ej = df_temp.groupby("movimiento").agg(
        Total_Intentos=("id", "count"),
        Validos=("es_valido", "sum"),
        Max_Kg=("peso", "max"),
        Prom_Kg=("peso", "mean")
    ).reset_index()
    df_resumen_ej["% Exito"] = (df_resumen_ej["Validos"] / df_resumen_ej["Total_Intentos"] * 100).round(1).astype(str) + "%"
    df_resumen_ej["Prom_Kg"] = df_resumen_ej["Prom_Kg"].round(1)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_kpis.to_excel(writer, sheet_name="Resumen KPIs", index=False)
        df_resumen_ej.to_excel(writer, sheet_name="Por Ejercicio", index=False)
        df.to_excel(writer, sheet_name="Detalle Completo", index=False)
        
    return output.getvalue()

def generar_dashboard_pdf(df, fecha_str, jornada_str):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "DASHBOARD DIARIO DE ENTRENAMIENTO", ln=True, align="C")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 5, f"Fecha: {fecha_str} | Turno: {jornada_str}", ln=True, align="C")
    pdf.ln(4)

    tot_movs = len(df)
    tot_val = len(df[df["resultado"] == "Completado"])
    tot_fal = len(df[df["resultado"] == "Falla"])
    pct_efectividad = (tot_val / tot_movs * 100) if tot_movs > 0 else 0
    tonelaje = df[df["resultado"] == "Completado"]["peso"].sum() if "peso" in df.columns else 0.0

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "1. RESUMEN Y TONELAJE DE SESIÓN", ln=True)
    pdf.set_font("Helvetica", "", 9)
    
    ancho_kpi = 47.5
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(ancho_kpi, 6, "Efectividad", border=1, align="C", fill=True)
    pdf.cell(ancho_kpi, 6, "Válidos / Fallas", border=1, align="C", fill=True)
    pdf.cell(ancho_kpi, 6, "Total Movs", border=1, align="C", fill=True)
    pdf.cell(ancho_kpi, 6, "Tonelaje Válido", border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(ancho_kpi, 8, f"{pct_efectividad:.1f}%", border=1, align="C")
    pdf.cell(ancho_kpi, 8, f"{tot_val} / {tot_fal}", border=1, align="C")
    pdf.cell(ancho_kpi, 8, f"{tot_movs}", border=1, align="C")
    pdf.cell(ancho_kpi, 8, f"{tonelaje:.1f} kg", border=1, align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "2. RENDIMIENTO POR EJERCICIO", ln=True)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(65, 6, "Ejercicio", border=1, align="C", fill=True)
    pdf.cell(30, 6, "Intentos", border=1, align="C", fill=True)
    pdf.cell(30, 6, "Válidos", border=1, align="C", fill=True)
    pdf.cell(30, 6, "Carga Máx (kg)", border=1, align="C", fill=True)
    pdf.cell(35, 6, "% Éxito", border=1, align="C", fill=True)
    pdf.ln()

    df_temp = df.copy()
    df_temp["es_valido"] = df_temp["resultado"] == "Completado"
    df_resumen_ej = df_temp.groupby("movimiento").agg(
        Total_Intentos=("id", "count"),
        Validos=("es_valido", "sum"),
        Max_Kg=("peso", "max")
    ).reset_index()

    pdf.set_font("Helvetica", "", 8)
    for _, r in df_resumen_ej.iterrows():
        pct_ej = (r["Validos"] / r["Total_Intentos"] * 100) if r["Total_Intentos"] > 0 else 0
        pdf.cell(65, 6, str(r["movimiento"])[:32], border=1)
        pdf.cell(30, 6, str(r["Total_Intentos"]), border=1, align="C")
        pdf.cell(30, 6, str(r["Validos"]), border=1, align="C")
        pdf.cell(30, 6, f"{r['Max_Kg']:.1f} kg", border=1, align="C")
        pdf.cell(35, 6, f"{pct_ej:.1f}%", border=1, align="C")
        pdf.ln()

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "3. REGISTRO DETALLADO INTENTO POR INTENTO", ln=True)
    
    pdf.set_font("Helvetica", "B", 8)
    columnas = ["Tipo", "Serie", "Rep", "Movimiento", "Kg", "%", "Estado", "Observación"]
    anchos = [18, 12, 12, 45, 14, 14, 18, 57]
    
    for col, ancho in zip(columnas, anchos):
        pdf.cell(ancho, 6, col, border=1, align="C", fill=True)
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 8)
    for _, fila in df.iterrows():
        tipo = str(fila.get("tipo_sesion", ""))[:10]
        serie = str(fila.get("serie", ""))[:6]
        rep = str(fila.get("repeticion", ""))[:6]
        mov = str(fila.get("movimiento", ""))[:24]
        kg = str(fila.get("peso", ""))[:6]
        pct = str(fila.get("pct_pr", ""))[:6]
        res = "Válido" if str(fila.get("resultado", "")) == "Completado" else "Falla"
        obs = str(fila.get("observacion", ""))[:32]

        pdf.cell(anchos[0], 5.5, tipo, border=1, align="C")
        pdf.cell(anchos[1], 5.5, serie, border=1, align="C")
        pdf.cell(anchos[2], 5.5, rep, border=1, align="C")
        pdf.cell(anchos[3], 5.5, mov, border=1)
        pdf.cell(anchos[4], 5.5, kg, border=1, align="C")
        pdf.cell(anchos[5], 5.5, pct, border=1, align="C")
        pdf.cell(anchos[6], 5.5, res, border=1, align="C")
        pdf.cell(anchos[7], 5.5, obs, border=1)
        pdf.ln()

    out = pdf.output()
    if isinstance(out, str):
        return out.encode("latin1")
    return bytes(out)

def generar_semestral_excel(df_all):
    output = io.BytesIO()
    df_all["is_comp"] = df_all["resultado"] == "Completado"
    
    # 1. Resumen Diario Consolidado
    df_diario = df_all.groupby(["fecha", "jornada"]).agg(
        Total_Movs=("id", "count"),
        Validos=("is_comp", "sum"),
        Tonelaje_Kg=("peso", lambda x: x[df_all.loc[x.index, "is_comp"]].sum())
    ).reset_index()
    df_diario["Fallas"] = df_diario["Total_Movs"] - df_diario["Validos"]
    df_diario["% Efectividad"] = (df_diario["Validos"] / df_diario["Total_Movs"] * 100).round(1)

    # 2. Desglose por Ejercicio Semestral
    df_ejercicios = df_all.groupby("movimiento").agg(
        Total_Intentos=("id", "count"),
        Validos=("is_comp", "sum"),
        Max_Kg=("peso", "max"),
        Prom_Kg=("peso", "mean")
    ).reset_index()
    df_ejercicios["% Éxito"] = (df_ejercicios["Validos"] / df_ejercicios["Total_Intentos"] * 100).round(1)
    df_ejercicios["Prom_Kg"] = df_ejercicios["Prom_Kg"].round(1)

    # 3. Métricas Globales
    tot_movs = len(df_all)
    tot_val = int(df_all["is_comp"].sum())
    tot_fal = tot_movs - tot_val
    pct_global = (tot_val / tot_movs * 100) if tot_movs > 0 else 0
    tonelaje_global = df_all[df_all["is_comp"]]["peso"].sum()

    df_kpi_sem = pd.DataFrame([
        {"Métrica": "Período", "Valor": "Histórico Semestral"},
        {"Métrica": "Total Sesiones Registradas", "Valor": len(df_diario)},
        {"Métrica": "Efectividad Global (%)", "Valor": f"{pct_global:.1f}%"},
        {"Métrica": "Total Levantamientos Válidos", "Valor": tot_val},
        {"Métrica": "Total Fallas Técnicas", "Valor": tot_fal},
        {"Métrica": "Volumen Total Intentos", "Valor": tot_movs},
        {"Métrica": "Tonelaje Total Acumulado (kg)", "Valor": f"{tonelaje_global:.1f} kg"}
    ])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_kpi_sem.to_excel(writer, sheet_name="KPIs Semestre", index=False)
        df_diario.to_excel(writer, sheet_name="Resumen Diario", index=False)
        df_ejercicios.to_excel(writer, sheet_name="Rendimiento Ejercicios", index=False)
        df_all.to_excel(writer, sheet_name="Todos los Intentos", index=False)
        
    return output.getvalue()

def generar_semestral_pdf(df_all):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "DASHBOARD SEMESTRAL DE HALTEROFILIA", ln=True, align="C")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 5, f"Reporte Consolidado de Rendimiento y Progresión", ln=True, align="C")
    pdf.ln(4)

    df_all["is_comp"] = df_all["resultado"] == "Completado"
    tot_movs = len(df_all)
    tot_val = int(df_all["is_comp"].sum())
    tot_fal = tot_movs - tot_val
    pct_global = (tot_val / tot_movs * 100) if tot_movs > 0 else 0
    tonelaje_global = df_all[df_all["is_comp"]]["peso"].sum()

    # 1. KPIs Globales
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "1. RESUMEN GLOBAL ACUMULADO", ln=True)
    pdf.set_font("Helvetica", "", 9)
    
    ancho_kpi = 47.5
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(ancho_kpi, 6, "Efectividad Global", border=1, align="C", fill=True)
    pdf.cell(ancho_kpi, 6, "Válidos / Fallas", border=1, align="C", fill=True)
    pdf.cell(ancho_kpi, 6, "Total Movs", border=1, align="C", fill=True)
    pdf.cell(ancho_kpi, 6, "Tonelaje Acumulado", border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(ancho_kpi, 8, f"{pct_global:.1f}%", border=1, align="C")
    pdf.cell(ancho_kpi, 8, f"{tot_val} / {tot_fal}", border=1, align="C")
    pdf.cell(ancho_kpi, 8, f"{tot_movs}", border=1, align="C")
    pdf.cell(ancho_kpi, 8, f"{tonelaje_global:.1f} kg", border=1, align="C")
    pdf.ln(10)

    # 2. Resumen Diario Consolidado
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "2. EVOLUCIÓN Y RESUMEN DIARIO", ln=True)
    
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(35, 6, "Fecha", border=1, align="C", fill=True)
    pdf.cell(45, 6, "Jornada", border=1, align="C", fill=True)
    pdf.cell(25, 6, "Total Movs", border=1, align="C", fill=True)
    pdf.cell(25, 6, "Válidos", border=1, align="C", fill=True)
    pdf.cell(30, 6, "% Efectividad", border=1, align="C", fill=True)
    pdf.cell(30, 6, "Tonelaje (kg)", border=1, align="C", fill=True)
    pdf.ln()

    df_diario = df_all.groupby(["fecha", "jornada"]).agg(
        Total_Movs=("id", "count"),
        Validos=("is_comp", "sum"),
        Tonelaje_Kg=("peso", lambda x: x[df_all.loc[x.index, "is_comp"]].sum())
    ).reset_index()

    pdf.set_font("Helvetica", "", 8)
    for _, r in df_diario.iterrows():
        pct_dia = (r["Validos"] / r["Total_Movs"] * 100) if r["Total_Movs"] > 0 else 0
        pdf.cell(35, 6, str(r["fecha"]), border=1, align="C")
        pdf.cell(45, 6, str(r["jornada"])[:22], border=1)
        pdf.cell(25, 6, str(r["Total_Movs"]), border=1, align="C")
        pdf.cell(25, 6, str(r["Validos"]), border=1, align="C")
        pdf.cell(30, 6, f"{pct_dia:.1f}%", border=1, align="C")
        pdf.cell(30, 6, f"{r['Tonelaje_Kg']:.1f} kg", border=1, align="C")
        pdf.ln()

    pdf.ln(6)

    # 3. Rendimiento por Ejercicio Semestral
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "3. RENDIMIENTO ACUMULADO POR EJERCICIO", ln=True)
    
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(65, 6, "Ejercicio", border=1, align="C", fill=True)
    pdf.cell(30, 6, "Total Intentos", border=1, align="C", fill=True)
    pdf.cell(30, 6, "Válidos", border=1, align="C", fill=True)
    pdf.cell(30, 6, "Carga Máx (kg)", border=1, align="C", fill=True)
    pdf.cell(35, 6, "% Éxito", border=1, align="C", fill=True)
    pdf.ln()

    df_ejercicios = df_all.groupby("movimiento").agg(
        Total_Intentos=("id", "count"),
        Validos=("is_comp", "sum"),
        Max_Kg=("peso", "max")
    ).reset_index()

    pdf.set_font("Helvetica", "", 8)
    for _, r in df_ejercicios.iterrows():
        pct_ej = (r["Validos"] / r["Total_Intentos"] * 100) if r["Total_Intentos"] > 0 else 0
        pdf.cell(65, 6, str(r["movimiento"])[:32], border=1)
        pdf.cell(30, 6, str(r["Total_Intentos"]), border=1, align="C")
        pdf.cell(30, 6, str(r["Validos"]), border=1, align="C")
        pdf.cell(30, 6, f"{r['Max_Kg']:.1f} kg", border=1, align="C")
        pdf.cell(35, 6, f"{pct_ej:.1f}%", border=1, align="C")
        pdf.ln()

    out = pdf.output()
    if isinstance(out, str):
        return out.encode("latin1")
    return bytes(out)

def generar_excel_simple(df, titulo_hoja="Entrenamiento"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=titulo_hoja[:30], index=False)
    return output.getvalue()

def generar_pdf_simple(df, titulo="Reporte de Entrenamiento", subtitulo=""):
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
# MÓDULO 1: CONFIGURACIÓN, ESQUEMA E IMPORTACIÓN EXCEL
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

    # ---------------------------------------------------------
    # IMPORTAR EXCEL DIRECTAMENTE A ESTA SESIÓN
    # ---------------------------------------------------------
    st.divider()
    with st.expander("📥 Importar Excel Directamente a Esta Sesión", expanded=True):
        st.markdown("Sube una planilla de Excel para cargarla a tu sesión activa de hoy o guardarla en el historial:")
        
        col_imp_top1, col_imp_top2 = st.columns([1, 2])
        with col_imp_top1:
            plantilla_bytes = generar_plantilla_excel()
            st.download_button(
                label="📄 Descargar Plantilla Excel Ejemplo",
                data=plantilla_bytes,
                file_name="Plantilla_Halterofilia_Ejemplo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_plantilla_esquema"
            )
        
        archivo_excel = st.file_uploader("Selecciona archivo Excel (.xlsx)", type=["xlsx", "xls"], key="uploader_excel_esquema")
        if archivo_excel is not None:
            try:
                df_excel_procesado = procesar_excel_importado(archivo_excel)
                st.write("**Previsualización de levantamientos:**")
                st.dataframe(df_excel_procesado, use_container_width=True)
                
                col_btn_in1, col_btn_in2 = st.columns(2)
                with col_btn_in1:
                    if st.button("⚡ Cargar a la Matriz Activa para Entrenar", type="primary"):
                        st.session_state["matriz_activa"] = df_excel_procesado
                        guardar_estado_disco("matriz_activa", df_excel_procesado.to_dict(orient="records"))
                        st.success("¡Planilla cargada en la matriz activa!")
                        st.session_state["menu_nav"] = "🏋️‍♂️ 2. Registro en Vivo"
                        st.rerun()
                
                with col_btn_in2:
                    if st.button("💾 Guardar Directamente en la Base de Datos"):
                        conn = get_db_connection()
                        c = conn.cursor()
                        f_imp = str(st.session_state.get("cfg_fecha", date.today()))
                        j_imp = str(st.session_state.get("cfg_jornada", "Sesión 1"))
                        pr_arr_g = float(cargar_estado_disco("pr_arr", 70.0))
                        pr_env_g = float(cargar_estado_disco("pr_env", 90.0))
                        
                        for _, r in df_excel_procesado.iterrows():
                            valido = bool(r["Válido (✔)"])
                            res = "Completado" if valido else "Falla"
                            tipo_actual = str(r["Tipo"])
                            pr_base = pr_arr_g if tipo_actual == "Arranque" else pr_env_g
                            obs = str(r["Observación Técnica"])
                            
                            c.execute("""
                                INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion, jornada)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                f_imp, tipo_actual, float(pr_base), str(r.get("Movimiento", "")),
                                str(r.get("Serie", "S1")), str(r.get("Rep", "Rep 1")), str(r.get("Movimiento", "")),
                                float(str(r.get("% 1RM", "70")).replace("%", "") if str(r.get("% 1RM", "70")).replace("%", "").isdigit() else 70.0),
                                float(r.get("Carga (kg)", 0.0)), res, obs, j_imp
                            ))
                        conn.commit()
                        conn.close()
                        st.success(f"✅ ¡Sesión guardada en el historial para el {f_imp} ({j_imp})!")
                        st.session_state["menu_nav"] = "🔍 Detalle Diario"
                        st.rerun()

            except Exception as e:
                st.error(f"Error al leer el archivo Excel: {e}")

    st.divider()
    st.subheader("➕ Agregar Ejercicio o Bloque Manualmente")
    
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
        st.info("No hay bloques agregados todavía. Usa el formulario de arriba o importa un Excel.")
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
        st.info("👈 Primero ve a **'1. Esquema y PRs'** en la barra lateral y presiona **'Generar Matriz'**, o importa un archivo Excel.")
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
            excel_bytes = generar_excel_simple(matriz_final, f"Entrenamiento_{fecha_act}")
            st.download_button(
                label="📥 Descargar Planilla Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"Entrenamiento_{fecha_act}_{jornada_act}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_excel_vivo"
            )

        with col_exp2:
            pdf_bytes = generar_pdf_simple(matriz_final, f"Planilla: {fecha_act}", f"Jornada: {jornada_act}")
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
# MÓDULO 3: DETALLE, EDICIÓN PROFUNDA Y DASHBOARD DIARIO EN 1 CLIC
# -------------------------------------------------------------
elif menu == "🔍 Detalle Diario":
    st.title("📋 Gestión y Edición de Entrenamientos")
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
        tonelaje_tot = df_sesion[df_sesion["resultado"] == "Completado"]["peso"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Efectividad", f"{pct_efectividad:.1f}%")
        c2.metric("Válidos", tot_val)
        c3.metric("Fallas", tot_fal)
        c4.metric("Tonelaje Válido", f"{tonelaje_tot:.1f} kg")

        st.write("---")
        st.subheader("📊 Generar Dashboard Diario Completo (1 Clic)")
        st.caption("Exporta un informe ejecutivo con KPIs, análisis por ejercicio, tonelaje y detalle técnico completo.")
        
        col_dash1, col_dash2 = st.columns(2)
        with col_dash1:
            bytes_dash_excel = generar_dashboard_excel(df_sesion, fecha_actual_sesion, jornada_actual_sesion)
            st.download_button(
                label="📊 Descargar Dashboard en Excel (.xlsx)",
                data=bytes_dash_excel,
                file_name=f"Dashboard_Diario_{fecha_actual_sesion}_{jornada_actual_sesion}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_dash_excel"
            )
            
        with col_dash2:
            bytes_dash_pdf = generar_dashboard_pdf(df_sesion, fecha_actual_sesion, jornada_actual_sesion)
            st.download_button(
                label="📑 Descargar Dashboard en PDF (.pdf)",
                data=bytes_dash_pdf,
                file_name=f"Dashboard_Diario_{fecha_actual_sesion}_{jornada_actual_sesion}.pdf",
                mime="application/pdf",
                key="btn_dl_dash_pdf"
            )

        st.write("---")
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            with st.expander("📋 Duplicar / Copiar esta Sesión a Otro Día"):
                col_cp1, col_cp2 = st.columns(2)
                with col_cp1:
                    fecha_copia_dest = st.date_input("Copiar al día:", date.today(), key="f_cp_dest")
                with col_cp2:
                    jornada_copia_dest = st.selectbox("Turno de destino:", ["Sesión 1 (Mañana)", "Sesión 2 (Tarde)", "Sesión 3 (Extra)"], key="j_cp_dest")
                
                if st.button("📑 Clonar Sesión a la Fecha Seleccionada"):
                    conn = get_db_connection()
                    c = conn.cursor()
                    for _, fila_cp in df_sesion.iterrows():
                        c.execute("""
                            INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion, jornada)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            str(fecha_copia_dest), fila_cp["tipo_sesion"], fila_cp["pr_base"], fila_cp["bloque_combo"],
                            fila_cp["serie"], fila_cp["repeticion"], fila_cp["movimiento"], fila_cp["pct_pr"],
                            fila_cp["peso"], fila_cp["resultado"], fila_cp["observacion"], jornada_copia_dest
                        ))
                    conn.commit()
                    conn.close()
                    st.success(f"¡Sesión duplicada correctamente al {fecha_copia_dest} ({jornada_copia_dest})!")
                    st.rerun()

        with col_h2:
            with st.expander("🚚 Mover un Ejercicio Específico a Otro Día"):
                opciones_mover = {
                    int(r["id"]): f"ID {r['id']} - {r['serie']} {r['movimiento']} ({r['peso']} kg)"
                    for _, r in df_sesion.iterrows()
                }
                id_a_mover = st.selectbox("Selecciona el intento a transferir:", list(opciones_mover.keys()), format_func=lambda x: opciones_mover[x])
                col_mv1, col_mv2 = st.columns(2)
                with col_mv1:
                    fecha_destino = st.date_input("Fecha destino:", date.today(), key="f_mv_dest")
                with col_mv2:
                    jornada_destino = st.selectbox("Jornada destino:", ["Sesión 1 (Mañana)", "Sesión 2 (Tarde)", "Sesión 3 (Extra)"], key="j_mv_dest")
                
                if st.button("🚀 Transferir Ejercicio Seleccionado"):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("""
                        UPDATE intentos 
                        SET fecha = ?, jornada = ? 
                        WHERE id = ?
                    """, (str(fecha_destino), jornada_destino, int(id_a_mover)))
                    conn.commit()
                    conn.close()
                    st.success("¡Ejercicio transferido exitosamente!")
                    st.rerun()

        with st.expander("📥 Importar Excel Directamente a Esta Sesión"):
            archivo_excel_hist = st.file_uploader("Subir Excel para agregar o reemplazar a esta sesión:", type=["xlsx", "xls"], key="uploader_hist")
            if archivo_excel_hist is not None:
                try:
                    df_imp_hist = procesar_excel_importado(archivo_excel_hist)
                    st.write("**Previsualización:**")
                    st.dataframe(df_imp_hist, use_container_width=True)
                    if st.button("➕ Anexar estos datos a la Sesión Actual"):
                        conn = get_db_connection()
                        c = conn.cursor()
                        pr_arr_g = float(cargar_estado_disco("pr_arr", 70.0))
                        pr_env_g = float(cargar_estado_disco("pr_env", 90.0))
                        
                        for _, r in df_imp_hist.iterrows():
                            valido = bool(r["Válido (✔)"])
                            res = "Completado" if valido else "Falla"
                            tipo_actual = str(r["Tipo"])
                            pr_base = pr_arr_g if tipo_actual == "Arranque" else pr_env_g
                            obs = str(r["Observación Técnica"])
                            c.execute("""
                                INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion, jornada)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                fecha_actual_sesion, tipo_actual, float(pr_base), str(r.get("Movimiento", "")),
                                str(r.get("Serie", "S1")), str(r.get("Rep", "Rep 1")), str(r.get("Movimiento", "")),
                                float(str(r.get("% 1RM", "70")).replace("%", "") if str(r.get("% 1RM", "70")).replace("%", "").isdigit() else 70.0),
                                float(r.get("Carga (kg)", 0.0)), res, obs, jornada_actual_sesion
                            ))
                        conn.commit()
                        conn.close()
                        st.success("¡Datos anexados a la sesión!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al leer Excel: {e}")

        with st.expander("📅 Cambiar Fecha de la Sesión Completa"):
            nueva_fecha_glob = st.date_input("Nueva fecha para toda esta sesión:", pd.to_datetime(fecha_actual_sesion).date(), key="n_f_g")
            if st.button("🔄 Aplicar Nueva Fecha"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("""
                    UPDATE intentos 
                    SET fecha = ? 
                    WHERE fecha = ? AND jornada = ?
                """, (str(nueva_fecha_glob), fecha_actual_sesion, jornada_actual_sesion))
                conn.commit()
                conn.close()
                st.success(f"Sesión transferida al {nueva_fecha_glob}")
                st.rerun()

        with st.expander("➕ Añadir Ejercicio Retroactivo Manual"):
            with st.form("form_retroactivo"):
                col_r1, col_r2, col_r3 = st.columns(3)
                with col_r1:
                    r_tipo = st.selectbox("Tipo", ["Arranque", "Envión", "Fuerza"], key="r_t")
                    r_mov = st.text_input("Movimiento / Ejercicio", placeholder="Ej: Clásico", key="r_m")
                with col_r2:
                    r_serie = st.text_input("Serie", value="S1", key="r_s")
                    r_rep = st.text_input("Repetición", value="Rep 1", key="r_r")
                with col_r3:
                    r_peso = st.number_input("Kilos", min_value=0.0, value=70.0, step=0.5, key="r_p")
                    r_pct = st.number_input("% 1RM", min_value=10, max_value=150, value=80, key="r_pct")
                
                col_r4, col_r5 = st.columns([1, 2])
                with col_r4:
                    r_valido = st.checkbox("¿Válido?", value=True, key="r_val")
                with col_r5:
                    r_obs = st.text_input("Observación Técnica", key="r_obs")
                
                if st.form_submit_button("➕ Insertar en esta Sesión"):
                    if r_mov.strip():
                        res_retro = "Completado" if r_valido else "Falla"
                        conn = get_db_connection()
                        c = conn.cursor()
                        pr_calc = float(cargar_estado_disco("pr_arr", 70.0)) if r_tipo == "Arranque" else float(cargar_estado_disco("pr_env", 90.0))
                        c.execute("""
                            INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion, jornada)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            fecha_actual_sesion, r_tipo, pr_calc, r_mov.strip(),
                            r_serie, r_rep, r_mov.strip(), float(r_pct), float(r_peso),
                            res_retro, r_obs, jornada_actual_sesion
                        ))
                        conn.commit()
                        conn.close()
                        st.success("¡Ejercicio insertado en la sesión!")
                        st.rerun()
                    else:
                        st.warning("Escribe el nombre del movimiento.")

        st.write("---")
        st.subheader("✏️ Editor de Intentos (Modificar o Eliminar Filas)")
        df_sesion["Válido (✔)"] = df_sesion["resultado"] == "Completado"
        columnas_visibles = ["id", "tipo_sesion", "serie", "repeticion", "movimiento", "pct_pr", "peso", "Válido (✔)", "observacion"]
        
        cfg_edicion = {
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "tipo_sesion": st.column_config.SelectboxColumn("Tipo", options=["Arranque", "Envión", "Fuerza"], required=True),
            "serie": st.column_config.TextColumn("Serie"),
            "repeticion": st.column_config.TextColumn("Rep"),
            "movimiento": st.column_config.TextColumn("Movimiento", width="medium"),
            "pct_pr": st.column_config.NumberColumn("% 1RM", format="%d%%"),
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
            if st.button("💾 Guardar Modificaciones / Eliminar Filas", type="primary"):
                conn = get_db_connection()
                c = conn.cursor()
                ids_anteriores = set(df_sesion["id"].tolist())
                ids_actuales = set(df_editado["id"].dropna().astype(int).tolist())
                ids_a_borrar = ids_anteriores - ids_actuales
                
                for id_borrar in ids_a_borrar:
                    c.execute("DELETE FROM intentos WHERE id = ?", (int(id_borrar),))

                for _, r in df_editado.iterrows():
                    res = "Completado" if bool(r["Válido (✔)"]) else "Falla"
                    obs = str(r["observacion"]) if pd.notna(r["observacion"]) else ""
                    tipo_u = str(r["tipo_sesion"]) if pd.notna(r["tipo_sesion"]) else "Arranque"
                    serie_u = str(r["serie"]) if pd.notna(r["serie"]) else "S1"
                    rep_u = str(r["repeticion"]) if pd.notna(r["repeticion"]) else "Rep 1"
                    mov_u = str(r["movimiento"]) if pd.notna(r["movimiento"]) else "Ejercicio"
                    pct_u = float(r["pct_pr"]) if pd.notna(r["pct_pr"]) else 70.0
                    peso_u = float(r["peso"]) if pd.notna(r["peso"]) else 0.0

                    if pd.notna(r["id"]) and int(r["id"]) in ids_anteriores:
                        c.execute("""
                            UPDATE intentos 
                            SET tipo_sesion = ?, serie = ?, repeticion = ?, movimiento = ?, 
                                pct_pr = ?, peso = ?, resultado = ?, observacion = ?
                            WHERE id = ?
                        """, (tipo_u, serie_u, rep_u, mov_u, pct_u, peso_u, res, obs, int(r["id"])))
                    else:
                        pr_calc = float(cargar_estado_disco("pr_arr", 70.0)) if tipo_u == "Arranque" else float(cargar_estado_disco("pr_env", 90.0))
                        c.execute("""
                            INSERT INTO intentos (fecha, tipo_sesion, pr_base, bloque_combo, serie, repeticion, movimiento, pct_pr, peso, resultado, observacion, jornada)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (fecha_actual_sesion, tipo_u, pr_calc, mov_u, serie_u, rep_u, mov_u, pct_u, peso_u, res, obs, jornada_actual_sesion))
                
                conn.commit()
                conn.close()
                st.success("✅ ¡Cambios guardados y sincronizados correctamente!")
                st.rerun()

        with col_btn_del:
            if st.button("🗑️ Eliminar Esta Sesión Completa"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("DELETE FROM intentos WHERE fecha = ? AND jornada = ?", (fecha_actual_sesion, jornada_actual_sesion))
                conn.commit()
                conn.close()
                st.warning(f"Sesión {fecha_actual_sesion} ({jornada_actual_sesion}) eliminada.")
                st.rerun()

# -------------------------------------------------------------
# MÓDULO 4: DASHBOARD SEMESTRAL (GRÁFICAS COMPARATIVAS Y DESCARGA)
# -------------------------------------------------------------
elif menu == "📊 Dashboard Semestral":
    st.title("📈 Dashboard Semestral y Progresión")
    conn = get_db_connection()
    df_all = pd.read_sql_query("SELECT * FROM intentos", conn)
    conn.close()

    if df_all.empty:
        st.info("Registra más sesiones para ver las estadísticas acumuladas.")
    else:
        df_all["is_comp"] = df_all["resultado"] == "Completado"
        df_all["jornada"] = df_all["jornada"].fillna("Sesión 1")

        # 1. Métricas Globales Acumuladas
        tot_movs = len(df_all)
        tot_val = int(df_all["is_comp"].sum())
        tot_fal = tot_movs - tot_val
        pct_global = (tot_val / tot_movs * 100) if tot_movs > 0 else 0
        tonelaje_global = df_all[df_all["is_comp"]]["peso"].sum()

        c_s1, c_s2, c_s3, c_s4 = st.columns(4)
        c_s1.metric("Efectividad Semestral", f"{pct_global:.1f}%")
        c_s2.metric("Válidos Acumulados", tot_val)
        c_s3.metric("Fallas Acumuladas", tot_fal)
        c_s4.metric("Tonelaje Semestral", f"{tonelaje_global:.1f} kg")

        st.write("---")
        st.subheader("📥 Exportar Reporte Semestral Completo (1 Clic)")
        st.caption("Descarga el informe ejecutivo con KPIs acumulados, tabla de progresión diaria y rendimiento por ejercicio.")
        
        col_dl_sem1, col_dl_sem2 = st.columns(2)
        with col_dl_sem1:
            bytes_sem_excel = generar_semestral_excel(df_all)
            st.download_button(
                label="📊 Descargar Dashboard Semestral en Excel (.xlsx)",
                data=bytes_sem_excel,
                file_name="Dashboard_Semestral_Halterofilia.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_dl_sem_excel"
            )
            
        with col_dl_sem2:
            bytes_sem_pdf = generar_semestral_pdf(df_all)
            st.download_button(
                label="📑 Descargar Dashboard Semestral en PDF (.pdf)",
                data=bytes_sem_pdf,
                file_name="Dashboard_Semestral_Halterofilia.pdf",
                mime="application/pdf",
                key="btn_dl_sem_pdf"
            )

        st.write("---")
        st.subheader("📈 Gráficas Comparativas")

        # Gráfica 1: Curva de Efectividad Diaria (Arranque vs Envión)
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
            title="Evolución Técnica Diaria: Arranque vs Envión (% Éxito)",
            labels={"fecha": "Fecha", "% Efectividad": "% Efectividad", "tipo_sesion": "Tipo"}
        )
        fig_line.update_yaxes(range=[0, 105])
        st.plotly_chart(fig_line, use_container_width=True)

        # Gráfica 2: Tonelaje Total Acumulado por Día
        df_tonelaje_dia = df_all[df_all["is_comp"]].groupby("fecha")["peso"].sum().reset_index()
        fig_bar = px.bar(
            df_tonelaje_dia,
            x="fecha",
            y="peso",
            title="Tonelaje Total Válido por Día (Kilos Acumulados)",
            labels={"fecha": "Fecha", "peso": "Kilos Levantados (kg)"},
            color_discrete_sequence=["#2E7D32"]
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.write("---")
        st.subheader("📋 Resumen Diario Consolidado")
        
        df_resumen_diario_vista = df_all.groupby(["fecha", "jornada"]).agg(
            Total_Movs=("id", "count"),
            Validos=("is_comp", "sum"),
            Tonelaje_Kg=("peso", lambda x: x[df_all.loc[x.index, "is_comp"]].sum())
        ).reset_index()
        df_resumen_diario_vista["Fallas"] = df_resumen_diario_vista["Total_Movs"] - df_resumen_diario_vista["Validos"]
        df_resumen_diario_vista["% Efectividad"] = (df_resumen_diario_vista["Validos"] / df_resumen_diario_vista["Total_Movs"] * 100).round(1).astype(str) + "%"
        df_resumen_diario_vista["Tonelaje_Kg"] = df_resumen_diario_vista["Tonelaje_Kg"].round(1).astype(str) + " kg"

        st.dataframe(
            df_resumen_diario_vista.rename(columns={
                "fecha": "Fecha", "jornada": "Jornada / Turno", "Total_Movs": "Total Movs",
                "Validos": "Válidos", "Fallas": "Fallas", "% Efectividad": "% Efectividad", "Tonelaje_Kg": "Tonelaje Válido"
            }),
            use_container_width=True
        )
