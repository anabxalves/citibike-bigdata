"""
ROI Engine — Citibike Big Data (AV2)
Frente: Economia Empresarial e Visualização — Victor Hora

Responde: "Quanto dinheiro economizamos quando o modelo acerta?"

Entradas  : tabelas da Gold Layer (demand_rolling_avg, agg_station_balance,
            agg_demand_hourly, dim_stations)
Saídas    : roi_summary.json  +  roi_detail.parquet  (em dados/gold/roi/)
"""

import os
import json
import pandas as pd

# ---------------------------------------------------------------------------
# PARÂMETROS DE NEGÓCIO (ajustáveis conforme dados reais do Citi Bike)
# ---------------------------------------------------------------------------
PARAMS = {
    # Custos logísticos
    "custo_caminhao_emergencia_usd": 350.00,   # rebalanceamento não planejado
    "custo_caminhao_planejado_usd":  130.00,   # rebalanceamento com antecedência
    # Receita por aluguel
    "receita_por_aluguel_usd": 4.50,           # tarifa média por viagem Citi Bike
    # Acurácia do modelo preditivo (será substituída pelo valor real na AV2)
    "model_accuracy": 0.80,
    # Limiar de net_flow negativo para considerar "crise iminente"
    "net_flow_crisis_threshold": -3,
    # Limiar de cumulative_balance para acionar alerta diário
    "cumulative_balance_alert_threshold": -5,
}

# ---------------------------------------------------------------------------
# CAMINHOS
# ---------------------------------------------------------------------------
BASE = os.path.join(os.path.dirname(__file__), "..", "dados", "gold")
OUT_DIR = os.path.join(BASE, "roi")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# CARREGAMENTO
# ---------------------------------------------------------------------------
def load_tables() -> dict[str, pd.DataFrame]:
    tables = {
        "demand_rolling": pd.read_parquet(os.path.join(BASE, "demand_rolling_avg")),
        "station_balance": pd.read_parquet(os.path.join(BASE, "agg_station_balance")),
        "demand_hourly": pd.read_parquet(os.path.join(BASE, "agg_demand_hourly")),
        "dim_stations": pd.read_parquet(os.path.join(BASE, "dim_stations")),
    }
    return tables


# ---------------------------------------------------------------------------
# 1. ANÁLISE DE REBALANCEAMENTOS
#    Para cada janela de 15min com rebalance_alert=True, o modelo detectou
#    o problema com antecedência. O ROI vem da diferença entre o custo
#    de uma intervenção PLANEJADA vs uma EMERGÊNCIA.
# ---------------------------------------------------------------------------
def compute_rebalance_roi(df_rolling: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Retorna um DataFrame com o ROI de cada evento de rebalanceamento detectado.
    rebalance_alert tem valores: 'OK' | 'WARNING' | 'CRITICAL'
    CRITICAL → custo de emergência; WARNING → custo planejado (modelo antecipou).
    """
    alerts = df_rolling[df_rolling["rebalance_alert"].isin(["WARNING", "CRITICAL"])].copy()

    accuracy = params["model_accuracy"]
    cost_emergency = params["custo_caminhao_emergencia_usd"]
    cost_planned = params["custo_caminhao_planejado_usd"]

    # WARNING = modelo detectou com antecedência → intervenção planejada
    # CRITICAL = situação chegou ao limite → emergência (modelo não antecipou a tempo)
    # Aplicamos a acurácia para simular a taxa real de acerto dentro dos WARNINGs
    warning_mask = alerts["rebalance_alert"] == "WARNING"
    critical_mask = alerts["rebalance_alert"] == "CRITICAL"

    saving_per_warning = cost_emergency - cost_planned  # economia por ter antecipado

    alerts["saving_usd"] = 0.0
    alerts["cost_usd"] = 0.0
    alerts["event_type"] = "rebalance_ok"

    # WARNINGs: modelo antecipou → economia (ponderada pela acurácia)
    alerts.loc[warning_mask, "saving_usd"] = saving_per_warning * accuracy
    alerts.loc[warning_mask, "cost_usd"] = cost_planned
    alerts.loc[warning_mask, "event_type"] = "rebalance_predicted"

    # CRITICALs: emergência → custo cheio, sem economia
    alerts.loc[critical_mask, "saving_usd"] = 0.0
    alerts.loc[critical_mask, "cost_usd"] = cost_emergency
    alerts.loc[critical_mask, "event_type"] = "rebalance_emergency"

    return alerts[["station_id", "station_name", "window_15min", "is_peak_hour",
                   "net_flow", "rebalance_alert", "event_type", "saving_usd", "cost_usd"]]


# ---------------------------------------------------------------------------
# 2. ANÁLISE DE RECEITA RECUPERADA (STOCK-OUTS EVITADOS)
#    Janelas de pico onde net_flow foi muito negativo = estação esvaziando.
#    Cada unidade de net_flow negativo em horário de pico ≈ 1 aluguel perdido.
#    O modelo, quando acerta, recupera essa receita.
# ---------------------------------------------------------------------------
def compute_revenue_recovery(df_rolling: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Retorna um DataFrame estimando a receita recuperada por janela de crise.
    """
    threshold = params["net_flow_crisis_threshold"]
    revenue_per_ride = params["receita_por_aluguel_usd"]
    accuracy = params["model_accuracy"]

    crisis = df_rolling[
        (df_rolling["net_flow"] <= threshold) & df_rolling["is_peak_hour"]
    ].copy()

    # Viagens perdidas estimadas = magnitude do déficit no net_flow
    crisis["estimated_lost_rides"] = crisis["net_flow"].abs()

    # Receita potencial perdida (sem modelo)
    crisis["potential_lost_revenue_usd"] = (
        crisis["estimated_lost_rides"] * revenue_per_ride
    )

    # Receita efetivamente recuperada (modelo acerta accuracy% dos casos)
    crisis["recovered_revenue_usd"] = (
        crisis["potential_lost_revenue_usd"] * accuracy
    )

    crisis["event_type"] = "stockout_crisis"

    return crisis[["station_id", "station_name", "window_15min", "is_peak_hour",
                   "net_flow", "event_type",
                   "estimated_lost_rides",
                   "potential_lost_revenue_usd",
                   "recovered_revenue_usd"]]


# ---------------------------------------------------------------------------
# 3. KPIs DE EFICIÊNCIA LOGÍSTICA
# ---------------------------------------------------------------------------
def compute_kpis(
    df_rolling: pd.DataFrame,
    df_balance: pd.DataFrame,
    df_hourly: pd.DataFrame,
    df_stations: pd.DataFrame,
    df_rebalance: pd.DataFrame,
    df_revenue: pd.DataFrame,
    params: dict,
) -> dict:
    """
    Calcula os 4 KPIs de negócio definidos no projeto.
    """
    # --- 1. Taxa de Ruptura de Estoque (Stock-out Rate) ---
    peak_windows = df_rolling[df_rolling["is_peak_hour"]]
    crisis_windows = peak_windows[
        peak_windows["net_flow"] <= params["net_flow_crisis_threshold"]
    ]
    stockout_rate = (
        len(crisis_windows) / len(peak_windows) * 100 if len(peak_windows) > 0 else 0
    )

    # --- 2. Custo de Rebalanceamento por Viagem ---
    n_warnings = (df_rolling["rebalance_alert"] == "WARNING").sum()
    n_criticals = (df_rolling["rebalance_alert"] == "CRITICAL").sum()
    total_alerts = n_warnings + n_criticals
    # WARNINGs = modelo antecipou → custo planejado; CRITICALs = emergência
    total_rebalance_cost = (
        n_warnings * params["custo_caminhao_planejado_usd"]
        + n_criticals * params["custo_caminhao_emergencia_usd"]
    )
    n_planned = int(n_warnings)
    n_missed = int(n_criticals)
    total_departures = df_rolling["departures"].sum()
    cost_per_trip = (
        total_rebalance_cost / total_departures if total_departures > 0 else 0
    )

    # --- 3. Receita Potencial Recuperada ---
    total_recovered = df_revenue["recovered_revenue_usd"].sum()
    total_potential_lost = df_revenue["potential_lost_revenue_usd"].sum()

    # --- 4. Índice de Rotatividade do Ativo ---
    total_bikes = df_stations["capacity"].sum()
    unique_days = df_hourly["date"].nunique()
    trips_per_day = total_departures / unique_days if unique_days > 0 else 0
    asset_turnover = trips_per_day / total_bikes if total_bikes > 0 else 0

    # --- Economia total gerada pelo modelo ---
    total_savings_rebalance = df_rebalance["saving_usd"].sum()
    net_savings = total_savings_rebalance + total_recovered

    return {
        "kpi_stockout_rate_pct": round(stockout_rate, 2),
        "kpi_rebalance_cost_per_trip_usd": round(cost_per_trip, 4),
        "kpi_recovered_revenue_usd": round(total_recovered, 2),
        "kpi_potential_lost_revenue_usd": round(total_potential_lost, 2),
        "kpi_asset_turnover_trips_per_bike_per_day": round(asset_turnover, 3),
        "meta_total_rebalance_alerts": int(total_alerts),
        "meta_alerts_warning_planned": int(n_planned),
        "meta_alerts_critical_emergency": int(n_missed),
        "meta_total_rebalance_cost_usd": round(total_rebalance_cost, 2),
        "meta_savings_on_rebalance_usd": round(total_savings_rebalance, 2),
        "meta_net_roi_usd": round(net_savings, 2),
        "meta_total_departures": int(total_departures),
        "meta_unique_days": int(unique_days),
        "meta_total_stations": int(df_stations.shape[0]),
        "meta_total_bikes_in_fleet": int(total_bikes),
        "params_used": params,
    }


# ---------------------------------------------------------------------------
# RELATÓRIO TEXTUAL
# ---------------------------------------------------------------------------
def print_report(kpis: dict) -> None:
    sep = "=" * 62
    print(f"\n{sep}")
    print("  CITIBIKE ROI ENGINE - RELATORIO DE EFICIENCIA LOGISTICA")
    print(sep)

    print("\n[KPIs DE NEGOCIO]")
    print(f"  Taxa de Ruptura de Estoque (pico)  : {kpis['kpi_stockout_rate_pct']:.2f} %")
    print(f"  Custo de Rebalanceamento / Viagem   : $ {kpis['kpi_rebalance_cost_per_trip_usd']:.4f}")
    print(f"  Receita Potencial Recuperada         : $ {kpis['kpi_recovered_revenue_usd']:,.2f}")
    print(f"  Receita Perdida sem Modelo           : $ {kpis['kpi_potential_lost_revenue_usd']:,.2f}")
    print(f"  Rotatividade do Ativo (viagens/bike) : {kpis['kpi_asset_turnover_trips_per_bike_per_day']:.3f} / dia")

    print("\n[ROI DO MODELO PREDITIVO]")
    print(f"  Alertas WARNING (planejados)        : {kpis['meta_alerts_warning_planned']:,}")
    print(f"  Alertas CRITICAL (emergencia)        : {kpis['meta_alerts_critical_emergency']:,}")
    print(f"  Economia em rebalanceamento          : $ {kpis['meta_savings_on_rebalance_usd']:,.2f}")
    print(f"  Receita recuperada                   : $ {kpis['kpi_recovered_revenue_usd']:,.2f}")
    print(f"  ROI LIQUIDO TOTAL                    : $ {kpis['meta_net_roi_usd']:,.2f}")

    print("\n[METADADOS DA ANALISE]")
    print(f"  Estacoes analisadas                 : {kpis['meta_total_stations']:,}")
    print(f"  Total de bikes na frota              : {kpis['meta_total_bikes_in_fleet']:,}")
    print(f"  Dias no periodo                      : {kpis['meta_unique_days']:,}")
    print(f"  Total de partidas                    : {kpis['meta_total_departures']:,}")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    print("Carregando tabelas da Gold Layer...")
    tables = load_tables()

    df_rolling = tables["demand_rolling"]
    df_balance = tables["station_balance"]
    df_hourly = tables["demand_hourly"]
    df_stations = tables["dim_stations"]

    print(f"  demand_rolling_avg : {df_rolling.shape[0]:,} linhas")
    print(f"  agg_station_balance: {df_balance.shape[0]:,} linhas")
    print(f"  agg_demand_hourly  : {df_hourly.shape[0]:,} linhas")
    print(f"  dim_stations       : {df_stations.shape[0]:,} estações")

    print("\nCalculando ROI de rebalanceamentos...")
    df_rebalance = compute_rebalance_roi(df_rolling, PARAMS)

    print("Calculando receita recuperada (stock-outs evitados)...")
    df_revenue = compute_revenue_recovery(df_rolling, PARAMS)

    print("Calculando KPIs...")
    kpis = compute_kpis(
        df_rolling, df_balance, df_hourly, df_stations,
        df_rebalance, df_revenue, PARAMS,
    )

    print_report(kpis)

    # Salva resultados
    summary_path = os.path.join(OUT_DIR, "roi_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(kpis, f, indent=2, ensure_ascii=False)
    print(f"Resumo salvo em: {summary_path}")

    detail_path = os.path.join(OUT_DIR, "roi_rebalance_detail.parquet")
    df_rebalance.to_parquet(detail_path, index=False)
    print(f"Detalhe de rebalanceamentos salvo em: {detail_path}")

    revenue_path = os.path.join(OUT_DIR, "roi_revenue_detail.parquet")
    df_revenue.to_parquet(revenue_path, index=False)
    print(f"Detalhe de receita recuperada salvo em: {revenue_path}")


if __name__ == "__main__":
    main()
