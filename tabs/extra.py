"""
Вкладка «Доп. нагрузка» — консультации и запросы (по сотрудникам / по ЮЦ).
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from config import AppConfig, COLORS_MAP, LoadType
from calculations import apply_calculations, calc_country_avg_by_employee, calc_country_avg_by_yuc
from components import (
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
        key="extra_sub_tab",
    )

    is_by_employees = "сотрудник" in sub_tab.lower()

    # Фильтры — единые ключи, не зависят от подтаба
    sel_types = _get_extra_filters()
    if not sel_types:
        st.warning("⚠️ Выберите типы нагрузки.")
        return

    if is_by_employees:
        _render_by_employees(df_main, df_country_main, cfg, emp_map, sel_types)
    else:
        _render_by_yuc(df_main, df_country_main, cfg, sel_types)


def _get_extra_filters() -> list[str]:
    """Фильтр Консультации/Запросы."""
    cols = st.columns(2)
    selected = []

    if cols[0].toggle("Консультации", value=True, key="extra_cons"):
        selected.append(LoadType.CONSULT.value)
    if cols[1].toggle("Запросы", value=True, key="extra_req"):
        selected.append(LoadType.REQUESTS.value)

    st.divider()
    return selected


def _render_by_employees(
    df_main: pd.DataFrame,
    df_country_main: pd.DataFrame,
    cfg: AppConfig,
    emp_map: dict[str, str],
    sel_types: list[str],
) -> None:
    """Подтаб «По сотрудникам»."""
    display_names = list(emp_map.values())

    if cfg.show_emp_filter:
        selected_display = st.multiselect(
            "Сотрудники:",
            display_names,
            default=display_names,
            key="extra_emp_select",
        )
    else:
        selected_display = display_names

    real_names = [name for name, display in emp_map.items() if display in selected_display]
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