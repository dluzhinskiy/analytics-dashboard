"""
Вкладка «Тепловая карта» — карта России с нагрузкой по регионам.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import AppConfig
from calculations import apply_calculations
from components import get_main_type_filters, tab_header
from capitals import REGION_CAPITALS

import re


def _find_capital(region: str) -> tuple[str, float, float] | None:
    """
    Находит столицу региона с нормализацией тире и пробелов.

    GeoJSON может содержать разные варианты тире (-, –, —)
    и разное количество пробелов вокруг них.
    """
    # Прямое совпадение
    cap = REGION_CAPITALS.get(region)
    if cap:
        return cap

    # Нормализация: заменяем любые тире и пробелы вокруг на единый формат
    def normalize(s: str) -> str:
        return re.sub(r"\s*[—–\-]\s*", " - ", s).strip().lower()

    norm_region = normalize(region)
    for key, val in REGION_CAPITALS.items():
        norm_key = normalize(key)
        if norm_key == norm_region:
            return val

    # Совпадение по началу строки (GeoJSON может опускать суффиксы вроде «- Югра»)
    for key, val in REGION_CAPITALS.items():
        norm_key = normalize(key)
        if norm_key.startswith(norm_region) or norm_region.startswith(norm_key):
            return val

    return None


# Контрастные цвета для ЮЦ — подобраны так, чтобы соседние регионы
# не сливались и серый (нет юриста) был заметен на их фоне.
# 10 цветов с максимальным разбросом по оттенку.
YUC_COLORS = [
    "#2196F3",  # синий
    "#FF9800",  # оранжевый
    "#4CAF50",  # зелёный
    "#E91E63",  # розовый
    "#9C27B0",  # фиолетовый
    "#00BCD4",  # бирюзовый
    "#F44336",  # красный
    "#8BC34A",  # лайм
    "#3F51B5",  # индиго
    "#FF5722",  # глубокий оранжевый
]

# Серый для регионов без юристов
COLOR_NO_LAWYER = "#B0B0B0"
# Серо-голубой для невыбранных ЮЦ
COLOR_UNSELECTED = "#D5DDE5"

# Регионы с офисами ЮЦ (отмечаются 👑)
CROWN_REGIONS = {
    "Приморский край",
    "Нижегородская область",
    "Новосибирская область",
    "Свердловская область",
    "Краснодарский край",
    "Ленинградская область",
}


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

    # Переключатель режима + кнопка Карта/Таблица на одной строке
    col_toggle, col_view_btn, col_spacer = st.columns([3, 2, 7])

    with col_toggle:
        show_distribution = st.toggle(
            "🗺️ Распределение юристов",
            value=False,
            key="map_distribution",
        )

    # Кнопка Карта ↔ Таблица (видна только в режиме распределения)
    if show_distribution:
        with col_view_btn:
            if "dist_view" not in st.session_state:
                st.session_state["dist_view"] = "map"
            is_table = st.session_state["dist_view"] == "table"
            btn_label = "📋 Таблица" if not is_table else "🗺️ Карта"
            if st.button(btn_label, key="dist_view_toggle"):
                st.session_state["dist_view"] = "table" if not is_table else "map"
                st.rerun()

    if show_distribution:
        _render_distribution(geojson, cfg, df_map_ref, df_all)
    else:
        _render_heatmap(geojson, cfg, df_main, df_map_ref)


# ==========================================
# Режим 1: Тепловая карта нагрузки
# ==========================================
def _render_heatmap(
    geojson: dict,
    cfg: AppConfig,
    df_main: pd.DataFrame,
    df_map_ref: pd.DataFrame,
) -> None:
    """Стандартная тепловая карта нагрузки по основным типам."""
    sel_types = get_main_type_filters("map")
    if not sel_types:
        st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
        return

    # Если ни один ЮЦ не выбран — серая карта
    if not cfg.selected_yucs:
        fig = _build_all_gray_map(geojson)
        st.plotly_chart(fig, use_container_width=True)
        st.info("ℹ️ Выберите хотя бы один ЮЦ в сайдбаре.")
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

    is_selected = df_plot["ЮЦ_карты"].isin([y.strip() for y in cfg.selected_yucs])
    df_active = df_plot[(df_plot["Value"] > 0) & is_selected]
    df_zero = df_plot[(df_plot["Value"] == 0) & is_selected]
    df_other = df_plot[~is_selected]

    fig = _build_heatmap_figure(geojson, df_active, df_zero, df_other)
    st.plotly_chart(fig, use_container_width=True)


# ==========================================
# Режим 2: Распределение юристов по ЮЦ
# ==========================================
def _prepare_distribution_data(
    geojson: dict,
    cfg: AppConfig,
    df_map_ref: pd.DataFrame,
    df_all: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Подготавливает данные распределения регионов по ЮЦ.

    Возвращает (df_dist, yuc_color_map):
      - df_dist: DataFrame с колонками Регион, ЮЦ, color, hover, group, lawyers_count
      - yuc_color_map: маппинг ЮЦ → цвет
    """
    reg_to_yuc = _build_region_yuc_map(df_map_ref, df_all)

    # Количество юристов по регионам
    lawyers_per_region = (
        df_all[df_all["Сотрудник"].notna()]
        .groupby(df_all["Регион"].astype(str).str.strip())["Сотрудник"]
        .nunique()
        .to_dict()
    )

    # Назначаем цвета ЮЦ
    all_yucs_sorted = sorted(df_all["ЮЦ"].unique())
    yuc_color_map = {
        yuc: YUC_COLORS[i % len(YUC_COLORS)]
        for i, yuc in enumerate(all_yucs_sorted)
    }

    geojson_regions = [f["properties"]["name"] for f in geojson["features"]]
    rows = []
    for region in geojson_regions:
        yuc = reg_to_yuc.get(region)
        is_selected = yuc in cfg.selected_yucs if yuc else False
        n_lawyers = lawyers_per_region.get(region, 0)

        if is_selected and n_lawyers > 0 and yuc:
            crown = "👑 " if region in CROWN_REGIONS else ""
            cap = _find_capital(region)
            cap_line = f"<br><i>Столица: {cap[0]}</i>" if cap else ""
            rows.append({
                "Регион": region,
                "ЮЦ": yuc,
                "color": yuc_color_map.get(yuc, YUC_COLORS[0]),
                "hover": f"<b>{crown}{region}</b><br>ЮЦ: {yuc}<br>Юристов: {n_lawyers}{cap_line}",
                "group": "active",
                "lawyers_count": n_lawyers,
                "is_crown": region in CROWN_REGIONS,
            })
        elif is_selected:
            cap = _find_capital(region)
            cap_line = f"<br><i>Столица: {cap[0]}</i>" if cap else ""
            rows.append({
                "Регион": region,
                "ЮЦ": yuc or "—",
                "color": COLOR_NO_LAWYER,
                "hover": f"<b>{region}</b><br>Нет юриста{cap_line}",
                "group": "no_lawyer",
                "lawyers_count": 0,
                "is_crown": False,
            })
        else:
            cap = _find_capital(region)
            cap_line = f"<br><i>Столица: {cap[0]}</i>" if cap else ""
            rows.append({
                "Регион": region,
                "ЮЦ": yuc or "—",
                "color": COLOR_UNSELECTED,
                "hover": f"<b>{region}</b><br>ЮЦ не выбран{cap_line}",
                "group": "unselected",
                "lawyers_count": 0,
                "is_crown": False,
            })

    return pd.DataFrame(rows), yuc_color_map


def _render_distribution(
    geojson: dict,
    cfg: AppConfig,
    df_map_ref: pd.DataFrame,
    df_all: pd.DataFrame,
) -> None:
    """Распределение юристов: карта или таблица."""

    # Если ни один ЮЦ не выбран — серая карта
    if not cfg.selected_yucs:
        fig = _build_all_gray_map(geojson)
        st.plotly_chart(fig, use_container_width=True)
        st.info("ℹ️ Выберите хотя бы один ЮЦ в сайдбаре.")
        return

    # Подготовка данных (общая для обоих режимов)
    df_dist, yuc_color_map = _prepare_distribution_data(geojson, cfg, df_map_ref, df_all)

    is_table = st.session_state.get("dist_view", "map") == "table"

    if is_table:
        _render_distribution_table(df_dist, yuc_color_map, cfg)
    else:
        _render_distribution_map_figure(geojson, df_dist)


def _render_distribution_map_figure(
    geojson: dict,
    df_dist: pd.DataFrame,
) -> None:
    """Карта распределения юристов по ЮЦ."""
    fig = go.Figure()

    # Один trace на каждый ЮЦ (для легенды)
    active = df_dist[df_dist["group"] == "active"]
    for yuc_name in active["ЮЦ"].unique():
        subset = active[active["ЮЦ"] == yuc_name]
        color = subset.iloc[0]["color"]
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=subset["Регион"],
            z=[1] * len(subset),
            featureidkey="properties.name",
            colorscale=[[0, color], [1, color]],
            marker_opacity=0.75,
            marker_line_width=0.5,
            marker_line_color="#444444",
            hovertext=subset["hover"].tolist(),
            hovertemplate="%{hovertext}<extra></extra>",
            showscale=False,
            name=yuc_name,
        ))

    # Регионы без юристов (серый)
    no_lawyer = df_dist[df_dist["group"] == "no_lawyer"]
    if not no_lawyer.empty:
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=no_lawyer["Регион"],
            z=[1] * len(no_lawyer),
            featureidkey="properties.name",
            colorscale=[[0, COLOR_NO_LAWYER], [1, COLOR_NO_LAWYER]],
            marker_opacity=0.65,
            marker_line_width=0.5,
            marker_line_color="#444444",
            hovertext=no_lawyer["hover"].tolist(),
            hovertemplate="%{hovertext}<extra></extra>",
            showscale=False,
            name="Нет юриста",
        ))

    # Невыбранные ЮЦ
    unselected = df_dist[df_dist["group"] == "unselected"]
    if not unselected.empty:
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=unselected["Регион"],
            z=[1] * len(unselected),
            featureidkey="properties.name",
            colorscale=[[0, COLOR_UNSELECTED], [1, COLOR_UNSELECTED]],
            marker_opacity=0.35,
            marker_line_width=0.3,
            marker_line_color="#555555",
            hovertext=unselected["hover"].tolist(),
            hovertemplate="%{hovertext}<extra></extra>",
            showscale=False,
            name="Не выбран",
            showlegend=False,
        ))

    # Точки столиц
    _add_capital_dots(fig, df_dist["Регион"].tolist())

    fig.update_layout(
        mapbox_style="white-bg",
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=800,
        mapbox_zoom=2.2,
        mapbox_center={"lat": 65, "lon": 100},
        legend=dict(
            title="Юридические центры",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="rgba(0,0,0,0.1)",
            borderwidth=1,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_distribution_table(
    df_dist: pd.DataFrame,
    yuc_color_map: dict[str, str],
    cfg: AppConfig,
) -> None:
    """Табличное представление: колонки ЮЦ, строки — регионы."""

    # Берём только выбранные ЮЦ из данных (active + no_lawyer)
    df_selected = df_dist[df_dist["group"].isin(["active", "no_lawyer"])].copy()

    if df_selected.empty:
        st.info("Нет данных для отображения.")
        return

    # Собираем данные по каждому ЮЦ
    yucs_in_data = [y for y in cfg.selected_yucs if y in df_selected["ЮЦ"].unique()]
    if not yucs_in_data:
        st.info("Нет данных для выбранных ЮЦ.")
        return

    # Создаём колонки Streamlit по числу ЮЦ
    cols = st.columns(len(yucs_in_data))

    for col, yuc_name in zip(cols, yucs_in_data):
        yuc_data = df_selected[df_selected["ЮЦ"] == yuc_name].sort_values(
            by=["group", "Регион"], ascending=[True, True]
        )

        # Считаем статистику
        n_with = len(yuc_data[yuc_data["group"] == "active"])
        n_without = len(yuc_data[yuc_data["group"] == "no_lawyer"])
        color = yuc_color_map.get(yuc_name, "#666")

        # Заголовок колонки: цветная полоска + название + статистика
        col.markdown(
            f'<div style="border-left: 5px solid {color}; padding-left: 10px; margin-bottom: 8px;">'
            f'<b style="font-size: 1.05rem;">{yuc_name}</b><br>'
            f'<span style="font-size: 0.85rem; color: var(--text-color);">'
            f'✅ {n_with} &nbsp; '
            f'<span style="color: {COLOR_NO_LAWYER};">⬜ {n_without}</span>'
            f'</span></div>',
            unsafe_allow_html=True,
        )

        # Список регионов
        lines = []
        for _, row in yuc_data.iterrows():
            region = row["Регион"]
            n_lawyers = int(row["lawyers_count"])
            crown = "👑 " if row.get("is_crown", False) else ""

            if row["group"] == "active":
                lines.append(
                    f'<div style="padding: 3px 0; font-size: 0.9rem;">'
                    f'{crown}{region} '
                    f'<span style="color: var(--text-color); opacity: 0.6;">({n_lawyers})</span>'
                    f'</div>'
                )
            else:
                lines.append(
                    f'<div style="padding: 3px 0; font-size: 0.9rem; '
                    f'color: {COLOR_NO_LAWYER};">'
                    f'{region}'
                    f'</div>'
                )

        col.markdown("".join(lines), unsafe_allow_html=True)


# ==========================================
# Общие вспомогательные функции
# ==========================================
def _format_hover(row: pd.Series, sel_types: list[str], use_coeffs: bool) -> str:
    """Форматирует hover-текст для одного региона."""
    region = row["Регион"]
    value = row["Value"]
    capital_info = _find_capital(region)
    capital_line = f"<i>Столица: {capital_info[0]}</i>" if capital_info else ""

    if value == 0:
        parts = [f"<b>{region}</b>", "нет данных/юриста"]
        if capital_line:
            parts.append(capital_line)
        return "<br>".join(parts)

    if use_coeffs:
        parts = [f"<b>{region}</b>", f"Единое приведенное значение: {value:.2f}"]
        if capital_line:
            parts.append(capital_line)
        return "<br>".join(parts)

    lines = [f"<b>{region}</b>"]
    for t in sel_types:
        t_val = row.get(t, 0)
        if t_val > 0:
            lines.append(f"{t}: {t_val:.2f}")
    lines.append(f"<b>Всего: {value:.2f}</b>")
    if capital_line:
        lines.append(capital_line)
    return "<br>".join(lines)


def _build_region_yuc_map(
    df_map_ref: pd.DataFrame,
    df_data: pd.DataFrame,
) -> dict[str, str]:
    """Строит маппинг Регион → ЮЦ из справочника и данных."""
    reg_to_yuc = {}
    for df in [df_map_ref, df_data]:
        if "Регион" not in df.columns or "ЮЦ" not in df.columns:
            continue
        for _, row in df.iterrows():
            if pd.notna(row.get("Регион")):
                reg_to_yuc[str(row["Регион"]).strip()] = str(row["ЮЦ"]).strip()
    return reg_to_yuc


def _add_capital_dots(fig: go.Figure, regions: list[str]) -> None:
    """
    Добавляет точки столиц регионов на карту.

    Точки только визуальные — hover отключён, название столицы
    отображается в hover самого региона (choropleth).
    """
    lats, lons = [], []
    for region in regions:
        cap = _find_capital(region)
        if cap:
            lats.append(cap[1])
            lons.append(cap[2])

    if lats:
        fig.add_trace(go.Scattermapbox(
            lat=lats,
            lon=lons,
            mode="markers",
            marker=dict(size=4, color="#333333", opacity=0.7),
            hoverinfo="skip",
            showlegend=False,
            name="Столицы",
        ))


def _build_all_gray_map(geojson: dict) -> go.Figure:
    """Полностью серая карта (когда нет выбранных ЮЦ)."""
    all_regions = [f["properties"]["name"] for f in geojson["features"]]
    hovers = []
    for r in all_regions:
        cap = _find_capital(r)
        cap_line = f"<br><i>Столица: {cap[0]}</i>" if cap else ""
        hovers.append(f"<b>{r}</b>{cap_line}")

    fig = go.Figure()
    fig.add_trace(go.Choroplethmapbox(
        geojson=geojson,
        locations=all_regions,
        z=[1] * len(all_regions),
        featureidkey="properties.name",
        colorscale=[[0, COLOR_NO_LAWYER], [1, COLOR_NO_LAWYER]],
        marker_opacity=0.5,
        marker_line_width=0.3,
        marker_line_color="#555555",
        hovertext=hovers,
        hovertemplate="%{hovertext}<extra></extra>",
        showscale=False,
    ))
    _add_capital_dots(fig, all_regions)
    fig.update_layout(
        mapbox_style="white-bg",
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=800,
        mapbox_zoom=2.2,
        mapbox_center={"lat": 65, "lon": 100},
    )
    return fig


def _build_heatmap_figure(
    geojson: dict,
    df_active: pd.DataFrame,
    df_zero: pd.DataFrame,
    df_other: pd.DataFrame,
) -> go.Figure:
    """Строит Choroplethmapbox с тремя слоями для режима нагрузки."""
    fig = go.Figure()

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

    if not df_other.empty:
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=df_other["Регион"],
            z=[1] * len(df_other),
            featureidkey="properties.name",
            colorscale=[[0, COLOR_UNSELECTED], [1, COLOR_UNSELECTED]],
            marker_opacity=0.4,
            marker_line_width=0.3,
            marker_line_color="#555555",
            hovertext=df_other["Hover_Text"].tolist(),
            hovertemplate="%{hovertext}<extra></extra>",
            showscale=False,
        ))

    if not df_zero.empty:
        fig.add_trace(go.Choroplethmapbox(
            geojson=geojson,
            locations=df_zero["Регион"],
            z=[1] * len(df_zero),
            featureidkey="properties.name",
            colorscale=[[0, COLOR_NO_LAWYER], [1, COLOR_NO_LAWYER]],
            marker_opacity=0.6,
            marker_line_width=0.3,
            marker_line_color="#555555",
            hovertext=df_zero["Hover_Text"].tolist(),
            hovertemplate="%{hovertext}<extra></extra>",
            showscale=False,
        ))

    # Точки столиц
    all_regions = (
        df_active["Регион"].tolist()
        + df_zero["Регион"].tolist()
        + df_other["Регион"].tolist()
    )
    _add_capital_dots(fig, all_regions)

    fig.update_layout(
        mapbox_style="white-bg",
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=800,
        mapbox_zoom=2.2,
        mapbox_center={"lat": 65, "lon": 100},
    )

    return fig
