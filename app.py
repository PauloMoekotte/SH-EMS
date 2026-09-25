import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- PAGINA CONFIGURATIE ---
st.set_page_config(
    page_title="Smart Energy Management Dashboard",
    page_icon="⚡",
    layout="wide",
)

# --- MOCK DATA GENERATOR ---
@st.cache_data
def generate_historical_data():
    """Genereert 24 uur aan historische energiegegevens."""
    now = datetime.now()
    times = [now - timedelta(minutes=15 * i) for i in range(96)]
    times.reverse()
    
    # Basispatronen voor verbruik (kWh)
    solar_gen = [max(0, 5 * np.sin(np.pi * (t.hour - 6) / 12)) if 6 <= t.hour <= 18 else 0 for t in times]
    hvac_load = [2.5 + 1.2 * np.sin(np.pi * (t.hour - 12) / 12) + np.random.normal(0, 0.2) for t in times]
    lighting_load = [0.5 if 8 <= t.hour <= 18 else 1.8 + np.random.normal(0, 0.1) for t in times]
    appliances = [1.0 + np.random.exponential(0.5) for _ in times]
    
    df = pd.DataFrame({
        "Timestamp": times,
        "Zonnepanelen (Opwekking)": solar_gen,
        "HVAC (Klimaatbeheersing)": hvac_load,
        "Verlichting": lighting_load,
        "Apparaten & Overig": appliances
    })
    df["Totaal Verbruik"] = df["HVAC (Klimaatbeheersing)"] + df["Verlichting"] + df["Apparaten & Overig"]
    df["Netto Netto-Invoeding"] = df["Zonnepanelen (Opwekking)"] - df["Totaal Verbruik"]
    return df

df_history = generate_historical_data()

# --- SIDEBAR & NAVIGATIE ---
st.sidebar.image("https://icons8.com", width=80)
st.sidebar.title("⚡ Energy OS")
page = st.sidebar.radio("Navigatie", ["Real-time Overzicht", "Historische Analyse", "Instellingen & Alerts"])

# Tarief configuratie (simulatie)
st.sidebar.markdown("---")
st.sidebar.subheader("🔋 Tarief Instellingen")
peak_rate = st.sidebar.slider("Piektarief (€/kWh)", 0.20, 0.60, 0.40)
off_peak_rate = st.sidebar.slider("Daltarief (€/kWh)", 0.10, 0.40, 0.25)

# --- PAGINA 1: REAL-TIME OVERZICHT ---
if page == "Real-time Overzicht":
    st.title("🔌 Real-time Energy Management")
    st.markdown("Actuele status van het energienetwerk en live verbruiksmonitoren.")

    # Live simulatie data (laatste rij uit dataframe met lichte afwijking)
    latest = df_history.iloc[-1].copy()
    
    # KPI Cijfers bovenaan
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Actueel Verbruik", f"{latest['Totaal Verbruik']:.2f} kW", delta="-0.34 kW (Afgelopen uur)")
    with col2:
        st.metric("Zonne-energie", f"{latest['Zonnepanelen (Opwekking)']:.2f} kW", delta="+0.12 kW", delta_color="normal")
    with col3:
        netto_tekst = "Netto Levering" if latest['Netto Netto-Invoeding'] > 0 else "Netto Verbruik"
        st.metric(netto_tekst, f"{abs(latest['Netto Netto-Invoeding']):.2f} kW", delta="Balancerend", delta_color="off")
    with col4:
        geschatte_kosten = latest['Totaal Verbruik'] * peak_rate
        st.metric("Kosten (Huidig uur)", f"€ {geschatte_kosten:.2f}", delta="Binnen budget", delta_color="inverse")

    st.markdown("---")
    
    # Grafieken Layout
    g_col1, g_col2 = st.columns([2, 1])
    
    with g_col1:
        st.subheader("📈 Energiebalans (Laatste 24 Uur)")
        fig_balance = go.Figure()
        fig_balance.add_trace(go.Scatter(x=df_history["Timestamp"], y=df_history["Totaal Verbruik"], name="Totaal Verbruik", line=dict(color='red', width=2)))
        fig_balance.add_trace(go.Scatter(x=df_history["Zonnepanelen (Opwekking)"], name="Zonne-opwekking", fill='tozeroy', line=dict(color='green')))
        fig_balance.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=350, legend_orientation="h")
        st.plotly_chart(fig_balance, use_container_width=True)

    with g_col2:
        st.subheader("🍰 Verbruik per Categorie")
        labels = ['HVAC', 'Verlichting', 'Apparaten']
        values = [latest["HVAC (Klimaatbeheersing)"], latest["Verlichting"], latest["Apparaten & Overig"]]
        fig_pie = px.pie(names=labels, values=values, color_discrete_sequence=px.colors.sequential.RdBu)
        fig_pie.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=350, showlegend=True)
        st.plotly_chart(fig_pie, use_container_width=True)

# --- PAGINA 2: HISTORISCHE ANALYSE ---
elif page == "Historische Analyse":
    st.title("📊 Data Analyse & Trends")
    
    # Filter op componenten
    options = st.multiselect(
        'Selecteer te analyseren verbruikers:',
        ["HVAC (Klimaatbeheersing)", "Verlichting", "Apparaten & Overig"],
        default=["HVAC (Klimaatbeheersing)", "Verlichting"]
    )
    
    if options:
        fig_trend = px.line(df_history, x="Timestamp", y=options, title="Gedetailleerde Verbruikstrend")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.warning("Selecteer minimaal één variabele om de trend te tonen.")

    # Anomalie detectie simulatie (Machine Learning component)
    st.markdown("---")
    st.subheader("🚨 Automatische Afwijkingsdetectie (Anomaly Detection)")
    
    # We markeren willekeurig 2 punten als anomalie boven een bepaalde drempel
    df_history["Anomalie"] = df_history["Totaal Verbruik"] > df_history["Totaal Verbruik"].quantile(0.95)
    anomalies = df_history[df_history["Anomalie"] == True]
    
    fig_anomaly = go.Figure()
    fig_anomaly.add_trace(go.Scatter(x=df_history["Timestamp"], y=df_history["Totaal Verbruik"], name="Normaal Verbruik", line=dict(color="blue")))
    fig_anomaly.add_trace(go.Scatter(x=anomalies["Timestamp"], y=anomalies["Totaal Verbruik"], mode="markers", name="Piek/Afwijking", marker=dict(color="red", size=10, symbol="x")))
    fig_anomaly.update_layout(title="Gedetecteerde ongewone verbruikspieken")
    st.plotly_chart(fig_anomaly, use_container_width=True)

# --- PAGINA 3: INSTELLINGEN & ALERTS ---
elif page == "Instellingen & Alerts":
    st.title("⚙️ Systeembeheer & Alerts")
    
    st.subheader("Drempelwaarden voor notificaties")
    max_load = st.number_input("Maximaal toegestane piekbelasting (kW)", value=5.0, step=0.5)
    email_alert = st.text_input("E-mailadres voor alerts", placeholder="voorbeeld@bedrijf.nl")
    
    if st.button("Instellingen Opslaan"):
        st.success(f"Configuratie succesvol opgeslagen! Alerts worden gestuurd naar {email_alert} bij overschrijding van {max_load} kW.")
