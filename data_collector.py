import os
import time
import requests
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

# 載入環境變數 (本地測試時讀取 .env，在 GitHub Actions 則讀取 Secrets)
load_dotenv()

# ==========================================
# 1. API 抓取函式設定
# ==========================================

def get_tdx_data():
    """獲取 TDX YouBike 即時動態與靜態容量資料 (全台各大縣市)"""
    app_id = os.getenv('TDX_CLIENT_ID')
    app_key = os.getenv('TDX_CLIENT_SECRET')
    
    if not app_id or not app_key:
        raise ValueError("❌ 找不到 TDX API 金鑰，請檢查環境變數。")

    # 取得 Token
    auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    auth_response = requests.post(auth_url, data={
        "grant_type": "client_credentials",
        "client_id": app_id,
        "client_secret": app_key
    })
    token = auth_response.json().get("access_token")
    headers = {"authorization": f"Bearer {token}"}

    # 建立全台有 YouBike 的縣市清單
    cities = [
        "Taipei", "NewTaipei", "Taoyuan", "Hsinchu", "HsinchuCounty", 
        "MiaoliCounty", "Taichung", "Chiayi", "Tainan", "Kaohsiung", "PingtungCounty"
    ]

    print(f"✅ TDX Token 取得成功，開始下載全台 {len(cities)} 個縣市的 YouBike 資料...")
    
    all_merged_df = pd.DataFrame()

    for city in cities:
        print(f"🔄 正在抓取 {city} 的資料...")
        try:
            # 抓取靜態資料 (為了取得總柱數 StationCapacity)
            static_url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Station/City/{city}?%24format=JSON"
            static_res = requests.get(static_url, headers=headers)
            
            if static_res.status_code != 200 or not static_res.json():
                print(f"  ⚠️ {city} 靜態資料無回應")
                continue
                
            df_static = pd.DataFrame(static_res.json())[['StationUID', 'BikesCapacity']]
            
            # 抓取動態資料 (目前可用車輛數)
            dynamic_url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Availability/City/{city}?%24format=JSON"
            dynamic_res = requests.get(dynamic_url, headers=headers)
            
            if dynamic_res.status_code != 200 or not dynamic_res.json():
                print(f"  ⚠️ {city} 動態資料無回應")
                continue
                
            df_dynamic = pd.DataFrame(dynamic_res.json())[['StationUID', 'AvailableRentBikes']]
            
            # 合併該縣市的兩張表
            df_merged = pd.merge(df_static, df_dynamic, on='StationUID')
            
            # 將該縣市資料加到全台總表中
            all_merged_df = pd.concat([all_merged_df, df_merged], ignore_index=True)
            
            # 稍微暫停 0.5 秒，避免密集請求被 TDX 伺服器阻擋 (Rate Limit)
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❌ 獲取 {city} 資料時發生錯誤: {e}")

    print(f"✅ 全台資料抓取完畢！共取得 {len(all_merged_df)} 個站點。")
    return all_merged_df

def get_weather_and_aqi():
    """使用中央氣象署 (CWA) 抓取天氣，環境部 (MOENV) 抓取 AQI"""
    print("🌤️ 正在抓取 CWA 天氣與環境部 AQI...")
    
    cwa_key = os.getenv("CWA_API_KEY")
    
    # 預設值 (若 API 失敗時的防呆機制)
    result = {"temperature": 25.0, "precipitation": 0.0, "wind_speed": 3.0, "aqi": 50.0}
    
    # --- 1. 抓取 CWA 天氣 (以局屬高雄站為例) ---
    if not cwa_key:
        print("⚠️ 未設定 CWA_API_KEY，將使用預設天氣。")
    else:
        try:
            # O-A0003-001 為局屬氣象站，包含即時溫度、風速、降雨等觀測資料
            cwa_url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001?Authorization={cwa_key}&format=JSON&StationName=高雄"
            cwa_res = requests.get(cwa_url).json()
            
            stations = cwa_res.get('records', {}).get('Station', [])
            if stations:
                station = stations[0]
                weather_elements = station.get('WeatherElement', {})
                
                # 氣溫與風速
                result["temperature"] = float(weather_elements.get('AirTemperature', result["temperature"]))
                result["wind_speed"] = float(weather_elements.get('WindSpeed', result["wind_speed"]))
                
                # 降雨量 (氣象署對於微量降雨會標示為 'T'，儀器故障為 '-99.0'，需做防呆)
                precip = weather_elements.get('Now', {}).get('Precipitation', 0.0)
                if str(precip) in ['-99.0', '-99', 'T']:
                    result["precipitation"] = 0.0
                else:
                    result["precipitation"] = float(precip)
        except Exception as e:
            print(f"⚠️ CWA 天氣 API 抓取失敗，使用預設值。錯誤: {e}")

    # --- 2. 抓取環境部 AQI (使用環境部開放資料平台公用金鑰) ---
        try:
        # 取得全台 AQI 測站最新資料
            moenv_key = os.getenv("MOENV_API_KEY")
            if not moenv_key:
                print("⚠️ 未設定 MOENV_API_KEY，跳過環境部 AQI 抓取。")
                raise ValueError("No API Key")
        # 使用您專屬的環境變數金鑰
            moenv_url = f"https://data.moenv.gov.tw/api/v2/aqx_p_432?api_key={moenv_key}&limit=1000&sort=ImportDate%20desc&format=JSON"
        
            response = requests.get(moenv_url)
        
        # 🛡️ 防呆機制：先檢查伺服器有沒有正常回覆 (Status Code 200)
            if response.status_code != 200:
                print(f"⚠️ 環境部 API 伺服器異常 (狀態碼: {response.status_code})")
                raise ValueError("Server Error")
            
            aqi_res = response.json()
            # 🛡️ 升級版防彈機制：自動適應政府 API 隨機變更格式
            if isinstance(aqi_res, dict):
                records = aqi_res.get('records', [])
            elif isinstance(aqi_res, list):
                records = aqi_res  # 如果它直接給列表，就直接把整個列表收下
            else:
                records = []
            # 篩選出高雄市的測站資料
            kh_records = [r for r in records if isinstance(r, dict) and r.get('county') == '高雄市']
        
            if kh_records:
            # 抓取高雄市第一個有數值的測站 AQI
                for record in kh_records:
                    aqi_val = record.get('aqi')
                    if aqi_val and str(aqi_val).isdigit():
                        result["aqi"] = float(aqi_val)
                        break
        except Exception as e:
            print(f"⚠️ 環境部 AQI 抓取失敗 ({e})，自動切換為 Open-Meteo 備用方案...")
        # 🛡️ 備用方案：如果環境部掛掉，無縫接軌用回免金鑰的 Open-Meteo
            try:
                lat, lon = 22.6273, 120.3014
                aqi_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=european_aqi"
                aqi_data = requests.get(aqi_url).json()['current']
                result["aqi"] = aqi_data['european_aqi']
                print(f"✅ 成功啟用備用方案獲取 AQI: {result['aqi']}")
            except:
                print("❌ 所有 AQI 來源皆失敗，使用預設值 50.0")

        return result

# ==========================================
# 2. 主執行邏輯：收集與上傳
# ==========================================

def collect_and_store():
    print(f"🚀 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 開始執行資料收集任務...")
    
    # --- 步驟 A：抓取資料 ---
    df_youbike = get_tdx_data()
    weather_info = get_weather_and_aqi()
    
    # --- 步驟 B：生成時間與環境特徵 ---
    now = datetime.now()
    hour = now.hour
    day_of_week = now.weekday()
    is_weekend = 1 if day_of_week >= 5 else 0
    month = now.month
    
    # 簡單的假日判斷 (實務上可串接行政院人事行政總處 API，這裡先用週末代替)
    is_holiday = is_weekend 

    print("⚙️ 正在整理資料格式以符合 Supabase 結構...")
    records_to_insert = []
    
    for _, row in df_youbike.iterrows():
        record = {
            "station_uid": row['StationUID'],
            "hour": hour,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "month": month,
            "is_holiday": is_holiday,
            "temperature": weather_info['temperature'],
            "precipitation": weather_info['precipitation'],
            "wind_speed": weather_info['wind_speed'],
            "aqi": weather_info['aqi'],
            "dist_to_mrt": 0.0, # 未來可在資料庫透過 SQL 計算，收集器先放 0
            "station_capacity": int(row['BikesCapacity']),
            "bikes_1h_ago": 0,  # 訓練模型時再用 pandas 的 shift() 推算，收集器先放 0
            "available_rent_bikes": int(row['AvailableRentBikes'])
        }
        records_to_insert.append(record)

    # --- 步驟 C：連線 Supabase 並分批寫入 ---
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        raise ValueError("❌ 找不到 Supabase 金鑰，請檢查環境變數。")

    supabase: Client = create_client(supabase_url, supabase_key)
    
    # 分批上傳 (Batch Insert)，每次 500 筆，避免封包過大
    batch_size = 500
    total_records = len(records_to_insert)
    print(f"📦 準備將 {total_records} 筆資料寫入 Supabase...")

    for i in range(0, total_records, batch_size):
        batch = records_to_insert[i:i + batch_size]
        try:
            supabase.table("youbike_history").insert(batch).execute()
            print(f"✅ 成功寫入第 {i+1} 到 {min(i+batch_size, total_records)} 筆資料。")
            time.sleep(1) # 稍微暫停 1 秒，對資料庫溫柔一點
        except Exception as e:
            print(f"❌ 寫入失敗 (批次 {i}): {e}")

    print("🎉 資料收集與上傳任務圓滿完成！")

if __name__ == "__main__":
    collect_and_store()