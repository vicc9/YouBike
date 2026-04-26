import streamlit as st
import pandas as pd
import joblib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
from datetime import datetime
from streamlit_folium import st_folium
import os
import math
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from streamlit_geolocation import streamlit_geolocation
from concurrent.futures import ThreadPoolExecutor

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

def get_coords_from_address(address):
    try:
        geolocator = Nominatim(user_agent="youbike_tw_search_v8", timeout=10)
        search_query = address
        if "台灣" not in search_query and "Taiwan" not in search_query:
            search_query = f"台灣 {search_query}"

        location = geolocator.geocode(search_query)
        if location:
            return location.latitude, location.longitude
        return None
    except:
        return None

# --- 資料抓取與快取 ---
@st.cache_data(show_spinner="📡 正在極速抓取全台 YouBike 與車況...", ttl=600) 
def fetch_all_youbike_data():
    
    # 【階段一】獲取 Token 與設定 Session
    token_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    
    client_id = os.getenv("TDX_CLIENT_ID")
    client_secret = os.getenv("TDX_CLIENT_SECRET")
    api_headers = {}
    
    if not client_id or not client_secret:
        st.warning("⚠️ 警告：找不到 TDX API 金鑰！目前使用「訪客模式」，很容易觸發限制。")
    else:
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret
        }
        try:
            res_token = requests.post(token_url, headers=headers, data=data)
            if res_token.status_code == 200:
                token = res_token.json().get('access_token')
                api_headers = {'authorization': f'Bearer {token}'}
            else:
                st.warning(f"⚠️ Token 申請失敗 (狀態碼: {res_token.status_code})。退回訪客模式。")
        except Exception as e:
            print(f"Token 獲取錯誤: {e}")

    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,  
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # 【階段二】多執行緒並行抓取全台資料 (極速化關鍵)
    cities = ['Taipei', 'NewTaipei', 'Taoyuan', 'Hsinchu', 'HsinchuCounty', 'MiaoliCounty', 'Taichung', 'Chiayi', 'ChiayiCounty', 'Tainan', 'Kaohsiung', 'PingtungCounty']
    all_stations = []
    
    # 定義單一縣市的抓取任務
    def fetch_city_data(city):
        station_url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Station/City/{city}?%24format=JSON"
        avail_url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Availability/City/{city}?%24format=JSON"
        city_stations = []
        try:
            res_station_req = session.get(station_url, headers=api_headers, timeout=10)
            res_avail_req = session.get(avail_url, headers=api_headers, timeout=10)
            
            if res_station_req.status_code == 200 and res_avail_req.status_code == 200:
                res_station = res_station_req.json()
                res_avail = res_avail_req.json()
                
                if isinstance(res_station, list) and isinstance(res_avail, list):
                    avail_dict = {
                        item.get('StationID'): {
                            'AvailableRentBikes': item.get('AvailableRentBikes', 0),
                            'AvailableReturnBikes': item.get('AvailableReturnBikes', 0)
                        } for item in res_avail if item.get('StationID')
                    }
                    
                    for station in res_station:
                        sid = station.get('StationID')
                        if sid in avail_dict:
                            city_stations.append({
                                'StationUID': station.get('StationUID', ''),
                                'StationID': sid,
                                'StationName': station.get('StationName', {}).get('Zh_tw', ''),
                                'City': city,
                                'StationPositionLat': float(station.get('StationPosition', {}).get('PositionLat', 0)),
                                'StationPositionLon': float(station.get('StationPosition', {}).get('PositionLon', 0)),
                                'latitude': float(station.get('StationPosition', {}).get('PositionLat', 0)),
                                'longitude': float(station.get('StationPosition', {}).get('PositionLon', 0)),
                                'BikesCapacity': station.get('BikesCapacity', 0),
                                'AvailableRentBikes': avail_dict[sid]['AvailableRentBikes'],
                                'AvailableReturnBikes': avail_dict[sid]['AvailableReturnBikes']
                            })
            else:
                 print(f"❌ {city} API 回傳異常: Station={res_station_req.status_code}, Avail={res_avail_req.status_code}")
                 
        except Exception as e:
            print(f"抓取 {city} 發生錯誤: {e}")
            
        return city_stations

    # 🚀 使用多執行緒 (開啟 6 個工人同時去抓)
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = executor.map(fetch_city_data, cities)
        for res in results:
            if res:
                all_stations.extend(res)
        
    df_merged = pd.DataFrame(all_stations)

    # 若無資料直接中斷
    if df_merged.empty:
        return None, None
        
    # 【階段三】取得天氣並進行預測
    try:
        weather = get_current_weather()
    except Exception:
        weather = None
        
    now = datetime.now()
    features = pd.DataFrame({
        'hour': [(now.hour + 1) % 24] * len(df_merged),
        'day_of_week': [now.weekday()] * len(df_merged),
        'is_weekend': [1 if now.weekday() >= 5 else 0] * len(df_merged),
        'month': [now.month] * len(df_merged),
        'is_holiday': [0] * len(df_merged), 
        'temperature': [weather.get('Temperature', 25) if weather else 25] * len(df_merged),
        'precipitation': [weather.get('Precipitation', 0) if weather else 0] * len(df_merged),
        'wind_speed': [0] * len(df_merged), 
        'aqi': [50] * len(df_merged),       
        'dist_to_mrt': [99999] * len(df_merged), 
        'station_capacity': df_merged['BikesCapacity'], 
        'bikes_1h_ago': df_merged['AvailableRentBikes'] 
    })
    
    try:
        features_dict = features.to_dict(orient='records') 
        response = requests.post("https://youbike-wrfi.onrender.com/predict", json=features_dict, timeout=120)

        if response.status_code == 200:
            df_merged['Predicted_Bikes'] = response.json()['predictions']
        else:
            df_merged['Predicted_Bikes'] = df_merged['AvailableRentBikes']
    except Exception as e:
        print(f"API 呼叫失敗: {e}")
        df_merged['Predicted_Bikes'] = df_merged['AvailableRentBikes']
        
    return df_merged, weather

# --- Streamlit 介面 ---
st.set_page_config(layout="wide", page_title="全台 YouBike 智慧導覽")
st.title("🚲 智慧型 YouBike 2.0 防撲空導覽圖 (全台版)")

# --- Session State 初始化 ---
if 'my_lat' not in st.session_state:
    st.session_state.my_lat = 25.0478
if 'my_lon' not in st.session_state:
    st.session_state.my_lon = 121.5170
if 'has_located' not in st.session_state:
    st.session_state.has_located = False
if 'last_location_method' not in st.session_state:
    st.session_state.last_location_method = "🔍 智慧搜尋地點"

df_all, current_weather = fetch_all_youbike_data()

if df_all is None:
    st.error("無法連線至 TDX API 或抓取不到資料，請檢查網路或 API 金鑰。")
    st.stop()

# ----------------------------------------
# 🎛️ 側邊欄設定
# ----------------------------------------
st.sidebar.header("📍 尋找位置")

location_method = st.sidebar.radio(
    "請選擇定位方式：", 
    ["🔍 智慧搜尋地點", "🛰️ 使用 GPS 定位"]
)

if st.session_state.last_location_method != location_method:
    st.session_state.has_located = False
    st.session_state.last_location_method = location_method
    st.rerun()

if location_method == "🛰️ 使用 GPS 定位":
    location = streamlit_geolocation()
    if location and location.get('latitude'):
        st.session_state.my_lat = location['latitude']
        st.session_state.my_lon = location['longitude']
        st.session_state.has_located = True
        st.sidebar.success("✅ 已成功獲取 GPS 定位")
    else:
        st.sidebar.info("👆 請點擊上方 ⌖ 按鈕獲取您的目前位置")
        
else:
    search_query = st.sidebar.text_input(
        "請輸入站點名稱、地標或地址：", 
        placeholder="例如: 高雄車站 或 左營巨蛋",
        value=""
    )
    
    if search_query:
        sq_tw = search_query.replace("台", "臺")
        sq_cn = search_query.replace("臺", "台")
        
        mask = df_all['StationName'].astype(str).str.contains(sq_tw, case=False, na=False) | \
               df_all['StationName'].astype(str).str.contains(sq_cn, case=False, na=False) | \
               df_all['StationName'].astype(str).str.contains(search_query, case=False, na=False)
               
        matched_df = df_all[mask].head(15)
        
        if not matched_df.empty:
            options_list = (matched_df['StationName']).tolist()
            selected_station = st.sidebar.selectbox("💡 找到相符站點，請確認：", options=options_list)
            
            target_row = matched_df[(matched_df['StationName']) == selected_station].iloc[0]
            st.session_state.my_lat = float(target_row['StationPositionLat'])
            st.session_state.my_lon = float(target_row['StationPositionLon'])
            st.session_state.has_located = True
            st.sidebar.success(f"📍 已定位至：{selected_station}")
            
        else:
            st.sidebar.info(f"💡 找不到名為「{search_query}」的站點，正在為您嘗試搜尋地標或地址座標...")
            coords = get_coords_from_address(search_query)
            if coords:
                st.session_state.my_lat, st.session_state.my_lon = coords
                st.session_state.has_located = True
                st.sidebar.success(f"📍 已定位至地點：{search_query}")
            else:
                st.sidebar.error("❌ 找不到該地點，請嘗試輸入更準確的地址。")
                st.session_state.has_located = False

st.sidebar.markdown("---")
st.sidebar.header("🎯 尋找條件")
mode = st.sidebar.radio("需求：", ["我要借車 🚲", "我要還車 🅿️"])
min_amount = st.sidebar.slider("最少需要數量：", 1, 20, 3)

if st.sidebar.button("🔄 立即重新整理車況"):
    st.cache_data.clear()
    st.rerun()

# ----------------------------------------
# ⚙️ 資料過濾與計算
# ----------------------------------------
target_col = 'Predicted_Bikes' if mode == "我要借車 🚲" else 'AvailableReturnBikes'
map_mode = "rent" if mode == "我要借車 🚲" else "return"

filtered_df = df_all[df_all[target_col] >= min_amount].copy()

# ----------------------------------------
# 📊 顯示區 (地圖與資訊)
# ----------------------------------------
col1, col2 = st.columns([1, 1])
with col1:
    st.write(f"🌤️ **天氣：** {current_weather['Temperature']}°C | 🌧️ **降雨：** {current_weather['Precipitation']}mm")
with col2:
    st.write(f"📋 **全台符合條件站點總數：** {len(filtered_df)} 站")

if not st.session_state.has_located:
    st.info("👋 歡迎使用！請從左側面板搜尋地點或使用 GPS 定位，地圖才會開始顯示您附近的 YouBike 站點喔！")
    m = create_map(pd.DataFrame(columns=filtered_df.columns), 25.0478, 121.5170, mode=map_mode)
    st_folium(m, use_container_width=True, height=500, key="map_initial")
else:
    if not filtered_df.empty:
        filtered_df['Distance_km'] = filtered_df.apply(
            lambda row: calculate_distance(st.session_state.my_lat, st.session_state.my_lon, row['StationPositionLat'], row['StationPositionLon']), axis=1
        )
        
        # 【修正細節 1】：這裡加上 .copy() 避免 Pandas 警告
        nearby_df = filtered_df[filtered_df['Distance_km'] <= 1.5].copy()
        
        if nearby_df.empty:
            st.warning("😭 您的所在位置周圍 1.5 公里內找不到符合「最少需要數量」條件的站點。")
            m = create_map(pd.DataFrame(columns=filtered_df.columns), st.session_state.my_lat, st.session_state.my_lon, mode=map_mode)
            st_folium(m, use_container_width=True, height=500, key=f"map_empty_{st.session_state.my_lat}_{mode}_{min_amount}")
        else:
            # 【修正細節 2】：強制打破距離平手局面，確保地圖只會有一個藍色標記
            closest_idx = nearby_df['Distance_km'].idxmin()
            
            # 將除了「第一名站點」以外的其他站點，距離都微調增加 0.001 公里
            nearby_df.loc[nearby_df.index != closest_idx, 'Distance_km'] += 0.001
            
            closest = nearby_df.loc[closest_idx]
            s_name = closest['StationName']
            st.success(f"🎯 推薦最近站點：**{s_name}** (距離約 {closest['Distance_km']:.2f} km)")
            
            m = create_map(nearby_df, st.session_state.my_lat, st.session_state.my_lon, mode=map_mode)
            st_folium(m, use_container_width=True, height=500, key=f"map_{st.session_state.my_lat}_{st.session_state.my_lon}_{mode}_{min_amount}")
            
            # 使用官方標準的 Google Maps 導航 URL 格式
            nav_url = f"https://www.google.com/maps/dir/?api=1&destination={closest['StationPositionLat']},{closest['StationPositionLon']}&travelmode=walking"
            st.link_button("🚀 開啟 Google Maps 導航", nav_url)
    else:
        st.error("😭 目前全台找不到符合條件的站點，請調整側邊欄的過濾條件。")