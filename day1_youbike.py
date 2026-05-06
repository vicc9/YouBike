import requests
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv('TDX_CLIENT_ID')
CLIENT_SECRET = os.getenv('TDX_CLIENT_SECRET')

def get_tdx_token():
    token_url = 'https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token'
    data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    try:
        response = requests.post(token_url, data=data)
        return response.json().get('access_token')
    except:
        return None

def get_station_info(token, city="Kaohsiung"):
    """獲取 YouBike 站點的靜態基本資料 (包含雙北免扣點防護)"""
    # 台北市直連
    if city == "Taipei":
        url = "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
        res = requests.get(url)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df.rename(columns={'sno': 'StationUID', 'sna': 'StationName', 'lat': 'StationPositionLat', 'lng': 'StationPositionLon'}, inplace=True)
            df['StationName'] = df['StationName'].str.replace('YouBike2.0_', '')
            return df[['StationUID', 'StationName', 'StationPositionLat', 'StationPositionLon']]
            
    # 新北市直連
    elif city == "NewTaipei":
        url = "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/json?page=0&size=3000"
        res = requests.get(url)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df.rename(columns={'sno': 'StationUID', 'sna': 'StationName', 'lat': 'StationPositionLat'}, inplace=True)
            df['StationPositionLon'] = df.get('lng', df.get('lon'))
            df['StationName'] = df['StationName'].str.replace('YouBike2.0_', '')
            return df[['StationUID', 'StationName', 'StationPositionLat', 'StationPositionLon']]

    # 其他縣市走 TDX
    url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Station/City/{city}?%24format=JSON"
    headers = {'authorization': f'Bearer {token}'}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        df = pd.DataFrame(res.json())
        df['StationPositionLat'] = df['StationPosition'].apply(lambda x: x['PositionLat'])
        df['StationPositionLon'] = df['StationPosition'].apply(lambda x: x['PositionLon'])
        return df[['StationUID', 'StationName', 'StationPositionLat', 'StationPositionLon']]
    return pd.DataFrame()

def get_youbike_data(token, city="Kaohsiung"):
    """獲取 YouBike 站點的即時動態資料 (包含雙北免扣點防護)"""
    if city == "Taipei":
        url = "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
        res = requests.get(url)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df.rename(columns={'sno': 'StationUID', 'sbi': 'AvailableRentBikes', 'bemp': 'AvailableReturnBikes'}, inplace=True)
            return df[['StationUID', 'AvailableRentBikes', 'AvailableReturnBikes']]
            
    elif city == "NewTaipei":
        url = "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/json?page=0&size=3000"
        res = requests.get(url)
        if res.status_code == 200:
            df = pd.DataFrame(res.json())
            df.rename(columns={'sno': 'StationUID', 'sbi': 'AvailableRentBikes', 'bemp': 'AvailableReturnBikes'}, inplace=True)
            return df[['StationUID', 'AvailableRentBikes', 'AvailableReturnBikes']]

    url = f"https://tdx.transportdata.tw/api/basic/v2/Bike/Availability/City/{city}?%24format=JSON"
    headers = {'authorization': f'Bearer {token}'}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        df = pd.DataFrame(res.json())
        return df[['StationUID', 'AvailableRentBikes', 'AvailableReturnBikes']]
    return pd.DataFrame()

if __name__ == "__main__":
    token = get_tdx_token()
    if token:
        df_ubike = get_youbike_data(token)
        print("成功抓取 YouBike 資料，前 5 筆：")
        print(df_ubike.head())