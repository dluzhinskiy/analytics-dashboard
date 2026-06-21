"""
Конфигурация приложения: константы, типы нагрузки, настройки по умолчанию.
"""

import os
from dataclasses import dataclass, field
from enum import Enum


# ==========================================
# Типы нагрузки
# ==========================================
class LoadType(str, Enum):
    """Перечисление типов юридической нагрузки."""
    COURT = "Судебные дела"
    ADMIN = "Административные дела"
    CLAIMS = "Претензии"
    CONSULT = "Консультации"
    REQUESTS = "Запросы"


# Основные типы (используются на большинстве вкладок)
MAIN_LOAD_TYPES = [LoadType.COURT, LoadType.ADMIN, LoadType.CLAIMS]

# Дополнительные типы (консультации и запросы)
EXTRA_LOAD_TYPES = [LoadType.CONSULT, LoadType.REQUESTS]

# Все типы
ALL_LOAD_TYPES = MAIN_LOAD_TYPES + EXTRA_LOAD_TYPES


# ==========================================
# Цветовая палитра для графиков
# ==========================================
COLORS_MAP = {
    LoadType.COURT.value: "#636EFA",
    LoadType.CLAIMS.value: "#EF553B",
    LoadType.ADMIN.value: "#00CC96",
    LoadType.CONSULT.value: "#AB63FA",
    LoadType.REQUESTS.value: "#FFA15A",
}

# Цвета для отдельных графиков
COLOR_PRIMARY = "#636EFA"
COLOR_SECONDARY = "#EF553B"
COLOR_AVERAGE_LINE = "#D62728"


# ==========================================
# Настройки приложения (dataclass вместо dict)
# ==========================================
@dataclass
class AppConfig:
    """Конфигурация, собираемая из сайдбара."""
    use_coeffs: bool = False
    k_sd: float = 1.0
    k_ad: float = 0.5
    k_pr_n: float = 0.5
    k_pr_a: float = 0.25
    show_avg: bool = True
    show_emp_filter: bool = False
    selected_yucs: list = field(default_factory=list)
    selected_year: int = 2025
    extrapolate_2026: bool = False
    include_court_unaccounted: bool = False
    include_admin_unaccounted: bool = False


# ==========================================
# Пути к файлам
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "statistics.xlsx")
DATA_FILE_2026 = os.path.join(BASE_DIR, "statistics 5m26.xlsx")
GEOJSON_FILE = os.path.join(BASE_DIR, "final_russia.geojson")

# Пять месяцев 2026 года линейно приводятся к полному году.
FORECAST_MONTHS_2026 = 5
FORECAST_FACTOR_2026 = 12 / FORECAST_MONTHS_2026


# ==========================================
# Навигация (вкладки)
# ==========================================
TABS = [
    "👥 Сотрудники",
    "🏢 ЮЦ",
    "🗺️ Тепловая карта",
    "💬 Доп. нагрузка",
    "📈 2025 / прогноз 2026",
]


# ==========================================
# Маппинг Raw_Type → Тип (для preprocess)
# ==========================================
RAW_TYPE_MAPPING = {
    "сд": LoadType.COURT.value,
    "ад": LoadType.ADMIN.value,
    "претензии": LoadType.CLAIMS.value,
    "консультации": LoadType.CONSULT.value,
    "запросы": LoadType.REQUESTS.value,
}


# ==========================================
# Ключевые слова для поиска колонок
# ==========================================
REGION_COLUMN_KEYWORDS = ["регион", "область", "край", "округ", "республика"]
YUC_COLUMN_KEYWORDS = ["юц", "центр"]
FIRED_COLUMN_KEYWORD = "уволен"
CROWN_COLUMN_KEYWORDS = ["работник юц", "сотрудник юц", "признак", "статус", "работник"]
MARK_PATTERN = r"[xXхХ]"
