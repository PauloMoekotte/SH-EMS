import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import asyncio
import goodwe
import requests

# ==========================================
# 1. PAGINA CONFIGURATIE & INSTELLINGEN
# ==========================================
st.set_page_config(
    page_title="Energy Management Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ⚠️ PAS HIER JOUW LOKALE IP-ADRESSEN AAN:
GOODWE_INVERTER_IP = "192.168.1.123" 
HOMEWIZARD_P1_IP = "192.168.1.150"  # Het IP-adres van je HomeWizard P1-meter

st.title("⚡ Energy Management & Optimization Dashboard")
st.markdown("Monitor live energieverbruik en zonne-opwekking direct via je apparaten.")

# ==========================================
# 2. API & HARDWARE INTEGRATIE
# ==========================================

async def fetch_local_goodwe_data():
    """Maakt live verbinding met de GoodWe omvormer via het lokale netwerk (UDP poort 8899)"""
    try:
        inverter = await goodwe.connect(GOODWE_INVERTER_IP)
        runtime_data = await inverter.read_runtime_data()
        
        solar_kw = runtime_data.get('ppv', 0) / 1000.0 # Watt naar kW
        battery_soc = runtime_data.get('battery_soc', 0)
        battery_p = runtime_data.get('p_battery', 0) / 1000.0
        
        return {
            "solar_power_kw": solar_kw,
            "battery_soc": battery_soc,
            "battery_power_kw": battery_p,
            "error": None
        }
    except Exception as e:
        return {
            "solar_power_kw": 0.0,
            "battery_soc": 0.0,
            "battery_power_kw": 0.0,
            "error": str(e)
        }

def get_live_homewizard_p1():
    """Haalt actueel netverbruik rechtstreeks op uit de HomeWizard P1 Lokale API"""
    url = f"http://{HOMEWIZARD_P1_IP}/api/v1/data"
    try:
        # Vraag JSON data op van de P1 meter
        response = requests.get(url, timeout=3).json()
        
        # 'active_power_w' geeft het netto vermogen in Watt
        # Positief = stroom importeren van het net, Negatief = stroom terugleveren
        net_grid_w = response.get('active_power_w', 0)
        
        return {
            "net_grid_kw": net_grid_w / 1000.0, # Watt naar kW
            "error": None
        }
    except Exception as e:
        return {
            "net_grid_kw": 0.0,
            "error": str(e)
        }

# Activeren van de asynchrone netwerk-loop voor de GoodWe
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

goodwe_data = loop.run_until_complete(fetch_local_goodwe_data())

# HomeWizard P1 data ophalen
p1_data = get_live_homewizard_p1()

# Live variabelen toewijzen
net_grid_kw = p1_data["net_grid_kw"]
solar_production_kw = goodwe_data["solar_power_kw"]
battery_soc = goodwe_data["battery_soc"]
battery_power_kw = goodwe_data["battery_power_kw"]

# Live berekening van het werkelijke energieverbruik in het huis:
# Huisverbruik = Zonne-energie + Netimport (of min netexport) - Batterijlading
house_consumption_kw = max(0, solar_production_kw + net_grid_kw - battery_power_kw)


# ==========================================
# 3. SIDEBAR & APPARATEN STATUS
# ==========================================
st.sidebar.header("⚙️ Dashboard Instellingen")
tarief_type = st.sidebar.selectbox("Tarief Type", ["Dynamisch (Uur)", "Vast Tarief", "Piek/Dal"])
st.sidebar.markdown("---")

# Statusmelding GoodWe
if goodwe_data["error"]:
    st.sidebar.error(f"🔴 GoodWe Omvormer: Offline\n({goodwe_data['error']})")
else:
    st.sidebar.success("🟢 GoodWe Omvormer: Verbonden")

# Statusmelding HomeWizard P1
if p1_data["error"]:
    st.sidebar.error(f"🔴 HomeWizard P1: Offline\n({p1_data['error']})")
else:
    st.sidebar.success("🟢 HomeWizard P1: Verbonden")

if st.sidebar.button("🔄 Nu Verversen"):
    st.rerun()


# ==========================================
# 4. TREND DATA SIMULATIE (VOOR GRAFIEKEN)
# ==========================================
@st.cache_data
def generate_historical_trend(live_solar):
    base = datetime.today()
    date_list = [base - timedelta(minutes=15 * x) for x in range(0, 96)]
    date_list.reverse()
    np.random.seed(42)
    
    verbruik = np.random.uniform(1.2, 3.5, 96)
    opwekking = np.zeros(96)
    opwekking[28:76] = np.sin(np.linspace(0, np.pi, 48)) * max(live_solar, 3.0)
    
    return pd.DataFrame({
        'Tijdstip': date_list,
        'Verbruik (kW)': verbruik,
        'Zonne-energie (kW)': opwekking,
        'Batterij SoC (%)': np.clip(50 + np.cumsum(opwekking - verbruik) * 5, 10, 100)
    })

df_history = generate_historical_trend(solar_production_kw)


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
    st.metric(label="Thuisbatterij Status", value=f"{battery_soc}%", delta=f"{battery_power_kw:.2f} kW")

st.markdown("---")


# ==========================================
# 6. VISUALISATIES (PLOTLY GRAFIEKEN)
# ==========================================
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📊 Energiebalans Vandaag (Trend)")
    fig_balance = go.Figure()
    fig_balance.add_trace(go.Scatter(x=df_history['Tijdstip'], y=df_history['Verbruik (kW)'], name='Verbruik (kW)', line=dict(color='#FF4B4B', width=2)))
    fig_balance.add_trace(go.Scatter(x=df_history['Tijdstip'], y=df_history['Zonne-energie (kW)'], name='Zon-productie (kW)', line=dict(color='#00CC96', width=2), fill='tozeroy'))
    fig_balance.update_layout(
        margin=dict(l=20, r=20, t=30, b=20), 
        hovermode="x unified", 
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_balance, use_container_width=True)

with col_right:
    st.subheader("🔋 Batterij State of Charge (Trend)")
    fig_soc = px.area(df_history, x='Tijdstip', y='Batterij SoC (%)', color_discrete_sequence=['#AB63FA'])
    fig_soc.update_layout(
        margin=dict(l=20, r=20, t=30, b=20), 
        yaxis_range=
    )
    st.plotly_chart(fig_soc, use_container_width=True)
