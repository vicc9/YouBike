import os
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def retrain_model():
    print("🔄 開始執行全台模型重訓機制...")
    
    # 1. 從 Supabase 資料庫下載歷史資料
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        print("❌ 找不到 Supabase 參數，請檢查 .env 檔案！")
        return
        
    supabase: Client = create_client(supabase_url, supabase_key)
    
    print("📥 正在從資料庫分批下載全台歷史數據 (突破 1000 筆限制)...")
    # --- 🛠️ 修正 1：分批下載全台海量資料 ---
    all_data = []
    limit = 1000
    offset = 0
    
    while True:
        response = supabase.table("youbike_history").select("*").range(offset, offset + limit - 1).execute()
        data = response.data
        if not data:
            break
        all_data.extend(data)
        if len(data) < limit:
            break  # 如果抓到的資料少於 1000 筆，代表抓完了
        offset += limit
        
    df_history = pd.DataFrame(all_data)
    
    if df_history.empty:
        print("⚠️ 資料庫為空，無法訓練模型。")
        return
        
    print(f"✅ 成功下載 {len(df_history)} 筆全台歷史資料！")

    print("⚙️ 正在處理特徵矩陣與缺失值...")
    # --- 🛠️ 修正 2：處理全台資料的缺失值 (NaN) ---
    # 非捷運城市的 dist_to_mrt 會是空值，我們將其補上極大數值 (代表非常遠)
    # 其他氣象資料若缺失，用平均值或預設值填補
    df_history.fillna({
        'dist_to_mrt': 99999,  
        'wind_speed': df_history.get('wind_speed', pd.Series([0])).mean(),
        'aqi': df_history.get('aqi', pd.Series([50])).mean(),
        'temperature': 25,
        'precipitation': 0,
        'station_capacity': 15,
        'bikes_1h_ago': df_history['available_rent_bikes'] # 假設沒資料就先拿當下車數墊檔
    }, inplace=True)

    # 2. 特徵工程
    # --- ⚠️ 修正 3：特徵對齊警告 ---
    # 這裡的 X 特徵必須與 app.py 裡預測時準備的 features DataFrame "欄位名稱"與"數量"完全一致！
    X = df_history[[
        'hour', 'day_of_week', 'is_weekend', 'month', 'is_holiday', 
        'temperature', 'precipitation', 'wind_speed', 'aqi',      
        'dist_to_mrt', 'station_capacity',                        
        'bikes_1h_ago'                                           
    ]]
    y = df_history['available_rent_bikes'] # 目標：預測可借車輛數

    # 3. 切分訓練集與測試集
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 4. 建立並訓練 Random Forest 模型
    print("🧠 正在訓練 Histogram-based Gradient Boosting 模型 (速度更快、檔案極小)...")
    
    # 🌟 2. 改用這個全新的輕量級演算法
    # max_iter=100 類似於原本的 n_estimators
    # max_depth=15 限制深度，進一步壓縮檔案大小
    model = HistGradientBoostingRegressor(
        max_iter=100,
        max_depth=15,
        random_state=42
    ) 
    model.fit(X_train, y_train)

    # 5. 評估模型表現
    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    print(f"📊 模型訓練完成！全台預測平均誤差為: {mae:.2f} 輛車")

    # 6. 儲存模型並覆蓋舊檔案
    joblib.dump(model, 'youbike_model.pkl', compress=9)
    print("✅ 全台模型已成功更新並儲存為 'youbike_model.pkl'")

if __name__ == "__main__":
    retrain_model()