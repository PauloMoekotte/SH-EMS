import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import requests
import os

# ==========================================
# 1. PAGINA CONFIGURATIE & INSTELLINGEN
# ==========================================
st.set_page_config(
    page_title="Mijn Energie Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ⚠️ VERIFIEER DIT IP-ADRES IN JE HOMEWIZARD ENERGY APP:
# (Instellingen > Apparaten > P1 Meter > IP-adres)
HOMEWIZARD_P1_IP = "192.168.2.4"
CSV_FILENAME = "stroomanalyse.csv"

st.title("⚡ Mijn Persoonlijke Energie Dashboard")
st.markdown("Live HomeWizard metingen gecombineerd met marktprijzen en jouw historische Jeroen.nl stroomanalyse.")

# ==========================================
# 2. HOMEWIZARD & MARKT DATA INTEGRATIE
# ==========================================

def fetch_local_homewizard_data():
    """Haalt live data op uit de HomeWizard API met omzeiling van systeem-proxies"""
    url = f"http://{HOMEWIZARD_P1_IP}/api/v1/data"
    
    # We forceren Python om GEEN gebruik te maken van actieve VPN/Proxy-instellingen 
    # voor dit specifieke verzoek naar je interne netwerk.
    session = requests.Session()
    session.trust_env = False 
    
    try:
        # We sturen exact dezelfde basis-headers mee als een standaard webbrowser
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json"
        }
        
        response = session.get(url, headers=headers, timeout=4)
        
        if response.status_code == 200:
            res = response.json()
            
            # P1 Meter API data mapping
            net_w = res.get('active_power_w', 0)
            
            # Sommige P1-meters geven opwek door onder 'active_power_production_w'.
            # Als je een aparte HomeWizard kWh-meter gebruikt, heet het vaak 'total_solar_power_w'.
            solar_w = res.get('active_power_production_w', res.get('total_solar_power_w', 0))
            
            # Thuisbatterij waarden
            battery_soc = res.get('battery_soc_percent', 0)
            battery_w = res.get('active_battery_power_w', 0)
            
            return {
                "net_grid_kw": net_w / 1000.0,
                "solar_kw": solar_w / 1000.0,
                "battery_soc": battery_soc,
                "battery_kw": battery_w / 1000.0,
                "error": None
            }
        else:
            return {"net_grid_kw": 0.0, "solar_kw": 0.0, "battery_soc": 0, "battery_kw": 0.0, 
                    "error": f"Server gaf HTTP {response.status_code}"}
            
    except requests.exceptions.Timeout:
        return {"net_grid_kw": 0.0, "solar_kw": 0.0, "battery_soc": 0, "battery_kw": 0.0, 
                "error": "Timeout: Het apparaat reageerde te traag."}
    except requests.exceptions.ConnectionError as ce:
        return {"net_grid_kw": 0.0, "solar_kw": 0.0, "battery_soc": 0, "battery_kw": 0.0, 
                "error": f"Verbinding geweigerd door netwerk: {str(ce)}"}
    except Exception as e:
        return {"net_grid_kw": 0.0, "solar_kw": 0.0, "battery_soc": 0, "battery_kw": 0.0, 
                "error": f"Onverwachte fout: {str(e)}"}

# ==========================================
# 4. SIDEBAR & VERBINDING STATUS
# ==========================================
st.sidebar.header("⚙️ Systeem Status")
st.sidebar.markdown("**Fysieke Hardware (Live):**")

if hw_metrics["error"]:
    st.sidebar.error(f"🔴 HomeWizard P1: Offline")
    st.sidebar.warning(f"Foutmelding: {hw_metrics['error']}")
else:
    st.sidebar.success("🟢 HomeWizard P1 Hub: Verbonden")

st.sidebar.markdown("**Historische Database:**")
if csv_warning:
    st.sidebar.info(f"ℹ️ {csv_warning}")
else:
    st.sidebar.success(f"🟢 {CSV_FILENAME} gekoppeld!")
    totaal_opwek = df_history['Opwek'].sum()
    totaal_export = df_history['Export'].sum()
    if totaal_opwek > 0:
        zelfconsumptie = ((totaal_opwek - totaal_export) / totaal_opwek) * 100
        st.sidebar.metric("Historische Zelfconsumptie", f"{zelfconsumptie:.1f}%")

if st.sidebar.button("🔄 Dashboard Nu Verversen"):
    st.rerun()

# ==========================================
# 5. LIVE KPI STATISTIEKEN RIJ
# ==========================================
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Live Huisverbruik", value=f"{house_consumption_kw:.2f} kW")
with col2:
    st.metric(label="Live Opwekking (HW)", value=f"{solar_production_kw:.2f} kW")
with col3:
    grid_label = "Net-Import (Vanaf net)" if net_grid_kw >= 0 else "Net-Export (Teruglevering)"
    st.metric(label=grid_label, value=f"{abs(net_grid_kw):.2f} kW")
with col4:
    st.metric(label="Thuisbatterij SoC", value=f"{battery_soc}%", delta=f"{battery_kw:.2f} kW")

st.markdown("---")

# ==========================================
# 6. VISUALISATIES (GRAFIEKEN)
# ==========================================
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📈 Dynamische Stroomprijzen Vandaag (All-in)")
    fig_prices = px.bar(df_prices, x='Uur', y='All-in prijs (€/kWh)', color_discrete_sequence=['#00CC96'])
    fig_prices.update_layout(margin=dict(l=20, r=20, t=20, b=20), hovermode="x unified")
    st.plotly_chart(fig_prices, use_container_width=True)

with col_right:
    st.subheader("📊 Jouw Stroomanalyse Historie (Jeroen.nl CSV)")
    fig_hist = go.Figure()
    
    if 'Werkelijk_Verbruik' in df_history.columns:
        fig_hist.add_trace(go.Scatter(x=df_history['DatumTijd'], y=df_history['Werkelijk_Verbruik'], name='Werkelijk Verbruik', line=dict(color='#FF4B4B', width=2)))
        fig_hist.add_trace(go.Scatter(x=df_history['DatumTijd'], y=df_history['Opwek'], name='Opwekking (Zon)', line=dict(color='#00CC96', width=1.5), fill='tozeroy'))
        fig_hist.add_trace(go.Scatter(x=df_history['DatumTijd'], y=df_history['Import'], name='Net-Import (P1)', line=dict(color='#FFA500', width=1, dash='dash')))
        fig_hist.add_trace(go.Scatter(x=df_history['DatumTijd'], y=df_history['Export'], name='Net-Export (Teruglevering)', line=dict(color='#1F77B4', width=1, dash='dot')))
    else:
        fig_hist.add_trace(go.Scatter(x=df_history['DatumTijd'], y=df_history['Import'], name='Import', line=dict(color='#FF4B4B')))
        fig_hist.add_trace(go.Scatter(x=df_history['DatumTijd'], y=df_history['Opwek'], name='Opwek', line=dict(color='#00CC96'), fill='tozeroy'))

    fig_hist.update_layout(margin=dict(l=20, r=20, t=20, b=20), hovermode="x unified")
    st.plotly_chart(fig_hist, use_container_width=True)
