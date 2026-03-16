"""
Конфигурация приложения: константы, типы нагрузки, настройки по умолчанию.
"""

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


# ==========================================
# Пути к файлам
# ==========================================
DATA_FILE = "statistics.xlsx"
GEOJSON_FILE = "final_russia.geojson"


# ==========================================
# Навигация (вкладки)
# ==========================================
TABS = [
    "👥 Сотрудники",
    "🏢 ЮЦ",
    "🗺️ Тепловая карта",
    "💬 Доп. нагрузка",
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