import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os

# --- Настройка страницы ---
st.set_page_config(page_title="Аналитика ЮЦ", layout="wide", initial_sidebar_state="expanded")

# --- МАГИЯ CSS: Превращаем радио-кнопки во вкладки и стилизуем поля ввода ---
st.markdown(
    """
    <style>
    /* 1. Прячем стандартные кружочки радио-кнопок */
    div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }

    /* 2. Настраиваем контейнер вкладок */
    div[role="radiogroup"] {
        flex-direction: row;
        gap: 5px;
        border-bottom: 2px solid rgba(150, 150, 150, 0.3);
        padding-bottom: 0 !important;
    }

    /* 3. Стилизуем сами элементы как корешки */
    div[role="radiogroup"] > label {
        background-color: var(--secondary-background-color); 
        color: var(--text-color); 
        padding: 10px 20px;
        border-radius: 8px 8px 0 0;
        border: 1px solid rgba(150, 150, 150, 0.3);
        border-bottom: none;
        margin-bottom: -2px; 
        cursor: pointer;
        transition: all 0.2s ease-in-out;
    }

    /* 4. Эффект при наведении */
    div[role="radiogroup"] > label:hover {
        filter: brightness(0.85); 
    }

    /* 5. Убираем лишние отступы у текста вкладок */
    div[role="radiogroup"] > label p {
        margin: 0;
        font-weight: 600;
    }

    /* 6. Выравнивание текста в боковой панели напротив полей ввода */
    .stNumberInput label {
        display: none; /* Скрываем стандартные лейблы у полей ввода в сайдбаре */
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Глобальная палитра цветов ---
COLORS_MAP = {
    'Судебные дела': '#636EFA',
    'Претензии': '#EF553B',
    'Административные дела': '#00CC96',
    'Судебные дела (мало)': '#A0A0A0',
    'Претензии (мало)': '#B0B0B0',
    'Административные дела (мало)': '#808080'
}


# --- 1. Загрузка данных ---
@st.cache_data
def load_data():
    df_stats = pd.DataFrame()
    df_mapping = pd.DataFrame()
    file_path = 'statistics.xlsx'

    try:
        xls = pd.ExcelFile(file_path)
        df_stats = pd.read_excel(xls, sheet_name=0)

        if len(xls.sheet_names) > 1:
            df_mapping_raw = pd.read_excel(xls, sheet_name=1)
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
                val = str(df_mapping_raw.iloc[0, 0])
                if any(x in val for x in
                       ['Дальний Восток', 'Сибирь', 'Урал', 'Поволжье', 'Северо-Запад', 'Юг', 'Центр']):
                    df_mapping = df_mapping_raw.iloc[:, [1, 0]].copy()
                else:
                    df_mapping = df_mapping_raw.iloc[:, :2].copy()

            if not df_mapping.empty:
                df_mapping.columns = ['Регион', 'ЮЦ']
                df_mapping['Регион'] = df_mapping['Регион'].astype(str).str.strip()
                df_mapping['ЮЦ'] = df_mapping['ЮЦ'].astype(str).str.strip()

    except Exception as e:
        st.error(f"❌ Ошибка загрузки файла '{file_path}': {e}")

    if not df_stats.empty:
        # ВАЖНО: Очищаем все ключевые текстовые поля от пробелов для корректного сравнения
        for col in ['ЮЦ', 'Регион', 'Сотрудник']:
            if col in df_stats.columns:
                df_stats[col] = df_stats[col].astype(str).str.strip()

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


# --- 3. Вспомогательные функции ---
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


def get_fired_employees(df):
    target_col = None
    # Ищем колонку, содержащую слово "уволен"
    for col in df.columns:
        if "уволен" in str(col).strip().lower():
            target_col = col
            break

    if target_col:
        # Ищем любой знак 'x', 'X', 'х', 'Х' (лат/кир)
        mask = df[target_col].astype(str).str.contains(r'[xXхХ]', na=False)
        # Возвращаем список сотрудников (уже очищенный в load_data)
        return set(df[mask]['Сотрудник'].unique())
    return set()


def get_crown_employees(df):
    target_col = None
    possible_names = ['работник юц', 'сотрудник юц', 'признак', 'статус', 'работник']
    for col in df.columns:
        if isinstance(col, str):
            if any(key in col.lower().strip() for key in possible_names):
                target_col = col
                break
    if target_col:
        mask = df[target_col].astype(str).str.contains(r'[xXхХ]', na=False)
        return set(df[mask]['Сотрудник'].unique())
    return set()


def get_load_type_filters(prefix, show_low_option=False):
    if show_low_option:
        c1, c2, c3, c4 = st.columns(4)
        show_low = c4.toggle("Показать уволенных (⚠️)", value=False, key=f"{prefix}_low")
    else:
        c1, c2, c3 = st.columns(3)
        show_low = False

    show_sd = c1.toggle("Судебные дела", value=True, key=f"{prefix}_sd")
    show_ad = c2.toggle("Административные дела", value=True, key=f"{prefix}_ad")
    show_pret = c3.toggle("Претензии", value=True, key=f"{prefix}_pret")

    selected = []
    if show_sd: selected.append("Судебные дела")
    if show_ad: selected.append("Административные дела")
    if show_pret: selected.append("Претензии")

    st.divider()
    return selected, show_low


def apply_coefficients(df_to_modify, use_coeffs, k_sd, k_ad, k_pr):
    if not use_coeffs:
        return df_to_modify

    df_mod = df_to_modify.copy()

    df_mod.loc[df_mod['Тип'] == 'Судебные дела', 'Value'] *= k_sd
    df_mod.loc[df_mod['Тип'] == 'Административные дела', 'Value'] *= k_ad
    df_mod.loc[df_mod['Тип'] == 'Претензии', 'Value'] *= k_pr

    return df_mod


# --- START APP ---
df_raw, df_map_ref = load_data()

if not df_raw.empty:
    df = preprocess_stats(df_raw)
    low_activity_set = get_fired_employees(df_raw)
    crown_employees_set = get_crown_employees(df_raw)

    # --- ИНТЕЛЛЕКТУАЛЬНАЯ НАВИГАЦИЯ ---
    selected_tab = st.radio(
        "Навигация:",
        ["👥 Сотрудники", "🏢 ЮЦ", "📈 Тренды", "🗺️ Тепловая карта"],
        horizontal=True,
        label_visibility="collapsed",
        key="nav_radio"
    )

    # --- ДИНАМИЧЕСКАЯ БОКОВАЯ ПАНЕЛЬ ---
    st.sidebar.title("📊 Дэшборд аналитики")
    st.sidebar.divider()

    st.sidebar.header("Фильтры")

    st.sidebar.subheader("Юридические Центры")
    all_yuc = sorted(df['ЮЦ'].unique())

    all_selected = True
    for i, yc in enumerate(all_yuc):
        yc_key = f"sidebar_yuc_{selected_tab}_{yc}"
        if yc_key in st.session_state:
            if not st.session_state[yc_key]:
                all_selected = False
                break
        else:
            default_yuc_val = True if selected_tab in ["🏢 ЮЦ", "📈 Тренды", "🗺️ Тепловая карта"] else (i == 0)
            if not default_yuc_val:
                all_selected = False
                break

    master_key = f"master_yuc_{selected_tab}"
    st.session_state[master_key] = all_selected


    def toggle_all_yuc_callback():
        current_tab = st.session_state.nav_radio
        m_key = f"master_yuc_{current_tab}"
        master_val = st.session_state[m_key]
        for yc_name in all_yuc:
            st.session_state[f"sidebar_yuc_{current_tab}_{yc_name}"] = master_val


    st.sidebar.toggle("✅ **Включить / Выключить все**", key=master_key, on_change=toggle_all_yuc_callback)
    st.sidebar.divider()

    selected_yuc = []
    for i, yc in enumerate(all_yuc):
        if selected_tab in ["🏢 ЮЦ", "📈 Тренды", "🗺️ Тепловая карта"]:
            default_yuc_val = True
        else:
            default_yuc_val = (i == 0)

        if st.sidebar.toggle(yc, value=default_yuc_val, key=f"sidebar_yuc_{selected_tab}_{yc}"):
            selected_yuc.append(yc)

    df_filtered_by_yuc = df[df['ЮЦ'].isin(selected_yuc)]

    st.sidebar.subheader("Годы")
    all_years = sorted(df['Год'].unique())
    selected_years = []
    for year in all_years:
        if selected_tab == "📈 Тренды":
            if st.sidebar.toggle(str(year), value=True, disabled=True, key=f"sidebar_year_{selected_tab}_{year}"):
                selected_years.append(year)
        else:
            default_year_val = (year == 2025)
            if st.sidebar.toggle(str(year), value=default_year_val, key=f"sidebar_year_{selected_tab}_{year}"):
                selected_years.append(year)

    df_main = df_filtered_by_yuc[df_filtered_by_yuc['Год'].isin(selected_years)].copy()

    # --- НОВЫЙ РАЗДЕЛ: ПРИВЕДЕННЫЕ ПОКАЗАТЕЛИ ---
    st.sidebar.divider()
    st.sidebar.subheader("Приведенные показатели")
    use_coeffs = st.sidebar.toggle("Включить коэффициенты пересчета", value=False, key="use_coeffs")

    k_sd, k_ad, k_pr = 1.0, 1.0, 1.0

    c_name_1, c_input_1 = st.sidebar.columns([1, 1.2])
    with c_name_1:
        st.markdown("**Судебные дела**")
    with c_input_1:
        k_sd = st.number_input("SD", value=1.00, step=0.1, format="%.2f", disabled=not use_coeffs,
                               label_visibility="collapsed", key="coeff_sd")

    c_name_2, c_input_2 = st.sidebar.columns([1, 1.2])
    with c_name_2:
        st.markdown("**Админ. дела**")
    with c_input_2:
        k_ad = st.number_input("AD", value=1.00, step=0.1, format="%.2f", disabled=not use_coeffs,
                               label_visibility="collapsed", key="coeff_ad")

    c_name_3, c_input_3 = st.sidebar.columns([1, 1.2])
    with c_name_3:
        st.markdown("**Претензии**")
    with c_input_3:
        k_pr = st.number_input("PR", value=1.00, step=0.1, format="%.2f", disabled=not use_coeffs,
                               label_visibility="collapsed", key="coeff_pr")

    # --- РЕНДЕР ВЫБРАННОГО РАЗДЕЛА ---

    if selected_tab == "👥 Сотрудники":
        st.header("Сравнение сотрудников")
        st.info("ℹ️ **Легенда статусов:** 👑 — Работник ЮЦ | ⚠️ — Сотрудник сейчас не работает в регионе (уволен)")

        selected_types_emp, show_low = get_load_type_filters("emp", show_low_option=True)

        raw_emps = sorted(df_filtered_by_yuc['Сотрудник'].unique())
        emp_map = {}
        for n in raw_emps:
            prefix = ""
            if n in crown_employees_set: prefix += "👑 "
            if n in low_activity_set: prefix += "⚠️ "
            emp_map[n] = prefix + n

        # ФИЛЬТРАЦИЯ СПИСКА: Если галочка выключена, убираем уволенных
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
                    df_sub = apply_coefficients(df_sub, use_coeffs, k_sd, k_ad, k_pr)
                    df_sub['Display'] = df_sub['Сотрудник'].map(emp_map)

                    chart_title = "Сравнительная гистограмма (с учетом коэффициентов)" if use_coeffs else "Сравнительная гистограмма нагрузки"

                    # --- ЛОГИКА СОРТИРОВКИ ДЛЯ ГРУППИРОВКИ ПО ЮЦ (БЕЗ МНОГОУРОВНЕВОЙ ОСИ) ---
                    # 1. Группируем, чтобы получить сумму для каждого сотрудника
                    emp_totals = df_sub.groupby(['Display', 'ЮЦ'])['Value'].sum().reset_index()

                    # 2. Сортируем: сначала по ЮЦ (чтобы все из одного центра были рядом),
                    #    затем по Значению (чтобы внутри центра была "лесенка")
                    emp_totals = emp_totals.sort_values(by=['ЮЦ', 'Value'], ascending=[True, False])

                    # 3. Получаем правильный порядок имен
                    ordered_names = emp_totals['Display'].tolist()

                    if use_coeffs:
                        grp = df_sub.groupby('Display')['Value'].sum().reset_index()
                        fig = px.bar(grp, x='Display', y='Value',
                                     text_auto='.1f',
                                     title=chart_title)
                        fig.update_traces(marker_color='#636EFA')
                    else:
                        def cat_color(row):
                            suffix = " (мало)" if row['Сотрудник'] in low_activity_set else ""
                            return f"{row['Тип']}{suffix}"


                        df_sub['Cat'] = df_sub.apply(cat_color, axis=1)
                        grp = df_sub.groupby(['Display', 'Cat'])['Value'].sum().reset_index()

                        fig = px.bar(grp, x='Display', y='Value', color='Cat',
                                     color_discrete_map=COLORS_MAP, text_auto=True,
                                     title=chart_title)

                        new_names = {
                            'Судебные дела': 'Судебные дела',
                            'Претензии': 'Претензии',
                            'Административные дела': 'Административные дела',
                            'Судебные дела (мало)': 'Судебные дела (неактивен)',
                            'Претензии (мало)': 'Претензии (неактивен)',
                            'Административные дела (мало)': 'Административные дела (неактивен)'
                        }
                        fig.for_each_trace(lambda t: t.update(name=new_names.get(t.name, t.name)))

                    # 4. Применяем принудительный порядок оси X
                    fig.update_xaxes(categoryorder='array', categoryarray=ordered_names)

                    st.plotly_chart(fig, use_container_width=True)

    elif selected_tab == "🏢 ЮЦ":
        st.header("Сравнение Юридических Центров")

        sel_types_yuc, _ = get_load_type_filters("yuc")

        if not sel_types_yuc:
            st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
        else:
            df_yuc_filtered = df_main[df_main['Тип'].isin(sel_types_yuc)].copy()
            df_yuc_filtered = apply_coefficients(df_yuc_filtered, use_coeffs, k_sd, k_ad, k_pr)

            if use_coeffs:
                grp_yu = df_yuc_filtered.groupby('ЮЦ')['Value'].sum().reset_index()

                if not grp_yu.empty:
                    col_total, col_eff = st.columns(2)

                    with col_total:
                        st.subheader("1. Общий объем")
                        fig_total = px.bar(grp_yu, x='ЮЦ', y='Value',
                                           text_auto='.1f', barmode='group')
                        fig_total.update_traces(marker_color='#636EFA')
                        st.plotly_chart(fig_total, use_container_width=True)

                    avg_data = []
                    for index, row in grp_yu.iterrows():
                        yc_name = row['ЮЦ']
                        total_val = row['Value']

                        employees_in_yc = df[df['ЮЦ'] == yc_name]['Сотрудник'].unique()
                        active_count = 0
                        for emp in employees_in_yc:
                            if emp not in low_activity_set:
                                active_count += 1

                        ratio = total_val / active_count if active_count > 0 else 0
                        avg_data.append(
                            {'ЮЦ': yc_name, 'Средняя нагрузка': ratio, 'Активных сотрудников': active_count})

                    df_avg = pd.DataFrame(avg_data)

                    with col_eff:
                        st.subheader("2. Эффективность")

                        fig_avg = px.bar(df_avg, x='ЮЦ', y='Средняя нагрузка',
                                         text_auto='.1f',
                                         hover_data=['Активных сотрудников'])
                        fig_avg.update_traces(marker_color='#EF553B')
                        st.plotly_chart(fig_avg, use_container_width=True)

                else:
                    st.info("Нет данных по выбранным фильтрам.")
            else:
                grp_yu = df_yuc_filtered.groupby(['ЮЦ', 'Тип'])['Value'].sum().reset_index()

                if not grp_yu.empty:
                    fig_yu = px.bar(grp_yu, x='ЮЦ', y='Value', color='Тип',
                                    color_discrete_map=COLORS_MAP, barmode='group', text_auto=True)
                    st.plotly_chart(fig_yu, use_container_width=True)
                else:
                    st.info("Нет данных по выбранным фильтрам.")

    elif selected_tab == "📈 Тренды":
        st.header("Динамика и Тренды")

        sel_types_trend, _ = get_load_type_filters("trend")

        if not sel_types_trend:
            st.warning("⚠️ Выберите хотя бы один тип нагрузки.")
        else:
            df_trend_filtered = df_main[df_main['Тип'].isin(sel_types_trend)].copy()

            if df_trend_filtered.empty:
                st.info("Нет данных по выбранным фильтрам.")
            else:
                df_trend_filtered = apply_coefficients(df_trend_filtered, use_coeffs, k_sd, k_ad, k_pr)
                df_grp = df_trend_filtered.groupby(['Год', 'ЮЦ'])['Value'].sum().reset_index()
                unique_years = df_grp['Год'].unique()
                title_suffix = " (с учетом коэффициентов)" if use_coeffs else ""

                if len(unique_years) == 1:
                    total_sum = df_grp['Value'].sum()
                    year_val = unique_years[0]
                    fig = px.pie(
                        df_grp, names='ЮЦ', values='Value', color='ЮЦ',
                        hole=0.5,
                        title=f"Структура нагрузки по ЮЦ за {year_val} год{title_suffix}"
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+value')
                    fmt_sum = f"{total_sum:.1f}" if use_coeffs else f"{int(total_sum)}"
                    fig.update_layout(
                        annotations=[
                            dict(text=f"<b>Всего:</b><br>{fmt_sum}", x=0.5, y=0.5, font_size=20, showarrow=False)]
                    )
                else:
                    fig = px.line(df_grp, x='Год', y='Value', color='ЮЦ', markers=True)
                    fig.update_layout(xaxis=dict(tickmode='linear', tick0=min(unique_years), dtick=1))

                st.plotly_chart(fig, use_container_width=True)

    elif selected_tab == "🗺️ Тепловая карта":
        geojson = load_geojson()

        if 'Регион' not in df.columns:
            st.error("❌ Не найдена колонка 'Регион' в файле Excel.")
        elif geojson is None:
            st.error("❌ Не удалось загрузить карту.")
        else:
            sel_types_map, _ = get_load_type_filters("map")

            if not sel_types_map:
                st.warning("⚠️ Выберите хотя бы один тип нагрузки, чтобы увидеть данные на карте.")
            else:
                df_map_filtered = df[df['Год'].isin(selected_years)].copy()

                if df_map_filtered.empty:
                    df_pivot = pd.DataFrame(columns=['Регион', 'Судебные дела', 'Административные дела', 'Претензии'])
                else:
                    df_map_filtered = apply_coefficients(df_map_filtered, use_coeffs, k_sd, k_ad, k_pr)
                    df_pivot = df_map_filtered.pivot_table(index='Регион', columns='Тип', values='Value',
                                                           aggfunc='sum').fillna(0).reset_index()

                for col in ['Судебные дела', 'Административные дела', 'Претензии']:
                    if col not in df_pivot.columns:
                        df_pivot[col] = 0

                all_map_regs = [f['properties']['name'] for f in geojson['features']]
                df_full = pd.DataFrame({'Регион': all_map_regs})

                df_plot = pd.merge(df_full, df_pivot, on='Регион', how='left').fillna(0)
                df_plot['Value'] = df_plot[sel_types_map].sum(axis=1)

                hover_texts = []
                for _, row in df_plot.iterrows():
                    if row['Value'] == 0:
                        hover_texts.append(f"<b>{row['Регион']}</b><br>нет юриста")
                    else:
                        lines = [f"<b>{row['Регион']}</b>"]
                        for t in sel_types_map:
                            val_t = row[t]
                            fmt_val = f"{val_t:.1f}" if use_coeffs else f"{int(val_t)}"
                            lines.append(f"{t}: {fmt_val}")

                        fmt_total = f"{row['Value']:.1f}" if use_coeffs else f"{int(row['Value'])}"
                        lines.append(f"Всего: {fmt_total}")
                        hover_texts.append("<br>".join(lines))

                df_plot['Hover_Text'] = hover_texts

                region_to_yuc = {}
                if not df_map_ref.empty:
                    for _, row in df_map_ref.iterrows():
                        reg = str(row['Регион']).strip()
                        yuc = str(row['ЮЦ']).strip()
                        if reg and yuc and reg != 'nan':
                            region_to_yuc[reg] = yuc

                if 'Регион' in df.columns:
                    for _, row in df.iterrows():
                        reg = str(row['Регион']).strip()
                        yuc = str(row['ЮЦ']).strip()
                        if reg and yuc and reg != 'nan' and reg not in region_to_yuc:
                            region_to_yuc[reg] = yuc

                df_plot['Регион_чистый'] = df_plot['Регион'].astype(str).str.strip()
                df_plot['ЮЦ_карты'] = df_plot['Регион_чистый'].map(region_to_yuc)

                selected_yuc_clean = [y.strip() for y in selected_yuc]
                is_selected_yuc = df_plot['ЮЦ_карты'].isin(selected_yuc_clean)

                df_active_selected = df_plot[(df_plot['Value'] > 0) & is_selected_yuc]
                df_zero_selected = df_plot[(df_plot['Value'] == 0) & is_selected_yuc]
                df_other = df_plot[~is_selected_yuc]

                if not df_active_selected.empty:
                    fig_map = px.choropleth_mapbox(
                        df_active_selected, geojson=geojson, locations='Регион', featureidkey='properties.name',
                        color='Value', color_continuous_scale="RdYlGn_r", mapbox_style="white-bg",
                        opacity=0.8,
                        custom_data=['Hover_Text'],
                        labels={'Value': 'Нагрузка'}
                    )
                    fig_map.update_traces(hovertemplate="%{customdata[0]}<extra></extra>", marker_line_width=0.3,
                                          marker_line_color='#555555')
                else:
                    fig_map = go.Figure(go.Choroplethmapbox(geojson=geojson, locations=[], z=[]))
                    fig_map.update_layout(mapbox_style="white-bg")

                if not df_other.empty:
                    fig_map.add_trace(go.Choroplethmapbox(
                        geojson=geojson, locations=df_other['Регион'], z=[1] * len(df_other),
                        featureidkey='properties.name',
                        colorscale=[[0, '#B0C4DE'], [1, '#B0C4DE']], showscale=False, marker_opacity=0.4,
                        marker_line_width=0.3, marker_line_color='#555555', name='Другие ЮЦ',
                        customdata=df_other[['Hover_Text']], hovertemplate="%{customdata[0]}<extra></extra>"
                    ))

                if not df_zero_selected.empty:
                    fig_map.add_trace(go.Choroplethmapbox(
                        geojson=geojson, locations=df_zero_selected['Регион'], z=[1] * len(df_zero_selected),
                        featureidkey='properties.name',
                        colorscale=[[0, 'gray'], [1, 'gray']], showscale=False, marker_opacity=0.6,
                        marker_line_width=0.3, marker_line_color='#555555', name='Нет юриста',
                        customdata=df_zero_selected[['Hover_Text']], hovertemplate="%{customdata[0]}<extra></extra>"
                    ))

                fig_map.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=800, mapbox_zoom=2.2,
                                      mapbox_center={"lat": 65, "lon": 100})
                st.plotly_chart(fig_map, use_container_width=True)