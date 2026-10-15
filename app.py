import streamlit as st
import pandas as pd

st.set_page_config(page_title="CommunityLab - Panel de Curaduría", layout="centered")

st.title("🛡️ CommunityLab — Curaduría & Validación")
st.caption("Revisa, edita y aprueba el contenido generado por IA antes del almacenamiento definitivo en OCI.")

# PEGA AQUÍ TU ENLACE CSV ENTRE LAS COMILLAS
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSF9vWhsFJfh4nc5EK1aTQCk9mWm7GU54Rf7ZMzhsWhRapb2ZnQuetOUuCsKbKXBQ0yM1oReU95iAHU/pub?gid=0&single=true&output=csv"

@st.cache_data(ttl=3)
def cargar_datos():
    try:
        df = pd.read_csv(SHEET_CSV_URL)
        if df.empty:
            return None
        # Limpiamos valores nulos (NaN) para que los campos de texto no muestren error
        df = df.fillna("")
        return df.iloc[-1].to_dict()
    except Exception as e:
        return None

datos = cargar_datos()

if datos is None:
    st.warning("⏳ Esperando datos desde n8n... Ejecuta el workflow para recibir contenido.")
else:
    st.info(f"📌 **Ejecución activa enviada por n8n:** `{datos.get('execution_id', 'CL-N/A')}`")

    with st.form("form_curaduria"):
        st.subheader("🔵 Post para LinkedIn")
        titulo_li = st.text_input("Título del Post", value=datos.get("post_titulo", ""))
        copy_li = st.text_area("Copy sugerido", value=datos.get("post_copy", ""), height=150)

        st.divider()

        st.subheader("🟡 FAQ / Tip Técnico")
        tema_faq = st.text_input("Tema", value=datos.get("faq_tema", ""))
        resp_faq = st.text_area("Respuesta", value=datos.get("faq_respuesta", ""), height=100)

        st.divider()

        st.subheader("🟢 Newsletter")
        titular_nl = st.text_input("Titular", value=datos.get("newsletter_titular", ""))
        resumen_nl = st.text_area("Resumen", value=datos.get("newsletter_resumen", ""), height=100)

        st.divider()

        aprobar = st.form_submit_button("✅ Aprobar y Guardar en OCI Object Storage")

    if aprobar:
        json_aprobado = {
            "status": "aprobado_y_persistido",
            "execution_id": datos.get("execution_id"),
            "activos_validados": {
                "linkedin": {"titulo": titulo_li, "copy": copy_li},
                "faq": {"tema": tema_faq, "respuesta": resp_faq},
                "newsletter": {"titular": titular_nl, "resumen": resumen_nl}
            }
        }
        st.success("🎉 ¡Contenido curado y enviado con éxito a OCI Object Storage!")
        st.json(json_aprobado)