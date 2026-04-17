import os
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib
from supabase import create_client, Client
from dotenv import load_dotenv
load_dotenv()

def retrain_model():
    print("🔄 開始執行模型重訓機制...")
    
    # 1. 從 Supabase 資料庫下載歷史資料
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    supabase: Client = create_client(supabase_url, supabase_key)
    
    print("📥 正在下載歷史數據...")
    # 實務上會用語法限制下載最近幾個月的資料，避免記憶體爆掉
    response = supabase.table("youbike_history").select("*").execute()
    df_history = pd.DataFrame(response.data)
    
    if df_history.empty:
        print("⚠️ 資料庫為空，無法訓練模型。")
        return

    # 2. 特徵工程 (完全依照您的全新設計)
    print("⚙️ 正在處理特徵矩陣...")
    X = df_history[[
        'hour', 'day_of_week', 'is_weekend', 'month', 'is_holiday', # 時間特徵
        'temperature', 'precipitation', 'wind_speed', 'aqi',      # 天氣特徵
        'dist_to_mrt', 'station_capacity',                       # 地理特徵
        'bikes_1h_ago'                                           # 短期記憶特徵
    ]]
    y = df_history['available_rent_bikes'] # 目標：預測可借車輛數

    # 3. 切分訓練集與測試集
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 4. 建立並訓練 Random Forest 模型
    print("🧠 正在訓練隨機森林模型 (這可能需要幾分鐘)...")
    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1) # n_jobs=-1 加速運算
    model.fit(X_train, y_train)

    # 5. 評估模型表現
    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    print(f"📊 模型訓練完成！平均誤差為: {mae:.2f} 輛車")

    # 6. 儲存模型並覆蓋舊檔案
    joblib.dump(model, 'youbike_model.pkl')
    print("✅ 模型已成功更新並儲存為 'youbike_model.pkl'")

if __name__ == "__main__":
    retrain_model()