import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os

# --- Настройка страницы ---
st.set_page_config(page_title="Аналитика ЮЦ", layout="wide")
st.title("📊 Дэшборд аналитики сотрудников и ЮЦ")

# --- Глобальная палитра цветов ---
COLORS_MAP = {
    'Судебные дела': '#636EFA',  # Синий
    'Претензии': '#EF553B',  # Красный
    'Административные дела': '#00CC96',  # Зеленый
    'Судебные дела (мало)': '#A0A0A0',  # Серый
    'Претензии (мало)': '#B0B0B0',  # Светло-серый
    'Административные дела (мало)': '#808080'  # Темно-серый
}


# --- 1. Загрузка данных (С УМНЫМ ПОИСКОМ КОЛОНОК) ---
@st.cache_data
def load_data():
    df_stats = pd.DataFrame()
    df_mapping = pd.DataFrame()
    file_path = 'statistics.xlsx'

    try:
        xls = pd.ExcelFile(file_path)
        df_stats = pd.read_excel(xls, sheet_name=0)

        # Читаем Лист 2 (Справочник)
        if len(xls.sheet_names) > 1:
            df_mapping_raw = pd.read_excel(xls, sheet_name=1)

            # Умный поиск колонок Региона и ЮЦ
            reg_col, yuc_col = None, None
            for col in df_mapping_raw.columns:
                c_low = str(col).lower()
                if not reg_col and any(x in c_low for x in ['регион', 'область', 'край', 'округ', 'республика']):
                    reg_col = col
                if not yuc_col and any(x in c_low for x in ['юц', 'центр']):
                    yuc_col = col

            if reg_col and yuc_col:
                df_mapping = df_mapping_raw[[reg_col, yuc_col]].copy()
            elif len(df_mapping_raw.columns) >= 2:
                # Если не нашли по заголовкам, пробуем угадать по данным
                val = str(df_mapping_raw.iloc[0, 0])
                if any(x in val for x in
                       ['Дальний Восток', 'Сибирь', 'Урал', 'Поволжье', 'Северо-Запад', 'Юг', 'Центр']):
                    df_mapping = df_mapping_raw.iloc[:, [1, 0]].copy()
                else:
                    df_mapping = df_mapping_raw.iloc[:, :2].copy()

            if not df_mapping.empty:
                df_mapping.columns = ['Регион', 'ЮЦ']
                # Срезаем лишние пробелы для идеального совпадения
                df_mapping['Регион'] = df_mapping['Регион'].astype(str).str.strip()
                df_mapping['ЮЦ'] = df_mapping['ЮЦ'].astype(str).str.strip()

    except Exception as e:
        try:
            df_stats = pd.read_csv('statistics.xlsx - Лист1.csv')
        except:
            st.error(f"Ошибка загрузки данных: {e}")

    # Очищаем данные от пробелов в основном листе
    if not df_stats.empty:
        if 'ЮЦ' in df_stats.columns:
            df_stats['ЮЦ'] = df_stats['ЮЦ'].astype(str).str.strip()
        if 'Регион' in df_stats.columns:
            df_stats['Регион'] = df_stats['Регион'].astype(str).str.strip()

    return df_stats, df_mapping


# --- 2. Загрузка карты ---
@st.cache_data
def load_geojson():
    filename = 'final_russia.geojson'

    if not os.path.exists(filename):
        st.error(f"❌ Файл карты '{filename}' не найден!")
        st.warning("⚠️ Пожалуйста, запустите скрипт 'prepare_map.py', чтобы создать этот файл из 'russia.geojson'.")
        return None

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Ошибка чтения файла карты: {e}")
        return None


# --- 3. Обработка статистики ---
def preprocess_stats(df):
    id_vars = ['ЮЦ', 'Сотрудник']
    if 'Регион' in df.columns:
        id_vars.append('Регион')

    value_vars = [c for c in df.columns if '20' in str(c) and '(' in str(c)]

    df_melted = df.melt(id_vars=id_vars, value_vars=value_vars, var_name='Year_Metric', value_name='Value')

    pattern = r'(\d{4})\s\((.*?)\)'
    extracted = df_melted['Year_Metric'].str.extract(pattern)
    df_melted['Год'] = extracted[0].astype(float).astype('Int64')
    df_melted['Тип'] = extracted[1]

    df_melted['Тип'] = df_melted['Тип'].replace({
        'СД': 'Судебные дела',
        'АД': 'Административные дела',
        'претензии': 'Претензии'
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
    target_col = None
    possible_names = ['работник юц', 'сотрудник юц', 'признак', 'статус', 'работник']
    for col in df.columns:
        if isinstance(col, str):
            c_low = col.lower().strip()
            if any(key in c_low for key in possible_names):
                target_col = col
                break
    if target_col:
        mask = df[target_col].astype(str).str.contains(r'[xXхХ]', na=False)
        return set(df[mask]['Сотрудник'].unique())
    return set()


# --- START APP ---
df_raw, df_map_ref = load_data()

if not df_raw.empty:
    df = preprocess_stats(df_raw)
    low_activity_set = identify_low_activity(df)
    crown_employees_set = get_crown_employees(df_raw)

    # --- SIDEBAR ---
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
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Сотрудники", "🏢 ЮЦ", "📈 Тренды", "🗺️ Тепловая карта"])

    # --- TAB 1: Сотрудники ---
    with tab1:
        st.header("Сравнение сотрудников")

        st.info(
            "ℹ️ **Легенда статусов:** 👑 — Работник ЮЦ | ⚠️ — Сотрудник сейчас не работает в регионе")

        st.write("##### Фильтр типов нагрузки:")
        col_sw1, col_sw2, col_sw3, col_sw4 = st.columns([1, 1, 1, 1])
        show_sd_emp = col_sw1.toggle("Судебные дела", value=True, key="emp_sd")
        show_ad_emp = col_sw2.toggle("Административные дела", value=True, key="emp_ad")
        show_pret_emp = col_sw3.toggle("Претензии", value=True, key="emp_pret")
        show_low = col_sw4.toggle("Показать уволенных (⚠️)", value=True, key="emp_low")

        selected_types_emp = []
        if show_sd_emp: selected_types_emp.append("Судебные дела")
        if show_ad_emp: selected_types_emp.append("Административные дела")
        if show_pret_emp: selected_types_emp.append("Претензии")

        st.divider()

        raw_emps = sorted(df_filtered_by_yuc['Сотрудник'].unique())
        emp_map = {}
        for n in raw_emps:
            prefix = ""
            if n in crown_employees_set: prefix += "👑 "
            if n in low_activity_set: prefix += "⚠️ "
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
                        suffix = " (мало)" if row['Сотрудник'] in low_activity_set else ""
                        return f"{row['Тип']}{suffix}"


                    df_sub['Cat'] = df_sub.apply(cat_color, axis=1)

                    grp = df_sub.groupby(['Display', 'Cat'])['Value'].sum().reset_index()

                    fig = px.bar(grp, x='Display', y='Value', color='Cat',
                                 color_discrete_map=COLORS_MAP, text_auto=True,
                                 title="Сравнительная гистограмма нагрузки")

                    new_names = {
                        'Судебные дела': 'Судебные дела',
                        'Претензии': 'Претензии',
                        'Административные дела': 'Административные дела',
                        'Судебные дела (мало)': 'Судебные дела (неактивен)',
                        'Претензии (мало)': 'Претензии (неактивен)',
                        'Административные дела (мало)': 'Административные дела (неактивен)'
                    }
                    fig.for_each_trace(lambda t: t.update(name=new_names.get(t.name, t.name)))

                    st.plotly_chart(fig, use_container_width=True)

    # --- TAB 2: ЮЦ ---
    with tab2:
        st.header("Сравнение Юридических Центров")

        st.write("##### Фильтр типов нагрузки:")
        col_y1, col_y2, col_y3 = st.columns(3)
        show_sd_yuc = col_y1.toggle("Судебные дела", value=True, key="yuc_sd")
        show_ad_yuc = col_y2.toggle("Административные дела", value=True, key="yuc_ad")
        show_pret_yuc = col_y3.toggle("Претензии", value=True, key="yuc_pret")

        sel_types_yuc = []
        if show_sd_yuc: sel_types_yuc.append("Судебные дела")
        if show_ad_yuc: sel_types_yuc.append("Административные дела")
        if show_pret_yuc: sel_types_yuc.append("Претензии")

        st.divider()

        if not sel_types_yuc:
            st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
        else:
            df_yuc_filtered = df_main[df_main['Тип'].isin(sel_types_yuc)]
            grp_yu = df_yuc_filtered.groupby(['ЮЦ', 'Тип'])['Value'].sum().reset_index()

            if not grp_yu.empty:
                fig_yu = px.bar(grp_yu, x='ЮЦ', y='Value', color='Тип',
                                color_discrete_map=COLORS_MAP, barmode='group', text_auto=True)
                st.plotly_chart(fig_yu, use_container_width=True)
            else:
                st.info("Нет данных по выбранным фильтрам.")

    # --- TAB 3: Тренды ---
    with tab3:
        st.header("Динамика и Тренды")
        trend_mode = st.radio("Что сравниваем?", ["Типы нагрузки (Структура)", "Юридические Центры (Сравнение)"],
                              horizontal=True)

        st.write("##### Фильтр типов нагрузки:")
        col_t1, col_t2, col_t3 = st.columns(3)
        show_sd_trend = col_t1.toggle("Судебные дела", value=True, key="trend_sd")
        show_ad_trend = col_t2.toggle("Административные дела", value=True, key="trend_ad")
        show_pret_trend = col_t3.toggle("Претензии", value=True, key="trend_pret")

        sel_types_trend = []
        if show_sd_trend: sel_types_trend.append("Судебные дела")
        if show_ad_trend: sel_types_trend.append("Административные дела")
        if show_pret_trend: sel_types_trend.append("Претензии")

        st.divider()

        if not sel_types_trend:
            st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
        else:
            df_trend_filtered = df_main[df_main['Тип'].isin(sel_types_trend)]

            if df_trend_filtered.empty:
                st.info("Нет данных по выбранным фильтрам.")
            else:
                if trend_mode == "Типы нагрузки (Структура)":
                    df_grp = df_trend_filtered.groupby(['Год', 'Тип'])['Value'].sum().reset_index()
                    fig = px.line(df_grp, x='Год', y='Value', color='Тип', markers=True, color_discrete_map=COLORS_MAP)
                else:
                    df_grp = df_trend_filtered.groupby(['Год', 'ЮЦ'])['Value'].sum().reset_index()
                    fig = px.line(df_grp, x='Год', y='Value', color='ЮЦ', markers=True)

                fig.update_layout(xaxis=dict(tickmode='linear', tick0=2023, dtick=1))
                st.plotly_chart(fig, use_container_width=True)

    # --- TAB 4: КАРТА ---
    with tab4:
        st.header("🗺️ Карта нагрузки (2025)")
        geojson = load_geojson()

        if 'Регион' not in df.columns:
            st.error("❌ Не найдена колонка 'Регион' в файле Excel.")
        elif geojson is None:
            st.error("❌ Не удалось загрузить карту.")
        else:
            st.write("##### Фильтр типов нагрузки:")
            c1, c2, c3 = st.columns(3)
            show_sd_map = c1.toggle("Судебные дела", value=True, key="map_sd")
            show_ad_map = c2.toggle("Административные дела", value=True, key="map_ad")
            show_pret_map = c3.toggle("Претензии", value=True, key="map_pret")

            sel_types_map = []
            if show_sd_map: sel_types_map.append("Судебные дела")
            if show_ad_map: sel_types_map.append("Административные дела")
            if show_pret_map: sel_types_map.append("Претензии")

            st.divider()

            if not sel_types_map:
                st.warning("⚠️ Выберите хотя бы один тип нагрузки, чтобы увидеть данные на карте.")
            else:
                df_2025 = df[df['Год'] == 2025]

                # Создаем сводную таблицу (pivot)
                if df_2025.empty:
                    df_pivot = pd.DataFrame(columns=['Регион', 'Судебные дела', 'Административные дела', 'Претензии'])
                else:
                    df_pivot = df_2025.pivot_table(index='Регион', columns='Тип', values='Value', aggfunc='sum').fillna(
                        0).reset_index()

                for col in ['Судебные дела', 'Административные дела', 'Претензии']:
                    if col not in df_pivot.columns:
                        df_pivot[col] = 0

                # Получаем список всех регионов из карты
                name_key = 'name'
                if geojson.get('features') and 'name' not in geojson['features'][0]['properties']:
                    props = geojson['features'][0]['properties']
                    for k in ['name', 'name_ru', 'latin_name', 'NAME_1']:
                        if k in props: name_key = k; break

                all_map_regs = [f['properties'][name_key] for f in geojson['features']]
                df_full = pd.DataFrame({'Регион': all_map_regs})

                df_plot = pd.merge(df_full, df_pivot, on='Регион', how='left').fillna(0)
                df_plot['Value'] = df_plot[sel_types_map].sum(axis=1)

                # --- Формирование детального текста для подсказки (HTML) ---
                hover_texts = []
                for _, row in df_plot.iterrows():
                    if row['Value'] == 0:
                        hover_texts.append(f"<b>{row['Регион']}</b><br>нет юриста")
                    else:
                        lines = [f"<b>{row['Регион']}</b>"]
                        for t in sel_types_map:
                            lines.append(f"{t}: {int(row[t])}")
                        lines.append(f"Всего: {int(row['Value'])}")
                        hover_texts.append("<br>".join(lines))

                df_plot['Hover_Text'] = hover_texts

                # --- ИНТЕЛЛЕКТУАЛЬНАЯ ПРИВЯЗКА РЕГИОНОВ К ЮЦ ---
                # Создаем справочник Регион -> ЮЦ для идеального маппинга
                region_to_yuc = {}

                # Шаг 1: Берем привязку из Листа 2
                if not df_map_ref.empty:
                    for _, row in df_map_ref.iterrows():
                        reg = str(row['Регион']).strip()
                        yuc = str(row['ЮЦ']).strip()
                        if reg and yuc and reg != 'nan':
                            region_to_yuc[reg] = yuc

                # Шаг 2: Дополняем из Листа 1, если в справочнике кого-то не хватает
                if 'Регион' in df.columns:
                    for _, row in df.iterrows():
                        reg = str(row['Регион']).strip()
                        yuc = str(row['ЮЦ']).strip()
                        if reg and yuc and reg != 'nan' and reg not in region_to_yuc:
                            region_to_yuc[reg] = yuc

                # Применяем справочник к карте
                df_plot['Регион_чистый'] = df_plot['Регион'].astype(str).str.strip()
                df_plot['ЮЦ_карты'] = df_plot['Регион_чистый'].map(region_to_yuc)

                # Проверяем, выбран ли ЮЦ в боковом фильтре
                selected_yuc_clean = [y.strip() for y in selected_yuc]
                is_selected_yuc = df_plot['ЮЦ_карты'].isin(selected_yuc_clean)

                # --- РАЗБИВКА НА 3 СЛОЯ ---
                # 1. Выбранный ЮЦ + есть нагрузка (Тепловая шкала)
                df_active_selected = df_plot[(df_plot['Value'] > 0) & is_selected_yuc]
                # 2. Выбранный ЮЦ + НЕТ нагрузки (Серые, "нет юриста")
                df_zero_selected = df_plot[(df_plot['Value'] == 0) & is_selected_yuc]
                # 3. Не выбранные ЮЦ (Светло-синий фон с данными)
                df_other = df_plot[~is_selected_yuc]

                # --- ОТРИСОВКА СЛОЕВ ---
                # СЛОЙ 1: Тепловая шкала
                if not df_active_selected.empty:
                    fig_map = px.choropleth_mapbox(
                        df_active_selected, geojson=geojson, locations='Регион', featureidkey=f'properties.{name_key}',
                        color='Value', color_continuous_scale="RdYlGn_r", mapbox_style="carto-positron",
                        zoom=2.5, center={"lat": 60, "lon": 95}, opacity=0.6,
                        custom_data=['Hover_Text'],
                        labels={'Value': 'Нагрузка'}
                    )
                    fig_map.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")
                else:
                    fig_map = go.Figure(go.Choroplethmapbox(
                        geojson=geojson, locations=[], z=[]
                    ))
                    fig_map.update_layout(
                        mapbox_style="carto-positron",
                        mapbox_zoom=2.5,
                        mapbox_center={"lat": 60, "lon": 95}
                    )

                # СЛОЙ 2: Другие ЮЦ (Светло-синий фон)
                if not df_other.empty:
                    fig_map.add_trace(go.Choroplethmapbox(
                        geojson=geojson,
                        locations=df_other['Регион'],
                        z=[1] * len(df_other),
                        featureidkey=f'properties.{name_key}',
                        colorscale=[[0, '#B0C4DE'], [1, '#B0C4DE']],  # LightSteelBlue
                        showscale=False,
                        marker_opacity=0.6,
                        marker_line_width=0.5,
                        name='Другие ЮЦ',
                        customdata=df_other[['Hover_Text']],
                        hovertemplate="%{customdata[0]}<extra></extra>"
                    ))

                # СЛОЙ 3: Выбранные ЮЦ без нагрузки (Серый цвет)
                if not df_zero_selected.empty:
                    fig_map.add_trace(go.Choroplethmapbox(
                        geojson=geojson,
                        locations=df_zero_selected['Регион'],
                        z=[1] * len(df_zero_selected),
                        featureidkey=f'properties.{name_key}',
                        colorscale=[[0, 'gray'], [1, 'gray']],
                        showscale=False,
                        marker_opacity=0.4,
                        marker_line_width=0.5,
                        name='Нет юриста',
                        customdata=df_zero_selected[['Hover_Text']],
                        hovertemplate="%{customdata[0]}<extra></extra>"
                    ))

                fig_map.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
                st.plotly_chart(fig_map, use_container_width=True)