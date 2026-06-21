"""
Загрузка и предобработка данных из Excel и GeoJSON.
"""

import json
import os

import pandas as pd
import streamlit as st

from config import (
    DATA_FILE, DATA_FILE_2026, GEOJSON_FILE, FORECAST_FACTOR_2026,
    REGION_COLUMN_KEYWORDS, YUC_COLUMN_KEYWORDS,
    FIRED_COLUMN_KEYWORD, CROWN_COLUMN_KEYWORDS,
    MARK_PATTERN, RAW_TYPE_MAPPING,
)


# ==========================================
# Загрузка данных
# ==========================================
@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Загружает statistics.xlsx:
      - Лист 0: основная статистика
      - Лист 1 (если есть): маппинг Регион → ЮЦ

    Возвращает (df_stats, df_mapping).
    """
    df_stats = pd.DataFrame()
    df_mapping = pd.DataFrame()

    try:
        xls = pd.ExcelFile(DATA_FILE)
        df_stats = pd.read_excel(xls, sheet_name=0)

        if len(xls.sheet_names) > 1:
            df_mapping = _parse_mapping_sheet(pd.read_excel(xls, sheet_name=1))

    except Exception as e:
        st.error(f"❌ Ошибка загрузки файла '{DATA_FILE}': {e}")
        return df_stats, df_mapping

    # Очистка строковых колонок
    if not df_stats.empty:
        for col in ["ЮЦ", "Регион", "Сотрудник"]:
            if col in df_stats.columns:
                df_stats[col] = df_stats[col].astype(str).str.strip()

    return df_stats, df_mapping


@st.cache_data
def load_2026_data() -> pd.DataFrame:
    """Загружает данные за январь–май 2026 года из отдельного файла."""
    try:
        df = pd.read_excel(DATA_FILE_2026, sheet_name=0)
    except Exception as e:
        st.error(f"❌ Ошибка загрузки файла '{DATA_FILE_2026}': {e}")
        return pd.DataFrame()

    for col in ["ЮЦ", "Регион", "Сотрудник"]:
        if col in df.columns:
            # Сохраняем пропуски пропусками, а не строкой "nan".
            df[col] = df[col].astype("string").str.strip()
    return df


def _parse_mapping_sheet(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Разбирает лист маппинга Регион → ЮЦ с автоопределением колонок."""
    reg_col = _find_column(df_raw, REGION_COLUMN_KEYWORDS)
    yuc_col = _find_column(df_raw, YUC_COLUMN_KEYWORDS)

    if reg_col and yuc_col:
        df_mapping = df_raw[[reg_col, yuc_col]].copy()
    elif len(df_raw.columns) >= 2:
        # Fallback: определяем порядок по содержимому первой строки
        first_val = str(df_raw.iloc[0, 0])
        if any(x in first_val for x in ["Дальний Восток", "Сибирь", "Урал"]):
            df_mapping = df_raw.iloc[:, [1, 0]].copy()
        else:
            df_mapping = df_raw.iloc[:, :2].copy()
    else:
        return pd.DataFrame()

    df_mapping.columns = ["Регион", "ЮЦ"]
    df_mapping["Регион"] = df_mapping["Регион"].astype(str).str.strip()
    df_mapping["ЮЦ"] = df_mapping["ЮЦ"].astype(str).str.strip()
    return df_mapping


def _find_column(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """Находит первую колонку, содержащую одно из ключевых слов."""
    for col in df.columns:
        col_lower = str(col).lower()
        if any(kw in col_lower for kw in keywords):
            return col
    return None


@st.cache_data
def load_geojson() -> dict | None:
    """Загружает GeoJSON-файл карты России."""
    if not os.path.exists(GEOJSON_FILE):
        return None
    with open(GEOJSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ==========================================
# Предобработка статистики
# ==========================================
def preprocess_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Преобразует wide-формат статистики в long-формат:
    колонки вида '2025 (СД)' → строки с Год, Тип, Value.
    """
    id_vars = ["ЮЦ", "Сотрудник"]
    if "Регион" in df.columns:
        id_vars.append("Регион")

    value_vars = [c for c in df.columns if "20" in str(c) and "(" in str(c)]

    df_melted = df.melt(
        id_vars=id_vars,
        value_vars=value_vars,
        var_name="Year_Metric",
        value_name="Value",
    )
    df_melted["Value"] = pd.to_numeric(df_melted["Value"], errors="coerce").fillna(0)

    # Извлекаем год и тип из названия колонки
    extracted = df_melted["Year_Metric"].str.extract(r"(\d{4})\s+(.*)")
    df_melted["Год"] = extracted[0].astype(float).astype("Int64")
    df_melted["Raw_Type"] = extracted[1].str.replace(r"[\(\)]", "", regex=True).str.strip()

    # Маппинг сокращений в читаемые названия
    df_melted["Тип"] = df_melted["Raw_Type"].map(_map_type)

    return df_melted.dropna(subset=["Год", "Тип"]).drop(columns=["Year_Metric"])


def preprocess_2026_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Приводит данные за 5 месяцев 2026 года к общей long-схеме.

    СД К исключаются полностью. СД Н и АД Н сохраняются отдельными
    сегментами, чтобы пользователь мог подключать их переключателями.
    Пустые числовые ячейки считаются нулями.
    """
    column_map = {
        "СД З": ("СД З", "Учтенная нагрузка"),
        "СД Ж": ("СД Ж", "Учтенная нагрузка"),
        "СД Н": ("СД Н", "СД Н (неучтенные)"),
        "АД": ("АД", "Учтенная нагрузка"),
        "АД Н": ("АД Н", "АД Н (неучтенные)"),
        "претензии неабонентские": ("претензии неабонентские", "Учтенная нагрузка"),
        "претензии абонентские": ("претензии абонентские", "Учтенная нагрузка"),
        "консультации": ("консультации", "Учтенная нагрузка"),
        "запросы": ("запросы", "Учтенная нагрузка"),
    }
    required = ["ЮЦ", "Сотрудник", *column_map]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "В файле 2026 отсутствуют обязательные колонки: " + ", ".join(missing)
        )

    id_vars = ["ЮЦ", "Сотрудник"]
    if "Регион" in df.columns:
        id_vars.append("Регион")

    melted = df.melt(
        id_vars=id_vars,
        value_vars=list(column_map),
        var_name="Source_Column",
        value_name="Value",
    )
    melted["Value"] = pd.to_numeric(melted["Value"], errors="coerce").fillna(0)
    melted["Raw_Type"] = melted["Source_Column"].map(
        lambda c: column_map[c][0]
    )
    melted["Сегмент"] = melted["Source_Column"].map(
        lambda c: column_map[c][1]
    )
    melted["Тип"] = melted["Raw_Type"].map(_map_type)
    melted["Год"] = 2026
    return melted.drop(columns=["Source_Column"])


def filter_2026_segments(
    df: pd.DataFrame,
    include_court_unaccounted: bool = False,
    include_admin_unaccounted: bool = False,
) -> pd.DataFrame:
    """Подключает неучтённые СД/АД к обычным вкладкам только по запросу."""
    allowed = ["Учтенная нагрузка"]
    if include_court_unaccounted:
        allowed.append("СД Н (неучтенные)")
    if include_admin_unaccounted:
        allowed.append("АД Н (неучтенные)")
    return df[df["Сегмент"].isin(allowed)].copy()


def extrapolate_2026_data(df: pd.DataFrame, enabled: bool = False) -> pd.DataFrame:
    """Линейно приводит факт за 5 месяцев к полному году при включённом режиме."""
    result = df.copy()
    if enabled:
        result["Value"] = result["Value"] * FORECAST_FACTOR_2026
    return result


def _map_type(raw_type: str) -> str:
    """Преобразует сокращение типа нагрузки в полное название."""
    t_lower = str(raw_type).lower()
    for keyword, full_name in RAW_TYPE_MAPPING.items():
        if keyword in t_lower:
            return full_name
    return raw_type


# ==========================================
# Фильтры сотрудников
# ==========================================
def get_fired_employees(df: pd.DataFrame) -> set[str]:
    """Возвращает множество уволенных сотрудников (отмечены X в колонке 'уволен')."""
    return _get_marked_employees(df, [FIRED_COLUMN_KEYWORD])


def get_crown_employees(df: pd.DataFrame) -> set[str]:
    """Возвращает множество работников ЮЦ (отмечены X в колонке-признаке)."""
    return _get_marked_employees(df, CROWN_COLUMN_KEYWORDS)


def _get_marked_employees(df: pd.DataFrame, keywords: list[str]) -> set[str]:
    """Общая логика поиска отмеченных сотрудников по ключевым словам в названии колонки."""
    target_col = None
    for col in df.columns:
        if isinstance(col, str):
            col_lower = col.lower().strip()
            if any(kw in col_lower for kw in keywords):
                target_col = col
                break

    if target_col is None:
        return set()

    mask = df[target_col].astype(str).str.contains(MARK_PATTERN, na=False)
    return set(df[mask]["Сотрудник"].unique())
