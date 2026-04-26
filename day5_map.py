import folium

def create_map(df_stations, my_lat, my_lon, mode="rent"):
    """
    建立地圖。
    my_lat, my_lon: 使用者目前定位或搜尋目標的座標 (地圖真正的中心)。
    df_stations: 要顯示在畫面的站點資料。
    """
    # 確保座標為浮點數，避免字串型別造成比對錯誤
    my_lat = float(my_lat)
    my_lon = float(my_lon)

    # 1. 決定縮放級別 (Zoom Level)
    zoom = 15 if len(df_stations) < 5 else 16

    # 2. 初始化地圖
    m = folium.Map(
        location=[my_lat, my_lon], 
        zoom_start=zoom,
        control_scale=True
    )
    
    target_is_station = False

    # 🌟 核心修正：先掃描找出距離 (my_lat, my_lon) 絕對最近的站點 UID
    closest_uid = None
    min_dist = float('inf')
    
    for _, row in df_stations.iterrows():
        lat_diff = abs(float(row['StationPositionLat']) - my_lat)
        lon_diff = abs(float(row['StationPositionLon']) - my_lon)
        # 使用畢氏定理計算直線距離
        dist = (lat_diff**2 + lon_diff**2)**0.5 
        if dist < min_dist:
            min_dist = dist
            closest_uid = row.get('StationUID')

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

        # 🌟 確保只有「唯一最接近，且距離小於閾值」的那一個站點會變成藍色
        is_target = (row.get('StationUID') == closest_uid) and (min_dist < 0.0005)

        if is_target:
            target_is_station = True
            color = 'blue'  # 強制將搜尋的目標站點變成藍色
            popup_text = f"<div style='color:blue; margin-bottom:5px;'><b>📍 您搜尋的站點 / 推薦站點</b></div>{popup_base}"
            z_index = 1000  # 確保它在最上層
            icon_type = 'info-sign'
            icon_prefix = 'glyphicon'
        else:
            popup_text = popup_base
            z_index = 0
            icon_type = 'bicycle'
            icon_prefix = 'fa'

        # 添加站點標記
        folium.Marker(
            location=[float(row['StationPositionLat']), float(row['StationPositionLon'])],
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=name_str,
            icon=folium.Icon(color=color, icon=icon_type, prefix=icon_prefix),
            z_index_offset=z_index
        ).add_to(m)

    # 4. 如果搜尋的目標「不是」任何一個顯示中的站點
    if not target_is_station:
        fallback_text = """
        <b>📍 您搜尋的目標 / 定位</b><br>
        <hr style="margin:5px 0px;">
        <span style='color:gray; font-size:12px;'>
        💡 若您搜尋的是特定 YouBike 站點卻無預測資料，<br>
        代表該站目前可能 <b>無車可借 / 無位可還</b>，<br>
        因此被系統自動過濾隱藏囉！
        </span>
        """
        folium.Marker(
            location=[my_lat, my_lon],
            popup=folium.Popup(fallback_text, max_width=300),
            icon=folium.Icon(color="blue", icon="info-sign"),
            z_index_offset=1000
        ).add_to(m)

    # 5. 邊界優化
    if not df_stations.empty and len(df_stations) > 1:
        sw = [min(df_stations['StationPositionLat'].astype(float).min(), my_lat), 
              min(df_stations['StationPositionLon'].astype(float).min(), my_lon)]
        ne = [max(df_stations['StationPositionLat'].astype(float).max(), my_lat), 
              max(df_stations['StationPositionLon'].astype(float).max(), my_lon)]
        m.fit_bounds([sw, ne], padding=(20, 20))
        
    return m