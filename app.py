import streamlit as st
import pandas as pd
import json

st.set_page_config(page_title="CommunityLab - Panel de Curaduría", layout="centered")
st.title("🛡️ CommunityLab — Curaduría & Validación")
st.caption("Revisa, edita y aprueba los activos generados por IA. (Versión Multi-Activo)")

# RECUERDA PONER AQUÍ TU ENLACE CSV DE LA PESTAÑA "Curaduria"
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTFou-OMBNVV4_KdDEB5w5lGbizrP6VcLYvcqAfbjJYbMn2USoWJFKo7ed4VsPZ9y77YkVldMZgiS7m/pub?gid=0&single=true&output=csv"

@st.cache_data(ttl=3)
def cargar_datos():
    try:
        df = pd.read_csv(SHEET_CSV_URL)
        if df.empty:
            return pd.DataFrame()
        # Filtramos solo los que están pendientes de curaduría
        df = df.fillna("")
        pendientes = df[df['estado'] == 'pendiente_curaduria']
        return pendientes
    except Exception as e:
        return pd.DataFrame()

df_pendientes = cargar_datos()

if df_pendientes.empty:
    st.info("✅ No hay contenido nuevo pendiente de revisión. Todo está al día.")
else:
    st.write(f"📌 Tienes **{len(df_pendientes)}** activos pendientes de revisión.")
    
    # Iterar sobre cada fila pendiente
    for index, fila in df_pendientes.iterrows():
        tipo = fila.get("tipo_activo", "").lower()
        asset_id = fila.get("asset_id", f"ID-{index}")
        
        # Extraer el JSON oculto en la columna
        try:
            contenido = json.loads(fila.get("contenido_json", "{}"))
        except:
            contenido = {}

        with st.expander(f"📝 Revisar Activo: {tipo.upper()} | ID: {asset_id}", expanded=True):
            # Aquí aplicamos el index para que la llave sea 100% única
            with st.form(f"form_{asset_id}_{index}"):
                
                # Campos dinámicos según el tipo de activo (también con llaves únicas)
                if tipo == "linkedin":
                    titulo = st.text_input("Título del Post", value=contenido.get("titulo", ""), key=f"tit_{index}")
                    copy = st.text_area("Copy sugerido", value=contenido.get("copy", ""), height=150, key=f"cop_{index}")
                    act_data = {"titulo": titulo, "copy": copy}
                    
                elif tipo == "faq":
                    tema = st.text_input("Tema", value=contenido.get("tema", ""), key=f"tem_{index}")
                    pregunta = st.text_input("Pregunta", value=contenido.get("pregunta", ""), key=f"preg_{index}")
                    respuesta = st.text_area("Respuesta", value=contenido.get("respuesta", ""), height=100, key=f"resp_{index}")
                    act_data = {"tema": tema, "pregunta": pregunta, "respuesta": respuesta}
                    
                elif tipo == "newsletter":
                    titular = st.text_input("Titular", value=contenido.get("titular", ""), key=f"titnl_{index}")
                    resumen = st.text_area("Resumen", value=contenido.get("resumen", ""), height=100, key=f"resnl_{index}")
                    act_data = {"titular": titular, "resumen": resumen}
                    
                else:
                    st.write("Contenido sin formato específico:", fila.get("contenido", ""))
                    act_data = {}

                st.divider()
                
                col1, col2 = st.columns(2)
                with col1:
                    aprobar = st.form_submit_button("✅ Aprobar y Enviar a OCI")
                with col2:
                    rechazar = st.form_submit_button("🗑️ Descartar")

                # Lógica de los botones
                if aprobar:
                    payload = {
                        "asset_id": asset_id,
                        "status": "aprobado_y_persistido",
                        "interaction_id": fila.get("interaction_id"),
                        "tipo": tipo,
                        "contenido_final": act_data
                    }
                    st.success("🎉 ¡Activo validado y empaquetado para OCI!")
                    st.json(payload)
                
                if rechazar:
                    st.error("❌ Activo descartado.")
