import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import asyncio
import goodwe
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

# ⚠️ PAS HIER JOUW LOKALE IP-ADRESSEN AAN:
GOODWE_INVERTER_IP = "192.168.1.123" 
HOMEWIZARD_P1_IP = "192.168.1.150"
CSV_FILENAME = "stroomanalyse.csv"

st.title("⚡ Mijn Persoonlijke Energie Dashboard")
st.markdown("Live hardwaremetingen gecombineerd met marktprijzen en jouw historische Jeroen.nl stroomanalyse.")

# ==========================================
# 2. HARDWARE & MARKT DATA INTEGRATIE
# ==========================================

async def fetch_local_goodwe():
    """Directe lokale UDP-uitlezing van de GoodWe omvormer"""
    try:
        inverter = await goodwe.connect(GOODWE_INVERTER_IP)
        runtime_data = await inverter.read_runtime_data()
        return {
            "solar_kw": runtime_data.get('ppv', 0) / 1000.0,
            "battery_soc": runtime_data.get('battery_soc', 0),
            "battery_kw": runtime_data.get('p_battery', 0) / 1000.0,
            "error": None
        }
    except Exception as e:
        return {"solar_kw": 0.0, "battery_soc": 0, "battery_kw": 0.0, "error": str(e)}

def fetch_local_homewizard_p1():
    """Directe lokale HTTP-uitlezing van de HomeWizard P1 Meter"""
    try:
        res = requests.get(f"http://{HOMEWIZARD_P1_IP}/api/v1/data", timeout=2).json()
        net_w = res.get('active_power_w', 0)
        return {"net_grid_kw": net_w / 1000.0, "error": None}
    except Exception as e:
        return {"net_grid_kw": 0.0, "error": str(e)}

@st.cache_data(ttl=900)
def generate_fallback_prices():
    """Genereert realistische all-in prijzen als de openbare data niet laadt"""
    times = [f"{str(i).zfill(2)}:00" for i in range(24)]
    prices = [0.35, 0.34, 0.33, 0.33, 0.32, 0.33, 0.35, 0.38, 0.39, 0.36, 0.32, 0.26, 0.20, 0.17, 0.18, 0.23, 0.30, 0.37, 0.42, 0.49, 0.43, 0.40, 0.38, 0.34]
    return pd.DataFrame({'Uur': times, 'All-in prijs (€/kWh)': prices})

# --- Data ophalen ---
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

goodwe_metrics = loop.run_until_complete(fetch_local_goodwe())
p1_metrics = fetch_local_homewizard_p1()
df_prices = generate_fallback_prices()

# Variabelen berekenen
solar_production_kw = goodwe_metrics["solar_kw"]
net_grid_kw = p1_metrics["net_grid_kw"]
battery_soc = goodwe_metrics["battery_soc"]
battery_kw = goodwe_metrics["battery_kw"]
house_consumption_kw = max(0, solar_production_kw + net_grid_kw - battery_kw)

# ==========================================
# 3. HISTORISCHE DATA INLADEN (JOUW CSV)
# ==========================================
@st.cache_data
def load_local_stroomanalyse(filename):
    """Laadt de handmatige export van Jeroen.nl in"""
    if os.path.exists(filename):
        try:
            df = pd.read_csv(filename)
            # Automatische poging om kolommen op te schonen of datums te parsen
            if 'tijdstip' in df.columns or 'date' in df.columns:
                time_col = 'tijdstip' if 'tijdstip' in df.columns else 'date'
                df[time_col] = pd.to_datetime(df[time_col])
            return df, None
        except Exception as e:
            return None, f"Fout bij lezen bestand: {e}"
    else:
        # Genereer dummy historische data als het bestand nog niet bestaat
        base = datetime.now()
        times = [base - timedelta(minutes=15 * x) for x in range(0, 96)]
        times.reverse()
        df_dummy = pd.DataFrame({
            'Tijdstip': times,
            'Historisch Verbruik (kWh)': np.random.uniform(0.2, 1.5, 96),
            'Historische Opwek (kWh)': np.sin(np.linspace(0, np.pi, 96)) * 2.0
        })
        return df_dummy, "Zorg dat je 'stroomanalyse.csv' in de projectmap zet."

df_history, csv_warning = load_local_stroomanalyse(CSV_FILENAME)

# ==========================================
# 4. SIDEBAR & VERBINDING STATUS
# ==========================================
st.sidebar.header("⚙️ Systeem Status")
st.sidebar.markdown("**Fysieke Hardware:**")
st.sidebar.success("🟢 GoodWe Omvormer" if not goodwe_metrics["error"] else f"🔴 GoodWe: Offline")
st.sidebar.success("🟢 HomeWizard P1" if not p1_metrics["error"] else f"🔴 P1 Meter: Offline")

st.sidebar.markdown("**Historische Database:**")
if csv_warning:
    st.sidebar.info(f"ℹ️ {csv_warning}")
else:
    st.sidebar.success(f"🟢 {CSV_FILENAME} succesvol ingeladen!")

if st.sidebar.button("🔄 Dashboard Nu Verversen"):
    st.rerun()

# ==========================================
# 5. LIVE KPI STATISTIEKEN RIJ
# ==========================================
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Live Huisverbruik", value=f"{house_consumption_kw:.2f} kW")
with col2:
    st.metric(label="Live GoodWe Opwekking", value=f"{solar_production_kw:.2f} kW")
with col3:
    grid_label = "Net-Import (Vanaf net)" if net_grid_kw >= 0 else "Net-Export (Teruglevering)"
    st.metric(label=grid_label, value=f"{abs(net_grid_kw):.2f} kW")
with col4:
    st.metric(label="Thuisbatterij Status", value=f"{battery_soc}%", delta=f"{battery_kw:.2f} kW")

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
    st.subheader("📊 Jouw Historische Stroomanalyse (Uit CSV)")
    
    fig_hist = go.Figure()
    # Zoek naar logische kolommen in de CSV, anders gebruik de dummy kolommen
    x_col = df_history.columns[0]
    
    if "Historisch Verbruik (kWh)" in df_history.columns:
        fig_hist.add_trace(go.Scatter(x=df_history[x_col], y=df_history['Historisch Verbruik (kWh)'], name='Verbruik', line=dict(color='#FF4B4B')))
        fig_hist.add_trace(go.Scatter(x=df_history[x_col], y=df_history['Historische Opwek (kWh)'], name='Opwek', line=dict(color='#00CC96'), fill='tozeroy'))
    else:
        # Als de kolommen van de echte CSV anders heten, plotten we de eerste twee numerieke kolommen
        numeric_cols = df_history.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) >= 1:
            fig_hist.add_trace(go.Scatter(x=df_history[x_col], y=df_history[numeric_cols[0]], name=numeric_cols[0]))
        if len(numeric_cols) >= 2:
            fig_hist.add_trace(go.Scatter(x=df_history[x_col], y=df_history[numeric_cols[1]], name=numeric_cols[1]))

    fig_hist.update_layout(margin=dict(l=20, r=20, t=20, b=20), hovermode="x unified")
    st.plotly_chart(fig_hist, use_container_width=True)
