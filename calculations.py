"""
Бизнес-логика расчётов: применение коэффициентов, вычисление средних.
"""

import pandas as pd

from config import AppConfig


# ==========================================
# Мультипликаторы по типам нагрузки
# ==========================================
def _get_multiplier(raw_type: str, cfg: AppConfig, force_flat: bool = False) -> float:
    """
    Возвращает коэффициент-множитель для конкретного Raw_Type.

    При force_flat=True все множители = 1.0 (для трендов/плоских сравнений).
    """
    if force_flat:
        return 1.0

    r = str(raw_type).lower().strip()

    if not cfg.use_coeffs:
        # Без коэффициентов: базовые множители
        if "сд з" in r or "неабонентские" in r:
            return 1.0
        if "сд ж" in r or "абонентские" in r:
            return 0.5
        return 1.0

    # С пользовательскими коэффициентами
    if "сд з" in r:
        return cfg.k_sd * 1.0
    if "сд ж" in r:
        return cfg.k_sd * 0.5
    if r == "сд":
        return cfg.k_sd
    if "ад" in r:
        return cfg.k_ad
    if "неабонентские" in r or r == "претензии":
        return cfg.k_pr_n
    if "абонентские" in r:
        return cfg.k_pr_a

    return 1.0


# ==========================================
# Применение расчётов к DataFrame
# ==========================================
def apply_calculations(
    df: pd.DataFrame,
    cfg: AppConfig,
    force_flat: bool = False,
) -> pd.DataFrame:
    """
    Применяет коэффициенты к значениям и группирует результат.

    Возвращает DataFrame с агрегированными Value.
    """
    df_mod = df.copy()

    # Векторное вычисление множителей (вместо .apply по строкам)
    multipliers = df_mod["Raw_Type"].map(
        lambda raw: _get_multiplier(raw, cfg, force_flat)
    )
    df_mod["Value"] = df_mod["Value"] * multipliers

    # Группировка: все колонки кроме Value и Raw_Type
    group_cols = [c for c in df_mod.columns if c not in ("Value", "Raw_Type")]
    return df_mod.groupby(group_cols, dropna=False)["Value"].sum().reset_index()


# ==========================================
# Расчёт средних по стране
# ==========================================
def calc_country_avg_by_employee(
    df_country: pd.DataFrame,
    sel_types: list[str],
    cfg: AppConfig,
) -> float:
    """Средняя нагрузка на сотрудника по РФ."""
    df_c = apply_calculations(
        df_country[df_country["Тип"].isin(sel_types)].copy(), cfg
    )
    if df_c.empty:
        return 0.0
    return df_c.groupby("Сотрудник")["Value"].sum().mean()


def calc_country_avg_by_yuc(
    df_country: pd.DataFrame,
    sel_types: list[str],
    cfg: AppConfig,
) -> float:
    """Средняя нагрузка на ЮЦ по РФ."""
    df_c = apply_calculations(
        df_country[df_country["Тип"].isin(sel_types)].copy(), cfg
    )
    if df_c.empty:
        return 0.0
    return df_c.groupby("ЮЦ")["Value"].sum().mean()