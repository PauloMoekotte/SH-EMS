import asyncio
import requests
import goodwe
import json
from mcp.server.fastmcp import FastMCP
from mcp import ClientSession
from mcp.client.sse import sse_client

# Initialiseer de lokale MCP server voor je dashboard
mcp = FastMCP("Thuis-Energie-Gateway")

# CONFIGURATIE HARDWARE & JEROEN.NL
GOODWE_INVERTER_IP = "192.168.1.123"
HOMEWIZARD_P1_IP = "192.168.1.150"

# Het toegangstoken dat hoort bij de koppeling op jeroen.nl/account/data/mcp
JEROEN_ACCOUNT_TOKEN = "JOUW_JEROEN_NL_ACCESS_TOKEN" 

@mcp.tool()
async def get_complete_energy_status() -> dict:
    """
    Combineert lokale hardware data (GoodWe & HomeWizard) met de officiële 
    publieke en persoonlijke markttarieven/analyses van de Jeroen.nl MCP servers.
    """
    data_output = {}

    # 1. LOKALE HARDWARE UITLEZEN
    try:
        inverter = await goodwe.connect(GOODWE_INVERTER_IP)
        runtime_data = await inverter.read_runtime_data()
        data_output["solar_production_kw"] = runtime_data.get('ppv', 0) / 1000.0
        data_output["battery_soc"] = runtime_data.get('battery_soc', 0)
        data_output["battery_power_kw"] = runtime_data.get('p_battery', 0) / 1000.0
    except:
        data_output["solar_production_kw"], data_output["battery_soc"], data_output["battery_power_kw"] = 0.0, 0, 0.0

    try:
        res = requests.get(f"http://{HOMEWIZARD_P1_IP}/api/v1/data", timeout=2).json()
        data_output["net_grid_kw"] = res.get('active_power_w', 0) / 1000.0
    except:
        data_output["net_grid_kw"] = 0.0

    data_output["house_consumption_kw"] = max(0, data_output["solar_production_kw"] + data_output["net_grid_kw"] - data_output["battery_power_kw"])

    # 2. VERBINDING MAKEN MET JEROEN.NL MCP (PUBLIEK)
    try:
        async with sse_client("https://jeroen.nl") as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                # Vraag de tool op die actuele dynamische prijzen levert
                prices_res = await session.call_tool("get_stroomprijzen_vandaag")
                data_output["jeroen_public_prices"] = json.loads(prices_res.content[0].text)
    except Exception as e:
        data_output["jeroen_public_prices_error"] = str(e)

    # 3. VERBINDING MAKEN MET JEROEN.NL MCP (PERSOONLIJK ACCOUNT)
    try:
        headers = {"Authorization": f"Bearer {JEROEN_ACCOUNT_TOKEN}"}
        async with sse_client("https://jeroen.nl/account", headers=headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                # Vraag persoonlijke analyses en contractgegevens op
                profile_res = await session.call_tool("get_account_samenvatting")
                data_output["jeroen_personal_profile"] = json.loads(profile_res.content[0].text)
    except Exception as e:
        data_output["jeroen_personal_profile_error"] = str(e)

    return data_output

if __name__ == "__main__":
    mcp.run(transport='stdio')
