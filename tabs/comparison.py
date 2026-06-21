"""Вкладка сравнения факта 2025 года с прогнозом 2026 года по ЮЦ."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from calculations import apply_calculations
from components import tab_header
from config import AppConfig, COLORS_MAP, FORECAST_FACTOR_2026, LoadType


ACCOUNTED = "Учтенная нагрузка"
COURT_UNACCOUNTED = "СД Н (неучтенные)"
ADMIN_UNACCOUNTED = "АД Н (неучтенные)"


def _change_cell_style(value: float) -> str:
    """Зелёная подсветка роста, красная — снижения, ноль остаётся нейтральным."""
    if pd.isna(value) or value == 0:
        return ""
    if value > 0:
        return "background-color: #DCFCE7; color: #166534; font-weight: 600;"
    return "background-color: #FEE2E2; color: #991B1B; font-weight: 600;"


def _render_type_filters() -> list[str]:
    """Пять типов общей нагрузки; на вкладке сравнения все включены по умолчанию."""
    labels = [
        ("Судебные дела", LoadType.COURT.value, "cmp_court", True),
        ("Админ. дела", LoadType.ADMIN.value, "cmp_admin", True),
        ("Претензии", LoadType.CLAIMS.value, "cmp_claims", True),
        ("Консультации", LoadType.CONSULT.value, "cmp_consult", False),
        ("Запросы", LoadType.REQUESTS.value, "cmp_requests", False),
    ]
    selected = []
    for col, (label, value, key, default) in zip(st.columns(5), labels):
        if col.toggle(label, value=default, key=key):
            selected.append(value)
    return selected


def prepare_comparison_data(
    df_2025: pd.DataFrame,
    df_2026: pd.DataFrame,
    cfg: AppConfig,
    selected_types: list[str],
    include_court_unaccounted: bool,
    include_admin_unaccounted: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Возвращает рассчитанные данные: 2025 факт, 2026 за 5 месяцев и прогноз."""
    d25 = df_2025[
        (df_2025["Год"] == 2025)
        & (df_2025["ЮЦ"].isin(cfg.selected_yucs))
        & (df_2025["Тип"].isin(selected_types))
    ].copy()
    d25["Сегмент"] = ACCOUNTED

    allowed_segments = [ACCOUNTED]
    if include_court_unaccounted:
        allowed_segments.append(COURT_UNACCOUNTED)
    if include_admin_unaccounted:
        allowed_segments.append(ADMIN_UNACCOUNTED)

    d26 = df_2026[
        (df_2026["ЮЦ"].isin(cfg.selected_yucs))
        & (df_2026["Тип"].isin(selected_types))
        & (df_2026["Сегмент"].isin(allowed_segments))
    ].copy()

    d25 = apply_calculations(d25, cfg)
    d26_5m = apply_calculations(d26, cfg)
    d26_forecast = d26_5m.copy()
    d26_forecast["Value"] *= FORECAST_FACTOR_2026
    return d25, d26_5m, d26_forecast


def _series_by_yuc(df: pd.DataFrame, yucs: list[str], segment: str | None = None) -> list[float]:
    source = df if segment is None else df[df["Сегмент"] == segment]
    values = source.groupby("ЮЦ")["Value"].sum()
    return [float(values.get(yuc, 0)) for yuc in yucs]


def render(
    df_2025: pd.DataFrame,
    df_2026: pd.DataFrame,
    cfg: AppConfig,
    flagged_2025_load: float = 0.0,
) -> None:
    """Отрисовывает сравнение общей нагрузки юридических центров."""
    tab_header("2025 год и прогноз на 2026 год", "📈 2025 / прогноз 2026")
    st.caption(
        "Прогноз 2026 = факт за январь–май × 2,4. "
        "Линейная экстраполяция не учитывает сезонность."
    )

    selected_types = _render_type_filters()
    if not selected_types:
        st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
        return

    u1, u2, _ = st.columns([2, 2, 6])
    include_court_unaccounted = u1.toggle(
        "СД Н — неучтённые", value=False,
        disabled=LoadType.COURT.value not in selected_types,
        key="cmp_court_unaccounted",
    )
    include_admin_unaccounted = u2.toggle(
        "АД Н — неучтённые", value=False,
        disabled=LoadType.ADMIN.value not in selected_types,
        key="cmp_admin_unaccounted",
    )
    st.divider()

    if flagged_2025_load != 0:
        st.warning(
            "У сотрудников с отметкой «Уволен/ЕЦПО» обнаружена ненулевая "
            f"нагрузка 2025 года: {flagged_2025_load:,.2f}. Она исключена из сравнения."
        )

    d25, d26_5m, d26_forecast = prepare_comparison_data(
        df_2025, df_2026, cfg, selected_types,
        include_court_unaccounted, include_admin_unaccounted,
    )
    if d25.empty and d26_forecast.empty:
        st.info("Нет данных для выбранных ЮЦ и типов нагрузки.")
        return

    total_2025 = float(d25["Value"].sum())
    total_2026_5m = float(d26_5m["Value"].sum())
    total_2026_forecast = float(d26_forecast["Value"].sum())
    delta = total_2026_forecast - total_2025
    delta_pct = delta / total_2025 * 100 if total_2025 else None

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("2025 — факт", f"{total_2025:,.1f}")
    m2.metric("2026 — факт за 5 мес.", f"{total_2026_5m:,.1f}")
    m3.metric("2026 — прогноз", f"{total_2026_forecast:,.1f}")
    m4.metric(
        "Изменение к 2025",
        f"{delta:+,.1f}",
        f"{delta_pct:+.1f}%" if delta_pct is not None else "нет базы",
    )

    yucs = [
        y for y in cfg.selected_yucs
        if y in set(d25["ЮЦ"]).union(set(d26_forecast["ЮЦ"]))
    ]
    fig = go.Figure()
    fig.add_bar(
        x=yucs, y=_series_by_yuc(d25, yucs), name="2025 — факт",
        marker_color="#636EFA", offsetgroup="2025",
        texttemplate="%{y:.1f}", textposition="auto",
    )
    fig.add_bar(
        x=yucs, y=_series_by_yuc(d26_forecast, yucs, ACCOUNTED),
        name="2026 — прогноз", marker_color="#F59E0B", offsetgroup="2026",
        texttemplate="%{y:.1f}", textposition="auto",
    )
    if include_court_unaccounted:
        fig.add_bar(
            x=yucs, y=_series_by_yuc(d26_forecast, yucs, COURT_UNACCOUNTED),
            name="СД Н — прогноз", marker_color="rgba(239,85,59,0.45)",
            offsetgroup="2026", texttemplate="%{y:.1f}", textposition="auto",
        )
    if include_admin_unaccounted:
        fig.add_bar(
            x=yucs, y=_series_by_yuc(d26_forecast, yucs, ADMIN_UNACCOUNTED),
            name="АД Н — прогноз", marker_color="rgba(0,204,150,0.45)",
            offsetgroup="2026", texttemplate="%{y:.1f}", textposition="auto",
        )
    fig.update_layout(
        title="Общая нагрузка по ЮЦ",
        barmode="stack",
        yaxis_title="Нагрузка",
        xaxis_title=None,
        legend_title=None,
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")

    type_2025 = d25.groupby("Тип")["Value"].sum()
    type_2026_accounted = (
        d26_forecast[d26_forecast["Сегмент"] == ACCOUNTED]
        .groupby("Тип")["Value"].sum()
    )
    type_order = [t for t in COLORS_MAP if t in selected_types]
    fig_types = go.Figure()
    fig_types.add_bar(
        x=type_order, y=[type_2025.get(t, 0) for t in type_order],
        name="2025 — факт", marker_color="#636EFA", offsetgroup="2025",
    )
    fig_types.add_bar(
        x=type_order, y=[type_2026_accounted.get(t, 0) for t in type_order],
        name="2026 — прогноз", marker_color="#F59E0B", offsetgroup="2026",
    )
    if include_court_unaccounted:
        court_n = d26_forecast[
            d26_forecast["Сегмент"] == COURT_UNACCOUNTED
        ]["Value"].sum()
        fig_types.add_bar(
            x=type_order,
            y=[court_n if t == LoadType.COURT.value else 0 for t in type_order],
            name="СД Н — прогноз", marker_color="rgba(239,85,59,0.45)",
            offsetgroup="2026",
        )
    if include_admin_unaccounted:
        admin_n = d26_forecast[
            d26_forecast["Сегмент"] == ADMIN_UNACCOUNTED
        ]["Value"].sum()
        fig_types.add_bar(
            x=type_order,
            y=[admin_n if t == LoadType.ADMIN.value else 0 for t in type_order],
            name="АД Н — прогноз", marker_color="rgba(0,204,150,0.45)",
            offsetgroup="2026",
        )
    fig_types.update_layout(
        title="Структура нагрузки по типам",
        barmode="stack", yaxis_title="Нагрузка", xaxis_title=None,
        legend_title=None,
    )
    st.plotly_chart(fig_types, width="stretch")

    rows = []
    for yuc in yucs:
        v25 = _series_by_yuc(d25[d25["ЮЦ"] == yuc], [yuc])[0]
        v5 = _series_by_yuc(d26_5m[d26_5m["ЮЦ"] == yuc], [yuc])[0]
        vf = _series_by_yuc(d26_forecast[d26_forecast["ЮЦ"] == yuc], [yuc])[0]
        diff = vf - v25
        rows.append({
            "ЮЦ": yuc,
            "2025 — факт": v25,
            "2026 — 5 мес.": v5,
            "2026 — прогноз": vf,
            "Изменение": diff,
            "Изменение, %": diff / v25 * 100 if v25 else None,
        })
    detail = pd.DataFrame(rows).sort_values("Изменение", ascending=False)
    styled_detail = detail.style.map(
        _change_cell_style,
        subset=["Изменение", "Изменение, %"],
    )
    st.subheader("Детализация по ЮЦ")
    st.dataframe(
        styled_detail,
        width="stretch",
        hide_index=True,
        column_config={
            "2025 — факт": st.column_config.NumberColumn(format="%.1f"),
            "2026 — 5 мес.": st.column_config.NumberColumn(format="%.1f"),
            "2026 — прогноз": st.column_config.NumberColumn(format="%.1f"),
            "Изменение": st.column_config.NumberColumn(format="%+.1f"),
            "Изменение, %": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
