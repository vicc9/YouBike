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
    print("🔄 開始執行全台模型重訓機制 (動態時間預測版)...")
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        print("❌ 找不到 Supabase 參數，請檢查 .env 檔案！")
        return
        
    supabase: Client = create_client(supabase_url, supabase_key)
    
    print("📥 正在從資料庫分批下載全台歷史數據...")
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
            break  
        offset += limit
        
    df_history = pd.DataFrame(all_data)
    
    if df_history.empty:
        print("⚠️ 資料庫為空，無法訓練模型。")
        return
        
    print(f"✅ 成功下載 {len(df_history)} 筆全台歷史資料！")

    print("⚙️ 正在處理特徵矩陣與多時間維度切片...")
    df_history.fillna({
        'dist_to_mrt': 99999,  
        'wind_speed': df_history.get('wind_speed', pd.Series([0])).mean(),
        'aqi': df_history.get('aqi', pd.Series([50])).mean(),
        'temperature': 25,
        'precipitation': 0,
        'station_capacity': 15,
    }, inplace=True)

    # 1. 確保依照「站點 ID」和「時間」進行排序
    if 'created_at' in df_history.columns:
        df_history['created_at'] = pd.to_datetime(df_history['created_at'])
        df_history.sort_values(by=['station_uid', 'created_at'], inplace=True)
    else:
        df_history.sort_values(by=['station_uid'], inplace=True)
    
    # 🌟【核心升級】擴增訓練資料，建立 5, 10, 15, 20 分鐘的預測目標
    dfs = []
    shifts_and_mins = [(1, 5), (2, 10), (3, 15), (4, 20)] # 假設資料每 5 分鐘抓取一次
    
    for shift_val, target_mins in shifts_and_mins:
        df_temp = df_history.copy()
        # 取得 N 分鐘後的車位數
        df_temp['target_bikes'] = df_temp.groupby('station_uid')['available_rent_bikes'].shift(-shift_val)
        # 標記這筆資料是要預測多久以後
        df_temp['target_minutes'] = target_mins
        dfs.append(df_temp)
        
    # 將所有不同時間差的資料合併成一張大表
    df_combined = pd.concat(dfs)
    df_combined.dropna(subset=['target_bikes'], inplace=True)
    df_combined['bikes_1h_ago'] = df_combined['available_rent_bikes']

    # 2. 特徵工程 (加入 target_minutes)
    X = df_combined[[
        'hour', 'day_of_week', 'is_weekend', 'month', 'is_holiday', 
        'temperature', 'precipitation', 'wind_speed', 'aqi',      
        'dist_to_mrt', 'station_capacity',                        
        'bikes_1h_ago',
        'target_minutes' # 🆕 讓模型知道現在是要預測幾分鐘後
    ]]
    
    y = df_combined['target_bikes']

    # 3. 切分訓練集與測試集
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 4. 建立並訓練模型
    print("🧠 正在訓練 Histogram-based Gradient Boosting 模型...")
    model = HistGradientBoostingRegressor(
        max_iter=60,       
        max_depth=5,       
        max_leaf_nodes=15, 
        random_state=42
    ) 
    model.fit(X_train, y_train)

    # 5. 評估模型表現
    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    print(f"📊 模型訓練完成！全台平均誤差為: {mae:.2f} 輛車")

    # 6. 儲存模型
    joblib.dump(model, 'youbike_model.pkl', compress=9)
    print("✅ 全台模型已成功更新並儲存為 'youbike_model.pkl'")

if __name__ == "__main__":
    retrain_model()