import streamlit as st
import pandas as pd
import plotly.express as px
import os
import re

# =========================================================================
# 1. ตั้งค่าหน้าจอและเกณฑ์เป้าหมายของโรงพยาบาล
# =========================================================================
st.set_page_config(page_title="Lab Napho Ultimate Dashboard", layout="wide")
st.title("📊 แดชบอร์ดวิเคราะห์ประสิทธิภาพและระบบดึงข้อเสนอแนะอัจฉริยะ")
st.subheader("🏥 ห้องปฏิบัติการโรงพยาบาลนาโพธิ์")
st.markdown("---")

# เกณฑ์เป้าหมาย 4.00 (ร้อยละ 80.00%)
KPI_TARGET = 4.00 

# ลิงก์ Google Sheets หลักของโรงพยาบาลนาโพธิ์
BASE_SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1E72miMz99dQ6irouyDCDqAMUGelJ1XJuBiHyP6kN3AY/gviz/tq?tqx=out:csv&sheet="

# จับคู่ชื่อแท็บจริงใน Google Sheets กับชื่อกลุ่มงานประเมิน
target_sheets = [
    {"sheet_name": "การตอบแบบฟอร์ม 1 ของกลุ่มองค์กรแพทย์", "name": "ฟอร์มที่ 1: กลุ่มองค์กรแพทย์"},
    {"sheet_name": "การตอบแบบฟอร์ม 2 กลุ่มพยาบาลและสหวิชาชีพ", "name": "ฟอร์มที่ 2: กลุ่มพยาบาลและสหวิชาชีพ"},
    {"sheet_name": "การตอบแบบฟอร์ม 3 กลุ่ม รพ.สต.", "name": "ฟอร์มที่ 3: กลุ่ม รพ.สต. และเครือข่าย"},
    {"sheet_name": "การตอบแบบฟอร์ม 4 กลุ่มผู้ช่วยเหลือคนไข้และเวรเปล", "name": "ฟอร์มที่ 4: กลุ่มผู้ช่วยเหลือคนไข้และเวรเปล"},
    {"sheet_name": "การตอบแบบฟอร์ม 5 กลุ่มผู้ป่วยและญาติ", "name": "ฟอร์มที่ 5: กลุ่มผู้ป่วยและญาติ"}
]

# =========================================================================
# 2. ฟังก์ชันจัดการข้อมูลและล้างฟอร์แมตวันที่ขั้นสูง
# =========================================================================
def get_aspect_name(col_name):
    col_str = str(col_name)
    if "1. ด้าน" in col_str or "1.ด้าน" in col_str: return "ด้านที่ 1 การให้บริการและวัสดุอุปกรณ์"
    elif "2. ด้าน" in col_str or "2.ด้าน" in col_str: return "ด้านที่ 2 การติดต่อประสานงาน/พฤติกรรมบริการ"
    elif "3. ด้าน" in col_str or "3.ด้าน" in col_str: return "ด้านที่ 3 ความสะดวกรวดเร็ว / TAT"
    elif "4. ด้าน" in col_str or "4.ด้าน" in col_str: return "ด้านที่ 4 บริการวิชาการและการให้ข้อมูล"
    return None

def clean_and_parse_date_series(series):
    cleaned_list = []
    th_months = {'ม.ค.':'01', 'ก.พ.':'02', 'มี.ค.':'03', 'เม.ย.':'04', 'พ.ค.':'05', 'มิ.ย.':'06',
                 'ก.ค.':'07', 'ส.ค.':'08', 'ก.ย.':'09', 'ต.ค.':'10', 'พ.ย.':'11', 'ธ.ค.':'12'}
    
    for val in series:
        s = str(val).strip().lower()
        if s == 'nan' or s == '':
            cleaned_list.append(pd.NaT)
            continue
            
        try:
            s = re.sub(r'\s*น\.?$', '', s)
            s = s.replace(',', ' ').replace('  ', ' ')
            
            for m_th, m_num in th_months.items():
                if m_th in s:
                    s = s.replace(m_th, f"/{m_num}/")
                    s = re.sub(r'/+', '/', s)
            
            parts = s.split(' ')
            date_part = parts[0]
            time_part = parts[1] if len(parts) > 1 else "00:00:00"
            
            date_pieces = re.split(r'[-/.]', date_part)
            if len(date_pieces) == 3:
                year = int(date_pieces[2])
                if year > 2500:
                    year = year - 543
                
                day = int(date_pieces[0])
                month = int(date_pieces[1])
                
                ts = pd.to_datetime(f"{year}-{month:02d}-{day:02d} {time_part}", errors='coerce')
                if pd.isna(ts):
                    ts = pd.to_datetime(f"{year}-{day:02d}-{month:02d} {time_part}", errors='coerce')
                
                cleaned_list.append(ts)
            else:
                cleaned_list.append(pd.to_datetime(s, errors='coerce', dayfirst=True))
        except:
            cleaned_list.append(pd.to_datetime(s, errors='coerce', dayfirst=True))
            
    return pd.Series(cleaned_list)

def parse_timestamp(df):
    possible_time_cols = [
        c for c in df.columns 
        if any(keyword in str(c).lower().strip() for keyword in [
            'ประทับเวลา', 'timestamp', 'เวลา', 'วันที่', 'date', 'time', 'วันเวลา'
        ])
    ]
    if possible_time_cols:
        target_col = possible_time_cols[0]
        df[target_col] = clean_and_parse_date_series(df[target_col])
        return target_col
    return None

# ดึงข้อมูลจากเน็ตอัปเดตทุก 1 นาทีเมื่อมีการ Rerun
@st.cache_data(ttl=60)
def load_online_data():
    online_data_dict = {}
    for sheet in target_sheets:
        import urllib.parse
        encoded_sheet_name = urllib.parse.quote(sheet["sheet_name"])
        sheet_url = f"{BASE_SPREADSHEET_URL}{encoded_sheet_name}"
        
        try:
            df = pd.read_csv(sheet_url, encoding='utf-8')
            if not df.empty and len(df) > 0:
                time_col = parse_timestamp(df)
                online_data_dict[sheet["name"]] = {"df": df, "time_col": time_col}
        except Exception as e:
            pass
    return online_data_dict

raw_files = load_online_data()

# =========================================================================
# 3. แถบเมนูด้านข้าง (Sidebar) พร้อมตราโลโก้โรงพยาบาลนาโพธิ์
# =========================================================================
with st.sidebar:
    if os.path.exists("hospital_logo.png"):
        st.image("hospital_logo.png", use_container_width=True)
    elif os.path.exists("hospital_logo.jpg"):
        st.image("hospital_logo.jpg", use_container_width=True)
    else:
        st.title("🏥")
    
    st.subheader("โรงพยาบาลนาโพธิ์")
    st.markdown("---")
    
    available_groups = list(raw_files.keys())
    if available_groups:
        selected_group = st.selectbox("🎯 เลือกกลุ่มผู้รับบริการ:", available_groups)
    else:
        selected_group = None
        
    st.markdown("---")
    st.subheader("📅 คัดกรองละเอียด (ระบุเวลา)")
    
    all_dates = []
    for g_name, g_info in raw_files.items():
        if g_info["time_col"] is not None:
            series_clean = g_info["df"][g_info["time_col"]].dropna()
            if not series_clean.empty:
                all_dates.extend(series_clean.tolist())
                
    if all_dates:
        all_dates_pd = pd.to_datetime(all_dates)
        min_datetime = all_dates_pd.min()
        max_datetime = all_dates_pd.max()
        
        if min_datetime.year < 2000: min_datetime = pd.Timestamp("2024-01-01 00:00:00")
        if max_datetime.year > 2030: max_datetime = pd.Timestamp.now()
        
        date_range = st.date_input(
            "1. เลือกช่วงวันที่ประเมิน:",
            value=(min_datetime.date(), max_datetime.date()),
            min_value=min_datetime.date(),
            max_value=max_datetime.date()
        )
        
        col_time1, col_time2 = st.columns(2)
        with col_time1:
            start_time = st.time_input("2. เวลาเริ่มต้น:", value=pd.to_datetime("00:00").time())
        with col_time2:
            end_time = st.time_input("3. เวลาสิ้นสุด:", value=pd.to_datetime("23:59").time())
    else:
        st.info("💡 ระบบกำลังอ่านฐานข้อมูลออนไลน์...")
        date_range = None
        start_time, end_time = None, None

# =========================================================================
# 4. ฟังก์ชันประมวลผลคัดกรองข้อมูลและคำนวณสถิติ (เวอร์ชันอัปเกรดความปลอดภัย)
# =========================================================================
def process_filtered_data(raw_files, date_range, start_time, end_time):
    all_groups_data = {}
    overall_list = []
    
    start_date, end_date = None, None
    if date_range and len(date_range) == 2:
        start_date, end_date = date_range
        
    for sheet_name, g_info in raw_files.items():
        df = g_info["df"].copy()
        time_col = g_info["time_col"]
        
        # กรองวันที่เฉพาะเมื่อกำหนดช่วงเวลาถูกต้องและคอลัมน์วันที่ใช้งานได้จริง
        if time_col and start_date and end_date and start_time and end_time:
            try:
                df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
                start_datetime = pd.Timestamp.combine(start_date, start_time)
                end_datetime = pd.Timestamp.combine(end_date, end_time)
                df = df[(df[time_col] >= start_datetime) & (df[time_col] <= end_datetime)]
            except:
                pass # ถ้าเกิดข้อผิดพลาดในการแปลงวันที่ ให้ใช้ข้อมูลทั้งหมดไปคำนวณต่อ ไม่ให้ระบบตัดทิ้ง
            
        if df.empty:
            continue
            
        score_cols = [c for c in df.columns if get_aspect_name(c) is not None]
        suggestion_col = [c for c in df.columns if "ข้อเสนอแนะ" in str(c)]
        
        # แปลงข้อความคะแนนให้เป็นตัวเลข
        for col in score_cols:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+)')[0], errors='coerce')
        
        if len(score_cols) == 0:
            continue
            
        df_sub_queries = df[score_cols].mean().reset_index()
        df_sub_queries.columns = ['หัวข้อคำถามย่อย', 'คะแนนเฉลี่ย']
        df_sub_queries['คิดเป็นร้อยละ'] = (df_sub_queries['คะแนนเฉลี่ย'] / 5) * 100
        df_sub_queries['ด้าน'] = df_sub_queries['หัวข้อคำถามย่อย'].apply(get_aspect_name)
        
        suggestions = []
        if suggestion_col:
            suggestions = df[suggestion_col[0]].dropna().astype(str).tolist()
            suggestions = [s for s in suggestions if s.strip() != "" and s.lower() != "nan"]

        # คำนวณค่าเฉลี่ยแบบปลอดภัย ป้องกันค่า NaN ปนเปื้อน
        group_avg = df[score_cols].mean().mean()
        if pd.isna(group_avg):
            group_avg = 0.0
            
        overall_list.append({
            "กลุ่ม": sheet_name,
            "คะแนนเฉลี่ยรวม": group_avg,
            "คิดเป็นร้อยละ": (group_avg / 5) * 100,
            "จำนวนผู้ตอบ": len(df)
        })
        
        all_groups_data[sheet_name] = {
            "sub_queries": df_sub_queries,
            "suggestions": suggestions,
            "raw_df": df,
            "score_cols": score_cols
        }
        
    return all_groups_data, pd.DataFrame(overall_list)

# =========================================================================
# 5. ส่วนแสดงผลบนหน้าจอแดชบอร์ด (UI)
# =========================================================================
if selected_group and available_groups:
    data_dict, df_overall = process_filtered_data(raw_files, date_range, start_time, end_time)
    
    if df_overall.empty or selected_group not in data_dict:
        st.warning("⚠️ ดึงข้อมูลเสร็จสิ้น แต่พบว่าข้อมูลยังว่างเปล่า หรือรูปแบบหัวข้อคำถามไม่ตรงกับเกณฑ์ค้นหา ดันนั้นระบบภาพรวมจึงยังไม่แสดงผลครับ")
    else:
        total_responses = df_overall['จำนวนผู้ตอบ'].sum()
        total_avg = df_overall['คะแนนเฉลี่ยรวม'].mean()
        total_percentage = (total_avg / 5) * 100

        if date_range and len(date_range) == 2:
            st.markdown(f"🗓️ **ช่วงเวลาที่กำลังประมวลผล:** {date_range[0].strftime('%d/%m/%Y')} ({start_time.strftime('%H:%M')}) ถึง {date_range[1].strftime('%d/%m/%Y')} ({end_time.strftime('%H:%M')})")
        
        c1, c2 = st.columns(2)
        with c1: 
            st.metric(label="👥 จำนวนผู้ประเมินรวม (ทุกกลุ่มงานในช่วงนี้)", value=f"{total_responses} คน")
        with c2: 
            st.metric(label="❤️ คะแนนเฉลี่ยพึงพอใจรวมทุกกลุ่ม (ภาพรวม รพ.)", value=f"{total_avg:.2f} / 5.00", delta=f"คิดเป็นร้อยละ {total_percentage:.2f}%")
        st.markdown("---")

        group_data = data_dict[selected_group]
        df_sub = group_data["sub_queries"].copy()
        df_sub['หัวข้อย่อยแบบสั้น'] = df_sub['หัวข้อคำถามย่อย'].apply(lambda x: str(x).split('[')[-1].replace(']', '') if '[' in str(x) else str(x))
        
        st.info(f"📋 **กำลังเจาะลึกเฉพาะข้อมูล:** {selected_group} | จำนวนผู้ตอบในเวลายอดนี้ {len(group_data['raw_df'])} คน")
        
        st.markdown("### 🏆 สรุปวิเคราะห์จุดเด่น และจุดที่ต้องปรับปรุงเร่งด่วน")
        
        df_sorted = df_sub.sort_values(by='คะแนนเฉลี่ย', ascending=False)
        df_low_kpi = df_sub[df_sub['คะแนนเฉลี่ย'] < KPI_TARGET].sort_values(by='คะแนนเฉลี่ย', ascending=True)
        
        col_top, col_low = st.columns(2)
        with col_top:
            if not df_sorted.empty:
                top_job = df_sorted.iloc[0]
                st.success(f"🌟 **จุดเด่นที่ทำได้ดีที่สุดในช่วงนี้:**\n\n\"{top_job['หัวข้อย่อยแบบสั้น']}\" \n\n**(คะแนนเฉลี่ย: {top_job['คะแนนเฉลี่ย']:.2f} | ร้อยละ {top_job['คิดเป็นร้อยละ']:.2f}%)**")
            else:
                st.info("ไม่พบข้อมูลคะแนนเฉลี่ย")
                
        with col_low:
            st.markdown("⚠️ **หัวข้อการประเมินที่ต่ำกว่าเกณฑ์เป้าหมาย (< 4.00):**")
            if df_low_kpi.empty:
                st.success("🎉 ยอดเยี่ยมมาก! ในช่วงเวลานี้ไม่มีหัวข้อคำถามไหนที่ได้คะแนนต่ำกว่าเกณฑ์ 4.00 เลยครับ")
            else:
                for _, row in df_low_kpi.iterrows():
                    st.error(f"• **{row['หัวข้อย่อยแบบสั้น']}** ได้คะแนนเฉลี่ยเพียง `{row['คะแนนเฉลี่ย']:.2f}` (ร้อยละ {row['คิดเป็นร้อยละ']:.2f}%)")
                    
        st.markdown("---")
        tab1, tab2 = st.tabs(["📊 คะแนนการประเมินรายข้อและเป้าหมาย KPI (4.00)", "💬 กล่องสรุปวิเคราะห์และค้นหาข้อเสนอแนะ"])
        
        with tab1:
            st.markdown(f"### 📈 กราฟคะแนนรายข้อตามด้านบริการ (เป้าหมายตัวชี้วัด >= {KPI_TARGET:.2f} หรือร้อยละ 80.00%)")
            unique_aspects = sorted(df_sub['ด้าน'].dropna().unique())
            for aspect in unique_aspects:
                st.markdown(f"#### 📍 {aspect}")
                df_aspect_sub = df_sub[df_sub['ด้าน'] == aspect].copy()
                df_aspect_sub['ผลประเมิน'] = df_aspect_sub['คะแนนเฉลี่ย'].apply(lambda x: 'ผ่านเกณฑ์ตัวชี้วัด (>= 4.00)' if x >= KPI_TARGET else 'ต่ำกว่าเกณฑ์ตัวชี้วัด (< 4.00)')
                
                fig_sub = px.bar(
                    df_aspect_sub, y='หัวข้อย่อยแบบสั้น', x='คะแนนเฉลี่ย', orientation='h', text_auto='.2f',
                    color='ผลประเมิน', color_discrete_map={'ผ่านเกณฑ์ตัวชี้วัด (>= 4.00)': '#2ca02c', 'ต่ำกว่าเกณฑ์ตัวชี้วัด (< 4.00)': '#ff7f0e'}, range_x=[0, 5]
                )
                fig_sub.add_vline(x=KPI_TARGET, line_dash="dash", line_color="red", annotation_text=f"เป้าหมาย {KPI_TARGET:.2f}")
                fig_sub.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=True)
                st.plotly_chart(fig_sub, use_container_width=True)
                
        with tab2:
            st.markdown("### 💬 ความคิดเห็นและข้อเสนอแนะจากผู้ประเมินจริงในช่วงเวลานี้")
            list_suggestions = group_data["suggestions"]
            search_query = st.text_input("🔍 พิมพ์คำสำคัญเพื่อค้นหาข้อเสนอแนะแบบเฉพาะเจาะจง:")
            filtered_suggestions = [s for s in list_suggestions if search_query.lower() in s.lower()] if search_query else list_suggestions
            
            if not filtered_suggestions: 
                st.info("🟢 ไม่พบข้อเสนอแนะเพิ่มเติมที่เป็นตัวอักษรในช่วงเวลานี้")
            else:
                for idx, text in enumerate(filtered_suggestions, 1):
                    st.markdown(f"**ข้อเสนอแนะฉบับที่ {idx}:** \"{text}\"")
                    st.markdown("---")

# =========================================================================
# 6. แผงสรุปภาพรวม 5 กลุ่ม (ปรับปรุงความยืดหยุ่น ย้ายออกนอกเงื่อนไขคัดกรองวันเวลา)
# =========================================================================
st.markdown("---")
st.markdown("## 🏢 ส่วนสรุปรายงานภาพรวมเปรียบเทียบ 5 กลุ่มผู้รับบริการ")

# ดึงสถิติพื้นฐานจากข้อมูลทั้งหมดแบบไม่ผ่านตัวกรองปฏิทินเพื่อเป็นเซฟตี้เน็ตให้ข้อมูลขึ้นชัวร์ๆ
try:
    _, df_backup_overall = process_filtered_data(raw_files, None, None, None)
    df_to_show = df_overall if (selected_group and available_groups and not df_overall.empty) else df_backup_overall

    if df_to_show.empty:
        st.info("💡 ระบบออนไลน์เชื่อมต่อสำเร็จ แต่ยังไม่มีข้อมูลดิบหรือคำตอบถูกส่งเข้ามาในแผ่นงานเลยครับ ตารางภาพรวมจึงสแตนบายรอข้อมูลอยู่ครับ")
    else:
        df_overall_sorted = df_to_show.sort_values(by="คะแนนเฉลี่ยรวม", ascending=False).reset_index(drop=True)
        df_overall_sorted.index = df_overall_sorted.index + 1
        
        # ป้องกันโค้ดบรรทัดยาวเกินไปขาดจากกัน
        df_overall_sorted['สถานะตามเกณฑ์ KPI'] = df_overall_sorted['คะแนนเฉลี่ยรวม'].apply(
            lambda x: '🟢 ผ่านเกณฑ์เป้าหมาย (>= 4.0)' if x >= KPI_TARGET else '🔴 ต่ำกว่าเกณฑ์เป้าหมาย (< 4.0)'
        )
        
        col_table, col_chart = st.columns([5, 5])
        with col_table:
            st.markdown("### 📋 ตารางสรุปอันดับ คะแนนเฉลี่ย และร้อยละความพึงพอใจ")
            st.dataframe(
                df_overall_sorted.style.format({
                    "คะแนนเฉลี่ยรวม": "{:.2f} / 5.00", 
                    "คิดเป็นร้อยละ": "{:.2f} %", 
                    "จำนวนผู้ตอบ": "{:,.0f} คน"
                }), 
                use_container_width=True
            )
            best_group = df_overall_sorted.iloc[0]
            st.success(f"🏆 **กลุ่มงานที่ได้รับความพึงพอใจสูงสุด:** {best_group['กลุ่ม']} ({best_group['คะแนนเฉลี่ยรวม']:.2f} คะแนน | {best_group['คิดเป็นร้อยละ']:.2f}%)")
            
        with col_chart:
            st.markdown("### 📊 กราฟเปรียบเทียบค่าร้อยละความพึงพอใจรวม")
            fig_overall = px.bar(
                df_overall_sorted, x='คิดเป็นร้อยละ', y='กลุ่ม', orientation='h', text='คิดเป็นร้อยละ', text_auto='.2f',
                color='สถานะตามเกณฑ์ KPI',
                color_discrete_map={'🟢 ผ่านเกณฑ์เป้าหมาย (>= 4.0)': '#2196F3', '🔴 ต่ำกว่าเกณฑ์เป้าหมาย (< 4.0)': '#FF5722'}, range_x=[0, 100]
            )
            fig_overall.add_vline(x=80.0, line_dash="dash", line_color="red", annotation_text="เป้าหมายร้อยละ 80%")
            fig_overall.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=True)
            st.plotly_chart(fig_overall, use_container_width=True)
except Exception as e:
    st.error(f"⚠️ เกิดข้อผิดพลาดทางโครงสร้างไฟล์รวม: {str(e)}")
