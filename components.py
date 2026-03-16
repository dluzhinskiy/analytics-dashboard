"""
Переиспользуемые UI-компоненты: фильтры типов нагрузки, средние линии, маппинг сотрудников.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    AppConfig, COLORS_MAP,
    LoadType, COLOR_PRIMARY, COLOR_AVERAGE_LINE,
)
from calculations import apply_calculations
from help_texts import TAB_HELP


# ==========================================
# Заголовок вкладки с кнопкой справки
# ==========================================
def tab_header(title: str, tab_key: str) -> None:
    """
    Отрисовывает заголовок вкладки с кнопкой «?» справа.

    При нажатии открывается модальное окно (st.dialog)
    с документацией по вкладке.

    Args:
        title: текст заголовка (например «Сравнение сотрудников»)
        tab_key: ключ вкладки из TABS (например «👥 Сотрудники»)
    """
    col_title, col_btn = st.columns([10, 1])

    with col_title:
        st.header(title)

    with col_btn:
        # Немного отступа сверху, чтобы кнопка была на уровне заголовка
        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
        if st.button("❓", key=f"help_{tab_key}", help="Показать справку по вкладке"):
            _show_help_dialog(tab_key)


@st.dialog("📖 Справка", width="large")
def _show_help_dialog(tab_key: str) -> None:
    """Модальное окно со справкой по вкладке."""
    help_text = TAB_HELP.get(tab_key, "Справка для этой вкладки пока не добавлена.")
    st.markdown(help_text)
    if st.button("Закрыть", key=f"close_help_{tab_key}", use_container_width=True):
        st.rerun()


# ==========================================
# Фильтры типов нагрузки
# ==========================================
def get_main_type_filters(prefix: str) -> list[str]:
    """Фильтр основных типов: Судебные дела, Админ. дела, Претензии."""
    cols = st.columns(3)
    selected = []

    if cols[0].toggle("Судебные дела", value=True, key=f"{prefix}_sd"):
        selected.append(LoadType.COURT.value)
    if cols[1].toggle("Админ. дела", value=True, key=f"{prefix}_ad"):
        selected.append(LoadType.ADMIN.value)
    if cols[2].toggle("Претензии", value=True, key=f"{prefix}_pret"):
        selected.append(LoadType.CLAIMS.value)

    st.divider()
    return selected


def get_extra_type_filters(prefix: str, disabled: bool = False) -> list[str]:
    """Фильтр дополнительных типов: Консультации, Запросы."""
    cols = st.columns(2)
    selected = []
    default = not disabled

    if cols[0].toggle("Консультации", value=default, disabled=disabled, key=f"{prefix}_cons"):
        selected.append(LoadType.CONSULT.value)
    if cols[1].toggle("Запросы", value=default, disabled=disabled, key=f"{prefix}_req"):
        selected.append(LoadType.REQUESTS.value)

    st.divider()
    return selected


def get_all_type_filters(prefix: str, disable_extra: bool = False) -> list[str]:
    """Фильтр всех 5 типов нагрузки в одну строку."""
    cols = st.columns(5)
    selected = []

    if cols[0].toggle("Судебные дела", value=True, key=f"{prefix}_sd"):
        selected.append(LoadType.COURT.value)
    if cols[1].toggle("Админ. дела", value=True, key=f"{prefix}_ad"):
        selected.append(LoadType.ADMIN.value)
    if cols[2].toggle("Претензии", value=True, key=f"{prefix}_pret"):
        selected.append(LoadType.CLAIMS.value)

    extra_default = False if disable_extra else False
    if cols[3].toggle("Консультации", value=extra_default, disabled=disable_extra, key=f"{prefix}_cons"):
        selected.append(LoadType.CONSULT.value)
    if cols[4].toggle("Запросы", value=extra_default, disabled=disable_extra, key=f"{prefix}_req"):
        selected.append(LoadType.REQUESTS.value)

    st.divider()
    return selected


# ==========================================
# Средняя линия на графике
# ==========================================
def add_average_line(
    fig: go.Figure,
    value: float,
    label: str = "Ср. (РФ)",
) -> None:
    """Добавляет горизонтальную пунктирную линию среднего значения."""
    if pd.notna(value) and value > 0:
        fig.add_hline(
            y=value,
            line_dash="dash",
            line_color=COLOR_AVERAGE_LINE,
            annotation_text=f"<b>{label}: {value:.2f}</b>",
            annotation_position="top left",
            annotation_font=dict(color=COLOR_AVERAGE_LINE, size=13),
        )


# ==========================================
# Маппинг сотрудников (имя → отображаемое имя с иконкой)
# ==========================================
def create_emp_map(raw_employees: list[str], crown_employees: set[str]) -> dict[str, str]:
    """Создаёт маппинг имя → отображаемое имя (с 👑 для работников ЮЦ)."""
    return {
        name: f"{'👑 ' if name in crown_employees else ''}{name}"
        for name in raw_employees
    }


# ==========================================
# Общие паттерны построения графиков
# ==========================================
def select_employees(
    emp_map: dict[str, str],
    cfg: AppConfig,
    key_prefix: str = "emp",
) -> list[str]:
    """
    UI-выбор сотрудников. Возвращает список реальных имён.
    Если фильтр выключен — возвращает всех.
    """
    display_names = list(emp_map.values())

    if cfg.show_emp_filter:
        selected_display = st.multiselect(
            "Выберите сотрудников:",
            display_names,
            default=display_names,
            key=f"{key_prefix}_multiselect",
        )
    else:
        selected_display = display_names

    # Обратный маппинг: отображаемое имя → реальное
    return [name for name, display in emp_map.items() if display in selected_display]


def get_ordered_names(df: pd.DataFrame, name_col: str = "Display") -> list[str]:
    """Сортирует имена по ЮЦ и Value для упорядоченного отображения на графике."""
    return (
        df.groupby([name_col, "ЮЦ"])["Value"]
        .sum()
        .reset_index()
        .sort_values(by=["ЮЦ", "Value"], ascending=[True, False])[name_col]
        .tolist()
    )


def build_bar_chart(
    df: pd.DataFrame,
    x: str,
    cfg: AppConfig,
    title: str = "",
    show_avg: bool = False,
    avg_value: float = 0.0,
) -> go.Figure:
    """
    Строит bar chart: с группировкой по типу (без коэфф.) или сплошной (с коэфф.).
    """
    if cfg.use_coeffs:
        grp = df.groupby(x)["Value"].sum().reset_index()
        fig = px.bar(grp, x=x, y="Value", text_auto=".2f", title=title)
        fig.update_traces(marker_color=COLOR_PRIMARY)
    else:
        grp = df.groupby([x, "Тип"])["Value"].sum().reset_index()
        fig = px.bar(
            grp, x=x, y="Value",
            color="Тип", color_discrete_map=COLORS_MAP,
            text_auto=".2f", title=title,
        )

    if show_avg and cfg.show_avg:
        add_average_line(fig, avg_value)

    return fig
