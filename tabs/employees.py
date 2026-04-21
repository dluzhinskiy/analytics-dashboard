"""
Вкладка «Сотрудники» — сравнение нагрузки по сотрудникам.
"""

import streamlit as st

from config import AppConfig
from calculations import apply_calculations, calc_country_avg_by_employee
from components import (
    get_main_type_filters,
    select_employees,
    get_ordered_names,
    build_bar_chart,
    tab_header,
)
import pandas as pd


def render(
    df_main: pd.DataFrame,
    df_country_main: pd.DataFrame,
    cfg: AppConfig,
    emp_map: dict[str, str],
) -> None:
    """Отрисовка вкладки «Сотрудники»."""
    tab_header("Сравнение сотрудников", "👥 Сотрудники")
    st.info("ℹ️ **Легенда статусов:** 👑 — Работник ЮЦ")

    # Фильтры типов нагрузки
    sel_types = get_main_type_filters("emp")
    if not sel_types:
        st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
        return

    # Выбор сотрудников
    real_names = select_employees(emp_map, cfg, key_prefix="emp")
    if not real_names:
        st.info("Нет данных.")
        return

    # Фильтрация и расчёт
    df_sub = df_main[
        (df_main["Сотрудник"].isin(real_names)) & (df_main["Тип"].isin(sel_types))
    ].copy()

    if df_sub.empty:
        st.info("Нет данных.")
        return

    df_sub = apply_calculations(df_sub, cfg)
    df_sub["Display"] = df_sub["Сотрудник"].map(emp_map)

    # Средняя по РФ
    avg_country = calc_country_avg_by_employee(df_country_main, sel_types, cfg)

    # Заголовок
    title = "Сравнительная гистограмма"
    if cfg.use_coeffs:
        title += " (с учетом коэффициентов)"

    # Построение графика (с регионом в hover)
    fig = build_bar_chart(
        df_sub, x="Display", cfg=cfg, title=title,
        show_avg=True, avg_value=avg_country,
        hover_extra_cols=["Регион"],
    )

    # Упорядочивание по ЮЦ и значению
    ordered = get_ordered_names(df_sub)
    fig.update_xaxes(categoryorder="array", categoryarray=ordered)

    st.plotly_chart(fig, use_container_width=True)
