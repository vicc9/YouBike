from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import pandas as pd
from typing import List  # 🌟 必須引入 List 來處理多筆資料

app = FastAPI(title="YouBike 智慧預測 API")

# 載入模型
model = joblib.load('youbike_model.pkl')

# 🌟 修正欄位名稱，使其與 app.py 的小寫定義完全一致
class PredictionFeatures(BaseModel):
    hour: int
    day_of_week: int
    is_weekend: int
    month: int
    is_holiday: int
    temperature: float
    precipitation: float
    wind_speed: float
    aqi: float
    dist_to_mrt: float
    station_capacity: int
    bikes_1h_ago: int

@app.post("/predict")
def predict_bikes(features: List[PredictionFeatures]):  # 🌟 這裡改成接收 List
    # 1. 將整串 API 資料轉換為 DataFrame (批量處理效率才高)
    input_data = pd.DataFrame([f.dict() for f in features])
    
    # 2. 進行批量預測
    predictions = model.predict(input_data)
    
    # 3. 確保預測結果不為負數，並轉成整數
    final_results = [max(0, int(round(p))) for p in predictions]
    
    # 🌟 這裡的回傳 Key 必須叫 "predictions"，以對應 app.py
    return {"predictions": final_results}

@app.get("/")
def health_check():
    return {"status": "API is running!"}