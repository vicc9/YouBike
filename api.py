import os
import requests
import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI(title="YouBike 智慧預測 API")

MODEL_PATH = 'youbike_model.pkl'
SUPABASE_URL = os.environ.get("SUPABASE_URL")
MODEL_URL = f"{SUPABASE_URL}/storage/v1/object/public/models/{MODEL_PATH}"

def download_model():
    print(f"⏳ 正在從雲端下載最新模型: {MODEL_URL}")
    try:
        response = requests.get(MODEL_URL)
        if response.status_code == 200:
            with open(MODEL_PATH, "wb") as f:
                f.write(response.content)
            print("✅ 模型下載完成！")
        else:
            print(f"⚠️ 下載失敗 (狀態碼: {response.status_code})，將嘗試載入本地舊版模型。")
    except Exception as e:
        print(f"❌ 下載過程發生錯誤: {e}")

download_model()

if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
else:
    model = None
    print("❌ 錯誤：找不到模型檔案，API 將無法運作。")

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
    target_minutes: int  # 🌟 新增這個特徵接收欄位
    
@app.post("/predict")
def predict_bikes(features: List[PredictionFeatures]):
    if model is None:
        return {"error": "Model is not loaded."}
        
    input_data = pd.DataFrame([f.dict() for f in features])
    predictions = model.predict(input_data)
    final_results = [max(0, int(round(p))) for p in predictions]
    
    return {"predictions": final_results}

@app.get("/")
def health_check():
    return {
        "status": "API is running!",
        "model_loaded": model is not None
    }