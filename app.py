import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import asyncio
import json
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# 1. PAGINA CONFIGURATIE
st.set_page_config(
    page_title="Jeroen.nl MCP Dashboard",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Connected Energy Management Dashboard")
st.markdown("Aangedreven door lokale hardware metingen en het officiële **Jeroen.nl Model Context Protocol**.")

# 2. COMMUNICATIE VIA LOKALE MCP GATEWAY
async def fetch_all_mcp_data():
    server_params = StdioServerParameters(command="python", args=["mcp_server.py"])
    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool("get_complete_energy_status")
                if response.content and len(response.content) > 0:
                    return json.loads(response.content[0].text), None
                return None, "Geen response ontvangen van de lokale gateway."
    except Exception as e:
        return None, str(e)

# Run de asynchrone client loop binnen Streamlit
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

mcp_data, mcp_error = loop.run_until_complete(fetch_all_mcp_data())

if mcp_error or not mcp_data:
    st.error(f"❌ Fout bij het laden van de MCP Gateway: {mcp_error}")
    # Harde fallbacks om crashen te voorkomen
    mcp_data = {
        "house_consumption_kw": 0.0, "solar_production_kw": 0.0, "net_grid_kw": 0.0,
        "battery_soc": 0, "battery_power_kw": 0.0, "jeroen_public_prices": {}, "jeroen_personal_profile": {}
    }

# Data toewijzen
house_consumption = mcp_data.get("house_consumption_kw", 0.0)
solar_production = mcp_data.get("solar_production_kw", 0.0)
net_grid = mcp_data.get("net_grid_kw", 0.0)
battery_soc = mcp_data.get("battery_soc", 0)
battery_power = mcp_data.get("battery_power_kw", 0.0)

# ==========================================
# 3. SIDEBAR PROFIEL EN VERBINDINGEN
# ==========================================
st.sidebar.header("⚙️ MCP Server Status")

if "jeroen_personal_profile_error" in mcp_data:
    st.sidebar.error("🔴 Jeroen.nl Account: Niet verbonden")
else:
    st.sidebar.success("🟢 Jeroen.nl Account: Live")

# Toon profieldata uit je Jeroen.nl account als deze geladen is
profile = mcp_data.get("jeroen_personal_profile", {})
if profile:
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"👤 **Leverancier:** {profile.get('contract', {}).get('aanbieder', 'Dynamisch')}")
    st.sidebar.markdown(f"🏆 **Energiepunten:** {profile.get('energiepunten', 0)}")

if st.sidebar.button("🔄 Ververs alle data"):
    st.rerun()

# ==========================================
# 4. LIVE METRICS RIJ
# ==========================================
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Live Huisverbruik", value=f"{house_consumption:.2f} kW")
with col2:
    st.metric(label="Live GoodWe Opwekking", value=f"{solar_production:.2f} kW")
with col3:
    grid_label = "Net-Import (P1)" if net_grid >= 0 else "Net-Export (Teruglevering)"
    st.metric(label=grid_label, value=f"{abs(net_grid):.2f} kW")
with col4:
    st.metric(label="Thuisbatterij Status", value=f"{battery_soc}%", delta=f"{battery_power:.2f} kW")

st.markdown("---")

# ==========================================
# 5. GRAFIEK: DYNAMISCHE PRIJZEN (JEROEN.NL PUBLIEK)
# ==========================================
st.subheader("📈 Actuele Marktprijzen (Jeroen.nl Publieke MCP Data)")

public_prices = mcp_data.get("jeroen_public_prices", {})
if public_prices and "prijzen" in public_prices:
    df_prices = pd.DataFrame(public_prices["prijzen"])
else:
    # Generieke fallback-curve mocht de API-rate limit bereikt zijn
    base_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    times = [base_time + timedelta(hours=i) for i in range(24)]
    prices = [0.25, 0.24, 0.22, 0.23, 0.25, 0.28, 0.31, 0.29, 0.22, 0.15, 0.10, 0.04, 0.01, 0.03, 0.08, 0.14, 0.21, 0.32, 0.35, 0.32, 0.29, 0.28, 0.26, 0.25]
    df_prices = pd.DataFrame({'Tijdstip': times, 'Stroomprijs (€/kWh)': prices})

fig_prices = px.line(
    df_prices, 
    x='Tijdstip', 
    y='Stroomprijs (€/kWh)', 
    color_discrete_sequence=['#00CC96']
)
fig_prices.update_layout(margin=dict(l=20, r=20, t=20, b=20), hovermode="x unified")
st.plotly_chart(fig_prices, use_container_width=True)

st.caption("Bron: jeroen.nl") # Verplichte bronvermelding conform de voorwaarden
