import streamlit as st
import pandas as pd
import joblib
from datetime import datetime
from streamlit_folium import st_folium
import requests
import os
import math
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from streamlit_geolocation import streamlit_geolocation

# 引入您自定義的模組
from day1_youbike import get_tdx_token, get_youbike_data, get_station_info
from day2_weather import get_current_weather
from day5_map import create_map

load_dotenv()

# --- 基礎函式 ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# 🌟 新增：透過 API 搜尋地點經緯度
def get_coords_from_address(address):
    try:
        geolocator = Nominatim(user_agent="my_youbike_app")
        # 自動補上 "高雄" 縮小搜尋範圍
        location = geolocator.geocode(f"{address}, 高雄市")
        if location:
            return location.latitude, location.longitude
        return None
    except:
        return None

# --- 資料抓取與快取 ---
@st.cache_data(ttl=300) # 快取 5 分鐘，避免頻繁刷 API
def fetch_all_data():
    token = get_tdx_token()
    df_static = get_station_info(token)
    df_dynamic = get_youbike_data(token)
    weather = get_current_weather()
    
    if df_static.empty or df_dynamic.empty:
        return None, None
        
    df_merged = pd.merge(df_static, df_dynamic, on='StationUID')
    
    # 執行預測邏輯
    now = datetime.now()
    next_hour = (now.hour + 1) % 24
    features = pd.DataFrame({
        'Hour': [next_hour] * len(df_merged),
        'DayOfWeek': [now.weekday()] * len(df_merged),
        'IsWeekend': [1 if now.weekday() >= 5 else 0] * len(df_merged),
        'Temperature': [weather['Temperature']] * len(df_merged),
        'Precipitation': [weather['Precipitation']] * len(df_merged)
    })
    
    try:
        model = joblib.load('youbike_model.pkl')
        df_merged['Predicted_Bikes'] = model.predict(features)
    except:
        df_merged['Predicted_Bikes'] = df_merged['AvailableRentBikes']
        
    return df_merged, weather

# --- Streamlit 介面 ---
st.set_page_config(layout="wide", page_title="高雄 YouBike 智慧導覽")
st.title("🚲 智慧型 YouBike 2.0 防撲空導覽圖")

# 🔄 進入頁面自動抓取資料
df_all, current_weather = fetch_all_data()

if df_all is None:
    st.error("無法連線至 TDX API，請檢查網路或金鑰。")
    st.stop()

# ----------------------------------------
# 🎛️ 側邊欄設定 (一進來就顯示)
# ----------------------------------------
st.sidebar.header("📍 您的位置")

# 🌟 新增：讓使用者明確選擇定位方式
location_method = st.sidebar.radio(
    "請選擇定位方式：", 
    ["🔍 手動輸入地點", "🛰️ 使用 GPS 定位"]
)

# 邏輯分流：根據使用者的選擇執行對應的定位方式
if location_method == "🛰️ 使用 GPS 定位":
    # 模式 A：GPS 定位
    location = streamlit_geolocation()
    if location and location.get('latitude'):
        my_lat, my_lon = location['latitude'], location['longitude']
        st.sidebar.success("✅ 已使用 GPS 定位")
    else:
        st.sidebar.info("👆 請點擊上方 ⌖ 按鈕獲取您的目前位置")
        my_lat, my_lon = 22.6394, 120.3025 # 如果還沒按，給預設值
        
else:
    # 模式 B：手動輸入 (包含路名)
    search_address = st.sidebar.text_input("輸入地點或路名 (例如：高雄巨蛋、中山路)", "")
    if search_address:
        with st.sidebar.spinner("搜尋中..."):
            coords = get_coords_from_address(search_address)
            if coords:
                my_lat, my_lon = coords
                st.sidebar.success(f"📍 已定位至：{search_address}")
            else:
                st.sidebar.error("找不到該地點，請嘗試加入『高雄市』或換個關鍵字。")
                my_lat, my_lon = 22.6394, 120.3025
    else:
        st.sidebar.info("👆 請在上方輸入您想查詢的地點或路名")
        my_lat, my_lon = 22.6394, 120.3025 # 如果還沒輸入，給預設值

st.sidebar.markdown("---")
st.sidebar.header("🎯 尋找條件")
mode = st.sidebar.radio("需求：", ["我要借車 🚲", "我要還車 🅿️"])
min_amount = st.sidebar.slider("最少需要數量：", 1, 20, 3)
station_keyword = st.sidebar.text_input("🔍 過濾站點名稱 (選填)：")

if st.sidebar.button("🔄 立即重新整理車況"):
    st.cache_data.clear()
    st.rerun()

# ----------------------------------------
# ⚙️ 資料過濾與計算
# ----------------------------------------
target_col = 'Predicted_Bikes' if mode == "我要借車 🚲" else 'AvailableReturnBikes'
map_mode = "rent" if mode == "我要借車 🚲" else "return"

filtered_df = df_all[df_all[target_col] >= min_amount].copy()
if station_keyword:
    filtered_df = filtered_df[filtered_df['StationName'].astype(str).str.contains(station_keyword, na=False)]

# ----------------------------------------
# 📊 顯示區 (地圖與資訊)
# ----------------------------------------
col1, col2 = st.columns([1, 1])
with col1:
    st.write(f"🌤️ **天氣：** {current_weather['Temperature']}°C | 🌧️ **降雨：** {current_weather['Precipitation']}mm")
with col2:
    st.write(f"📋 **搜尋結果：** {len(filtered_df)} 站")

if not filtered_df.empty:
    # 1. 計算所有站點與您的距離
    filtered_df['Distance_km'] = filtered_df.apply(
        lambda row: calculate_distance(my_lat, my_lon, row['StationPositionLat'], row['StationPositionLon']), axis=1
    )
    
    # 2. 找出最近的站點並顯示文字提示
    closest = filtered_df.loc[filtered_df['Distance_km'].idxmin()]
    s_name = closest['StationName']['Zh_tw'] if isinstance(closest['StationName'], dict) else closest['StationName']
    st.success(f"🎯 推薦最近站點：**{s_name}** (距離約 {closest['Distance_km']:.2f} km)")
    
    # 🌟 關鍵修正：只保留距離您「 2 公里以內」的站點來畫地圖
    nearby_df = filtered_df[filtered_df['Distance_km'] <= 2.0]
    
    # 防呆機制：如果 2 公里內剛好完全沒半台車，就強迫顯示最近的 5 個站點
    if nearby_df.empty:
        nearby_df = filtered_df.nsmallest(5, 'Distance_km')
    
    # 3. 將「過濾後的附近站點 (nearby_df)」交給地圖，而不是全高雄的站點
    m = create_map(nearby_df, my_lat, my_lon, mode=map_mode)
    
    # 將地圖的 key 綁定經緯度，確保位置一變就重新繪製
    st_folium(m, use_container_width=True, height=500, key=f"map_{my_lat}_{my_lon}")
    
    # 導航按鈕
    nav_url = f"https://www.google.com/maps/dir/?api=1&origin={my_lat},{my_lon}&destination={closest['StationPositionLat']},{closest['StationPositionLon']}&travelmode=walking"
    st.link_button("🚀 開啟 Google Maps 導航", nav_url)
else:
    st.error("😭 找不到符合條件的站點，請調整過濾條件。")