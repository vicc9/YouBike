import streamlit as st
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta
from streamlit_folium import st_folium
import os
import math
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from streamlit_geolocation import streamlit_geolocation
from concurrent.futures import ThreadPoolExecutor

# 引入自定義模組
from day1_youbike import get_tdx_token, get_youbike_data, get_station_info
from day2_weather import get_all_cities_weather
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

# ==========================================
# 🆕 步驟一：嚴格獨立的「基礎資料抓取」 (不受 UI 影響)
# ==========================================
@st.cache_data(show_spinner="📡 正在極速抓取全台 YouBike 與天氣資料...", ttl=600) 
def fetch_base_data():
    token_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    client_id = os.getenv("TDX_CLIENT_ID")
    client_secret = os.getenv("TDX_CLIENT_SECRET")
    api_headers = {}
    
    # 取得 TDX Token
    if client_id and client_secret:
        data = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}
        try:
            res_token = requests.post(token_url, headers=headers, data=data)
            if res_token.status_code == 200:
                api_headers = {'authorization': f'Bearer {res_token.json().get("access_token")}'}
        except:
            pass

    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    cities = ['Taipei', 'NewTaipei', 'Taoyuan', 'Hsinchu', 'HsinchuCounty', 'MiaoliCounty', 'Taichung', 'Chiayi', 'ChiayiCounty', 'Tainan', 'Kaohsiung', 'PingtungCounty']
    all_stations = []
    
    def fetch_city_data(city):
        city_stations = []
        try:
            # 🔄 全面統一使用 TDX API，廢除舊版台北/新北直連，確保資料完整與格式一致
            station_url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Station/City/{city}?%24format=JSON"
            avail_url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Availability/City/{city}?%24format=JSON"
            
            res_station_req = session.get(station_url, headers=api_headers, timeout=10)
            res_avail_req = session.get(avail_url, headers=api_headers, timeout=10)
            
            if res_station_req.status_code == 200 and res_avail_req.status_code == 200:
                res_station = res_station_req.json()
                res_avail = res_avail_req.json()
                
                if isinstance(res_station, list) and isinstance(res_avail, list):
                    avail_dict = {item.get('StationID'): {'AvailableRentBikes': item.get('AvailableRentBikes', 0), 'AvailableReturnBikes': item.get('AvailableReturnBikes', 0)} for item in res_avail if item.get('StationID')}
                    
                    for station in res_station:
                        sid = station.get('StationID')
                        if sid in avail_dict:
                            lat = float(station.get('StationPosition', {}).get('PositionLat', 0))
                            lng = float(station.get('StationPosition', {}).get('PositionLon', 0))
                            
                            # 🛡️ 台灣專屬座標防呆：只允許經緯度落在台灣範圍內的站點，徹底杜絕藍色海洋！
                            if not (21.0 <= lat <= 27.0) or not (118.0 <= lng <= 123.0): 
                                continue
                            
                            # 🧹 統一清理站點名稱，移除全台各縣市的 YouBike2.0_ 贅字
                            clean_name = station.get('StationName', {}).get('Zh_tw', '').replace('YouBike2.0_', '')
                            
                            city_stations.append({
                                'StationUID': station.get('StationUID', ''), 'StationID': sid,
                                'StationName': clean_name, 'City': city,
                                'StationPositionLat': lat, 'StationPositionLon': lng,
                                'BikesCapacity': station.get('BikesCapacity', 0),
                                'AvailableRentBikes': avail_dict[sid]['AvailableRentBikes'],
                                'AvailableReturnBikes': avail_dict[sid]['AvailableReturnBikes']
                            })
        except Exception:
            pass
        return city_stations
        
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_city_data, cities)
        
    for res in results:
        if res: all_stations.extend(res)
            
    df_merged = pd.DataFrame(all_stations)
    if df_merged.empty: return None, None
    
    try:
        all_weather_dict = get_all_cities_weather()
    except Exception:
        all_weather_dict = {}

    return df_merged, all_weather_dict

# ==========================================
# 🆕 步驟二：處理 AI 預測邏輯 (只有改時間才會呼叫 API)
# ==========================================
@st.cache_data(show_spinner="🧠 正在呼叫 AI 計算未來車況...", ttl=600)
def get_predictions(df_merged, all_weather_dict, target_mins):
    df_pred = df_merged.copy()
    
    if target_mins == 0:
        df_pred['Predicted_Bikes'] = df_pred['AvailableRentBikes']
        return df_pred

    now = datetime.now()
    future_time = now + timedelta(minutes=target_mins)

    df_pred['temperature'] = df_pred['City'].apply(lambda c: all_weather_dict.get(c, {}).get('Temperature', 25.0))
    df_pred['precipitation'] = df_pred['City'].apply(lambda c: all_weather_dict.get(c, {}).get('Precipitation', 0.0))

    features = pd.DataFrame({
        'hour': [future_time.hour] * len(df_pred),
        'day_of_week': [future_time.weekday()] * len(df_pred),
        'is_weekend': [1 if future_time.weekday() >= 5 else 0] * len(df_pred),
        'month': [future_time.month] * len(df_pred),
        'is_holiday': [0] * len(df_pred), 
        'temperature': df_pred['temperature'],
        'precipitation': df_pred['precipitation'],
        'wind_speed': [0.0] * len(df_pred), 
        'aqi': [50.0] * len(df_pred),       
        'dist_to_mrt': [1000.0] * len(df_pred), 
        'station_capacity': df_pred['BikesCapacity'], 
        'bikes_1h_ago': df_pred['AvailableRentBikes'],
        'target_minutes': [target_mins] * len(df_pred),
        'current_bikes': df_pred['AvailableRentBikes']  # 🌟 新增這行：把當下車況傳給 API
    })
    
    try:
        features_dict = features.to_dict(orient='records') 
        response = requests.post("https://youbike-wrfi.onrender.com/predict", json=features_dict, timeout=100)
        if response.status_code == 200:
            res_data = response.json()
            # 🛡️ 檢查回傳的 JSON 裡面有沒有 predictions
            if "predictions" in res_data:
                df_pred['Predicted_Bikes'] = res_data['predictions']
            else:
                # 🎯 如果 API 回傳 {"error": "Model is not loaded."} 會被這裡抓到
                st.error(f"🚨 後端 API 回報錯誤: {res_data.get('error', '未知錯誤')}")
                df_pred['Predicted_Bikes'] = df_pred['AvailableRentBikes']
        else:
            st.error(f"🚨 API 拒絕處理或資料格式不符 (狀態碼: {response.status_code}) \n\n 錯誤內容: {response.text}")
            df_pred['Predicted_Bikes'] = df_pred['AvailableRentBikes']
            
    except Exception as e:
        st.error(f"🚨 無法連線至後端 AI 伺服器，詳細錯誤: {e}")
        df_pred['Predicted_Bikes'] = df_pred['AvailableRentBikes']
        
    return df_pred

# --- Streamlit 介面 ---
st.set_page_config(layout="wide", page_title="全台 YouBike 智慧導覽")
st.title("🚲 智慧型 YouBike 2.0 防撲空預測導覽圖")

if 'my_lat' not in st.session_state: st.session_state.my_lat = 25.0478
if 'my_lon' not in st.session_state: st.session_state.my_lon = 121.5170
if 'has_located' not in st.session_state: st.session_state.has_located = False
if 'last_location_method' not in st.session_state: st.session_state.last_location_method = "🔍 智慧搜尋地點"

# 🌟 取得基礎資料
base_df, current_weather_dict = fetch_base_data()

if base_df is None:
    st.error("無法連線至 TDX API 或抓取不到資料，請檢查網路或 API 金鑰。")
    st.stop()

# ----------------------------------------
# 🎛️ 側邊欄設定
# ----------------------------------------
st.sidebar.header("📍 尋找位置")

location_method = st.sidebar.radio("請選擇定位方式：", ["🔍 智慧搜尋地點", "🛰️ 使用 GPS 定位"])

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
    search_query = st.sidebar.text_input("請輸入站點名稱、地標或地址：", placeholder="例如: 台北車站 或 左營巨蛋", value="")
    
    if search_query:
        sq_tw = search_query.replace("台", "臺")
        sq_cn = search_query.replace("臺", "台")
        
        mask = base_df['StationName'].astype(str).str.contains(sq_tw, case=False, na=False) | \
               base_df['StationName'].astype(str).str.contains(sq_cn, case=False, na=False) | \
               base_df['StationName'].astype(str).str.contains(search_query, case=False, na=False)
               
        matched_df = base_df[mask].head(15)
        
        if not matched_df.empty:
            options_list = (matched_df['StationName']).tolist()
            selected_station = st.sidebar.selectbox("💡 找到相符站點，請確認：", options=options_list)
            target_row = matched_df[(matched_df['StationName']) == selected_station].iloc[0]
            st.session_state.my_lat = float(target_row['StationPositionLat'])
            st.session_state.my_lon = float(target_row['StationPositionLon'])
            st.session_state.has_located = True
            st.sidebar.success(f"📍 已定位至：{selected_station}")
        else:
            st.sidebar.info(f"💡 找不到名為「{search_query}」的站點，正在嘗試搜尋地址座標...")
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

st.sidebar.markdown("---")
st.sidebar.header("⏳ 智慧預測")
predict_minutes = st.sidebar.selectbox(
    "預測幾分鐘後的車況？", options=[0, 5, 10, 15, 20],
    format_func=lambda x: "即時車況 (現在)" if x == 0 else f"預測 {x} 分鐘後", index=2
)

if st.sidebar.button("🔄 立即重新整理車況"):
    st.cache_data.clear()
    st.rerun()

# ----------------------------------------
# ⚙️ 核心資料觸發點
# ----------------------------------------
df_all = get_predictions(base_df, current_weather_dict, predict_minutes)

target_col = 'Predicted_Bikes' if mode == "我要借車 🚲" else 'AvailableReturnBikes'
map_mode = "rent" if mode == "我要借車 🚲" else "return"
filtered_df = df_all[df_all[target_col] >= min_amount].copy()

# ----------------------------------------
# 📊 顯示區 (地圖與資訊)
# ----------------------------------------
# 🌟 動態判斷使用者目前所在的縣市 (藉由距離最近的站點反查)
local_city_eng = 'Taipei'
if st.session_state.has_located and not base_df.empty:
    # 算出距離定位點最近的站點，抓取它的 City
    base_df['Temp_Dist'] = base_df.apply(
        lambda row: calculate_distance(st.session_state.my_lat, st.session_state.my_lon, row['StationPositionLat'], row['StationPositionLon']), axis=1
    )
    local_city_eng = base_df.loc[base_df['Temp_Dist'].idxmin(), 'City']

# 中英縣市對照表 (用於顯示)
city_zh_mapping = {
    'Taipei': '臺北市', 'NewTaipei': '新北市', 'Taoyuan': '桃園市',
    'Hsinchu': '新竹市', 'HsinchuCounty': '新竹縣', 'MiaoliCounty': '苗栗縣',
    'Taichung': '臺中市', 'Chiayi': '嘉義市', 'ChiayiCounty': '嘉義縣',
    'Tainan': '臺南市', 'Kaohsiung': '高雄市', 'PingtungCounty': '屏東縣'
}
local_city_zh = city_zh_mapping.get(local_city_eng, '臺北市')

display_temp, display_precip = 25.0, 0.0
if current_weather_dict:
    # 🌟 根據所在位置抓取當地氣候，不再全台綁定台北！
    local_weather = current_weather_dict.get(local_city_eng, {})
    display_temp = local_weather.get('Temperature', 25.0)
    display_precip = local_weather.get('Precipitation', 0.0)

col1, col2 = st.columns([1, 1])

with col1:
    if predict_minutes > 0:
        st.info(f"🔮 系統正為您展示 **{predict_minutes} 分鐘後** 的預測車況！")
    else:
        st.info("⚡ 目前顯示為即時車況 (現在)")
        
with col2:
    # 🌟 畫面字眼改成「當地氣溫」並顯示當地縣市名稱
    st.write(f"📍 **{local_city_zh} 當地氣溫：** {display_temp}°C | 🌧️ **降雨：** {display_precip}mm")
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
        
        nearby_df = filtered_df[filtered_df['Distance_km'] <= 1.5].copy()
        
        if nearby_df.empty:
            st.warning("😭 您的所在位置周圍 1.5 公里內找不到符合條件的站點。")
            m = create_map(pd.DataFrame(columns=filtered_df.columns), st.session_state.my_lat, st.session_state.my_lon, mode=map_mode)
            st_folium(m, use_container_width=True, height=500, key=f"map_empty_{st.session_state.my_lat}_{mode}_{min_amount}")
        else:
            closest_idx = nearby_df['Distance_km'].idxmin()
            nearby_df.loc[nearby_df.index != closest_idx, 'Distance_km'] += 0.001
            
            closest = nearby_df.loc[closest_idx]
            s_name = closest['StationName']
            st.success(f"🎯 推薦最近站點：**{s_name}** (距離約 {closest['Distance_km']:.2f} km)")
            
            m = create_map(nearby_df, st.session_state.my_lat, st.session_state.my_lon, mode=map_mode)
            st_folium(m, use_container_width=True, height=500, key=f"map_{st.session_state.my_lat}_{st.session_state.my_lon}_{mode}_{min_amount}_{predict_minutes}")
            
            nav_url = f"https://www.google.com/maps/dir/?api=1&destination={closest['StationPositionLat']},{closest['StationPositionLon']}&travelmode=walking"
            st.link_button("🚀 開啟 Google Maps 導航", nav_url)
    else:
        st.error("😭 目前全台找不到符合條件的站點，請調整側邊欄的過濾條件。")