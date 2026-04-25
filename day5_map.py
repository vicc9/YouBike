import folium

def create_map(df_stations, my_lat, my_lon, mode="rent"):
    """
    建立地圖。
    my_lat, my_lon: 使用者目前定位或搜尋目標的座標 (地圖真正的中心)。
    df_stations: 要顯示在畫面的站點資料。
    """
    
    # 1. 決定縮放級別 (Zoom Level)
    zoom = 15 if len(df_stations) < 5 else 16

    # 2. 初始化地圖
    m = folium.Map(
        location=[my_lat, my_lon], 
        zoom_start=zoom,
        control_scale=True
    )
    
    # 🌟 新增一個旗標，用來紀錄「搜尋的地點是否剛好就是 YouBike 站點」
    target_is_station = False

    # 3. 標註 YouBike 站點
    for _, row in df_stations.iterrows():
        # 安全地處理站點名稱
        station_name = row['StationName']
        if isinstance(station_name, dict) and 'Zh_tw' in station_name:
            name_str = station_name['Zh_tw']
        else:
            name_str = str(station_name)
            
        # 取得數量與基本 popup 內文
        if mode == "rent":
            amount = row.get('Predicted_Bikes', row.get('AvailableRentBikes', 0))
            popup_base = f"<b>{name_str}</b><br>🚲 預測可借: {int(amount)} 輛"
        else:
            amount = row.get('AvailableReturnBikes', 0)
            popup_base = f"<b>{name_str}</b><br>🅿️ 目前可還空位: {int(amount)} 格"

        # 決定顏色
        if amount < 3: color = 'red'
        elif amount < 10: color = 'orange'
        else: color = 'green'

        # 🌟 核心修正：
        # 1. 優先使用 app.py 算好的 Distance_km (距離 < 0.02km / 20公尺 即視為重疊)
        # 2. 放寬經緯度浮點數誤差容忍度到 0.0002
        dist_km = row.get('Distance_km', 999)
        lat_diff = abs(row['StationPositionLat'] - my_lat)
        lon_diff = abs(row['StationPositionLon'] - my_lon)
        
        is_target = (dist_km < 0.02) or (lat_diff < 0.0002 and lon_diff < 0.0002)

        if is_target:
            target_is_station = True
            color = 'blue'  # 強制將搜尋的目標站點變成藍色
            popup_text = f"<div style='color:blue; margin-bottom:5px;'><b>📍 您搜尋的站點</b></div>{popup_base}"
            z_index = 1000  # 確保它在最上層
            icon_type = 'info-sign'
            icon_prefix = 'glyphicon'
        else:
            popup_text = popup_base
            z_index = 0
            icon_type = 'bicycle'
            icon_prefix = 'fa'

        # 添加站點標記 (加上 folium.Popup 確保樣式不會跑版)
        folium.Marker(
            location=[row['StationPositionLat'], row['StationPositionLon']],
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=name_str,
            icon=folium.Icon(color=color, icon=icon_type, prefix=icon_prefix),
            z_index_offset=z_index
        ).add_to(m)

    # 4. 如果搜尋的目標「不是」任何一個站點 (例如只是普通地址)，才加上純藍色定位標籤
    if not target_is_station:
        folium.Marker(
            location=[my_lat, my_lon],
            popup=folium.Popup("<b>📍 您在這裡 / 搜尋目標</b>", max_width=300),
            icon=folium.Icon(color="blue", icon="info-sign"),
            z_index_offset=1000
        ).add_to(m)

    # 5. 邊界優化
    if not df_stations.empty and len(df_stations) > 1:
        sw = [min(df_stations['StationPositionLat'].min(), my_lat), min(df_stations['StationPositionLon'].min(), my_lon)]
        ne = [max(df_stations['StationPositionLat'].max(), my_lat), max(df_stations['StationPositionLon'].max(), my_lon)]
        m.fit_bounds([sw, ne], padding=(20, 20))
        
    return m