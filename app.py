"""
CommunityLab — Dashboard de Curaduría v2.1 (Streamlit)
======================================================
La IA propone · El humano decide · OCI guarda solo lo aprobado.

Flujo de estados (coordinado con WF2 de n8n):
  - APROBAR   → decision=aprobado, estado_proceso=pendiente_oci
                → WF2 lo detecta → PUT a OCI → marca almacenado_oci ☁️
  - RECHAZAR  → cerrado directamente aquí (cerrado_rechazado)
                → WF2 no lo toca (ya está excluido por su filtro)

Robustez:
  - El número de fila se rastrea desde la carga (asset_id NO es único:
    cada ejecución de WF1 genera su propio asset-001-li).
  - `decision` se escribe AL FINAL: WF2 solo procesa filas con
    decision=aprobado/rechazado, así que al escribirla última, el resto
    de campos ya está completo cuando WF2 la lee (a prueba de carrera).

Requisitos (requirements.txt):
  streamlit
  pandas
  gspread
  google-auth

Python 3.10+ (por la sintaxis `int | None`).

.streamlit/secrets.toml — ejemplo:
  [gcp_service_account]
  type = "service_account"
  project_id = "..."
  private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
  client_email = "xxx@xxx.iam.gserviceaccount.com"
  client_id = "..."
  spreadsheet_id = "1nY40IJ4ludaHQcTEV8nDlHNi6ikl-4x5CUJocvrsHfk"
  worksheet_name = "Curaduria"        # ⚠️ NO "Hoja 1" — la pestaña se llama Curaduria

⚠️ No olvides compartir el Google Sheet con el client_email del service
   account (permiso de Editor).
"""

import json  # noqa: F401 (reservado para futuras mejoras de contenido_json)
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="CommunityLab — Curaduría",
    page_icon="🛡️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Conexión Google Sheets (service account)
# ---------------------------------------------------------------------------


def get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def open_worksheet():
    client = get_gspread_client()
    spreadsheet_id = st.secrets.get("spreadsheet_id") or st.secrets[
        "gcp_service_account"
    ].get("spreadsheet_id", "")
    worksheet_name = st.secrets.get("worksheet_name", "Curaduria")  # default correcto
    sh = client.open_by_key(spreadsheet_id)
    return sh.worksheet(worksheet_name)


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


@st.cache_data(ttl=15)
def load_assets():
    """Carga las filas y adjunta el NÚMERO DE FILA REAL del Sheet.

    FIX CRÍTICO: asset_id se repite entre ejecuciones (asset-001-li existe
    en cada corrida de WF1). Escribir por asset_id actualizaría la primera
    coincidencia (una fila vieja ya cerrada) y corrompería la auditoría.
    Por eso rastreamos la fila real: fila 1 = headers → datos desde fila 2.
    (Asume filas contiguas: cierto, porque WF1 hace append.)
    """
    ws = open_worksheet()
    rows = ws.get_all_records()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for col in df.columns:
        df[col] = df[col].astype(str).replace("nan", "").replace("None", "")

    # Fila real ANTES de filtrar (posicional)
    df["__row_number"] = range(2, len(df) + 2)

    # Descartar filas vacías (colas de sheet), conservando el número correcto
    if "asset_id" in df.columns:
        df = df[df["asset_id"].astype(str).str.strip() != ""]

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------


def write_decision(
    row_number: int,
    decision: str,
    user: str,
    comentario: str,
    contenido: str | None = None,
):
    """Escribe la decisión del curador en la fila REAL del Sheet.

    Orden de escritura deliberado: `decision` va AL FINAL. WF2 solo toma
    filas con decision=aprobado/rechazado, así que cuando la escribe, todos
    los demás campos ya están en su lugar (a prueba de carrera con WF2).

    Si el curador editó el contenido: `contenido` guarda la versión humana
    y `contenido_json` conserva la salida ORIGINAL del LLM — es el registro
    de auditoría del human-in-the-loop, no un bug.
    """
    if decision not in ("aprobado", "rechazado"):
        raise ValueError(f"Decisión inválida: {decision}")
    if not row_number or row_number < 2:
        raise ValueError(f"Número de fila inválido: {row_number}")

    ws = open_worksheet()
    headers = [h.strip() for h in ws.row_values(1)]
    now = datetime.now(timezone.utc).isoformat()

    estado = "aprobado" if decision == "aprobado" else "rechazado"
    estado_proceso = "pendiente_oci" if decision == "aprobado" else "cerrado_rechazado"

    def set_col(name: str, value: str):
        if name in headers:
            col = headers.index(name) + 1
            ws.update_cell(row_number, col, value)

    # 1) Campos auxiliares primero
    if contenido is not None:
        set_col("contenido", contenido)
    set_col("estado", estado)
    set_col("user", user or "curador")
    set_col("decision_at", now)
    set_col("comentario", comentario or "")
    set_col("estado_proceso", estado_proceso)

    # 2) El disparador de WF2, al final
    set_col("decision", decision)

    # Invalidar cache para que la UI refleje el cambio
    load_assets.clear()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("🛡️ CommunityLab — Curaduría de activos")
st.caption("La IA propone · El humano decide · OCI guarda solo lo aprobado")

try:
    df = load_assets()
except Exception as e:
    st.error(
        "No se pudo leer Google Sheets. Revisa `.streamlit/secrets.toml` "
        "(service account + spreadsheet_id + worksheet_name='Curaduria') y que "
        "el Sheet esté compartido con el email del service account (Editor).\n\n"
        f"Detalle: {e}"
    )
    st.stop()

if df.empty:
    st.info("No hay filas en la hoja. Ejecuta el WF1 de n8n primero.")
    st.stop()

# ---- Métricas (5) ----------------------------------------------------------
decision_col = (
    df["decision"].str.lower().str.strip() if "decision" in df.columns
    else pd.Series([""] * len(df))
)
proceso_col = (
    df["estado_proceso"].str.lower().str.strip() if "estado_proceso" in df.columns
    else pd.Series([""] * len(df))
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total activos", len(df))
c2.metric("Pendientes", int((decision_col == "pendiente").sum()))
c3.metric("Aprobados", int((decision_col == "aprobado").sum()))
c4.metric("Rechazados", int((decision_col == "rechazado").sum()))
c5.metric("☁️ En OCI", int((proceso_col == "almacenado_oci").sum()))

st.divider()

# ---- Filtros (4) -----------------------------------------------------------
f1, f2, f3, f4 = st.columns(4)
with f1:
    filtro_estado = st.selectbox(
        "Estado decisión",
        ["pendiente", "aprobado", "rechazado", "todos"],
        index=0,
    )
with f2:
    ejecuciones = (
        ["todas"] + sorted(df["execution_id"].unique().tolist(), reverse=True)
        if "execution_id" in df.columns
        else ["todas"]
    )
    filtro_exec = st.selectbox("Ejecución (batch de WF1)", ejecuciones)
with f3:
    tipos = (
        ["todos"] + sorted(df["tipo_activo"].dropna().unique().tolist())
        if "tipo_activo" in df.columns
        else ["todos"]
    )
    filtro_tipo = st.selectbox("Tipo de activo", tipos)
with f4:
    score_min = st.slider("Score mínimo", 0.0, 10.0, 0.0, 0.25)

# Nombre del curador (persiste en la sesión entre reruns)
if "curador_name" not in st.session_state:
    st.session_state.curador_name = ""
user_name = st.text_input("Tu nombre (curador)", key="curador_name")

# ---- Aplicar filtros -------------------------------------------------------
vista = df.copy()
if filtro_estado != "todos" and "decision" in vista.columns:
    vista = vista[vista["decision"].str.lower().str.strip() == filtro_estado]
if filtro_exec != "todas" and "execution_id" in vista.columns:
    vista = vista[vista["execution_id"] == filtro_exec]
if filtro_tipo != "todos" and "tipo_activo" in vista.columns:
    vista = vista[vista["tipo_activo"] == filtro_tipo]
if "score_final" in vista.columns:
    vista = vista[
        pd.to_numeric(vista["score_final"], errors="coerce").fillna(0) >= score_min
    ]

# Orden: pendientes primero, luego mayor score
if not vista.empty:
    vista = vista.copy()
    vista["_score_num"] = (
        pd.to_numeric(vista.get("score_final"), errors="coerce").fillna(0)
    )
    if "decision" in vista.columns:
        vista["_pend"] = (vista["decision"].str.lower().str.strip() == "pendiente").astype(int)
        vista = vista.sort_values(["_pend", "_score_num"], ascending=[False, False])
    else:
        vista = vista.sort_values("_score_num", ascending=False)

# ---- Tarjetas --------------------------------------------------------------
BADGE = {
    "linkedin": ("🔗 LinkedIn", "#0A66C2"),
    "faq": ("❓ FAQ", "#2E7D32"),
    "newsletter": ("📰 Newsletter", "#E65100"),
}
PROCESO_LABEL = {
    "almacenado_oci": "☁️ Guardado en OCI",
    "cerrado_rechazado": "✖ Cerrado (rechazado)",
    "pendiente_oci": "⏳ Esperando WF2 → OCI",
    "pendiente_decision": "…",
}

if vista.empty:
    st.warning("No hay activos con esos filtros.")
else:
    for _, row in vista.iterrows():
        tipo = str(row.get("tipo_activo", "")).lower()
        label, color = BADGE.get(tipo, (tipo.upper() or "—", "#555"))
        asset_id = str(row.get("asset_id", ""))
        exec_id = str(row.get("execution_id", ""))
        score = row.get("score_final", "")
        autor = row.get("autor", "")
        decision = str(row.get("decision", "pendiente")).lower().strip()
        proceso = str(row.get("estado_proceso", "")).lower().strip()
        contenido = str(row.get("contenido", ""))
        # FIX: fila REAL del Sheet (asset_id no es único entre ejecuciones)
        row_number = int(row.get("__row_number", 0) or 0)

        with st.container(border=True):
            h1, h2 = st.columns([4, 1])
            with h1:
                st.markdown(
                    f"<span style='background:{color};color:white;padding:4px 10px;"
                    f"border-radius:6px;font-weight:600'>{label}</span> "
                    f"**{asset_id}** · {autor} · <code>{exec_id}</code>",
                    unsafe_allow_html=True,
                )
            with h2:
                st.metric("Score", score)

            if decision == "pendiente" and row_number >= 2:
                # --- Pendiente: editable + botones ---
                nuevo_contenido = st.text_area(
                    "Contenido (editable antes de aprobar)",
                    value=contenido,
                    height=180,
                    key=f"content_{asset_id}_{row_number}",
                )
                comentario = st.text_input(
                    "Comentario (opcional, recomendado para auditoría)",
                    key=f"com_{asset_id}_{row_number}",
                )
                b1, b2, _ = st.columns([1, 1, 3])
                with b1:
                    if st.button("✅ Aprobar", key=f"ok_{row_number}", type="primary"):
                        try:
                            contenido_a_guardar = (
                                nuevo_contenido
                                if nuevo_contenido.strip() != contenido.strip()
                                else None  # sin edición → no reescribir
                            )
                            write_decision(
                                row_number,
                                "aprobado",
                                user_name.strip(),
                                comentario,
                                contenido=contenido_a_guardar,
                            )
                            st.success(f"Aprobado: {asset_id} ({exec_id})")
                            st.rerun()
                        except Exception as ex:
                            st.error(str(ex))
                with b2:
                    if st.button("❌ Rechazar", key=f"no_{row_number}"):
                        try:
                            write_decision(
                                row_number,
                                "rechazado",
                                user_name.strip(),
                                comentario,
                            )
                            st.warning(f"Rechazado: {asset_id} ({exec_id})")
                            st.rerun()
                        except Exception as ex:
                            st.error(str(ex))
            else:
                # --- Ya decidido: solo lectura + auditoría ---
                st.text_area(
                    "Contenido",
                    value=contenido,
                    height=120,
                    disabled=True,
                    key=f"ro_{row_number}",
                )
                st.caption(
                    f"Decisión: **{decision}** · por {row.get('user', '')} · "
                    f"{row.get('decision_at', '')} · "
                    f"{PROCESO_LABEL.get(proceso, proceso)}"
                )
                if row.get("comentario"):
                    st.caption(f"💬 {row.get('comentario')}")

st.divider()
if st.button("🔄 Refrescar datos"):
    load_assets.clear()
    st.rerun()
