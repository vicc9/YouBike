import requests
import os
from dotenv import load_dotenv
import urllib3

# 告訴 Python 去尋找並載入旁邊的 .env 檔案
load_dotenv()
CWA_API_KEY = os.getenv('CWA_API_KEY')

# 隱藏 SSL 憑證檢查的黃色警告訊息，讓終端機保持乾淨
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_current_weather():
    """獲取氣象署即時天氣資料，並回傳字典格式供模型使用"""
    api_key = os.getenv('CWA_API_KEY')
    if not api_key:
        print("未設定氣象 API 金鑰，使用預設天氣")
        # 💡 這裡補上了 'Precipitation': 0.0
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
                
                # 💡 這裡也補上了 'Precipitation': 0.0
                return {
                    'Weather': weather, 
                    'Temperature': float(temp),
                    'Precipitation': 0.0
                }
                
        # 如果找不到高雄測站，回傳預設值
        return {'Weather': '晴', 'Temperature': 25.0, 'Precipitation': 0.0}
        
    except Exception as e:
        print(f"天氣獲取失敗: {e}，使用預設天氣")
        return {'Weather': '晴', 'Temperature': 25.0, 'Precipitation': 0.0}

if __name__ == "__main__":
    weather = get_current_weather()
    print(f"目前天氣特徵：{weather}")