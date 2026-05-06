import requests
import os
from dotenv import load_dotenv
import urllib3

load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 給資料庫爬蟲用的舊版函式 (保持不變) ---
def get_current_weather():
    """獲取氣象署即時天氣資料 (預設單一城市)供資料庫使用"""
    api_key = os.getenv('CWA_API_KEY')
    if not api_key:
        return {'Weather': '晴', 'Temperature': 25.0, 'Precipitation': 0.0}
        
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={api_key}&format=JSON"
    try:
        response = requests.get(url, verify=False)
        data = response.json()
        stations = data['records']['Station']
        for station in stations:
            if station.get('GeoInfo', {}).get('CountyName') == '高雄市':
                temp = station['WeatherElement']['AirTemperature']
                weather = station['WeatherElement']['Weather']
                return {
                    'Weather': weather, 
                    'Temperature': float(temp),
                    'Precipitation': 0.0
                }
        return {'Weather': '晴', 'Temperature': 25.0, 'Precipitation': 0.0}
    except Exception:
        return {'Weather': '晴', 'Temperature': 25.0, 'Precipitation': 0.0}

# --- 🆕 給 app.py 全台預測用的新函式 ---
def get_all_cities_weather():
    """獲取全台各縣市氣象資料，並映射為英文縣市名稱供模型比對"""
    api_key = os.getenv('CWA_API_KEY')
    default_weather = {'Weather': '晴', 'Temperature': 25.0, 'Precipitation': 0.0}
    
    # 建立氣象署中文縣市名與 TDX 英文縣市名的對應表
    city_mapping = {
        '臺北市': 'Taipei', '新北市': 'NewTaipei', '桃園市': 'Taoyuan',
        '新竹市': 'Hsinchu', '新竹縣': 'HsinchuCounty', '苗栗縣': 'MiaoliCounty',
        '臺中市': 'Taichung', '嘉義市': 'Chiayi', '嘉義縣': 'ChiayiCounty',
        '臺南市': 'Tainan', '高雄市': 'Kaohsiung', '屏東縣': 'PingtungCounty'
    }
    
    city_weather_dict = {eng_city: default_weather.copy() for eng_city in city_mapping.values()}
    
    if not api_key:
        return city_weather_dict

    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={api_key}&format=JSON"
    try:
        response = requests.get(url, verify=False)
        data = response.json()
        stations = data['records']['Station']
        
        # 暫存每個縣市找到的第一個測站資料
        for station in stations:
            county_zh = station.get('GeoInfo', {}).get('CountyName')
            if county_zh in city_mapping:
                eng_city = city_mapping[county_zh]
                
                # 如果該縣市還是預設值，就用找到的測站資料覆蓋
                if city_weather_dict[eng_city]['Temperature'] == 25.0:
                    temp = station['WeatherElement']['AirTemperature']
                    # 防呆：確保溫度不是負數異常值 (如 -99)
                    if float(temp) > -10: 
                        city_weather_dict[eng_city]['Temperature'] = float(temp)
                        city_weather_dict[eng_city]['Weather'] = station['WeatherElement']['Weather']
                        
        return city_weather_dict
    except Exception as e:
        print(f"全台天氣獲取失敗: {e}")
        return city_weather_dict

if __name__ == "__main__":
    weather_dict = get_all_cities_weather()
    print(f"全台天氣特徵：{weather_dict}")