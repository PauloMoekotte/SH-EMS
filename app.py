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

@st.cache_data(ttl=1800)
def fetch_dynamic_prices():
    """Haalt actuele dynamische stroomprijzen op via de EnergyZero API (Nederland)"""
    today = datetime.now().strftime('%Y-%m-%d')
    url = f"https://api.energyzero.nl/v1/energyprices?fromDate={today}T00:00:00.000Z&tillDate={today}T23:59:59.999Z&interval=4&usageType=1&inclBtw=true"
    
    try:
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            prices_list = data.get('Prices', [])
            if prices_list:
                times = [f"{str(i).zfill(2)}:00" for i in range(len(prices_list))]
                prices = [p.get('price', 0.0) for p in prices_list]
                return pd.DataFrame({'Uur': times, 'All-in prijs (€/kWh)': prices}), "Live (EnergyZero API)"
    except Exception:
        pass
    
    # Fallback bij netwerkfouten
    times = [f"{str(i).zfill(2)}:00" for i in range(24)]
    prices = [0.22, 0.19, 0.19, 0.19, 0.22, 0.23, 0.23, 0.19, 0.13, 0.07, 0.05, 0.02, 0.02, 0.07, 0.16, 0.23, 0.25, 0.29, 0.28, 0.25, 0.24, 0.23, 0.22, 0.22]
    return pd.DataFrame({'Uur': times, 'All-in prijs (€/kWh)': prices}), "Fallback (Gecacht)"

# --- Data ophalen ---
hw_metrics = fetch_local_homewizard_data()
df_prices, price_source_status = fetch_dynamic_prices()

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
            
            # Jeroen.nl CSV export bevat waarden in Watt-uren (Wh) per 15-minuten interval.
            # Converteer Wh naar kWh als het gemiddelde > 5 is.
            for col in ['Import', 'Export', 'Opwek']:
                if col in df.columns:
                    if df[col].mean() > 5:
                        df[col] = df[col] / 1000.0

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

st.sidebar.markdown("**Marktprijzen Bron:**")
if "Live" in price_source_status:
    st.sidebar.success(f"🟢 {price_source_status}")
else:
    st.sidebar.warning(f"⚠️ {price_source_status}")

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
# 5. TABBLAD STRUCTUUR (TABS)
# ==========================================
tab1, tab2, tab3 = st.tabs([
    "⚡ Live Overzicht", 
    "💶 Dynamische Stroomprijzen", 
    "📊 Stroomanalyse"
])

# ------------------------------------------
# TAB 1: LIVE OVERZICHT
# ------------------------------------------
with tab1:
    st.subheader("⚡ Actuele Energie Status (Live HomeWizard P1)")
    
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
    
    # Systeem Samenvatting / Energie Balans
    st.subheader("💡 Actuele Stroombalans")
    col_bal1, col_bal2 = st.columns(2)
    with col_bal1:
        st.info(f"**Huidige Net Status:** {'⚠️ Stroomafname van net' if net_grid_kw >= 0 else '🟢 Teruglevering aan het net'}")
        st.write(f"- **Totaal opgewekt vermogen:** {solar_production_kw:.2f} kW")
        st.write(f"- **Direct eigen verbruik inschatting:** {min(solar_production_kw, house_consumption_kw):.2f} kW")
    with col_bal2:
        if battery_soc > 0:
            st.success(f"**Thuisbatterij:** {battery_soc}% geladen ({battery_kw:.2f} kW vermogen)")
        else:
            st.warning("**Thuisbatterij:** Geen actieve batterij-data of 0% lading")
        st.write(f"- **Huisverbruik op dit moment:** {house_consumption_kw:.2f} kW")

# ------------------------------------------
# TAB 2: DYNAMISCHE STROOMPRIJZEN
# ------------------------------------------
with tab2:
    st.subheader(f"💶 Dynamische Stroomprijzen Vandaag ({price_source_status})")
    
    # KPI's voor prijzen
    current_hour = datetime.now().hour
    curr_price = df_prices.iloc[current_hour]['All-in prijs (€/kWh)'] if current_hour < len(df_prices) else 0.0
    min_price = df_prices['All-in prijs (€/kWh)'].min()
    max_price = df_prices['All-in prijs (€/kWh)'].max()
    avg_price = df_prices['All-in prijs (€/kWh)'].mean()
    min_hour = df_prices.loc[df_prices['All-in prijs (€/kWh)'].idxmin()]['Uur']
    max_hour = df_prices.loc[df_prices['All-in prijs (€/kWh)'].idxmax()]['Uur']

    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    with p_col1:
        st.metric(label=f"Huidige Uurprijs ({current_hour}:00)", value=f"€{curr_price:.2f} / kWh")
    with p_col2:
        st.metric(label="Gemiddelde Prijs Vandaag", value=f"€{avg_price:.2f} / kWh")
    with p_col3:
        st.metric(label="Goedkoopste Uur", value=f"€{min_price:.2f} / kWh", delta=f"om {min_hour}", delta_color="inverse")
    with p_col4:
        st.metric(label="Duurste Uur", value=f"€{max_price:.2f} / kWh", delta=f"om {max_hour}", delta_color="normal")

    st.markdown("---")

    # Slim Verbruiksadvies
    prices_list = df_prices['All-in prijs (€/kWh)'].tolist()
    if len(prices_list) >= 3:
        window_sums = [sum(prices_list[i:i+3]) for i in range(len(prices_list)-2)]
        best_window_idx = int(np.argmin(window_sums))
        best_window_start = df_prices.iloc[best_window_idx]['Uur']
        best_window_end = df_prices.iloc[min(best_window_idx+3, len(df_prices)-1)]['Uur']
        best_window_avg = window_sums[best_window_idx] / 3.0

        st.subheader("💡 Slim Verbruiks- & Laadadvies")
        adv_col1, adv_col2 = st.columns(2)
        with adv_col1:
            st.success(
                f"**Beste 3-uurs venster (Wasmachine / EV / Accu laden):**\n\n"
                f"🕒 **{best_window_start} tot {best_window_end}** (Gemiddeld €{best_window_avg:.2f} / kWh)"
            )
        with adv_col2:
            if curr_price <= avg_price * 0.85:
                st.info("🟢 **Nu gunstig tarief!** Dit is een goed moment om apparaten in te schakelen.")
            elif curr_price >= avg_price * 1.15:
                st.warning("⚠️ **Piek-uur!** Probeer zwaar verbruik (wasmachine, droger) uit te stellen.")
            else:
                st.info("ℹ️ **Normaal tarief:** Prijs ligt rond het daggemiddelde.")

    st.markdown("---")

    # Grafiek dynamische stroomprijzen (volledige breedte)
    fig_prices = px.bar(
        df_prices, 
        x='Uur', 
        y='All-in prijs (€/kWh)', 
        color='All-in prijs (€/kWh)',
        color_continuous_scale='Viridis',
        title="Uurprijzen Overzicht Vandaag (€/kWh)"
    )
    # Verticale stippellijn en indicator voor het huidige uur (veilig voor categorische string x-as)
    current_hour_str = f"{str(current_hour).zfill(2)}:00"
    if current_hour < len(df_prices):
        fig_prices.add_shape(
            type="line",
            x0=current_hour_str,
            x1=current_hour_str,
            y0=0,
            y1=1,
            yref="paper",
            line=dict(color="#FF4B4B", width=2, dash="dash")
        )
        fig_prices.add_annotation(
            x=current_hour_str,
            y=curr_price,
            text="📍 Nu",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#FF4B4B",
            ax=0,
            ay=-30,
            font=dict(color="#FF4B4B", size=12, family="Arial")
        )

    fig_prices.update_layout(
        margin=dict(l=20, r=20, t=40, b=20), 
        hovermode="x unified",
        xaxis_title="Uur van de dag",
        yaxis_title="Prijs in € per kWh"
    )
    st.plotly_chart(fig_prices, use_container_width=True)

# ------------------------------------------
# TAB 3: STROOMANALYSE
# ------------------------------------------
with tab3:
    st.subheader("📊 Jouw Stroomanalyse Historie (Jeroen.nl CSV)")

    if df_history is not None and not df_history.empty:
        # Hulpkolommen voor datum-aggregatie
        df_work = df_history.copy()
        if 'DatumTijd' in df_work.columns and pd.api.types.is_datetime64_any_dtype(df_work['DatumTijd']):
            df_work['Jaar'] = df_work['DatumTijd'].dt.year
            df_work['MaandNum'] = df_work['DatumTijd'].dt.month
            df_work['Dag'] = df_work['DatumTijd'].dt.day
            df_work['JaarMaandStr'] = df_work['DatumTijd'].dt.strftime('%Y-%m')
            
            MONTH_NAMES_NL = {
                1: 'Januari', 2: 'Februari', 3: 'Maart', 4: 'April', 
                5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Augustus', 
                9: 'September', 10: 'Oktober', 11: 'November', 12: 'December'
            }
            df_work['MaandNaam'] = df_work['MaandNum'].map(MONTH_NAMES_NL)
            df_work['Label'] = df_work['MaandNaam'] + ' ' + df_work['Jaar'].astype(str)

        # Keuze voor weergave-modus (Granulariteit)
        view_mode = st.radio(
            "Granulariteit / Weergave:",
            ["🗓️ Maandelijks Totaaloverzicht", "🔍 Maand Selectie & Vorig Jaar Vergelijking", "📈 Gedetailleerd (15-minuten data)"],
            horizontal=True
        )

        st.markdown("---")

        # ----------------------------------------------------
        # OPTIE 1: MAANDELIJKS TOTAALOVERZICHT
        # ----------------------------------------------------
        if view_mode == "🗓️ Maandelijks Totaaloverzicht":
            st.markdown("##### 📅 Maandelijks Energieverbruik & Opwekking")
            
            # Groeperen per maand
            monthly_df = df_work.groupby(['Jaar', 'MaandNum', 'Label'], as_index=False)[
                ['Werkelijk_Verbruik', 'Opwek', 'Import', 'Export']
            ].sum().sort_values(by=['Jaar', 'MaandNum'])

            # Totale KPI's over de hele historie
            tot_verbruik = monthly_df['Werkelijk_Verbruik'].sum()
            tot_opwek = monthly_df['Opwek'].sum()
            tot_import = monthly_df['Import'].sum()
            tot_export = monthly_df['Export'].sum()

            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric(label="Totaal Werkelijk Verbruik", value=f"{tot_verbruik:.2f} kWh")
            with m_col2:
                st.metric(label="Totaal Zonne-opwek", value=f"{tot_opwek:.2f} kWh")
            with m_col3:
                st.metric(label="Totaal Net-Import", value=f"{tot_import:.2f} kWh")
            with m_col4:
                st.metric(label="Totaal Net-Export", value=f"{tot_export:.2f} kWh")

            st.markdown("---")

            fig_m = go.Figure()
            fig_m.add_trace(go.Bar(x=monthly_df['Label'], y=monthly_df['Werkelijk_Verbruik'], name='Werkelijk Verbruik', marker_color='#FF4B4B'))
            fig_m.add_trace(go.Bar(x=monthly_df['Label'], y=monthly_df['Opwek'], name='Opwekking (Zon)', marker_color='#00CC96'))
            fig_m.add_trace(go.Bar(x=monthly_df['Label'], y=monthly_df['Import'], name='Net-Import (P1)', marker_color='#FFA500'))
            fig_m.add_trace(go.Bar(x=monthly_df['Label'], y=monthly_df['Export'], name='Net-Export (Teruglevering)', marker_color='#1F77B4'))

            fig_m.update_layout(
                barmode='group',
                title="Totaal per Maand (kWh)",
                margin=dict(l=20, r=20, t=40, b=20),
                hovermode="x unified",
                xaxis_title="Maand",
                yaxis_title="Energie (kWh)"
            )
            st.plotly_chart(fig_m, use_container_width=True)

        # ----------------------------------------------------
        # OPTIE 2: MAAND SELECTIE & JAAR-OP-JAAR VERGELIJKING
        # ----------------------------------------------------
        elif view_mode == "🔍 Maand Selectie & Vorig Jaar Vergelijking":
            unique_months = df_work[['Jaar', 'MaandNum', 'Label']].drop_duplicates().sort_values(by=['Jaar', 'MaandNum'], ascending=False)
            month_labels = unique_months['Label'].tolist()

            sel_col1, sel_col2 = st.columns(2)
            with sel_col1:
                selected_label = st.selectbox("Selecteer Hoofdmaand om te analyseren:", month_labels, index=0)
            
            sel_row = unique_months[unique_months['Label'] == selected_label].iloc[0]
            sel_year = int(sel_row['Jaar'])
            sel_month = int(sel_row['MaandNum'])

            # 1. Probeer dezelfde maand vorig jaar (YoY)
            prev_year_label = f"{MONTH_NAMES_NL[sel_month]} {sel_year - 1}"
            
            # 2. Probeer de vorige maand als fallback
            prev_m_num = 12 if sel_month == 1 else sel_month - 1
            prev_m_year = sel_year - 1 if sel_month == 1 else sel_year
            prev_month_label = f"{MONTH_NAMES_NL[prev_m_num]} {prev_m_year}"

            available_comp_labels = [l for l in month_labels if l != selected_label]

            if prev_year_label in available_comp_labels:
                default_comp = prev_year_label
                comp_info = f"🟢 Vorig jaar ({prev_year_label}) automatisch geselecteerd."
            elif prev_month_label in available_comp_labels:
                default_comp = prev_month_label
                comp_info = f"ℹ️ {prev_year_label} staat niet in de CSV. {prev_month_label} (vorige maand) gekozen."
            else:
                default_comp = available_comp_labels[0] if available_comp_labels else selected_label
                comp_info = "ℹ️ Vergelijkingsmaand geselecteerd uit beschikbare data."

            default_idx = available_comp_labels.index(default_comp) if default_comp in available_comp_labels else 0

            with sel_col2:
                comp_label = st.selectbox("Selecteer Vergelijkingsmaand:", available_comp_labels, index=default_idx)
                st.caption(comp_info)


            # Filter data voor hoofdmaand
            df_main = df_work[(df_work['Jaar'] == sel_year) & (df_work['MaandNum'] == sel_month)]
            df_main_daily = df_main.groupby('Dag', as_index=False)[
                ['Werkelijk_Verbruik', 'Opwek', 'Import', 'Export']
            ].sum()

            # Filter data voor vergelijkingsmaand
            comp_row = unique_months[unique_months['Label'] == comp_label].iloc[0]
            comp_year = int(comp_row['Jaar'])
            comp_month = int(comp_row['MaandNum'])

            df_comp = df_work[(df_work['Jaar'] == comp_year) & (df_work['MaandNum'] == comp_month)]
            df_comp_daily = df_comp.groupby('Dag', as_index=False)[
                ['Werkelijk_Verbruik', 'Opwek', 'Import', 'Export']
            ].sum()

            # KPI Vergelijking
            main_verbruik = df_main['Werkelijk_Verbruik'].sum()
            comp_verbruik = df_comp['Werkelijk_Verbruik'].sum()
            verbruik_delta = ((main_verbruik - comp_verbruik) / comp_verbruik * 100) if comp_verbruik > 0 else 0.0

            main_opwek = df_main['Opwek'].sum()
            comp_opwek = df_comp['Opwek'].sum()
            opwek_delta = ((main_opwek - comp_opwek) / comp_opwek * 100) if comp_opwek > 0 else 0.0

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            with kpi1:
                st.metric(
                    label=f"Verbruik ({selected_label})", 
                    value=f"{main_verbruik:.2f} kWh", 
                    delta=f"{verbruik_delta:+.1f}% vs {comp_label}",
                    delta_color="inverse"
                )
            with kpi2:
                st.metric(
                    label=f"Opwek ({selected_label})", 
                    value=f"{main_opwek:.2f} kWh", 
                    delta=f"{opwek_delta:+.1f}% vs {comp_label}"
                )
            with kpi3:
                st.metric(label=f"Net-Import ({selected_label})", value=f"{df_main['Import'].sum():.2f} kWh")
            with kpi4:
                st.metric(label=f"Net-Export ({selected_label})", value=f"{df_main['Export'].sum():.2f} kWh")

            st.markdown("---")

            # GRAFIEK 1: Gekozen Maand
            st.markdown(f"##### 📊 Dagelijks Verloop: **{selected_label}**")
            fig_main = go.Figure()
            fig_main.add_trace(go.Scatter(x=df_main_daily['Dag'], y=df_main_daily['Werkelijk_Verbruik'], name='Werkelijk Verbruik', line=dict(color='#FF4B4B', width=2)))
            fig_main.add_trace(go.Scatter(x=df_main_daily['Dag'], y=df_main_daily['Opwek'], name='Opwekking (Zon)', line=dict(color='#00CC96', width=1.5), fill='tozeroy'))
            fig_main.add_trace(go.Scatter(x=df_main_daily['Dag'], y=df_main_daily['Import'], name='Net-Import', line=dict(color='#FFA500', width=1, dash='dash')))
            fig_main.add_trace(go.Scatter(x=df_main_daily['Dag'], y=df_main_daily['Export'], name='Net-Export', line=dict(color='#1F77B4', width=1, dash='dot')))

            fig_main.update_layout(
                title=f"Dagelijks Energieverloop - {selected_label}",
                margin=dict(l=20, r=20, t=40, b=20),
                hovermode="x unified",
                xaxis_title="Dag van de maand",
                yaxis_title="Energie (kWh)"
            )
            st.plotly_chart(fig_main, use_container_width=True)

            st.markdown("---")

            # GRAFIEK 2: Vergelijkingsmaand (Onder de hoofdgrafiek)
            st.markdown(f"##### 📊 Vergelijkingsmaand: **{comp_label}** (Ter vergelijking)")
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Scatter(x=df_comp_daily['Dag'], y=df_comp_daily['Werkelijk_Verbruik'], name='Werkelijk Verbruik', line=dict(color='#FF7777', width=2)))
            fig_comp.add_trace(go.Scatter(x=df_comp_daily['Dag'], y=df_comp_daily['Opwek'], name='Opwekking (Zon)', line=dict(color='#33E0AD', width=1.5), fill='tozeroy'))
            fig_comp.add_trace(go.Scatter(x=df_comp_daily['Dag'], y=df_comp_daily['Import'], name='Net-Import', line=dict(color='#FFC04D', width=1, dash='dash')))
            fig_comp.add_trace(go.Scatter(x=df_comp_daily['Dag'], y=df_comp_daily['Export'], name='Net-Export', line=dict(color='#52A0D8', width=1, dash='dot')))

            fig_comp.update_layout(
                title=f"Dagelijks Energieverloop - {comp_label}",
                margin=dict(l=20, r=20, t=40, b=20),
                hovermode="x unified",
                xaxis_title="Dag van de maand",
                yaxis_title="Energie (kWh)"
            )
            st.plotly_chart(fig_comp, use_container_width=True)

        # ----------------------------------------------------
        # OPTIE 3: GEDETAILLEERD (15-MINUTEN DATA & DATUMFILTER)
        # ----------------------------------------------------
        else:
            min_date = df_work['DatumTijd'].min().date()
            max_date = df_work['DatumTijd'].max().date()
            
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                start_selected = st.date_input("Vanaf datum", value=min_date, min_value=min_date, max_value=max_date)
            with f_col2:
                end_selected = st.date_input("Tot en met datum", value=max_date, min_value=min_date, max_value=max_date)
            
            mask = (df_work['DatumTijd'].dt.date >= start_selected) & (df_work['DatumTijd'].dt.date <= end_selected)
            df_filtered = df_work.loc[mask]

            tot_verbruik = df_filtered['Werkelijk_Verbruik'].sum()
            tot_opwek = df_filtered['Opwek'].sum()
            tot_import = df_filtered['Import'].sum()
            tot_export = df_filtered['Export'].sum()
            direct_eigen_verbruik = max(0.0, tot_opwek - tot_export)

            a_col1, a_col2, a_col3, a_col4 = st.columns(4)
            with a_col1:
                st.metric(label="Totaal Werkelijk Verbruik", value=f"{tot_verbruik:.2f} kWh")
            with a_col2:
                st.metric(label="Totaal Zonne-opwek", value=f"{tot_opwek:.2f} kWh")
            with a_col3:
                st.metric(label="Totaal Net-Import", value=f"{tot_import:.2f} kWh")
            with a_col4:
                st.metric(label="Totaal Net-Export", value=f"{tot_export:.2f} kWh")

            st.markdown("---")

            chart_col1, chart_col2 = st.columns([2, 1])

            with chart_col1:
                st.markdown("##### 📈 Verloop van Verbruik en Opwekking (15-minuten data)")
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Scatter(x=df_filtered['DatumTijd'], y=df_filtered['Werkelijk_Verbruik'], name='Werkelijk Verbruik', line=dict(color='#FF4B4B', width=2)))
                fig_hist.add_trace(go.Scatter(x=df_filtered['DatumTijd'], y=df_filtered['Opwek'], name='Opwekking (Zon)', line=dict(color='#00CC96', width=1.5), fill='tozeroy'))
                fig_hist.add_trace(go.Scatter(x=df_filtered['DatumTijd'], y=df_filtered['Import'], name='Net-Import (P1)', line=dict(color='#FFA500', width=1, dash='dash')))
                fig_hist.add_trace(go.Scatter(x=df_filtered['DatumTijd'], y=df_filtered['Export'], name='Net-Export (Teruglevering)', line=dict(color='#1F77B4', width=1, dash='dot')))

                fig_hist.update_layout(
                    margin=dict(l=20, r=20, t=20, b=20), 
                    hovermode="x unified",
                    xaxis_title="Datum / Tijd",
                    yaxis_title="Energie (kWh)"
                )
                st.plotly_chart(fig_hist, use_container_width=True)

            with chart_col2:
                st.markdown("##### 🍕 Energieverdeling")
                pie_labels = ['Direct Eigen Verbruik', 'Net-Import', 'Net-Export']
                pie_values = [direct_eigen_verbruik, tot_import, tot_export]
                
                fig_pie = px.pie(
                    names=pie_labels, 
                    values=pie_values,
                    color=pie_labels,
                    color_discrete_map={
                        'Direct Eigen Verbruik': '#00CC96',
                        'Net-Import': '#FF4B4B',
                        'Net-Export': '#1F77B4'
                    },
                    hole=0.4
                )
                fig_pie.update_layout(margin=dict(l=10, r=10, t=20, b=20))
                st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.warning("Geen historische data beschikbaar om te analyseren.")



