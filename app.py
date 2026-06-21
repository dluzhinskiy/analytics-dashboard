"""
Аналитика ЮЦ — главный модуль приложения.

Точка входа: streamlit run app.py
"""

import os
import sys

# Гарантируем, что директория app.py в sys.path (для Streamlit Cloud)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import pandas as pd
import streamlit as st

from config import AppConfig, TABS
from data_loader import (
    load_data, load_2026_data, load_geojson,
    preprocess_stats, preprocess_2026_stats,
    filter_2026_segments, extrapolate_2026_data,
    get_fired_employees, get_crown_employees,
)
from components import create_emp_map
from help_texts import HELP_COEFFICIENTS
from tabs import employees, yuc, heatmap, extra, comparison


# ==========================================
# Настройки страницы и CSS
# ==========================================
st.set_page_config(
    page_title="Аналитика ЮЦ",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Стилизация ТОЛЬКО навигационного radio (внутри .nav-tabs) */
    .nav-tabs div[role="radiogroup"] > label > div:first-child { display: none !important; }
    .nav-tabs div[role="radiogroup"] {
        flex-direction: row; gap: 5px;
        border-bottom: 2px solid rgba(150, 150, 150, 0.3);
        padding-bottom: 0 !important;
    }
    .nav-tabs div[role="radiogroup"] > label {
        background-color: var(--secondary-background-color);
        color: var(--text-color);
        padding: 10px 20px;
        border-radius: 8px 8px 0 0;
        border: 1px solid rgba(150, 150, 150, 0.3);
        border-bottom: none;
        margin-bottom: -2px;
        cursor: pointer;
        transition: all 0.2s ease-in-out;
    }
    .nav-tabs div[role="radiogroup"] > label:hover { filter: brightness(0.85); }
    .nav-tabs div[role="radiogroup"] > label p { margin: 0; font-weight: 600; }
    .stNumberInput label { display: none; }

    /* Кликабельные заголовки-справки: пунктирное подчёркивание + курсор-вопрос */
    button[kind="tertiary"] {
        text-decoration: underline dashed !important;
        text-decoration-color: rgba(150, 150, 150, 0.6) !important;
        text-underline-offset: 4px !important;
        cursor: help !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        padding: 0 !important;
    }
    button[kind="tertiary"]:hover {
        text-decoration-color: rgba(100, 100, 100, 0.9) !important;
    }
    /* В сайдбаре — чуть меньший шрифт */
    section[data-testid="stSidebar"] button[kind="tertiary"] {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# Сайдбар: фильтры и настройки
# ==========================================
def render_sidebar(df_all, selected_tab: str) -> AppConfig:
    """Отрисовка сайдбара, возвращает конфигурацию."""

    st.sidebar.title("📊 Дэшборд аналитики")
    st.sidebar.divider()

    # --- Период данных ---
    st.sidebar.subheader("Период данных")
    selected_year = st.sidebar.radio(
        "Год",
        [2025, 2026],
        horizontal=True,
        format_func=lambda year: "2025" if year == 2025 else "2026 · 5 мес.",
        label_visibility="collapsed",
        key="selected_year",
    )

    extrapolation_toggle = st.sidebar.toggle(
        "Экстраполировать до конца 2026 года",
        value=False,
        disabled=selected_year != 2026 or selected_tab == TABS[4],
        key="sidebar_extrapolate_2026",
        help="Умножает факт за январь–май на 12/5 = 2,4.",
    )
    extrapolate_2026 = (
        selected_year == 2026
        and selected_tab != TABS[4]
        and extrapolation_toggle
    )

    if selected_tab == TABS[4]:
        st.sidebar.caption(
            "Вкладка сравнения использует оба периода; выбор года влияет на остальные вкладки."
        )

    include_court_unaccounted = False
    include_admin_unaccounted = False
    if selected_year == 2026 and selected_tab != TABS[4]:
        st.sidebar.caption("Неучтённая нагрузка")
        include_court_unaccounted = st.sidebar.toggle(
            "СД Н", value=False, key="sidebar_court_unaccounted"
        )
        include_admin_unaccounted = st.sidebar.toggle(
            "АД Н", value=False, key="sidebar_admin_unaccounted"
        )
    st.sidebar.divider()

    # --- Юридические Центры ---
    st.sidebar.subheader("Юридические Центры")
    all_yucs = sorted(df_all["ЮЦ"].unique())

    def _on_master_change():
        """При переключении мастера — обновляем все дочерние toggle."""
        new_val = st.session_state["master_yuc"]
        for y in all_yucs:
            st.session_state[f"yuc_{y}"] = new_val

    master_toggle = st.sidebar.toggle(
        "**Включить / Выключить все**",
        value=True,
        key="master_yuc",
        on_change=_on_master_change,
    )
    st.sidebar.divider()

    selected_yucs = []
    for y in all_yucs:
        key = f"yuc_{y}"
        # Не передаём value= если ключ уже в session_state (иначе Streamlit ругается)
        if key in st.session_state:
            val = st.sidebar.toggle(y, key=key)
        else:
            val = st.sidebar.toggle(y, value=True, key=key)
        if val:
            selected_yucs.append(y)

    # --- Коэффициенты ---
    st.sidebar.divider()
    if st.sidebar.button(
        "Приведенные показатели",
        key="help_coeffs",
        type="tertiary",
    ):
        _show_coeffs_help()
    use_coeffs = st.sidebar.toggle("Включить коэффициенты", value=False)

    coefficients = _render_coefficient_inputs(use_coeffs)

    # --- Настройки отображения ---
    st.sidebar.divider()
    st.sidebar.subheader("Настройки отображения")
    show_avg = st.sidebar.toggle("📉 Показывать среднюю линию (РФ)", value=True)
    show_emp = st.sidebar.toggle("👥 Показывать фильтр сотрудников", value=False)

    return AppConfig(
        use_coeffs=use_coeffs,
        k_sd=coefficients["k_sd"],
        k_ad=coefficients["k_ad"],
        k_pr_n=coefficients["k_pr_n"],
        k_pr_a=coefficients["k_pr_a"],
        show_avg=show_avg,
        show_emp_filter=show_emp,
        selected_yucs=selected_yucs,
        selected_year=selected_year,
        extrapolate_2026=extrapolate_2026,
        include_court_unaccounted=include_court_unaccounted,
        include_admin_unaccounted=include_admin_unaccounted,
    )


def _render_coefficient_inputs(use_coeffs: bool) -> dict:
    """Отрисовка инпутов коэффициентов в сайдбаре."""
    params = [
        ("Судебные", "SD", 1.0),
        ("Админ.", "AD", 0.5),
        ("Прет. (неабон)", "PR_N", 0.5),
        ("Прет. (абон)", "PR_A", 0.25),
    ]
    keys = ["k_sd", "k_ad", "k_pr_n", "k_pr_a"]
    result = {}

    for (label, input_label, default), key in zip(params, keys):
        c1, c2 = st.sidebar.columns([1, 1.2])
        with c1:
            st.markdown(label)
        with c2:
            result[key] = st.number_input(
                input_label,
                value=default,
                step=0.05,
                format="%.2f",
                disabled=not use_coeffs,
                label_visibility="collapsed",
            )

    return result


@st.dialog("📖 Приведённые показатели", width="large")
def _show_coeffs_help() -> None:
    """Модальное окно со справкой по коэффициентам."""
    st.markdown(HELP_COEFFICIENTS)
    if st.button("Закрыть", key="close_help_coeffs", use_container_width=True):
        st.rerun()


# ==========================================
# Главная функция
# ==========================================
def main() -> None:
    """Точка входа приложения."""

    # Загрузка данных
    df_raw, df_map_ref = load_data()

    if df_raw.empty:
        st.error("❌ Нет данных для отображения. Проверьте файл statistics.xlsx.")
        return

    # Предобработка 2025
    df_all_unfiltered = preprocess_stats(df_raw)
    fired_emps = get_fired_employees(df_raw)
    crown_emps_2025 = get_crown_employees(df_raw)

    flagged_2025_load = df_all_unfiltered[
        (df_all_unfiltered["Год"] == 2025)
        & (df_all_unfiltered["Сотрудник"].isin(fired_emps))
    ]["Value"].sum()

    # В 2025 убираем уволенных; их нагрузка 2025 в текущем файле равна нулю.
    df_2025 = df_all_unfiltered[
        (~df_all_unfiltered["Сотрудник"].isin(fired_emps))
        & (df_all_unfiltered["Год"] == 2025)
    ].copy()

    # Предобработка факта за январь–май 2026. Все сотрудники считаются действующими.
    df_2026_raw = load_2026_data()
    if df_2026_raw.empty:
        st.error("❌ Нет данных 2026 года. Проверьте файл statistics 5m26.xlsx.")
        return
    try:
        df_2026 = preprocess_2026_stats(df_2026_raw)
    except ValueError as e:
        st.error(f"❌ {e}")
        return
    crown_emps_2026 = get_crown_employees(df_2026_raw)

    # Навигация (обёрнута в div.nav-tabs для точечной CSS-стилизации)
    st.markdown('<div class="nav-tabs">', unsafe_allow_html=True)
    selected_tab = st.radio(
        "Навигация:",
        TABS,
        horizontal=True,
        label_visibility="collapsed",
        key="main_nav",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # Сайдбар
    cfg = render_sidebar(
        pd.concat([df_2025, df_2026], ignore_index=True), selected_tab
    )

    if cfg.selected_year == 2025:
        df_year = df_2025.copy()
        crown_emps = crown_emps_2025
    else:
        df_year = filter_2026_segments(
            df_2026,
            cfg.include_court_unaccounted,
            cfg.include_admin_unaccounted,
        )
        df_year = extrapolate_2026_data(df_year, cfg.extrapolate_2026)
        crown_emps = crown_emps_2026

    emp_map = create_emp_map(sorted(df_year["Сотрудник"].unique()), crown_emps)
    df_main = df_year[df_year["ЮЦ"].isin(cfg.selected_yucs)]
    df_country_main = df_year

    if selected_tab != TABS[4]:
        if cfg.selected_year == 2025:
            period_label = "2025 год"
        elif cfg.extrapolate_2026:
            period_label = "2026 год — линейный прогноз (январь–май × 2,4)"
        else:
            period_label = "2026 год — фактические данные за январь–май"
        st.caption(f"Период: **{period_label}**")

    # Роутинг по вкладкам
    if selected_tab == TABS[0]:  # Сотрудники
        employees.render(df_main, df_country_main, cfg, emp_map)
    elif selected_tab == TABS[1]:  # ЮЦ
        yuc.render(df_main, df_country_main, cfg, df_year)
    elif selected_tab == TABS[2]:  # Тепловая карта
        heatmap.render(df_main, load_geojson(), cfg, df_map_ref, df_year)
    elif selected_tab == TABS[3]:  # Доп. нагрузка
        extra.render(df_main, df_country_main, cfg, emp_map)
    elif selected_tab == TABS[4]:  # Сравнение 2025 / 2026
        comparison.render(df_2025, df_2026, cfg, float(flagged_2025_load))


# ==========================================
# Запуск
# ==========================================
main()
