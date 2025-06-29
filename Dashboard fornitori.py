# app.py - VERSIONE AGGIORNATA PER DEPLOYMENT

import streamlit as st
import pandas as pd
import plotly.express as px
# import sqlite3 # Non più necessario per la connessione principale
import libsql_client # Nuovo client per Turso
from pathlib import Path
from datetime import datetime
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

# La connessione ora punta a Turso DB usando le credenziali in st.secrets
def get_connection():
    # Carica le credenziali dai segreti di Streamlit
    url = st.secrets["DB_URL"]
    auth_token = st.secrets["DB_AUTH_TOKEN"]
    
    # Crea una connessione sincrona
    # check_same_thread=False non è necessario con questo client
    conn = libsql_client.create_client_sync(url=url, auth_token=auth_token)
    return conn

def execute_query(query, params=()):
    conn = get_connection()
    try:
        # libsql_client usa un'API leggermente diversa.
        # .execute() restituisce un ResultSet.
        result_set = conn.execute(query, params)
        
        # Per le query SELECT, convertiamo il risultato in un DataFrame pandas.
        if query.strip().upper().startswith("SELECT"):
            columns = [col for col in result_set.columns]
            data = [list(row) for row in result_set.rows]
            return pd.DataFrame(data, columns=columns)
        
        # Per INSERT, UPDATE, DELETE, etc., non c'è bisogno di restituire dati.
        # Possiamo committare (anche se l'autocommit è spesso predefinito)
        conn.sync() # Assicura che le scritture siano inviate
        return None # Indica successo
    finally:
        conn.close()

def init_db():
    conn = get_connection()
    try:
        # Le tabelle vengono create solo se non esistono già
        conn.batch([
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('read','modify','admin'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS risks (
                id INTEGER PRIMARY KEY, data_inizio TEXT NOT NULL, data_fine TEXT NOT NULL, fornitore TEXT NOT NULL,
                rischio TEXT NOT NULL, stato TEXT NOT NULL, gravita TEXT NOT NULL, note TEXT, data_chiusura TEXT,
                contract_owner TEXT NOT NULL, area_riferimento TEXT NOT NULL, perc_avanzamento INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY, fornitore_nome TEXT NOT NULL, data_invio TEXT NOT NULL,
                stato_reminder TEXT NOT NULL CHECK(stato_reminder IN ('Attivo', 'Risposto')),
                note TEXT, test_bc INTEGER NOT NULL DEFAULT 0, test_it INTEGER NOT NULL DEFAULT 0,
                test_pt_va INTEGER NOT NULL DEFAULT 0, access_review INTEGER NOT NULL DEFAULT 0, ppt INTEGER NOT NULL DEFAULT 0
            )
            """
        ])
        
        # Controlla se l'utente admin esiste e inseriscilo se necessario
        result = conn.execute("SELECT 1 FROM users WHERE username = ?", ("Flavio",))
        if len(result.rows) == 0:
            conn.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", ("Flavio","Dashboard2003","admin"))
        
        conn.sync() # Sincronizza tutte le modifiche
    finally:
        conn.close()

# Inizializza il DB all'avvio dell'app
init_db()

# Funzioni di caricamento dati aggiornate per usare execute_query
def load_users():
    return execute_query("SELECT * FROM users")

def load_risks_df():
    df = execute_query("SELECT * FROM risks ORDER BY id DESC")
    # Converte manualmente le colonne data
    for col in ["data_inizio", "data_fine", "data_chiusura"]:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    return df

def load_reminders_df():
    df_reminders = execute_query("SELECT * FROM reminders ORDER BY data_invio ASC")
    if not df_reminders.empty:
        df_reminders["data_invio"] = pd.to_datetime(df_reminders["data_invio"], errors='coerce')
        today = pd.to_datetime(datetime.now().date())
        df_reminders['giorni_trascorsi'] = (today - df_reminders['data_invio']).dt.days
        df_reminders['giorni_al_reminder'] = (5 - df_reminders['giorni_trascorsi']).clip(lower=0)
    return df_reminders
    
# Funzioni di modifica dati aggiornate
def db_write(query, params=()):
    conn = get_connection()
    try:
        conn.execute(query, params)
        conn.sync()
    finally:
        conn.close()

# —————————————————————————————
# 2) SESSION_STATE INIT
# (Nessuna modifica qui)
# —————————————————————————————
for key, val in [("authenticated", False), ("username", ""), ("role", ""), ("page", "Dashboard"), ("last_activity", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# —————————————————————————————
# 3) STILE GRAFICO
# (Nessuna modifica qui)
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
        .stDataFrame, .stDataEditor {{
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid rgba(148, 163, 184, 0.2);
        }}
        [data-testid="stDataFrame"] thead th, [data-testid="stDataEditor-header"] {{
            background-color: #1E293B;
            color: white;
            font-weight: bold;
            text-transform: uppercase;
            font-size: 14px;
        }}
        [data-testid="stDataFrame"] tbody tr, [data-testid="stDataEditor-row"] {{
            background-color: transparent;
        }}
        [data-testid="stDataFrame"] tbody tr:nth-child(even), [data-testid="stDataEditor-row"]:nth-child(even) {{
            background-color: rgba(45, 55, 72, 0.5);
        }}
        [data-testid="stDataFrame"] td, [data-testid="stDataEditor-cell"] {{
            color: #E2E8F0;
            border-color: rgba(148, 163, 184, 0.2) !important;
        }}
        div[data-testid="stDataFrame"] div[role="grid"], div[data-testid="stDataEditor"] div[role="grid"] {{
            scrollbar-color: #4A5568 #2D3748;
            scrollbar-width: thin;
        }}
        div[data-testid="stDataFrame"] div[role="grid"]::-webkit-scrollbar, div[data-testid="stDataEditor"] div[role="grid"]::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        div[data-testid="stDataFrame"] div[role="grid"]::-webkit-scrollbar-track, div[data-testid="stDataEditor"] div[role="grid"]::-webkit-scrollbar-track {{
            background: #2D3748;
        }}
        div[data-testid="stDataFrame"] div[role="grid"]::-webkit-scrollbar-thumb, div[data-testid="stDataEditor"] div[role="grid"]::-webkit-scrollbar-thumb {{
            background-color: #4A5568;
            border-radius: 10px;
            border: 2px solid #2D3748;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# —————————————————————————————
# 4) LOGIN, LOGOUT & GESTIONE SESSIONE
# —————————————————————————————
def do_login(user, pwd):
    # Modificato per usare il nuovo client
    conn = get_connection()
    try:
        rs = conn.execute("SELECT role FROM users WHERE username=? AND password=?", (user, pwd))
        if len(rs.rows) > 0:
            role = rs.rows[0][0] # Estrai il ruolo dalla prima riga e colonna
            st.session_state.update(authenticated=True, username=user, role=role, page="Dashboard", last_activity=datetime.now())
            return True
        return False
    finally:
        conn.close()

def do_logout(message="Logout effettuato con successo."):
    st.session_state.update(authenticated=False, username="", role="", page="Login", last_activity=None)
    st.info(message)

# DA QUI IN POI, IL CODICE USA LE FUNZIONI DI ALTO LIVELLO (load_risks_df, db_write, etc.)
# QUINDI LE MODIFICHE SONO MINIME, SOLO PER SOSTITUIRE LE CHIAMATE DIRETTE A conn.execute
# CON LA NUOVA FUNZIONE db_write().

set_page_style()

if not st.session_state.authenticated:
    st.title("Risk Management Dashboard")
    st.markdown("---")
    col1, col2 = st.columns([1, 1], gap="large")
    with col1:
        st.subheader("Benvenuto")
        st.markdown("Questa applicazione è uno strumento completo per il censimento, la gestione e il monitoraggio dei rischi e delle comunicazioni con i fornitori.")
        st.subheader("Funzionalità Principali")
        with st.expander("📊 Dashboard"): st.write("Visualizza i dati dei rischi e ricevi notifiche per i reminder scaduti.")
        with st.expander("⚙️ Gestione Dati"): st.write("Gli utenti autorizzati possono inserire, modificare e tracciare rischi e comunicazioni.")
        with st.expander("📄 Report PDF"): st.write("Genera report professionali in formato PDF, ideali per la condivisione.")
    with col2:
        st.subheader("Login")
        with st.form("login_form"):
            user, pwd = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Entra", use_container_width=True):
                if do_login(user, pwd): st.rerun()
                else: st.error("Credenziali errate")
    st.stop()

if st.session_state.authenticated:
    if st.session_state.last_activity:
        if (datetime.now() - st.session_state.last_activity).total_seconds() > 1800:
            do_logout(message="Sessione scaduta per inattività. Effettua nuovamente il login.")
            st.rerun()
        else:
            st.session_state.last_activity = datetime.now()
    else:
        do_logout(message="Errore di sessione. Effettua nuovamente il login.")
        st.rerun()

with st.sidebar:
    st.title("Risk Dashboard")
    st.markdown(f"Benvenuto, **{st.session_state.username}**!")
    st.markdown(f"Ruolo: `{st.session_state.role}`")
    st.markdown("---")
    base_menu, modify_menu, admin_menu = ["Dashboard", "Report PDF"], ["Censimento Fornitori", "Modifica", "Follow-up"], ["Admin"]
    final_menu = base_menu.copy()
    if st.session_state.role in ['modify', 'admin']: final_menu.extend(modify_menu)
    if st.session_state.role == 'admin': final_menu.extend(admin_menu)
    for item in final_menu:
        if st.button(item, key=f"menu_{item}"):
            st.session_state.page = item
            st.rerun()
    st.markdown("---")
    if st.button("🔓 Logout"):
        do_logout()
        st.rerun()

# —————————————————————————————
# 5) ROUTING DELLE PAGINE
# —————————————————————————————
page = st.session_state.page
st.title(page)

# ... (Il resto del codice rimane quasi identico, ma le chiamate a conn.execute e conn.commit
# devono essere sostituite con la nuova funzione db_write)

if page == "Dashboard":
    # (Nessuna modifica, usa load_risks_df)
    df_risks = load_risks_df()
    df_reminders = load_reminders_df()

    st.subheader("Reminder Scaduti (5+ giorni)")
    if not df_reminders.empty and 'giorni_trascorsi' in df_reminders.columns:
        reminders_scaduti = df_reminders[(df_reminders['giorni_trascorsi'] >= 5) & (df_reminders['stato_reminder'] == 'Attivo')]
    else:
        reminders_scaduti = pd.DataFrame() 

    if reminders_scaduti.empty:
        st.success("✔️ Nessun reminder scaduto. Ottimo lavoro!")
    else:
        for _, row in reminders_scaduti.iterrows():
            st.warning(f"⚠️ **{row['fornitore_nome']}**: Sono passati **{row['giorni_trascorsi']} giorni** dall'invio dell'email. Controllare le risposte.")
    
    st.markdown("---")
    st.subheader("Riepilogo Rapido Rischi")
    total, open_r, closed = len(df_risks), len(df_risks[df_risks['stato'] == 'aperto']), len(df_risks[df_risks['stato'] == 'chiuso'])
    c1, c2, c3 = st.columns(3)
    c1.metric("Rischi Totali", total); c2.metric("Rischi Aperti", open_r); c3.metric("Rischi Chiusi", closed)
    st.markdown("---")

    c1, c2 = st.columns([1, 3])
    with c1:
        st.subheader("Filtri Rischi")
        sup_opts = ["Tutti"] + sorted(df_risks["fornitore"].unique().tolist())
        sel_sup = st.selectbox("Fornitore", sup_opts)
        sel_stati = st.multiselect("Stato", ["aperto", "chiuso"], default=["aperto", "chiuso"])
    dff = df_risks[df_risks["stato"].isin(sel_stati)]
    if sel_sup != "Tutti": dff = dff[dff["fornitore"] == sel_sup]
    with c2:
        st.subheader("Grafici di Riepilogo Rischi")
        if dff.empty: st.warning("Nessun rischio da visualizzare con i filtri correnti.")
        else:
            gc1, gc2 = st.columns(2)
            with gc1:
                fig_bar = px.bar(dff.groupby("stato").size().reset_index(name="count"), x="stato", y="count", color="stato", title="Conteggio Rischi per Stato")
                st.plotly_chart(fig_bar, use_container_width=True)
            with gc2:
                agg_pie = dff.groupby("gravita").size().reset_index(name="count")
                fig_pie = px.pie(agg_pie, values="count", names="gravita", hole=0.4, title="Ripartizione Rischi per Gravità", color_discrete_map={"Critical": "#d9534f", "Hight": "#f0ad4e", "Low": "#5cb85c"})
                st.plotly_chart(fig_pie, use_container_width=True)
    st.subheader("Dettaglio Rischi")
    st.dataframe(dff, use_container_width=True)

elif page == "Follow-up":
    st.info("Traccia le comunicazioni inviate ai fornitori e le evidenze ricevute.")
    with st.expander("➕ Aggiungi Nuovo Reminder", expanded=False):
        with st.form("form_reminder", clear_on_submit=True):
            fornitore_nome = st.text_input("Nome Fornitore o Contatto")
            data_invio = st.date_input("Data di invio email", value=datetime.today())
            if st.form_submit_button("Aggiungi Reminder", use_container_width=True):
                if fornitore_nome:
                    # MODIFICA: Usa db_write
                    db_write("INSERT INTO reminders (fornitore_nome, data_invio, stato_reminder) VALUES (?, ?, 'Attivo')", (fornitore_nome, data_invio.isoformat()))
                    st.success(f"Reminder per {fornitore_nome} aggiunto!"); st.rerun()
                else: st.error("Il nome del fornitore è obbligatorio.")
    st.markdown("---")
    st.subheader("Tracciamento Reminder Attivi")
    df_reminders = load_reminders_df()
    dff_attivi = df_reminders[df_reminders['stato_reminder'] == 'Attivo'].copy()
    if dff_attivi.empty:
        st.success("✔️ Nessun reminder attivo al momento.")
    else:
        edited_reminders = st.data_editor(dff_attivi, column_config={
                "id": None, "fornitore_nome": st.column_config.TextColumn("Fornitore", width="medium"),
                "data_invio": st.column_config.DateColumn("Data Invio", format="DD/MM/YYYY", disabled=True),
                "giorni_trascorsi": st.column_config.NumberColumn("Giorni Trascorsi"),
                "giorni_al_reminder": st.column_config.ProgressColumn("Giorni a Notifica (5)", format="%f", min_value=0, max_value=5),
                "stato_reminder": st.column_config.SelectboxColumn("Stato", options=["Attivo", "Risposto"]),
                "note": st.column_config.TextColumn("Note", width="large"), "test_bc": st.column_config.CheckboxColumn("Test BC"),
                "test_it": st.column_config.CheckboxColumn("Test IT"), "test_pt_va": st.column_config.CheckboxColumn("PT/VA"),
                "access_review": st.column_config.CheckboxColumn("Access Review"), "ppt": st.column_config.CheckboxColumn("PPT"),
            }, use_container_width=True, hide_index=True, key="editor_reminders")
        if st.button("Salva Modifiche Reminder", use_container_width=True):
            try:
                original_to_compare = dff_attivi.set_index('id')
                edited_to_compare = edited_reminders.set_index('id')
                diff_df = original_to_compare.compare(edited_to_compare)
                if diff_df.empty: st.toast("Nessuna modifica da salvare.")
                else:
                    ids_to_update = diff_df.index.get_level_values('id').unique()
                    for row_id in ids_to_update:
                        row_to_update = edited_to_compare.loc[row_id]
                        data_tuple = (row_to_update["fornitore_nome"], row_to_update["stato_reminder"], row_to_update["note"],
                            int(row_to_update["test_bc"]), int(row_to_update["test_it"]), int(row_to_update["test_pt_va"]),
                            int(row_to_update["access_review"]), int(row_to_update["ppt"]), int(row_id))
                        # MODIFICA: Usa db_write
                        db_write("UPDATE reminders SET fornitore_nome=?, stato_reminder=?, note=?, test_bc=?, test_it=?, test_pt_va=?, access_review=?, ppt=? WHERE id=?", data_tuple)
                    st.success(f"Salvate {len(ids_to_update)} modifiche."); st.rerun()
            except Exception as e: st.error(f"Errore durante il salvataggio: {e}")

elif page == "Censimento Fornitori":
    with st.form("form_ins_risks", clear_on_submit=True):
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
                # MODIFICA: Usa db_write
                db_write("INSERT INTO risks(data_inizio,data_fine,fornitore,rischio,stato,gravita,note,data_chiusura,contract_owner,area_riferimento,perc_avanzamento) VALUES(?,?,?,?,?,?,?,?,?,?,?)", 
                             (data_inizio.isoformat(), data_fine.isoformat(), fornitore, rischio, stato, gravita, note, data_chiusura.isoformat() if data_chiusura else None, contract_owner, area_riferimento, perc_avanzamento))
                st.success("Rischio inserito.")

elif page == "Modifica":
    df_risks = load_risks_df()
    st.info("In questa sezione puoi modificare i dati dei rischi esistenti.")
    sup_opts = ["Tutti"] + sorted(df_risks["fornitore"].unique().tolist())
    sel = st.selectbox("Filtra Fornitore per modificare", sup_opts, key="modifica_sel")
    dff_original = df_risks.copy()
    if sel != "Tutti":
        dff_original = dff_original[dff_original["fornitore"] == sel]
    
    # Converti le date in oggetti date per il data_editor, altrimenti darà errore
    dff_original['data_inizio'] = pd.to_datetime(dff_original['data_inizio']).dt.date
    dff_original['data_fine'] = pd.to_datetime(dff_original['data_fine']).dt.date
    dff_original['data_chiusura'] = pd.to_datetime(dff_original['data_chiusura']).dt.date

    edited_df = st.data_editor(dff_original, num_rows="static", use_container_width=True,
        column_config={"id": st.column_config.NumberColumn("ID", disabled=True), "data_fine": st.column_config.DateColumn("Due Date", format="YYYY-MM-DD")},
        key="data_editor_modifica")
        
    if st.button("Salva Modifiche", use_container_width=True):
        try:
            # Re-indicizza per il confronto
            original_to_compare = dff_original.set_index('id')
            edited_to_compare = edited_df.set_index('id')
            diff_df = original_to_compare.compare(edited_to_compare)
            
            if diff_df.empty: st.toast("Nessuna modifica da salvare.")
            else:
                ids_to_update = diff_df.index.get_level_values('id').unique()
                for row_id in ids_to_update:
                    row_to_update = edited_to_compare.loc[row_id]
                    # Funzione helper per convertire in isoformat solo se non è NaT
                    def to_iso_or_none(date_obj):
                        if pd.isna(date_obj): return None
                        # Se è un oggetto datetime.date, convertilo in stringa
                        if isinstance(date_obj, datetime.date): return date_obj.isoformat()
                        return None
                    
                    data_tuple = (
                        to_iso_or_none(row_to_update["data_inizio"]),
                        to_iso_or_none(row_to_update["data_fine"]),
                        row_to_update["fornitore"], row_to_update["rischio"], row_to_update["stato"], row_to_update["gravita"], row_to_update["note"],
                        to_iso_or_none(row_to_update["data_chiusura"]),
                        row_to_update["contract_owner"], row_to_update["area_riferimento"], int(row_to_update["perc_avanzamento"]), int(row_id))
                    
                    # MODIFICA: Usa db_write
                    db_write("UPDATE risks SET data_inizio=?, data_fine=?, fornitore=?, rischio=?, stato=?, gravita=?, note=?, data_chiusura=?, contract_owner=?, area_riferimento=?, perc_avanzamento=? WHERE id=?", data_tuple)
                st.success(f"Salvate {len(ids_to_update)} modifiche."); st.rerun()
        except Exception as e: st.error(f"Errore durante il salvataggio: {e}")

# ... La pagina Report PDF non scrive nel DB, quindi non necessita modifiche ...
elif page == "Report PDF":
    df_risks = load_risks_df()
    st.info("Genera un report PDF avanzato con grafici di sintesi e dettagli strutturati per ogni rischio.")
    st.subheader("1. Seleziona il Perimetro del Report")
    all_suppliers, default_stati, default_gravita = sorted(df_risks["fornitore"].unique().tolist()), list(df_risks["stato"].unique()), list(df_risks["gravita"].unique())
    sel_suppliers = st.multiselect("Filtro Fornitore/i", all_suppliers)
    c1, c2 = st.columns(2)
    with c1: sel_stati = st.multiselect("Filtro Stato", default_stati, default=default_stati)
    with c2: sel_gravita = st.multiselect("Filtro Gravità", default_gravita, default=default_gravita)
    dff = df_risks.copy()
    if sel_suppliers: dff = dff[dff["fornitore"].isin(sel_suppliers)]
    dff = dff[dff["stato"].isin(sel_stati) & dff["gravita"].isin(sel_gravita)]
    st.markdown("---")
    st.subheader("2. Anteprima Dati e Generazione PDF")
    if dff.empty: st.warning("Nessun dato corrisponde ai filtri selezionati.")
    else:
        st.write(f"**{len(dff)} record selezionati** per il report.")
        st.dataframe(dff.head(), use_container_width=True)
        if st.button("🚀 Genera Report PDF Avanzato", use_container_width=True):
            def build_advanced_pdf(data: pd.DataFrame) -> bytes:
                buffer = BytesIO(); doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=50)
                styles=getSampleStyleSheet(); style_title, style_h1, style_h2, style_body = styles['Title'], styles['h1'], styles['h2'], styles['BodyText']
                style_body.leading = 14; color_map = {"Critical": colors.HexColor("#d9534f"), "Hight": colors.HexColor("#f0ad4e"), "Low": colors.HexColor("#5cb85c")}
                def header_footer(canvas, doc):
                    canvas.saveState(); canvas.setFont('Helvetica', 9)
                    canvas.drawString(doc.leftMargin, doc.pagesize[1] - 20, "Report Rischi Fornitori | Confidenziale")
                    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.bottomMargin - 20, f"Pagina {doc.page}"); canvas.restoreState()
                frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
                template = PageTemplate(id='main', frames=frame, onPage=header_footer); doc.addPageTemplates([template])
                story = []
                story.append(Paragraph("Report di Analisi Rischi", style_title)); story.append(Spacer(1, 24))
                story.append(Paragraph(f"Data di Generazione: {datetime.now().strftime('%d/%m/%Y %H:%M')}", style_body))
                story.append(Paragraph(f"Fornitori Analizzati: {', '.join(sel_suppliers) if sel_suppliers else 'Tutti'}", style_body)); story.append(Spacer(1, 48))
                story.append(Paragraph("Executive Summary", style_h1)); story.append(Spacer(1, 12))
                total, open_r, critical = len(data), len(data[data['stato'] == 'aperto']), len(data[data['gravita'] == 'Critical'])
                story.append(Paragraph(f"Totale riscontri: {total} | Aperti: {open_r} | Critici: {critical}", style_body)); story.append(Spacer(1, 24))
                if not data.empty and not data.groupby("gravita").size().empty:
                    try:
                        agg_pie = data.groupby("gravita").size().reset_index(name="count")
                        fig_pie = px.pie(agg_pie, values="count", names="gravita", title="Ripartizione per Gravità", color="gravita", color_discrete_map=color_map)
                        pie_img_bytes = fig_pie.to_image(format="png", width=500, height=350, engine="kaleido")
                        story.append(Image(BytesIO(pie_img_bytes), width=450, height=315))
                    except Exception as e: story.append(Paragraph(f"Errore generazione grafico: {e}", style_body))
                story.append(Spacer(1, 24)); story.append(Paragraph("Dettaglio dei Riscontri", style_h1))
                for fornitore, group in data.groupby("fornitore"):
                    story.append(Spacer(1, 12)); story.append(Paragraph(f"Fornitore: {fornitore}", style_h2))
                    for _, risk in group.iterrows():
                        risk_color = color_map.get(risk['gravita'], colors.black)
                        risk_title_style = ParagraphStyle(name=f'RiskTitleStyle_{risk["id"]}', parent=style_h2, textColor=risk_color)
                        story.append(Spacer(1, 12)); story.append(Paragraph(f"ID {risk['id']}: {risk.get('rischio', 'N/D')}", risk_title_style))
                        details_data = [['Gravità:', Paragraph(f"<b>{risk.get('gravita', 'N/D')}</b>", style_body)],
                                        ['Stato:', risk.get('stato', 'N/D')],
                                        ['Due Date:', risk['data_fine'].strftime('%d/%m/%Y') if pd.notna(risk['data_fine']) else 'N/A'],
                                        ['Owner:', risk.get('contract_owner', 'N/D')], ['Avanz.:', f"{risk.get('perc_avanzamento', 0)}%"],
                                        ['Note:', Paragraph(risk.get('note', 'Nessuna nota.') if pd.notna(risk.get('note')) else 'Nessuna nota.', style_body)],
                                        ['Data Chiusura:', risk['data_chiusura'].strftime('%d/%m/%Y') if pd.notna(risk['data_chiusura']) else 'N/A']]
                        details_table = Table(details_data, colWidths=[100, doc.width - 100])
                        details_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (0,0), (-1,-1), 'LEFT'), ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'), ('BOX', (0,0), (-1,-1), 1, risk_color), ('INNERGRID', (0,0), (-1,-1), 0.25, colors.grey), ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#F0F0F0"))]))
                        story.append(details_table)
                doc.build(story)
                return buffer.getvalue()
            with st.spinner("Creazione del report PDF avanzato..."):
                try:
                    pdf_bytes = build_advanced_pdf(dff)
                    st.download_button(label="✅ Download Report PDF", data=pdf_bytes, file_name=f"report_rischi_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e: st.error(f"Errore generazione PDF: {e}. Assicurati di aver installato 'kaleido'.")

elif page == "Admin":
    users_df = load_users()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Elenco Utenti")
        st.dataframe(users_df[["id", "username", "role"]], use_container_width=True)
    with c2:
        with st.form("form_user", clear_on_submit=True):
            st.subheader("Crea Nuovo Utente")
            nu, npwd = st.text_input("Username"), st.text_input("Password", type="password")
            nrole = st.selectbox("Ruolo", ["read", "modify", "admin"])
            if st.form_submit_button("Crea Utente", use_container_width=True):
                if not nu or not npwd: st.error("Compila tutti i campi.")
                else:
                    try:
                        # MODIFICA: Usa db_write
                        db_write("INSERT INTO users(username,password,role) VALUES(?,?,?)", (nu, npwd, nrole))
                        st.success("Utente creato."); st.rerun()
                    except Exception: st.error("Username già esistente.")
        st.markdown("---")
        with st.form("delete_user", clear_on_submit=True):
            st.subheader("Elimina Utente")
            users_list = [u for u in users_df["username"].tolist() if u != st.session_state.username]
            if not users_list: st.info("Nessun altro utente da eliminare.")
            else:
                user_to_delete = st.selectbox("Seleziona utente", users_list)
                if st.form_submit_button("Elimina Utente", type="primary", use_container_width=True):
                    # MODIFICA: Usa db_write
                    db_write("DELETE FROM users WHERE username = ?", (user_to_delete,))
                    st.success(f"Utente '{user_to_delete}' eliminato."); st.rerun()
