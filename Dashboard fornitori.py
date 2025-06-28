import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
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
DB_PATH = Path("app.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Tabella Utenti
    c.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('read','modify','admin'))
      )
    """)
    # Tabella Rischi
    c.execute("""
      CREATE TABLE IF NOT EXISTS risks (
        id INTEGER PRIMARY KEY,
        data_inizio TEXT NOT NULL, data_fine TEXT NOT NULL, fornitore TEXT NOT NULL,
        rischio TEXT NOT NULL, stato TEXT NOT NULL, gravita TEXT NOT NULL,
        note TEXT, data_chiusura TEXT, contract_owner TEXT NOT NULL,
        area_riferimento TEXT NOT NULL, perc_avanzamento INTEGER NOT NULL DEFAULT 0
      )
    """)
    # NUOVA TABELLA: REMINDERS
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY,
            fornitore_nome TEXT NOT NULL,
            data_invio TEXT NOT NULL,
            stato_reminder TEXT NOT NULL CHECK(stato_reminder IN ('Attivo', 'Risposto')),
            note TEXT,
            test_bc INTEGER NOT NULL DEFAULT 0,
            test_it INTEGER NOT NULL DEFAULT 0,
            test_pt_va INTEGER NOT NULL DEFAULT 0,
            access_review INTEGER NOT NULL DEFAULT 0,
            ppt INTEGER NOT NULL DEFAULT 0
        )
    """)
    
    # Utente admin di default
    c.execute("SELECT 1 FROM users WHERE username = ?", ("Flavio",))
    if not c.fetchone():
        c.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", ("Flavio","Dashboard2003","admin"))
    
    conn.commit()
    conn.close()

init_db()
conn = get_connection()

def load_users():
    return pd.read_sql_query("SELECT * FROM users", conn)

def load_risks_df():
    return pd.read_sql_query("SELECT * FROM risks ORDER BY id DESC", conn, parse_dates=["data_inizio","data_fine","data_chiusura"])

def load_reminders_df():
    df_reminders = pd.read_sql_query("SELECT * FROM reminders ORDER BY data_invio ASC", conn, parse_dates=["data_invio"])
    if not df_reminders.empty:
        today = pd.to_datetime(datetime.now().date())
        df_reminders['giorni_trascorsi'] = (today - df_reminders['data_invio']).dt.days
        df_reminders['giorni_al_reminder'] = (5 - df_reminders['giorni_trascorsi']).clip(lower=0)
    return df_reminders

# —————————————————————————————
# 2) SESSION_STATE INIT
# —————————————————————————————
for key, val in [("authenticated", False), ("username", ""), ("role", ""), ("page", "Dashboard"), ("last_activity", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# —————————————————————————————
# 3) STILE GRAFICO
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
            authenticated=True, username=user, role=row["role"],
            page="Dashboard", last_activity=datetime.now()
        )
        return True
    return False

def do_logout(message="Logout effettuato con successo."):
    st.session_state.update(authenticated=False, username="", role="", page="Login", last_activity=None)
    st.info(message)

set_page_style()

if not st.session_state.authenticated:
    st.title("Risk Management Dashboard")
    st.markdown("---")
    col1, col2 = st.columns([1, 1], gap="large")
    with col1:
        st.subheader("Benvenuto")
        st.markdown("""
        Questa applicazione è uno strumento completo per il censimento, la gestione e il monitoraggio dei rischi e delle comunicazioni con i fornitori.
        """)
        st.subheader("Funzionalità Principali")
        with st.expander("📊 Dashboard"): st.write("Visualizza i dati dei rischi e ricevi notifiche per i reminder scaduti.")
        with st.expander("⚙️ Gestione Dati"): st.write("Gli utenti autorizzati possono inserire, modificare e tracciare rischi e comunicazioni.")
        with st.expander("📄 Report PDF"): st.write("Genera report professionali in formato PDF, ideali per la condivisione.")
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
# 5) ROUTING E CONTENUTO DELLE PAGINE
# —————————————————————————————
page = st.session_state.page
st.title(page)

if page == "Dashboard":
    df_risks = load_risks_df()
    df_reminders = load_reminders_df()

    st.subheader("Reminder Scaduti (5+ giorni)")
    reminders_scaduti = df_reminders[(df_reminders['giorni_trascorsi'] >= 5) & (df_reminders['stato_reminder'] == 'Attivo')]
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
                fig_pie = px.pie(dff.groupby("gravita").size().reset_index(name="count"), values="count", names="gravita", hole=0.4, title="Ripartizione Rischi per Gravità", color_discrete_map={"Critical": "#d9534f", "Hight": "#f0ad4e", "Low": "#5cb85c"})
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
                    conn.execute("INSERT INTO reminders (fornitore_nome, data_invio, stato_reminder) VALUES (?, ?, 'Attivo')", (fornitore_nome, data_invio.isoformat()))
                    conn.commit()
                    st.success(f"Reminder per {fornitore_nome} aggiunto!")
                    st.rerun()
                else:
                    st.error("Il nome del fornitore è obbligatorio.")

    st.markdown("---")
    st.subheader("Tracciamento Reminder Attivi")
    
    df_reminders = load_reminders_df()
    dff_attivi = df_reminders[df_reminders['stato_reminder'] == 'Attivo'].copy()

    if dff_attivi.empty:
        st.success("✔️ Nessun reminder attivo al momento.")
    else:
        edited_reminders = st.data_editor(
            dff_attivi,
            column_config={
                "id": None,
                "fornitore_nome": st.column_config.TextColumn("Fornitore", width="medium"),
                "data_invio": st.column_config.DateColumn("Data Invio", format="DD/MM/YYYY", disabled=True),
                "giorni_trascorsi": st.column_config.NumberColumn("Giorni Trascorsi"),
                "giorni_al_reminder": st.column_config.ProgressColumn("Giorni a Notifica (5)", format="%f", min_value=0, max_value=5),
                "stato_reminder": st.column_config.SelectboxColumn("Stato", options=["Attivo", "Risposto"]),
                "note": st.column_config.TextColumn("Note", width="large"),
                "test_bc": st.column_config.CheckboxColumn("Test BC"),
                "test_it": st.column_config.CheckboxColumn("Test IT"),
                "test_pt_va": st.column_config.CheckboxColumn("PT/VA"),
                "access_review": st.column_config.CheckboxColumn("Access Review"),
                "ppt": st.column_config.CheckboxColumn("PPT"),
            },
            use_container_width=True, hide_index=True, key="editor_reminders"
        )

        if st.button("Salva Modifiche Reminder", use_container_width=True):
            try:
                original_to_compare = dff_attivi.set_index('id')
                edited_to_compare = edited_reminders.set_index('id')
                diff_df = original_to_compare.compare(edited_to_compare)
                if diff_df.empty:
                    st.toast("Nessuna modifica da salvare.")
                else:
                    ids_to_update = diff_df.index.get_level_values('id').unique()
                    for row_id in ids_to_update:
                        row_to_update = edited_to_compare.loc[row_id]
                        data_tuple = (
                            row_to_update["fornitore_nome"], row_to_update["stato_reminder"], row_to_update["note"],
                            int(row_to_update["test_bc"]), int(row_to_update["test_it"]), int(row_to_update["test_pt_va"]),
                            int(row_to_update["access_review"]), int(row_to_update["ppt"]), int(row_id)
                        )
                        conn.execute("UPDATE reminders SET fornitore_nome=?, stato_reminder=?, note=?, test_bc=?, test_it=?, test_pt_va=?, access_review=?, ppt=? WHERE id=?", data_tuple)
                    conn.commit()
                    st.success(f"Salvate {len(ids_to_update)} modifiche.")
                    st.rerun()
            except Exception as e:
                st.error(f"Errore durante il salvataggio: {e}")

elif page == "Censimento Fornitori":
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
                conn.execute("INSERT INTO risks(data_inizio,data_fine,fornitore,rischio,stato,gravita,note,data_chiusura,contract_owner,area_riferimento,perc_avanzamento) VALUES(?,?,?,?,?,?,?,?,?,?,?)", 
                             (data_inizio.isoformat(), data_fine.isoformat(), fornitore, rischio, stato, gravita, note, data_chiusura.isoformat() if data_chiusura else None, contract_owner, area_riferimento, perc_avanzamento))
                conn.commit()
                st.success("Rischio inserito.")

elif page == "Modifica":
    df_risks = load_risks_df()
    st.info("In questa sezione puoi modificare i dati dei rischi esistenti.")
    sup_opts = ["Tutti"] + sorted(df_risks["fornitore"].unique().tolist())
    sel = st.selectbox("Filtra Fornitore per modificare", sup_opts, key="modifica_sel")
    
    dff_original = df_risks.copy()
    if sel != "Tutti":
        dff_original = dff_original[dff_original["fornitore"] == sel]

    edited_df = st.data_editor(dff_original, num_rows="static", use_container_width=True,
        column_config={"id": st.column_config.NumberColumn("ID", disabled=True), "data_fine": st.column_config.DateColumn("Due Date", format="YYYY-MM-DD")},
        key="data_editor_modifica"
    )

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
                        row_to_update["contract_owner"], row_to_update["area_riferimento"], int(row_to_update["perc_avanzamento"]), int(row_id)
                    )
                    conn.execute("UPDATE risks SET data_inizio=?, data_fine=?, fornitore=?, rischio=?, stato=?, gravita=?, note=?, data_chiusura=?, contract_owner=?, area_riferimento=?, perc_avanzamento=? WHERE id=?", data_tuple)
                conn.commit()
                st.success(f"Salvate {len(ids_to_update)} modifiche.")
                st.rerun()
        except Exception as e:
            st.error(f"Errore durante il salvataggio: {e}")

elif page == "Report PDF":
    df_risks = load_risks_df()
    st.info("Genera un report PDF avanzato con grafici di sintesi e dettagli strutturati per ogni rischio.")
    st.subheader("1. Seleziona il Perimetro del Report")
    # ... (logica dei filtri e del pulsante come prima, assicurandosi che usi df_risks)
    
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
                        conn.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", (nu, npwd, nrole))
                        conn.commit()
                        st.success("Utente creato."); st.rerun()
                    except sqlite3.IntegrityError: st.error("Username già esistente.")
        st.markdown("---")
        with st.form("delete_user", clear_on_submit=True):
            st.subheader("Elimina Utente")
            users_list = [u for u in users_df["username"].tolist() if u != st.session_state.username]
            if not users_list: st.info("Nessun altro utente da eliminare.")
            else:
                user_to_delete = st.selectbox("Seleziona utente", users_list)
                if st.form_submit_button("Elimina Utente", type="primary", use_container_width=True):
                    conn.execute("DELETE FROM users WHERE username = ?", (user_to_delete,))
                    conn.commit()
                    st.success(f"Utente '{user_to_delete}' eliminato."); st.rerun()
