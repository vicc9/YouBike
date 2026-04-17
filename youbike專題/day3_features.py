import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_mock_history_data(days=30, stations=10):
    """生成模擬的 YouBike 歷史借還紀錄以供訓練"""
    np.random.seed(42)
    records = []
    start_time = datetime.now() - timedelta(days=days)
    
    for day in range(days):
        for hour in range(24):
            current_time = start_time + timedelta(days=day, hours=hour)
            # 模擬天氣：白天較熱，偶爾下雨
            temp = 20 + 10 * np.sin(np.pi * hour / 12) + np.random.normal(0, 2)
            rain = np.random.choice([0, 0, 0, 5, 15]) if hour % 4 == 0 else 0
            
            for station_id in range(stations):
                # 模擬借車邏輯：上下班尖峰時間變化大，下雨天借車少
                base_bikes = 15
                if hour in [8, 9, 17, 18]: # 尖峰
                    bikes = np.random.randint(0, 30)
                else:
                    bikes = np.random.randint(5, 25)
                
                if rain > 0: # 下雨天車輛變動小(停在站裡)
                    bikes = np.random.randint(10, 20)
                
                records.append({
                    'StationUID': f"KHH{station_id:04d}",
                    'UpdateTime': current_time,
                    'AvailableRentBikes': bikes,
                    'Temperature': round(temp, 1),
                    'Precipitation': rain
                })
                
    return pd.DataFrame(records)

def prepare_training_data(df):
    """將原始資料轉換為機器學習特徵 (X) 與標籤 (y)"""
    df['UpdateTime'] = pd.to_datetime(df['UpdateTime'])
    df['Hour'] = df['UpdateTime'].dt.hour
    df['DayOfWeek'] = df['UpdateTime'].dt.dayofweek
    df['IsWeekend'] = df['DayOfWeek'].apply(lambda x: 1 if x >= 5 else 0)
    
    features = ['Hour', 'DayOfWeek', 'IsWeekend', 'Temperature', 'Precipitation']
    X = df[features]
    y = df['AvailableRentBikes']
    
    return X, y

if __name__ == "__main__":
    df_history = generate_mock_history_data()
    X, y = prepare_training_data(df_history)
    print("特徵工程完成！X 的前 5 筆：")
    print(X.head())