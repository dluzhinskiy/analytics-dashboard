"""
Вкладка «ЮЦ» — сравнение юридических центров.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from config import AppConfig, COLORS_MAP, COLOR_PRIMARY, COLOR_SECONDARY
from calculations import apply_calculations, calc_country_avg_by_yuc
from components import get_main_type_filters, add_average_line, tab_header


def render(
    df_main: pd.DataFrame,
    df_country_main: pd.DataFrame,
    cfg: AppConfig,
    df_all: pd.DataFrame,
) -> None:
    """Отрисовка вкладки «ЮЦ»."""
    tab_header("Сравнение Юридических Центров", "🏢 ЮЦ")

    sel_types = get_main_type_filters("yuc")
    if not sel_types:
        st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
        return

    df_yuc = apply_calculations(
        df_main[df_main["Тип"].isin(sel_types)].copy(), cfg
    )
    df_country = apply_calculations(
        df_country_main[df_country_main["Тип"].isin(sel_types)].copy(), cfg
    )

    avg_country_total = calc_country_avg_by_yuc(df_country_main, sel_types, cfg)

    if cfg.use_coeffs:
        _render_with_coeffs(df_yuc, df_country, df_all, cfg, avg_country_total)
    else:
        _render_without_coeffs(df_yuc, cfg, avg_country_total)


def _render_with_coeffs(
    df_yuc: pd.DataFrame,
    df_country: pd.DataFrame,
    df_all: pd.DataFrame,
    cfg: AppConfig,
    avg_country_total: float,
) -> None:
    """Отображение с коэффициентами: объём + эффективность."""
    grp_yu = df_yuc.groupby("ЮЦ")["Value"].sum().reset_index()
    if grp_yu.empty:
        st.info("Нет данных.")
        return

    col1, col2 = st.columns(2)

    # 1. Общий объём
    with col1:
        st.subheader("Общий объем")
        fig1 = px.bar(grp_yu, x="ЮЦ", y="Value", text_auto=".2f")
        fig1.update_traces(marker_color=COLOR_PRIMARY)
        if cfg.show_avg:
            add_average_line(fig1, avg_country_total)
        st.plotly_chart(fig1, use_container_width=True)

    # 2. Эффективность (нагрузка на сотрудника)
    avg_country_eff = _calc_country_efficiency(df_country, df_all)
    efficiency_data = _calc_yuc_efficiency(grp_yu, df_all)

    with col2:
        st.subheader("Эффективность")
        fig2 = px.bar(
            pd.DataFrame(efficiency_data),
            x="ЮЦ", y="Эффективность",
            text_auto=".2f",
            hover_data=["Сотрудников"],
        )
        fig2.update_traces(marker_color=COLOR_SECONDARY)
        if cfg.show_avg:
            add_average_line(fig2, avg_country_eff)
        st.plotly_chart(fig2, use_container_width=True)


def _render_without_coeffs(
    df_yuc: pd.DataFrame,
    cfg: AppConfig,
    avg_country_total: float,
) -> None:
    """Отображение без коэффициентов: стековый bar chart по типам."""
    grp_yu = df_yuc.groupby(["ЮЦ", "Тип"])["Value"].sum().reset_index()
    if grp_yu.empty:
        st.info("Нет данных.")
        return

    fig = px.bar(
        grp_yu, x="ЮЦ", y="Value",
        color="Тип", color_discrete_map=COLORS_MAP,
        barmode="stack", text_auto=".2f",
    )
    if cfg.show_avg:
        add_average_line(fig, avg_country_total)
    st.plotly_chart(fig, use_container_width=True)


def _calc_country_efficiency(
    df_country: pd.DataFrame,
    df_all: pd.DataFrame,
) -> float:
    """Средняя эффективность по всем ЮЦ в РФ."""
    efficiencies = []
    for yuc, total_val in df_country.groupby("ЮЦ")["Value"].sum().items():
        active_count = df_all[df_all["ЮЦ"] == yuc]["Сотрудник"].nunique()
        if active_count > 0:
            efficiencies.append(total_val / active_count)
    return sum(efficiencies) / len(efficiencies) if efficiencies else 0.0


def _calc_yuc_efficiency(
    grp_yu: pd.DataFrame,
    df_all: pd.DataFrame,
) -> list[dict]:
    """Эффективность по каждому ЮЦ (нагрузка / количество сотрудников)."""
    result = []
    for _, row in grp_yu.iterrows():
        active_count = df_all[df_all["ЮЦ"] == row["ЮЦ"]]["Сотрудник"].nunique()
        result.append({
            "ЮЦ": row["ЮЦ"],
            "Эффективность": row["Value"] / active_count if active_count > 0 else 0,
            "Сотрудников": active_count,
        })
    return result
