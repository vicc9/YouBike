import os
import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from supabase import create_client, Client # 🌟 新增：引入 supabase SDK

app = FastAPI(title="YouBike 智慧預測 API")

# 🌟 設定檔案路徑與 Supabase 環境變數
MODEL_PATH = 'youbike_model.pkl'
BUCKET_NAME = 'models'
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") # 🔐 改用私密管理員金鑰

def download_model():
    print("⏳ 正在透過私密權限從 Supabase 下載模型...")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ 錯誤：缺少 SUPABASE_URL 或 SUPABASE_SERVICE_KEY 環境變數，無法連線。")
        return False
        
    try:
        # 初始化 Supabase 客戶端
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 透過 SDK 直接從 Bucket 下載檔案的二進位內容
        res = supabase.storage.from_(BUCKET_NAME).download(MODEL_PATH)
        
        # 寫入本地端
        with open(MODEL_PATH, "wb") as f:
            f.write(res)
            
        print("✅ 模型私有下載成功！")
        return True
    except Exception as e:
        print(f"❌ 私有下載過程發生錯誤: {e}")
        return False

# 執行下載
download_model()

# 載入模型
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
    print("✅ 模型已成功載入記憶體！")
else:
    model = None
    print("❌ 錯誤：找不到模型檔案，API 將無法運作。")

# 🌟 請求資料結構
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
    target_minutes: int  
    current_bikes: int   # 🌟 接收當下車輛數，用於計算最終結果
    
@app.post("/predict")
def predict_bikes(features: List[PredictionFeatures]):
    if model is None:
        return {"error": "Model is not loaded."}
        
    # 1. 將所有輸入特徵轉換為 DataFrame
    df_input = pd.DataFrame([f.dict() for f in features])
    
    # 2. 🌟 嚴格篩選模型「訓練時」真正使用的欄位
    # 必須排除掉 current_bikes，否則模型會因為沒看過這個特徵而報錯
    feature_cols = [
        'hour', 'day_of_week', 'is_weekend', 'month', 'is_holiday',
        'temperature', 'precipitation', 'wind_speed', 'aqi',
        'dist_to_mrt', 'station_capacity', 'bikes_1h_ago', 'target_minutes'
    ]
    model_input = df_input[feature_cols]
    
    # 3. 進行預測：此時得到的 predictions 是「變化量 (Delta)」 (例如：+2.3 或 -1.5)
    deltas = model.predict(model_input)
    
    # 4. 🌟 計算最終結果並執行上下限防呆
    final_results = []
    for i, delta in enumerate(deltas):
        current = df_input.loc[i, 'current_bikes']
        capacity = df_input.loc[i, 'station_capacity']
        
        # 計算：現在數量 + 預測變化量 (並四捨五入)
        final_bikes = int(round(current + delta))
        
        # 防呆機制：確保車輛不會是負數，也不會大於該站的車柱總數
        final_bikes = max(0, min(capacity, final_bikes))
        
        final_results.append(final_bikes)
        
    return {"predictions": final_results}

@app.get("/")
def health_check():
    return {
        "status": "API is running!",
        "model_loaded": model is not None
    }