import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from io import BytesIO

# --- Dipendenze per il Report PDF ---
from reportlab.lib.pagesizes import A4
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(layout="wide", page_title="Risk Management Dashboard", initial_sidebar_state="expanded")

# —————————————————————————————
# 1) DB & HELPERS
# —————————————————————————————
DB_PATH = Path("app.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # ... (il resto della funzione init_db rimane invariato)
    c.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('read','modify','admin'))
      )
    """)
    c.execute("SELECT 1 FROM users WHERE username = ?", ("Flavio",))
    if not c.fetchone():
        c.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", ("Flavio","Dashboard2003","admin"))
    c.execute("""
      CREATE TABLE IF NOT EXISTS risks (
        id INTEGER PRIMARY KEY,
        data_inizio TEXT NOT NULL,
        data_fine TEXT NOT NULL,
        fornitore TEXT NOT NULL,
        rischio TEXT NOT NULL,
        stato TEXT NOT NULL CHECK(stato IN ('aperto','chiuso')),
        gravita TEXT NOT NULL CHECK(gravita IN ('Low','Hight','Critical')),
        note TEXT,
        data_chiusura TEXT,
        contract_owner TEXT NOT NULL,
        area_riferimento TEXT NOT NULL,
        perc_avanzamento INTEGER NOT NULL DEFAULT 0
      )
    """)
    conn.commit()
    conn.close()

init_db()
conn = get_connection()

def load_users():
    return pd.read_sql_query("SELECT * FROM users", conn)

def load_risks_df():
    return pd.read_sql_query(
        "SELECT * FROM risks ORDER BY id DESC",
        conn,
        parse_dates=["data_inizio","data_fine","data_chiusura"]
    )

# —————————————————————————————
# 2) SESSION_STATE INIT
# —————————————————————————————
# Aggiunto 'last_activity' per il timeout
for key, val in [("authenticated", False), ("username", ""), ("role", ""), ("page", "Dashboard"), ("last_activity", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# —————————————————————————————
# 3) STILE GRAFICO (CSS con Tema Scuro Fisso)
# —————————————————————————————
def set_page_style():
    bg_color, sidebar_bg_color, text_color = "#000000", "#0F172A", "#FFFFFF"
    css = f"""
    <style>
        .st-emotion-cache-18ni7ap, .st-emotion-cache-h4xjwg {{ display: none; }}
        .stApp {{ background-color: {bg_color}; color: {text_color}; }}
        [data-testid="stSidebar"] {{
            background-color: {sidebar_bg_color};
            border-right: 1px solid rgba(148, 163, 184, 0.2);
        }}
        [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
        h1, h2, h3, p, label, .st-emotion-cache-16txtl3, .st-emotion-cache-qbe2hs, .st-emotion-cache-aw8l5d, .st-emotion-cache-bm2z3a {{
             color: {text_color} !important; 
        }}
        [data-testid="stToolbar"] {{ display: none !important; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# —————————————————————————————
# 4) LOGIN, LOGOUT & GESTIONE SESSIONE
# —————————————————————————————
def do_login(user, pwd):
    row = conn.execute("SELECT role FROM users WHERE username=? AND password=?", (user, pwd)).fetchone()
    if row:
        st.session_state.update(
            authenticated=True,
            username=user,
            role=row["role"],
            page="Dashboard",
            last_activity=datetime.now() # Registra l'ora del login
        )
        return True
    return False

def do_logout(message="Logout effettuato con successo."):
    st.session_state.update(authenticated=False, username="", role="", page="Login", last_activity=None)
    st.info(message)

set_page_style()

# Pagina di Login
if not st.session_state.authenticated:
    st.title("Risk Management Dashboard")
    st.markdown("---")
    col1, col2 = st.columns([1, 1], gap="large")
    with col1:
        st.subheader("Benvenuto")
        st.markdown("""
        Questa applicazione è uno strumento completo per il censimento, la gestione e il monitoraggio dei rischi associati ai fornitori. 
        Permette di centralizzare le informazioni, analizzare i dati attraverso una dashboard interattiva e generare report dettagliati.
        """)
        st.subheader("Funzionalità Principali")
        # MODIFICA: Descrizioni generiche visibili a tutti
        with st.expander("📊 Dashboard"):
            st.write("Visualizza i dati dei rischi in forma aggregata tramite grafici interattivi. Puoi filtrare i dati per un'analisi mirata.")
        with st.expander("📄 Report PDF"):
            st.write("Genera report professionali in formato PDF, con grafici di sintesi e dettagli strutturati, ideali per la condivisione e l'archiviazione.")
        with st.expander("⚙️ Gestione Dati"):
            st.write("Gli utenti autorizzati possono inserire nuovi rischi e modificare i record esistenti per mantenere il database sempre aggiornato.")
    with col2:
        st.subheader("Login")
        with st.form("login_form"):
            user = st.text_input("Username")
            pwd  = st.text_input("Password", type="password")
            if st.form_submit_button("Entra", use_container_width=True):
                if do_login(user, pwd):
                    st.rerun()
                else:
                    st.error("Credenziali errate")
    st.stop()

# --- GESTIONE TIMEOUT SESSIONE (solo per utenti loggati) ---
if st.session_state.authenticated:
    if st.session_state.last_activity:
        timeout_seconds = 30 * 60  # 30 minuti
        elapsed_time = (datetime.now() - st.session_state.last_activity).total_seconds()
        if elapsed_time > timeout_seconds:
            do_logout(message="Sessione scaduta per inattività. Effettua nuovamente il login.")
            st.rerun()
        else:
            # Aggiorna il timestamp ad ogni interazione
            st.session_state.last_activity = datetime.now()
    else:
        # Se per qualche motivo manca il timestamp, forza il logout
        do_logout(message="Errore di sessione. Effettua nuovamente il login.")
        st.rerun()


# --- SIDEBAR (solo per utenti loggati) ---
with st.sidebar:
    st.title("Risk Dashboard")
    st.markdown(f"Benvenuto, **{st.session_state.username}**!")
    st.markdown(f"Ruolo: `{st.session_state.role}`")
    st.markdown("---")
    
    base_menu, modify_menu, admin_menu = ["Dashboard", "Report PDF"], ["Censimento Fornitori", "Modifica"], ["Admin"]
    final_menu = base_menu.copy()
    if st.session_state.role in ['modify', 'admin']: final_menu.extend(modify_menu)
    if st.session_state.role == 'admin': final_menu.extend(admin_menu)

    for item in final_menu:
        if st.button(item, key=f"menu_{item}"):
            st.session_state.page = item
            st.rerun() # Rerun per cambiare pagina
    
    st.markdown("---")
    if st.button("🔓 Logout"):
        do_logout()
        st.rerun()

# —————————————————————————————
# 5) ROUTING E CONTENUTO DELLE PAGINE
# —————————————————————————————
df = load_risks_df()
page = st.session_state.page
st.title(page)

if page == "Dashboard":
    st.subheader("Riepilogo Rapido")
    total, open_r, closed = len(df), len(df[df['stato'] == 'aperto']), len(df[df['stato'] == 'chiuso'])
    c1, c2, c3 = st.columns(3)
    c1.metric("Rischi Totali", total); c2.metric("Rischi Aperti", open_r); c3.metric("Rischi Chiusi", closed)
    st.markdown("---")
    c1, c2 = st.columns([1, 3])
    with c1:
        st.subheader("Filtri")
        sup_opts, default_stati = ["Tutti"] + sorted(df["fornitore"].unique().tolist()), ["aperto", "chiuso"]
        sel_sup = st.selectbox("Fornitore", sup_opts)
        sel_stati = st.multiselect("Stato", default_stati, default=default_stati)
    dff = df[df["stato"].isin(sel_stati)]
    if sel_sup != "Tutti": dff = dff[dff["fornitore"] == sel_sup]
    with c2:
        st.subheader("Grafici di Riepilogo")
        if dff.empty: st.warning("Nessun dato da visualizzare con i filtri correnti.")
        else:
            gc1, gc2 = st.columns(2)
            # ... (contenuto dei grafici invariato)
            with gc1:
                agg_bar = dff.groupby("stato").size().reset_index(name="count")
                fig_bar = px.bar(agg_bar, x="stato", y="count", color="stato", labels={"stato": "Stato", "count": "Numero"}, title="Conteggio per Stato")
                st.plotly_chart(fig_bar, use_container_width=True)
            with gc2:
                agg_pie = dff.groupby("gravita").size().reset_index(name="count")
                fig_pie = px.pie(agg_pie, values="count", names="gravita", hole=0.4, title="Ripartizione per Gravità", color="gravita", color_discrete_map={"Critical": "#d9534f", "Hight": "#f0ad4e", "Low": "#5cb85c"})
                st.plotly_chart(fig_pie, use_container_width=True)
    st.subheader("Dati in Dettaglio")
    st.dataframe(dff, use_container_width=True)


elif page == "Censimento Fornitori":
    # ... (contenuto del censimento invariato)
    with st.form("form_ins", clear_on_submit=True):
        st.subheader("Censimento Nuovo Rischio Fornitore")
        c1, c2 = st.columns(2)
        with c1:
            fornitore, contract_owner, area_riferimento = st.text_input("Nome fornitore"), st.text_input("Contract Owner"), st.text_input("Area di riferimento")
            gravita = st.selectbox("Livello di gravità", ["Low","Hight","Critical"])
        with c2:
            rischio = st.selectbox("Scenario di rischio", ["-- seleziona --", "Inadeguate Security of third party", "Inadeguate resilience of third party", "Inadequate outsourcing of third party"])
            stato = st.radio("Stato", ["aperto","chiuso"], horizontal=True)
            data_inizio, data_fine = st.date_input("Data inizio", value=datetime.today()), st.date_input("Due Date", value=datetime.today())
            data_chiusura = st.date_input("Data di chiusura effettiva", value=datetime.today()) if stato == "chiuso" else None
        perc_avanzamento = st.slider("Percentuale di avanzamento (%)", 0, 100, 0)
        note = st.text_area("Note libere")
        if st.form_submit_button("Salva Rischio", use_container_width=True):
            if not all([fornitore, contract_owner, area_riferimento]) or rischio.startswith("--"): st.error("Compila tutti i campi obbligatori.")
            else:
                conn.execute("""INSERT INTO risks(data_inizio,data_fine,fornitore,rischio,stato,gravita,note,data_chiusura,contract_owner,area_riferimento,perc_avanzamento) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", 
                             (data_inizio.isoformat(), data_fine.isoformat(), fornitore, rischio, stato, gravita, note, data_chiusura.isoformat() if data_chiusura else None, contract_owner, area_riferimento, perc_avanzamento))
                conn.commit()
                st.success("Rischio inserito.")

elif page == "Modifica":
    # ... (contenuto della modifica invariato)
    st.info("In questa sezione puoi modificare i dati esistenti. L'aggiunta di nuove righe è disabilitata.")
    sup_opts = ["Tutti"] + sorted(df["fornitore"].unique().tolist())
    sel = st.selectbox("Filtra Fornitore per modificare", sup_opts, key="modifica_sel")
    dff_original = df.copy()
    if sel != "Tutti":
        dff_original = dff_original[dff_original["fornitore"] == sel]
    edited_df = st.data_editor(dff_original, num_rows="static", use_container_width=True,
        column_config={"id": st.column_config.NumberColumn("ID", disabled=True), "data_fine": st.column_config.DateColumn("Due Date", format="YYYY-MM-DD")},
        key="data_editor_modifica")
    if st.button("Salva Modifiche", use_container_width=True):
        try:
            original_to_compare = dff_original.set_index('id')
            edited_to_compare = edited_df.set_index('id')
            diff_df = original_to_compare.compare(edited_to_compare)
            if diff_df.empty:
                st.toast("Nessuna modifica da salvare.")
            else:
                ids_to_update = diff_df.index.get_level_values('id').unique()
                for row_id in ids_to_update:
                    row_to_update = edited_to_compare.loc[row_id]
                    data_tuple = (
                        row_to_update["data_inizio"].isoformat() if pd.notna(row_to_update["data_inizio"]) else None,
                        row_to_update["data_fine"].isoformat() if pd.notna(row_to_update["data_fine"]) else None,
                        row_to_update["fornitore"], row_to_update["rischio"], row_to_update["stato"], row_to_update["gravita"], row_to_update["note"],
                        row_to_update["data_chiusura"].isoformat() if pd.notna(row_to_update["data_chiusura"]) else None,
                        row_to_update["contract_owner"], row_to_update["area_riferimento"], int(row_to_update["perc_avanzamento"]), int(row_id))
                    conn.execute("""UPDATE risks SET data_inizio=?, data_fine=?, fornitore=?, rischio=?, stato=?, gravita=?, note=?, data_chiusura=?, contract_owner=?, area_riferimento=?, perc_avanzamento=? WHERE id=?""", data_tuple)
                conn.commit()
                st.success(f"Salvate {len(ids_to_update)} modifiche.")
                st.rerun()
        except Exception as e:
            st.error(f"Errore durante il salvataggio: {e}")

elif page == "Report PDF":
    # ... (contenuto del report invariato, con la sua funzione build_advanced_pdf)
    st.info("Genera un report PDF avanzato con grafici di sintesi e dettagli strutturati per ogni rischio.")
    # ... (tutta la logica dei filtri e del pulsante di download)
    st.subheader("1. Seleziona il Perimetro del Report")
    all_suppliers, default_stati, default_gravita = sorted(df["fornitore"].unique().tolist()), list(df["stato"].unique()), list(df["gravita"].unique())
    sel_suppliers = st.multiselect("Filtro Fornitore/i (lascia vuoto per tutti)", all_suppliers)
    c1, c2 = st.columns(2)
    with c1: sel_stati = st.multiselect("Filtro Stato", default_stati, default=default_stati)
    with c2: sel_gravita = st.multiselect("Filtro Gravità", default_gravita, default=default_gravita)
    dff = df.copy()
    if sel_suppliers: dff = dff[dff["fornitore"].isin(sel_suppliers)]
    dff = dff[dff["stato"].isin(sel_stati) & dff["gravita"].isin(sel_gravita)]
    st.markdown("---")
    st.subheader("2. Anteprima Dati e Generazione PDF")
    if dff.empty: st.warning("Nessun dato corrisponde ai filtri selezionati.")
    else:
        st.write(f"**{len(dff)} record selezionati** per il report.")
        st.dataframe(dff.head(), use_container_width=True)
        if st.button("🚀 Genera Report PDF Avanzato", use_container_width=True):
            # (la funzione build_advanced_pdf va qui)
            pass

elif page == "Admin":
    # ... (contenuto della pagina admin invariato)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Elenco Utenti")
        users_df = load_users()[["id", "username", "role"]]
        st.dataframe(users_df, use_container_width=True)
    with c2:
        with st.form("form_user", clear_on_submit=True):
            st.subheader("Crea Nuovo Utente")
            # ... (form)
        st.markdown("---")
        with st.form("delete_user", clear_on_submit=True):
            st.subheader("Elimina Utente")
            # ... (form)
            pass
