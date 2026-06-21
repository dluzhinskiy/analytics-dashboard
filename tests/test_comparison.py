"""Проверки загрузки и расчётов вкладки сравнения."""

import os
import sys
import unittest

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from calculations import _get_multiplier
from config import AppConfig, DATA_FILE, DATA_FILE_2026, FORECAST_FACTOR_2026
from data_loader import (
    extrapolate_2026_data,
    filter_2026_segments,
    preprocess_2026_stats,
    preprocess_stats,
)
from tabs.comparison import (
    ADMIN_UNACCOUNTED,
    COURT_UNACCOUNTED,
    prepare_comparison_data,
)


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_2025 = pd.read_excel(DATA_FILE, sheet_name=0)
        cls.raw_2026 = pd.read_excel(DATA_FILE_2026, sheet_name=0)
        cls.df_2025 = preprocess_stats(cls.raw_2025)
        cls.df_2026 = preprocess_2026_stats(cls.raw_2026)
        cls.cfg = AppConfig(
            selected_yucs=sorted(cls.raw_2026["ЮЦ"].dropna().unique().tolist())
        )
        cls.types = sorted(cls.df_2026["Тип"].unique().tolist())

    def test_2026_schema_excludes_red_court_cases(self):
        self.assertNotIn("СД К", set(self.df_2026["Raw_Type"]))
        self.assertEqual(len(self.df_2026), len(self.raw_2026) * 9)

    def test_empty_cells_are_zero(self):
        self.assertFalse(self.df_2026["Value"].isna().any())

    def test_unaccounted_coefficients_are_always_one(self):
        cfg = AppConfig(use_coeffs=True, k_sd=4.0, k_ad=3.0)
        self.assertEqual(_get_multiplier("СД Н", cfg), 1.0)
        self.assertEqual(_get_multiplier("АД Н", cfg), 1.0)

    def test_unaccounted_segments_are_off_by_default(self):
        _, five_months, forecast = prepare_comparison_data(
            self.df_2025, self.df_2026, self.cfg, self.types, False, False
        )
        self.assertFalse(
            five_months["Сегмент"].isin([COURT_UNACCOUNTED, ADMIN_UNACCOUNTED]).any()
        )
        self.assertAlmostEqual(
            forecast["Value"].sum(),
            five_months["Value"].sum() * FORECAST_FACTOR_2026,
        )

    def test_unaccounted_segments_can_be_enabled(self):
        _, five_months, _ = prepare_comparison_data(
            self.df_2025, self.df_2026, self.cfg, self.types, True, True
        )
        self.assertIn(COURT_UNACCOUNTED, set(five_months["Сегмент"]))
        self.assertIn(ADMIN_UNACCOUNTED, set(five_months["Сегмент"]))

    def test_regular_2026_tabs_exclude_unaccounted_by_default(self):
        regular = filter_2026_segments(self.df_2026)
        self.assertEqual(set(regular["Сегмент"]), {"Учтенная нагрузка"})

        with_unaccounted = filter_2026_segments(self.df_2026, True, True)
        added = with_unaccounted["Value"].sum() - regular["Value"].sum()
        self.assertEqual(float(added), 445.0)

    def test_2026_extrapolation_is_optional(self):
        regular = filter_2026_segments(self.df_2026)
        unchanged = extrapolate_2026_data(regular, False)
        forecast = extrapolate_2026_data(regular, True)
        self.assertEqual(float(unchanged["Value"].sum()), float(regular["Value"].sum()))
        self.assertAlmostEqual(
            float(forecast["Value"].sum()),
            float(regular["Value"].sum()) * FORECAST_FACTOR_2026,
        )

    def test_marked_2025_employees_have_zero_load(self):
        marked = self.raw_2025["Уволен\\ЕЦПО"].astype(str).str.contains(
            r"[xXхХ]", na=False
        )
        names = set(self.raw_2025.loc[marked, "Сотрудник"])
        total = self.df_2025[
            (self.df_2025["Год"] == 2025)
            & (self.df_2025["Сотрудник"].isin(names))
        ]["Value"].sum()
        self.assertEqual(float(total), 0.0)


if __name__ == "__main__":
    unittest.main()
