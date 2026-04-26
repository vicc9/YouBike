import os
import requests
import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI(title="YouBike 智慧預測 API")

# --- 方案 C：模型下載邏輯 ---
MODEL_PATH = 'youbike_model.pkl'
# 請確保您在 Render 的 Environment Variables 設定了 SUPABASE_URL
SUPABASE_URL = os.environ.get("SUPABASE_URL")
# 假設您的 Bucket 名稱叫 'models'，檔案叫 'youbike_model.pkl'
MODEL_URL = f"{SUPABASE_URL}/storage/v1/object/public/models/{MODEL_PATH}"

def download_model():
    """啟動時從 Supabase 下載模型"""
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

# 1. 執行下載
download_model()

# 2. 載入模型 (現在確保硬碟裡已經有檔案了)
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
else:
    # 預防萬一連本地都沒有模型
    model = None
    print("❌ 錯誤：找不到模型檔案，API 將無法運作。")

# --- API 定義區 ---

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
def predict_bikes(features: List[PredictionFeatures]):
    if model is None:
        return {"error": "Model is not loaded."}
        
    # 1. 將整串 API 資料轉換為 DataFrame
    input_data = pd.DataFrame([f.dict() for f in features])
    
    # 2. 進行批量預測
    predictions = model.predict(input_data)
    
    # 3. 確保預測結果不為負數，並轉成整數
    final_results = [max(0, int(round(p))) for p in predictions]
    
    # 🌟 回傳結果
    return {"predictions": final_results}

@app.get("/")
def health_check():
    return {
        "status": "API is running!",
        "model_loaded": model is not None
    }