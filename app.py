import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import urllib.request

# --- Настройка страницы ---
st.set_page_config(page_title="Аналитика ЮЦ", layout="wide")
st.title("📊 Дэшборд аналитики сотрудников и ЮЦ")

# --- Глобальная палитра цветов ---
COLORS_MAP = {
    'Судебные дела': '#636EFA',  # Синий
    'претензии': '#EF553B',  # Красный
    'Административные дела': '#00CC96',  # Зеленый
    'Судебные дела (мало)': '#A0A0A0',  # Серый
    'претензии (мало)': '#B0B0B0',  # Светло-серый
    'Административные дела (мало)': '#808080'  # Темно-серый
}


# --- 1. Загрузка данных ---
@st.cache_data
def load_data():
    df_stats = pd.DataFrame()
    file_path = 'statistics.xlsx'

    try:
        # Пробуем Excel
        xls = pd.ExcelFile(file_path)
        df_stats = pd.read_excel(xls, sheet_name=0)
    except Exception as e:
        # Fallback для CSV
        try:
            df_stats = pd.read_csv('statistics.xlsx - Лист1.csv')
        except:
            st.error(f"Ошибка загрузки данных: {e}")

    return df_stats


# --- 2. Исправление GeoJSON ---
def fix_custom_geojson(raw_data):
    features = []
    for region_name, parts in raw_data.items():
        multi_polygon_coords = []
        for part_id in sorted(parts.keys()):
            points = parts[part_id]
            # Меням Lat/Lon местами
            ring = []
            for p in points:
                if len(p) >= 2:
                    ring.append([p[1], p[0]])
            multi_polygon_coords.append([ring])

        feature = {
            "type": "Feature",
            "properties": {"name": region_name},
            "geometry": {"type": "MultiPolygon", "coordinates": multi_polygon_coords}
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


# --- 3. Загрузка карты ---
@st.cache_data
def load_geojson():
    local_file = 'russia.geojson'
    data = None

    # 1. Локальный
    if os.path.exists(local_file):
        try:
            with open(local_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            st.warning(f"Ошибка чтения 'russia.geojson': {e}")

    # 2. Онлайн
    if data is None:
        url = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/russia.geojson"
        try:
            with urllib.request.urlopen(url) as response:
                data = json.load(response)
        except Exception:
            pass

    if data is None:
        return None

    # Исправление формата
    if isinstance(data, dict) and 'features' not in data:
        try:
            data = fix_custom_geojson(data)
        except Exception:
            return None

    return data


# --- 4. Обработка статистики ---
def preprocess_stats(df):
    id_vars = ['ЮЦ', 'Сотрудник']
    if 'Регион' in df.columns:
        id_vars.append('Регион')

    # Ищем только колонки с годами
    value_vars = [c for c in df.columns if '20' in str(c) and '(' in str(c)]

    df_melted = df.melt(id_vars=id_vars, value_vars=value_vars, var_name='Year_Metric', value_name='Value')

    pattern = r'(\d{4})\s\((.*?)\)'
    extracted = df_melted['Year_Metric'].str.extract(pattern)
    df_melted['Год'] = extracted[0].astype(float).astype('Int64')
    df_melted['Тип'] = extracted[1]

    # Замена сокращений
    df_melted['Тип'] = df_melted['Тип'].replace({
        'СД': 'Судебные дела',
        'АД': 'Административные дела'
    })

    return df_melted.dropna(subset=['Год', 'Тип']).drop(columns=['Year_Metric'])


def identify_low_activity(df, threshold=5):
    df_2025 = df[df['Год'] == 2025]
    if df_2025.empty: return set()

    activity_2025 = df_2025.groupby('Сотрудник')['Value'].sum()
    low_activity_emps = activity_2025[activity_2025 <= threshold].index.tolist()

    all_emps = df['Сотрудник'].unique()
    emps_with_data = df_2025['Сотрудник'].unique()
    no_data = list(set(all_emps) - set(emps_with_data))
    return set(low_activity_emps + no_data)


def get_crown_employees(df):
    """Ищет сотрудников с пометкой X в спец. колонке"""
    target_col = None
    possible_names = ['работник юц', 'сотрудник юц', 'признак', 'статус', 'работник']

    for col in df.columns:
        if isinstance(col, str):
            c_low = col.lower().strip()
            if any(key in c_low for key in possible_names):
                target_col = col
                break

    if target_col:
        # Ищем 'X', 'x', 'Х', 'х'
        mask = df[target_col].astype(str).str.contains(r'[xXхХ]', na=False)
        return set(df[mask]['Сотрудник'].unique())

    return set()


# --- START APP ---
df_raw = load_data()

if not df_raw.empty:
    df = preprocess_stats(df_raw)
    low_activity_set = identify_low_activity(df)
    crown_employees_set = get_crown_employees(df_raw)

    # --- SIDEBAR (Фильтры) ---
    st.sidebar.header("Фильтры")

    st.sidebar.subheader("Юридические Центры")
    all_yuc = sorted(df['ЮЦ'].unique())
    selected_yuc = []
    for yc in all_yuc:
        is_checked = (yc == "Дальний Восток")
        if st.sidebar.checkbox(yc, value=is_checked, key=f"check_{yc}"):
            selected_yuc.append(yc)

    df_filtered_by_yuc = df[df['ЮЦ'].isin(selected_yuc)]

    st.sidebar.subheader("Годы")
    all_years = sorted(df['Год'].unique())
    selected_years = []
    for year in all_years:
        if st.sidebar.checkbox(str(year), value=True, key=f"year_{year}"):
            selected_years.append(year)

    df_main = df_filtered_by_yuc[df_filtered_by_yuc['Год'].isin(selected_years)].copy()

    # --- TABS ---
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Сотрудники", "🏢 По ЮЦ", "📈 Тренды", "🗺️ Карта РФ"])

    # --- TAB 1: Сотрудники ---
    with tab1:
        st.header("Сравнение сотрудников")

        st.write("##### Фильтр типов нагрузки:")
        col_sw1, col_sw2, col_sw3, col_sw4 = st.columns([1, 1, 1, 1])

        show_sd_emp = col_sw1.toggle("Судебные дела", value=True, key="emp_sd")
        show_ad_emp = col_sw2.toggle("Административные дела", value=True, key="emp_ad")
        show_pret_emp = col_sw3.toggle("Претензии", value=True, key="emp_pret")
        show_low = col_sw4.toggle("Показать малоактивных (⚠️)", value=True, key="emp_low")

        selected_types_emp = []
        if show_sd_emp: selected_types_emp.append("Судебные дела")
        if show_ad_emp: selected_types_emp.append("Административные дела")
        if show_pret_emp: selected_types_emp.append("претензии")

        st.divider()

        raw_emps = sorted(df_filtered_by_yuc['Сотрудник'].unique())

        emp_map = {}
        for n in raw_emps:
            prefix = ""
            if n in crown_employees_set:
                prefix += "👑 "
            if n in low_activity_set:
                prefix += "⚠️ "
            emp_map[n] = prefix + n

        opts = [emp_map[n] for n in raw_emps if show_low or n not in low_activity_set]
        sel_display = st.multiselect("Выберите сотрудников:", opts, default=opts)

        if sel_display:
            if not selected_types_emp:
                st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
            else:
                rev_map = {v: k for k, v in emp_map.items()}
                real_names = [rev_map[x] for x in sel_display]

                df_sub = df_main[
                    (df_main['Сотрудник'].isin(real_names)) &
                    (df_main['Тип'].isin(selected_types_emp))
                    ].copy()

                if df_sub.empty:
                    st.info("Нет данных.")
                else:
                    df_sub['Display'] = df_sub['Сотрудник'].map(emp_map)


                    def cat_color(row):
                        return f"{row['Тип']} (мало)" if row['Сотрудник'] in low_activity_set else row['Тип']


                    df_sub['Cat'] = df_sub.apply(cat_color, axis=1)

                    grp = df_sub.groupby(['Display', 'Cat'])['Value'].sum().reset_index()

                    st.plotly_chart(px.bar(grp, x='Display', y='Value', color='Cat',
                                           color_discrete_map=COLORS_MAP, text_auto=True), use_container_width=True)
                    with st.expander("Таблица"):
                        st.dataframe(
                            df_sub.pivot_table(index='Сотрудник', columns=['Год', 'Тип'], values='Value', fill_value=0))

    # --- TAB 2: ЮЦ ---
    with tab2:
        grp_yu = df_main.groupby(['ЮЦ', 'Тип'])['Value'].sum().reset_index()
        if not grp_yu.empty:
            st.plotly_chart(px.bar(grp_yu, x='ЮЦ', y='Value', color='Тип',
                                   color_discrete_map=COLORS_MAP, barmode='group', text_auto=True),
                            use_container_width=True)

    # --- TAB 3: Тренды ---
    with tab3:
        st.header("Динамика и Тренды")
        trend_mode = st.radio("Что сравниваем?", ["Типы нагрузки (Структура)", "Юридические Центры (Сравнение)"],
                              horizontal=True)
        all_types = sorted(df_main['Тип'].unique())
        selected_types_trend = st.multiselect("Включить типы:", all_types, default=all_types)

        if not selected_types_trend:
            st.warning("⚠️ Выберите хотя бы один тип.")
        else:
            df_trend_filtered = df_main[df_main['Тип'].isin(selected_types_trend)]
            if trend_mode == "Типы нагрузки (Структура)":
                df_grp = df_trend_filtered.groupby(['Год', 'Тип'])['Value'].sum().reset_index()
                fig = px.line(df_grp, x='Год', y='Value', color='Тип', markers=True, color_discrete_map=COLORS_MAP)
            else:
                df_grp = df_trend_filtered.groupby(['Год', 'ЮЦ'])['Value'].sum().reset_index()
                fig = px.line(df_grp, x='Год', y='Value', color='ЮЦ', markers=True)
            fig.update_layout(xaxis=dict(tickmode='linear', tick0=2023, dtick=1))
            st.plotly_chart(fig, use_container_width=True)

    # --- TAB 4: КАРТА (ОБНОВЛЕННАЯ ПОДСКАЗКА) ---
    with tab4:
        st.header("🗺️ Карта нагрузки (2025)")
        geojson = load_geojson()

        if 'Регион' not in df.columns:
            st.error("❌ Не найдена колонка 'Регион' в файле Excel.")
        elif geojson is None:
            st.error("❌ Не удалось загрузить карту.")
        else:
            st.write("##### Типы нагрузки:")
            c1, c2, c3 = st.columns(3)
            show_sd_map = c1.toggle("Судебные дела", value=True, key="map_sd")
            show_ad_map = c2.toggle("Административные дела", value=True, key="map_ad")
            show_pret_map = c3.toggle("Претензии", value=True, key="map_pret")

            sel_types_map = []
            if show_sd_map: sel_types_map.append("Судебные дела")
            if show_ad_map: sel_types_map.append("Административные дела")
            if show_pret_map: sel_types_map.append("претензии")

            if not sel_types_map:
                st.warning("⚠️ Выберите тип нагрузки.")
            else:
                df_map_filtered = df[(df['Год'] == 2025) & (df['Тип'].isin(sel_types_map))]
                df_2025_reg = df_map_filtered.groupby('Регион')['Value'].sum().reset_index()

                # Подготовка списка регионов
                name_key = 'name'
                if geojson.get('features') and 'name' not in geojson['features'][0]['properties']:
                    props = geojson['features'][0]['properties']
                    for k in ['name', 'name_ru', 'latin_name', 'NAME_1']:
                        if k in props: name_key = k; break

                all_map_regs = []
                if geojson.get('features'):
                    for f in geojson['features']:
                        if name_key in f['properties']: all_map_regs.append(f['properties'][name_key])

                df_full = pd.DataFrame({'Регион': all_map_regs})
                df_plot = pd.merge(df_full, df_2025_reg, on='Регион', how='left').fillna(0)

                # РАЗДЕЛЕНИЕ НА АКТИВНЫЕ И НУЛЕВЫЕ
                df_active = df_plot[df_plot['Value'] > 0]
                df_zero = df_plot[df_plot['Value'] == 0]

                # 1. Активные
                if not df_active.empty:
                    fig_map = px.choropleth_mapbox(
                        df_active, geojson=geojson, locations='Регион', featureidkey=f'properties.{name_key}',
                        color='Value', color_continuous_scale="RdYlGn_r", mapbox_style="carto-positron",
                        zoom=2.5, center={"lat": 60, "lon": 95}, opacity=0.6,
                        hover_name='Регион', hover_data={'Регион': False, 'Value': True},
                        labels={'Value': 'Нагрузка'}
                    )
                else:
                    fig_map = go.Figure(go.Choroplethmapbox(
                        geojson=geojson, locations=[], z=[],
                        mapbox_style="carto-positron", zoom=2.5, center={"lat": 60, "lon": 95}
                    ))

                # 2. Нулевые (Серые) - с обновленным шаблоном
                if not df_zero.empty:
                    fig_map.add_trace(go.Choroplethmapbox(
                        geojson=geojson,
                        locations=df_zero['Регион'],
                        z=[1] * len(df_zero),
                        featureidkey=f'properties.{name_key}',
                        colorscale=[[0, 'gray'], [1, 'gray']],
                        showscale=False,
                        marker_opacity=0.4,
                        marker_line_width=0.5,
                        name='Нет нагрузки',
                        # --- СТИЛЬ ПОДСКАЗКИ ---
                        hovertemplate='<b>%{location}</b><br>нет юриста<extra></extra>'
                    ))

                fig_map.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
                st.plotly_chart(fig_map, use_container_width=True)

                st.divider()
                with st.expander("🔍 Диагностика"):
                    excel_regions = set(df_2025_reg['Регион'].unique())
                    map_regions_set = set(all_map_regs)
                    not_found = excel_regions - map_regions_set
                    if len(not_found) > 0:
                        st.error(f"Не найдены на карте ({len(not_found)}): {not_found}")
                    else:
                        st.success("Все регионы успешно найдены!")