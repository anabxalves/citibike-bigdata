"""
Dashboard Operacional — Citibike ROI Engine
Frente: Economia Empresarial e Visualização

Execute dentro do Docker:  streamlit run /home/jovyan/work/src/dashboard.py
Ou localmente:             streamlit run src/dashboard.py
"""

import os
import json
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Citibike ROI Dashboard",
    page_icon="🚲",
    layout="wide",
)

BASE = os.path.join(os.path.dirname(__file__), "..", "dados", "gold")
ROI_DIR = os.path.join(BASE, "roi")


# ---------------------------------------------------------------------------
# CARREGAMENTO (cacheado para não reler a cada interação)
# ---------------------------------------------------------------------------
@st.cache_data
def load_summary() -> dict:
    with open(os.path.join(ROI_DIR, "roi_summary.json"), encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_rebalance() -> pd.DataFrame:
    return pd.read_parquet(os.path.join(ROI_DIR, "roi_rebalance_detail.parquet"))


@st.cache_data
def load_revenue() -> pd.DataFrame:
    return pd.read_parquet(os.path.join(ROI_DIR, "roi_revenue_detail.parquet"))


@st.cache_data
def load_stations() -> pd.DataFrame:
    return pd.read_parquet(os.path.join(BASE, "dim_stations"))


@st.cache_data
def load_hourly() -> pd.DataFrame:
    return pd.read_parquet(os.path.join(BASE, "agg_demand_hourly"))


summary   = load_summary()
df_reb    = load_rebalance()
df_rev    = load_revenue()
df_sta    = load_stations()
df_hourly = load_hourly()

# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.title("🚲 Citibike NYC — Painel de ROI Logístico")
st.caption(
    "Frente de Economia Empresarial e Visualização · Equipe 10 · CESAR School 2026.1"
)
st.divider()

# ---------------------------------------------------------------------------
# SEÇÃO 1 — KPI CARDS
# ---------------------------------------------------------------------------
st.subheader("Indicadores de Eficiência Logística")

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Taxa de Ruptura de Estoque",
    f"{summary['kpi_stockout_rate_pct']:.2f} %",
    help="% de janelas de pico onde o net_flow indicou estação esvaziando",
)
c2.metric(
    "Custo de Rebalanceamento / Viagem",
    f"$ {summary['kpi_rebalance_cost_per_trip_usd']:.4f}",
    help="Custo total de rebalanceamento dividido pelo total de partidas",
)
c3.metric(
    "Receita Recuperada pelo Modelo",
    f"$ {summary['kpi_recovered_revenue_usd']:,.0f}",
    delta=f"- $ {summary['kpi_potential_lost_revenue_usd'] - summary['kpi_recovered_revenue_usd']:,.0f} ainda perdidos",
    delta_color="inverse",
    help="Receita recuperada = aluguéis que seriam perdidos × acurácia do modelo",
)
c4.metric(
    "Rotatividade do Ativo",
    f"{summary['kpi_asset_turnover_trips_per_bike_per_day']:.3f}",
    help="Média de viagens por bicicleta por dia no período analisado",
)

st.divider()

# ---------------------------------------------------------------------------
# SEÇÃO 2 — ROI GERAL
# ---------------------------------------------------------------------------
st.subheader("ROI do Modelo Preditivo")

col_roi, col_meta = st.columns([2, 1])

with col_roi:
    acc = summary["params_used"]["model_accuracy"]
    labels = ["Economia em Rebalanceamento", "Receita Recuperada"]
    values = [
        summary["meta_savings_on_rebalance_usd"],
        summary["kpi_recovered_revenue_usd"],
    ]
    fig_pie = px.pie(
        names=labels,
        values=values,
        title=f"Composição do ROI Líquido  (modelo a {acc*100:.0f}% de acurácia)",
        color_discrete_sequence=["#1f77b4", "#2ca02c"],
        hole=0.45,
    )
    fig_pie.update_traces(textinfo="percent+label+value",
                          texttemplate="%{label}<br>$ %{value:,.0f}")
    st.plotly_chart(fig_pie, use_container_width=True)

with col_meta:
    st.markdown("#### Resumo do Período")
    st.markdown(f"- **Estações analisadas:** {summary['meta_total_stations']:,}")
    st.markdown(f"- **Bikes na frota:** {summary['meta_total_bikes_in_fleet']:,}")
    st.markdown(f"- **Dias no período:** {summary['meta_unique_days']:,}")
    st.markdown(f"- **Total de partidas:** {summary['meta_total_departures']:,}")
    st.markdown("---")
    st.markdown(f"- **Alertas WARNING:** {summary['meta_alerts_warning_planned']:,}")
    st.markdown(f"- **Alertas CRITICAL:** {summary['meta_alerts_critical_emergency']:,}")
    st.markdown(f"- **Custo total rebalanceamento:** $ {summary['meta_total_rebalance_cost_usd']:,.0f}")
    st.markdown("---")
    st.markdown(
        f"### 💰 ROI Líquido Total\n"
        f"# $ {summary['meta_net_roi_usd']:,.0f}"
    )

st.divider()

# ---------------------------------------------------------------------------
# SEÇÃO 3 — ALERTAS POR ESTAÇÃO
# ---------------------------------------------------------------------------
st.subheader("Alertas de Rebalanceamento por Estação")

# Top estações com mais alertas
alert_counts = (
    df_reb.groupby(["station_name", "rebalance_alert"])
    .size()
    .reset_index(name="count")
)
top_stations = (
    alert_counts.groupby("station_name")["count"]
    .sum()
    .nlargest(20)
    .index
)
alert_top = alert_counts[alert_counts["station_name"].isin(top_stations)]

color_map = {"WARNING": "#f0a500", "CRITICAL": "#d62728"}
fig_bar = px.bar(
    alert_top.sort_values("count", ascending=True),
    x="count",
    y="station_name",
    color="rebalance_alert",
    orientation="h",
    title="Top 20 Estações com Mais Alertas",
    labels={"count": "Nº de Alertas", "station_name": "Estação",
            "rebalance_alert": "Severidade"},
    color_discrete_map=color_map,
)
fig_bar.update_layout(height=550, yaxis=dict(tickfont=dict(size=11)))
st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# SEÇÃO 4 — STOCK-OUTS EM HORÁRIO DE PICO
# ---------------------------------------------------------------------------
st.subheader("Estações com Maior Perda de Receita em Pico")

rev_by_station = (
    df_rev.groupby("station_name")[["potential_lost_revenue_usd", "recovered_revenue_usd"]]
    .sum()
    .reset_index()
    .sort_values("potential_lost_revenue_usd", ascending=False)
    .head(15)
)
rev_by_station["ainda_perdido_usd"] = (
    rev_by_station["potential_lost_revenue_usd"] - rev_by_station["recovered_revenue_usd"]
)

fig_rev = go.Figure()
fig_rev.add_trace(go.Bar(
    name="Receita Recuperada",
    x=rev_by_station["station_name"],
    y=rev_by_station["recovered_revenue_usd"],
    marker_color="#2ca02c",
))
fig_rev.add_trace(go.Bar(
    name="Ainda Perdido",
    x=rev_by_station["station_name"],
    y=rev_by_station["ainda_perdido_usd"],
    marker_color="#d62728",
))
fig_rev.update_layout(
    barmode="stack",
    title="Receita Recuperada vs Ainda Perdida — Top 15 Estações Críticas",
    xaxis_tickangle=-40,
    yaxis_title="USD",
    height=480,
)
st.plotly_chart(fig_rev, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# SEÇÃO 5 — DEMANDA POR HORA (PERFIL DO DIA)
# ---------------------------------------------------------------------------
st.subheader("Perfil de Demanda ao Longo do Dia")

hourly_agg = (
    df_hourly.groupby("hour_of_day")[["departures", "arrivals"]]
    .mean()
    .reset_index()
)
fig_hour = px.line(
    hourly_agg,
    x="hour_of_day",
    y=["departures", "arrivals"],
    title="Média de Partidas e Chegadas por Hora do Dia",
    labels={"hour_of_day": "Hora", "value": "Média de Viagens", "variable": ""},
    markers=True,
    color_discrete_map={"departures": "#1f77b4", "arrivals": "#ff7f0e"},
)
fig_hour.update_layout(xaxis=dict(tickmode="linear", dtick=1))
st.plotly_chart(fig_hour, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# SEÇÃO 6 — BUSCA POR ESTAÇÃO
# ---------------------------------------------------------------------------
st.subheader("Detalhe por Estação")

all_stations = sorted(df_reb["station_name"].dropna().unique())
selected = st.selectbox("Selecione uma estação:", ["— todas —"] + list(all_stations))

if selected != "— todas —":
    df_sel_reb = df_reb[df_reb["station_name"] == selected]
    df_sel_rev = df_rev[df_rev["station_name"] == selected]

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**Alertas de rebalanceamento:** {len(df_sel_reb):,}")
        st.markdown(f"**Economia gerada:** $ {df_sel_reb['saving_usd'].sum():,.2f}")
        st.dataframe(
            df_sel_reb[["window_15min", "rebalance_alert", "net_flow", "saving_usd", "cost_usd"]]
            .sort_values("window_15min"),
            use_container_width=True,
            height=280,
        )
    with col_b:
        st.markdown(f"**Janelas de crise em pico:** {len(df_sel_rev):,}")
        st.markdown(f"**Receita recuperada:** $ {df_sel_rev['recovered_revenue_usd'].sum():,.2f}")
        st.dataframe(
            df_sel_rev[["window_15min", "net_flow", "estimated_lost_rides",
                         "potential_lost_revenue_usd", "recovered_revenue_usd"]]
            .sort_values("window_15min"),
            use_container_width=True,
            height=280,
        )
else:
    st.info("Selecione uma estação acima para ver o detalhamento.")

# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------
st.divider()
params = summary["params_used"]
st.caption(
    f"Parâmetros utilizados — "
    f"Caminhão emergência: $ {params['custo_caminhao_emergencia_usd']} · "
    f"Caminhão planejado: $ {params['custo_caminhao_planejado_usd']} · "
    f"Tarifa/aluguel: $ {params['receita_por_aluguel_usd']} · "
    f"Acurácia do modelo: {params['model_accuracy']*100:.0f}%"
)
