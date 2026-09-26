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

# ⚠️ VERIFIEER DIT LOKALE IP-ADRES MET JOUW BROWSER:
HOMEWIZARD_P1_IP = "192.168.2.4"
CSV_FILENAME = "stroomanalyse.csv"

st.title("⚡ Mijn Persoonlijke Energie Dashboard")
st.markdown("Live HomeWizard netwerkmetingen gecombineerd met marktprijzen en jouw historische Jeroen.nl stroomanalyse.")

# ==========================================
# 2. HOMEWIZARD LOKALE DATA INTEGRATIE
# ==========================================

def fetch_local_homewizard_data():
    """Haalt live data op uit de HomeWizard P1 Meter via het lokale wifinetwerk"""
    url = f"http://{HOMEWIZARD_P1_IP}/api/v1/data"
    
    # We forceren Python om eventuele actieve VPN/Proxy-instellingen op je pc te negeren
    session = requests.Session()
    session.trust_env = False 
    
    try:
        # Browser-achtige headers meesturen voorkomt netwerkweigeringen
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json"
        }
        response = session.get(url, headers=headers, timeout=3)
        
        if response.status_code == 200:
            res = response.json()
            net_w = res.get('active_power_w', 0)
            
            # P1 meters vangen opwek op via 'active_power_production_w'
            solar_w = res.get('active_power_production_w', res.get('total_solar_power_w', 0))
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
            return {
                "net_grid_kw": 0.0, "solar_kw": 0.0, "battery_soc": 0, "battery_kw": 0.0, 
                "error": f"HomeWizard gaf HTTP statuscode {response.status_code}"
            }
            
    except Exception as e:
        # Volledige foutomschrijving teruggeven om crashes te voorkomen
        return {
            "net_grid_kw": 0.0, "solar_kw": 0.0, "battery_soc": 0, "battery_kw": 0.0,
            "error": f"Kan geen verbinding maken met {HOMEWIZARD_P1_IP}. Details: {str(e)}"
        }

@st.cache_data(ttl=900)
def generate_fallback_prices():
    times = [f"{str(i).zfill(2)}:00" for i in range(24)]
    prices = [0.35, 0.34, 0.33, 0.33, 0.32, 0.33, 0.35, 0.38, 0.39, 0.36, 0.32, 0.26, 0.20, 0.17, 0.18, 0.23, 0.30, 0.37, 0.42, 0.49, 0.43, 0.40, 0.38, 0.34]
    return pd.DataFrame({'Uur': times, 'All-in prijs (€/kWh)': prices})

# --- Data ophalen ---
hw_metrics = fetch_local_homewizard_data()
df_prices = generate_fallback_prices()

# Toewijzen met veilige fallbacks
solar_production_kw = hw_metrics.get("solar_kw", 0.0)
net_grid_kw = hw_metrics.get("net_grid_kw", 0.0)
battery_soc = hw_metrics.get("battery_soc", 0)
battery_kw = hw_metrics.get("battery_kw", 0.0)
house_consumption_kw = max(0, solar_production_kw + net_grid_kw - battery_kw)

# ==========================================
# 3. JOUW JEROEN.NL CSV INLADEN & VERWERKEN
# ==========================================
@st.cache_data
def load_local_stroomanalyse(filename):
    if os.path.exists(filename):
        try:
            df = pd.read_csv(filename, sep=None, engine='python')
            df.columns = df.columns.str.strip()
            if 'DatumTijd' in df.columns:
                df['DatumTijd'] = pd.to_datetime(df['DatumTijd'])
            return df, None
        except Exception as e:
            return None, f"Fout bij lezen bestand: {e}"
    else:
        base = datetime.now()
        times = [base - timedelta(minutes=15 * x) for x in range(0, 96)]
        times.reverse()
        df_dummy = pd.DataFrame({
            'DatumTijd': times, 
            'Import': np.random.uniform(0.1, 1.2, 96),
            'Export': np.random.uniform(0.0, 2.0, 96), 
            'Opwek': np.sin(np.linspace(0, np.pi, 96)) * 2.5,
            'DatumTijdUTC': times
        })
        df_dummy.loc[df_dummy['Opwek'] < 0, 'Opwek'] = 0
        return df_dummy, f"Bestand '{filename}' niet gevonden. Dummy data geladen."

df_history, csv_warning = load_local_stroomanalyse(CSV_FILENAME)

if not csv_warning and df_history is not None:
    df_history['Werkelijk_Verbruik'] = df_history['Import'] + df_history['Opwek'] - df_history['Export']
    df_history['Werkelijk_Verbruik'] = df_history['Werkelijk_Verbruik'].clip(lower=0)

# ==========================================
# 4. SIDEBAR & VERBINDING STATUS
# ==========================================
st.sidebar.header("⚙️ Systeem Status")
st.sidebar.markdown("**Fysieke Hardware (Live):**")

# Waterdichte controle op foutmeldingen
hw_error = hw_metrics.get("error")
if hw_error:
    st.sidebar.error("🔴 HomeWizard P1: Offline")
    st.sidebar.warning(hw_error)
else:
    st.sidebar.success("🟢 HomeWizard P1 Hub: Live verbonden")

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
    fig_prices.update_layout(margin=dict(l=20, r=20, t=20), hovermode="x unified")
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

    fig_hist.update_layout(margin=dict(l=20, r=20, t=20), hovermode="x unified")
    st.plotly_chart(fig_hist, use_container_width=True)
