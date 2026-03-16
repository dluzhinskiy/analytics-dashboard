"""
Вкладка «Доп. нагрузка» — консультации и запросы (по сотрудникам / по ЮЦ).
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from config import AppConfig, COLORS_MAP
from calculations import apply_calculations, calc_country_avg_by_employee, calc_country_avg_by_yuc
from components import (
    get_extra_type_filters,
    select_employees,
    get_ordered_names,
    add_average_line,
    tab_header,
)


def render(
    df_main: pd.DataFrame,
    df_country_main: pd.DataFrame,
    cfg: AppConfig,
    emp_map: dict[str, str],
) -> None:
    """Отрисовка вкладки «Доп. нагрузка»."""
    tab_header("Консультации и запросы", "💬 Доп. нагрузка")

    sub_tab = st.radio(
        "Анализ отображения:",
        ["👥 По сотрудникам", "🏢 По Юридическим Центрам"],
        horizontal=True,
    )

    sel_types = get_extra_type_filters("extra")
    if not sel_types:
        st.warning("⚠️ Выберите типы нагрузки.")
        return

    if "Сотр" in sub_tab:
        _render_by_employees(df_main, df_country_main, cfg, emp_map, sel_types)
    else:
        _render_by_yuc(df_main, df_country_main, cfg, sel_types)


def _render_by_employees(
    df_main: pd.DataFrame,
    df_country_main: pd.DataFrame,
    cfg: AppConfig,
    emp_map: dict[str, str],
    sel_types: list[str],
) -> None:
    """Подтаб «По сотрудникам»."""
    real_names = select_employees(emp_map, cfg, key_prefix="extra_emp")
    if not real_names:
        st.info("Нет данных.")
        return

    df_sub = apply_calculations(
        df_main[
            (df_main["Сотрудник"].isin(real_names)) & (df_main["Тип"].isin(sel_types))
        ].copy(),
        cfg,
    )
    if df_sub.empty:
        st.info("Нет данных.")
        return

    df_sub["Display"] = df_sub["Сотрудник"].map(emp_map)

    avg_country = calc_country_avg_by_employee(df_country_main, sel_types, cfg)
    ordered = get_ordered_names(df_sub)

    grp = df_sub.groupby(["Display", "Тип"])["Value"].sum().reset_index()
    fig = px.bar(
        grp, x="Display", y="Value",
        color="Тип", color_discrete_map=COLORS_MAP,
        text_auto=".2f",
    )
    fig.update_xaxes(categoryorder="array", categoryarray=ordered)

    if cfg.show_avg:
        add_average_line(fig, avg_country)

    st.plotly_chart(fig, use_container_width=True)


def _render_by_yuc(
    df_main: pd.DataFrame,
    df_country_main: pd.DataFrame,
    cfg: AppConfig,
    sel_types: list[str],
) -> None:
    """Подтаб «По ЮЦ»."""
    df_yuc = apply_calculations(
        df_main[df_main["Тип"].isin(sel_types)].copy(), cfg
    )
    grp_yu = df_yuc.groupby(["ЮЦ", "Тип"])["Value"].sum().reset_index()

    if grp_yu.empty:
        st.info("Нет данных.")
        return

    avg_country = calc_country_avg_by_yuc(df_country_main, sel_types, cfg)

    fig = px.bar(
        grp_yu, x="ЮЦ", y="Value",
        color="Тип", color_discrete_map=COLORS_MAP,
        barmode="stack", text_auto=".2f",
    )
    if cfg.show_avg:
        add_average_line(fig, avg_country)

    st.plotly_chart(fig, use_container_width=True)
