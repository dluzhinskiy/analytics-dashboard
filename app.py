"""
Аналитика ЮЦ — главный модуль приложения.

Точка входа: streamlit run app.py
"""

import streamlit as st

from config import AppConfig, TABS
from data_loader import load_data, load_geojson, preprocess_stats, get_fired_employees, get_crown_employees
from components import create_emp_map
from help_texts import HELP_COEFFICIENTS
from tabs import employees, yuc, heatmap, extra


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
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# Сайдбар: фильтры и настройки
# ==========================================
def render_sidebar(df_all) -> AppConfig:
    """Отрисовка сайдбара, возвращает конфигурацию."""

    st.sidebar.title("📊 Дэшборд аналитики")
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
        "✅ **Включить / Выключить все**",
        value=True,
        key="master_yuc",
        on_change=_on_master_change,
    )
    st.sidebar.divider()

    selected_yucs = [
        y for y in all_yucs
        if st.sidebar.toggle(y, value=True, key=f"yuc_{y}")
    ]

    # --- Коэффициенты ---
    st.sidebar.divider()
    c_title, c_help = st.sidebar.columns([5, 1])
    with c_title:
        st.subheader("Приведенные показатели")
    with c_help:
        st.markdown("<div style='height: 0.3rem'></div>", unsafe_allow_html=True)
        if st.button("❓", key="help_coeffs", help="Справка по коэффициентам"):
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

    # Предобработка
    df_all = preprocess_stats(df_raw)
    fired_emps = get_fired_employees(df_raw)
    crown_emps = get_crown_employees(df_raw)

    # Глобальный фильтр: убираем уволенных
    df_all = df_all[~df_all["Сотрудник"].isin(fired_emps)]

    # Маппинг сотрудников
    emp_map = create_emp_map(sorted(df_all["Сотрудник"].unique()), crown_emps)

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
    cfg = render_sidebar(df_all)

    # Динамический выбор последнего года (вместо хардкода 2025)
    available_years = sorted(df_all["Год"].dropna().unique())
    sel_years = [available_years[-1]] if available_years else [2025]

    # Фильтрация данных
    df_main = df_all[
        (df_all["ЮЦ"].isin(cfg.selected_yucs)) & (df_all["Год"].isin(sel_years))
    ]
    df_country_main = df_all[df_all["Год"].isin(sel_years)]

    # Роутинг по вкладкам
    if selected_tab == TABS[0]:  # Сотрудники
        employees.render(df_main, df_country_main, cfg, emp_map)
    elif selected_tab == TABS[1]:  # ЮЦ
        yuc.render(df_main, df_country_main, cfg, df_all)
    elif selected_tab == TABS[2]:  # Тепловая карта
        heatmap.render(df_main, load_geojson(), cfg, df_map_ref, df_all)
    elif selected_tab == TABS[3]:  # Доп. нагрузка
        extra.render(df_main, df_country_main, cfg, emp_map)


# ==========================================
# Запуск
# ==========================================
main()
