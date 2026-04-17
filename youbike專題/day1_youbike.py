import requests
import pandas as pd
import os
from dotenv import load_dotenv
# 告訴 Python 去尋找並載入旁邊的 .env 檔案
load_dotenv()

# 透過 os.getenv('變數名稱') 把金鑰偷偷拿出來用
CLIENT_ID = os.getenv('TDX_CLIENT_ID')
CLIENT_SECRET = os.getenv('TDX_CLIENT_SECRET')

def get_tdx_token():
    token_url = 'https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token'
    data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    response = requests.post(token_url, data=data)
    return response.json().get('access_token')

def get_station_info(token, city="Kaohsiung"):
    """獲取 YouBike 站點的靜態基本資料 (包含經緯度與站名)"""
    url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Station/City/{city}?%24format=JSON"
    headers = {'authorization': f'Bearer {token}'}
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200:
        df = pd.DataFrame(res.json())
        df['StationPositionLat'] = df['StationPosition'].apply(lambda x: x['PositionLat'])
        df['StationPositionLon'] = df['StationPosition'].apply(lambda x: x['PositionLon'])
        return df[['StationUID', 'StationName', 'StationPositionLat', 'StationPositionLon']]
    else:
        print(f"🚨 靜態資料 API 發生錯誤！狀態碼：{res.status_code}")
        return pd.DataFrame()

def get_youbike_data(token, city="Kaohsiung"):
    """獲取 YouBike 站點的即時動態車位資料"""
    url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Availability/City/{city}?%24format=JSON"
    headers = {'authorization': f'Bearer {token}'}
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200:
        df = pd.DataFrame(res.json())
        return df[['StationUID', 'AvailableRentBikes', 'AvailableReturnBikes']]
    else:
        print(f"🚨 動態資料 API 發生錯誤！狀態碼：{res.status_code}")
        return pd.DataFrame()
        
if __name__ == "__main__":
    token = get_tdx_token()
    if token:
        df_ubike = get_youbike_data(token)
        print("成功抓取 YouBike 資料，前 5 筆：")
        print(df_ubike.head())