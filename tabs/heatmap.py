"""
Вкладка «Тепловая карта» — карта России с нагрузкой по регионам.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import AppConfig
from calculations import apply_calculations
from components import get_all_type_filters, tab_header


def render(
    df_main: pd.DataFrame,
    geojson: dict | None,
    cfg: AppConfig,
    df_map_ref: pd.DataFrame,
    df_all: pd.DataFrame,
) -> None:
    """Отрисовка вкладки «Тепловая карта»."""
    tab_header("Тепловая карта", "🗺️ Тепловая карта")

    if geojson is None:
        st.error("❌ Не удалось загрузить карту 'final_russia.geojson'.")
        return

    sel_types = get_all_type_filters("map", disable_extra=cfg.use_coeffs)
    if not sel_types:
        st.warning("⚠️ Выберите типы нагрузки.")
        return

    # Расчёт значений
    df_map = apply_calculations(df_main.copy(), cfg)

    # Пивот по регионам
    df_pivot = (
        df_map.pivot_table(index="Регион", columns="Тип", values="Value", aggfunc="sum")
        .fillna(0)
        .reset_index()
    )
    for col in sel_types:
        if col not in df_pivot.columns:
            df_pivot[col] = 0

    # Объединяем с GeoJSON-регионами
    geojson_regions = [f["properties"]["name"] for f in geojson["features"]]
    df_plot = pd.merge(
        pd.DataFrame({"Регион": geojson_regions}),
        df_pivot,
        on="Регион",
        how="left",
    ).fillna(0)

    df_plot["Value"] = df_plot[sel_types].sum(axis=1)

    # Hover-тексты
    df_plot["Hover_Text"] = df_plot.apply(
        lambda row: _format_hover(row, sel_types, cfg.use_coeffs), axis=1
    )

    # Маппинг регион → ЮЦ
    reg_to_yuc = _build_region_yuc_map(df_map_ref, df_main)
    df_plot["ЮЦ_карты"] = df_plot["Регион"].astype(str).str.strip().map(reg_to_yuc)

    # Разделение на группы для разной стилизации
    is_selected = df_plot["ЮЦ_карты"].isin([y.strip() for y in cfg.selected_yucs])
    df_active = df_plot[(df_plot["Value"] > 0) & is_selected]
    df_zero = df_plot[(df_plot["Value"] == 0) & is_selected]
    df_other = df_plot[~is_selected]

    # Построение карты
    fig = _build_map(geojson, df_active, df_zero, df_other)
    st.plotly_chart(fig, use_container_width=True)


# ==========================================
# Вспомогательные функции
# ==========================================
def _format_hover(row: pd.Series, sel_types: list[str], use_coeffs: bool) -> str:
    """Форматирует hover-текст для одного региона."""
    region = row["Регион"]
    value = row["Value"]

    if value == 0:
        return f"<b>{region}</b><br>нет данных/юриста"

    if use_coeffs:
        return f"<b>{region}</b><br>Единое приведенное значение: {value:.2f}"

    lines = [f"<b>{region}</b>"]
    for t in sel_types:
        t_val = row.get(t, 0)
        if t_val > 0:
            lines.append(f"{t}: {t_val:.2f}")
    lines.append(f"<b>Всего: {value:.2f}</b>")
    return "<br>".join(lines)


def _build_region_yuc_map(
    df_map_ref: pd.DataFrame,
    df_main: pd.DataFrame,
) -> dict[str, str]:
    """Строит маппинг Регион → ЮЦ из справочника и данных."""
    reg_to_yuc = {}

    for df in [df_map_ref, df_main]:
        for _, row in df.iterrows():
            if pd.notna(row.get("Регион")):
                reg_to_yuc[str(row["Регион"]).strip()] = str(row["ЮЦ"]).strip()

    return reg_to_yuc


def _build_map(
    geojson: dict,
    df_active: pd.DataFrame,
    df_zero: pd.DataFrame,
    df_other: pd.DataFrame,
) -> go.Figure:
    """Строит Choroplethmapbox с тремя слоями."""
    fig = go.Figure()

    # Слой 1: активные регионы (с данными, в выбранных ЮЦ)
    if not df_active.empty:
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=df_active["Регион"],
            z=df_active["Value"],
            featureidkey="properties.name",
            colorscale="RdYlGn_r",
            marker_opacity=0.8,
            marker_line_width=0.3,
            marker_line_color="#555555",
            hovertext=df_active["Hover_Text"].tolist(),
            hovertemplate="%{hovertext}<extra></extra>",
            showscale=True,
        ))

    # Слой 2: невыбранные ЮЦ (серо-голубой фон)
    if not df_other.empty:
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=df_other["Регион"],
            z=[1] * len(df_other),
            featureidkey="properties.name",
            colorscale=[[0, "#B0C4DE"], [1, "#B0C4DE"]],
            marker_opacity=0.4,
            marker_line_width=0.3,
            marker_line_color="#555555",
            hovertext=df_other["Hover_Text"].tolist(),
            hovertemplate="%{hovertext}<extra></extra>",
            showscale=False,
        ))

    # Слой 3: пустые регионы (серый)
    if not df_zero.empty:
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=df_zero["Регион"],
            z=[1] * len(df_zero),
            featureidkey="properties.name",
            colorscale=[[0, "gray"], [1, "gray"]],
            marker_opacity=0.6,
            marker_line_width=0.3,
            marker_line_color="#555555",
            hovertext=df_zero["Hover_Text"].tolist(),
            hovertemplate="%{hovertext}<extra></extra>",
            showscale=False,
        ))

    fig.update_layout(
        mapbox_style="white-bg",
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=800,
        mapbox_zoom=2.2,
        mapbox_center={"lat": 65, "lon": 100},
    )

    return fig
