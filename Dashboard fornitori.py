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
import sys
from pathlib import Path

# --- Gestione del percorso per PyInstaller ---
if getattr(sys, 'frozen', False):
    # Se l'app è "congelata" (es. tramite PyInstaller)
    application_path = Path(sys._MEIPASS)
else:
    # Se l'app sta girando normalmente come script .py
    application_path = Path(__file__).parent

DB_PATH = application_path / "app.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
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
for key, val in [("authenticated", False), ("username", ""), ("role", ""), ("page", "Home")]:
    if key not in st.session_state:
        st.session_state[key] = val

# —————————————————————————————
# 3) STILE GRAFICO (CSS con Background Animato più Veloce e Scuro)
# —————————————————————————————
def set_page_style():
    # MODIFICA: Palette più scura e animazione più veloce
    css = f"""
    <style>
        @keyframes dynamicGradient {{
            0%   {{ background-position: 0% 50%; }}
            50%  {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}

        .stApp {{
            background: linear-gradient(-45deg, #020024, #090979, #00d4ff, #23d5ab);
            background-size: 400% 400%;
            animation: dynamicGradient 15s ease infinite;
            color: #FFFFFF;
        }}
        
        [data-testid="stSidebar"] {{
            background-color: rgba(15, 23, 42, 0.85); /* Leggermente più opaco per leggibilità */
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border-right: 1px solid rgba(148, 163, 184, 0.2);
        }}
        
        [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
        
        h1, h2, h3, p, label, .st-emotion-cache-16txtl3, .st-emotion-cache-qbe2hs, .st-emotion-cache-aw8l5d, .st-emotion-cache-bm2z3a {{
             color: #FFFFFF !important; 
        }}
        
        /* Stile per i widget all'interno delle sezioni per renderli più visibili */
        .st-emotion-cache-uf99v8, .st-emotion-cache-1r6slb0, .st-emotion-cache-1jicfl2 {{
             background-color: rgba(15, 23, 42, 0.4);
             padding: 20px;
             border-radius: 10px;
        }}

        [data-testid="stToolbar"] {{ display: none !important; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# —————————————————————————————
# 4) LOGIN & SIDEBAR
# —————————————————————————————
def do_login(user, pwd):
    row = conn.execute("SELECT role FROM users WHERE username=? AND password=?", (user, pwd)).fetchone()
    if row:
        st.session_state.update(authenticated=True, username=user, role=row["role"], page="Home")
        return True
    return False

def do_logout():
    st.session_state.update(authenticated=False, username="", role="", page="Login")

set_page_style()

if not st.session_state.authenticated:
    st.title("Risk Management Login")
    with st.form("login"):
        user = st.text_input("Username")
        pwd  = st.text_input("Password", type="password")
        if st.form_submit_button("Entra", use_container_width=True):
            if do_login(user, pwd): st.rerun()
            else: st.error("Credenziali errate")
    st.stop()

with st.sidebar:
    st.title("Risk Dashboard")
    st.markdown(f"Benvenuto, **{st.session_state.username}**!")
    st.markdown(f"Ruolo: `{st.session_state.role}`")
    st.markdown("---")
    
    base_menu, modify_menu, admin_menu = ["Home", "Dashboard", "Report PDF"], ["Censimento Fornitori", "Modifica"], ["Admin"]
    final_menu = base_menu.copy()
    if st.session_state.role in ['modify', 'admin']: final_menu.extend(modify_menu)
    if st.session_state.role == 'admin': final_menu.extend(admin_menu)

    for item in final_menu:
        if st.button(item, key=f"menu_{item}"): st.session_state.page = item
    
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

if page == "Home":
    st.subheader(f"Guida alle Sezioni dell'Applicazione")
    st.info("Espandi ogni sezione per scoprire a cosa serve.")
    if "Home" in final_menu:
        with st.expander("🏠 Home", expanded=True): st.write("Pagina di benvenuto con un riepilogo rapido dei rischi e questa guida.")
    if "Dashboard" in final_menu:
        with st.expander("📊 Dashboard"): st.write("Visualizza i dati dei rischi in forma aggregata tramite grafici interattivi.")
    if "Report PDF" in final_menu:
        with st.expander("📄 Report PDF"): st.write("Genera report professionali in formato PDF, con grafici e dettagli strutturati.")
    if "Censimento Fornitori" in final_menu:
        with st.expander("➕ Censimento Fornitori"): st.write("Inserisci nuovi rischi associati ai fornitori nel database.")
    if "Modifica" in final_menu:
        with st.expander("✏️ Modifica"): st.write("Modifica i dati dei rischi esistenti.")
    if "Admin" in final_menu:
        with st.expander("🔧 Admin"): st.write("Sezione per la gestione degli utenti.")
    st.subheader("Riepilogo Rapido")
    total, open_r, closed = len(df), len(df[df['stato'] == 'aperto']), len(df[df['stato'] == 'chiuso'])
    c1, c2, c3 = st.columns(3)
    c1.metric("Rischi Totali", total); c2.metric("Rischi Aperti", open_r); c3.metric("Rischi Chiusi", closed)

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
                conn.execute("""INSERT INTO risks(data_inizio,data_fine,fornitore,rischio,stato,gravita,note,data_chiusura,contract_owner,area_riferimento,perc_avanzamento) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", 
                             (data_inizio.isoformat(), data_fine.isoformat(), fornitore, rischio, stato, gravita, note, data_chiusura.isoformat() if data_chiusura else None, contract_owner, area_riferimento, perc_avanzamento))
                conn.commit()
                st.success("Rischio inserito.")

elif page == "Dashboard":
    c1, c2 = st.columns([1, 3])
    with c1:
        st.subheader("Filtri")
        sup_opts, default_stati = ["Tutti"] + sorted(df["fornitore"].unique().tolist()), ["aperto", "chiuso"]
        sel_sup = st.selectbox("Fornitore", sup_opts)
        sel_stati = st.multiselect("Stato", default_stati, default=default_stati)
    dff = df[df["stato"].isin(sel_stati)]
    if sel_sup != "Tutti": dff = dff[dff["fornitore"] == sel_sup]
    with c2:
        if dff.empty: st.warning("Nessun dato da visualizzare con i filtri correnti.")
        else:
            gc1, gc2 = st.columns(2)
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

elif page == "Modifica":
    st.info("In questa sezione puoi modificare i dati esistenti.")
    sup_opts = ["Tutti"] + sorted(df["fornitore"].unique().tolist())
    sel = st.selectbox("Filtra Fornitore per modificare", sup_opts, key="modifica_sel")
    
    dff_original = df.copy()
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
                    conn.execute("""UPDATE risks SET data_inizio=?, data_fine=?, fornitore=?, rischio=?, stato=?, gravita=?, note=?, data_chiusura=?, contract_owner=?, area_riferimento=?, perc_avanzamento=? WHERE id=?""", data_tuple)
                
                conn.commit()
                st.success(f"Salvate {len(ids_to_update)} modifiche.")
                st.rerun()
        except Exception as e:
            st.error(f"Errore durante il salvataggio: {e}")


elif page == "Report PDF":
    st.info("Genera un report PDF avanzato con grafici di sintesi e dettagli strutturati per ogni rischio.")
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
            def build_advanced_pdf(data: pd.DataFrame) -> bytes:
                buffer = BytesIO()
                doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=50)
                styles=getSampleStyleSheet()
                style_title, style_h1, style_h2, style_body = styles['Title'], styles['h1'], styles['h2'], styles['BodyText']
                style_body.leading = 14
                color_map = {"Critical": colors.HexColor("#d9534f"), "Hight": colors.HexColor("#f0ad4e"), "Low": colors.HexColor("#5cb85c")}
                def header_footer(canvas, doc):
                    canvas.saveState(); canvas.setFont('Helvetica', 9)
                    canvas.drawString(doc.leftMargin, doc.pagesize[1] - 20, "Report Rischi Fornitori | Confidenziale")
                    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.bottomMargin - 20, f"Pagina {doc.page}"); canvas.restoreState()
                frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
                template = PageTemplate(id='main', frames=frame, onPage=header_footer)
                doc.addPageTemplates([template])
                story = []
                story.append(Paragraph("Report di Analisi Rischi", style_title))
                story.append(Spacer(1, 24))
                story.append(Paragraph(f"Data di Generazione: {datetime.now().strftime('%d/%m/%Y %H:%M')}", style_body))
                story.append(Paragraph(f"Fornitori Analizzati: {', '.join(sel_suppliers) if sel_suppliers else 'Tutti'}", style_body))
                story.append(Spacer(1, 48))
                story.append(Paragraph("Executive Summary", style_h1))
                story.append(Spacer(1, 12))
                total, open_r, critical = len(data), len(data[data['stato'] == 'aperto']), len(data[data['gravita'] == 'Critical'])
                story.append(Paragraph(f"Totale riscontri: {total} | Aperti: {open_r} | Critici: {critical}", style_body))
                story.append(Spacer(1, 24))
                if not data.empty and not data.groupby("gravita").size().empty:
                    try:
                        agg_pie = data.groupby("gravita").size().reset_index(name="count")
                        fig_pie = px.pie(agg_pie, values="count", names="gravita", title="Ripartizione per Gravità", color="gravita", color_discrete_map=color_map)
                        pie_img_bytes = fig_pie.to_image(format="png", width=500, height=350, engine="kaleido")
                        story.append(Image(BytesIO(pie_img_bytes), width=450, height=315))
                    except Exception as e: story.append(Paragraph(f"Errore generazione grafico: {e}", style_body))
                story.append(Spacer(1, 24))
                story.append(Paragraph("Dettaglio dei Riscontri", style_h1))
                for fornitore, group in data.groupby("fornitore"):
                    story.append(Spacer(1, 12)); story.append(Paragraph(f"Fornitore: {fornitore}", style_h2))
                    for _, risk in group.iterrows():
                        risk_color = color_map.get(risk['gravita'], colors.black)
                        risk_title_style = ParagraphStyle(name=f'RiskTitleStyle_{risk["id"]}', parent=style_h2, textColor=risk_color)
                        story.append(Spacer(1, 12))
                        story.append(Paragraph(f"ID {risk['id']}: {risk.get('rischio', 'N/D')}", risk_title_style))
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
                    st.download_button(label="✅ Download Report PDF", data=pdf_bytes,
                        file_name=f"report_rischi_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e: st.error(f"Errore generazione PDF: {e}. Assicurati di aver installato 'kaleido'.")

elif page == "Admin":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Elenco Utenti")
        users_df = load_users()[["id", "username", "role"]]
        st.dataframe(users_df, use_container_width=True)
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