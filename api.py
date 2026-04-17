from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import pandas as pd

app = FastAPI(title="YouBike 智慧預測 API")

# 載入模型 (Render 啟動時會讀取最新的 pkl)
model = joblib.load('youbike_model.pkl')

# 🌟 依照您的新特徵，定義 API 接收的資料格式
class PredictionFeatures(BaseModel):
    Hour: int
    DayOfWeek: int
    IsWeekend: int
    Month: int
    Is_Holiday: int
    Temperature: float
    Precipitation: float
    WindSpeed: float
    AQI: float
    Dist_to_MRT: float
    Station_Capacity: int
    Bikes_1h_ago: int

@app.post("/predict")
def predict_bikes(features: PredictionFeatures):
    # 1. 將收到的 API 資料轉換為 DataFrame
    input_data = pd.DataFrame([features.dict()])
    
    # 2. 進行預測
    prediction = model.predict(input_data)[0]
    
    # 3. 回傳結果 (確保不能有負數車輛)
    return {"predicted_bikes": max(0, round(prediction))}

# 供 Render 檢查服務是否存活
@app.get("/")
def health_check():
    return {"status": "API is running!"}