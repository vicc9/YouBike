import folium

def create_map(df_stations, my_lat, my_lon, mode="rent"):
    """
    建立地圖。
    my_lat, my_lon: 使用者目前定位或搜尋目標的座標 (地圖真正的中心)。
    df_stations: 要顯示在畫面的站點資料。
    """
    
    # 1. 決定縮放級別 (Zoom Level)
    # 如果搜尋後附近沒什麼站點，縮放級別 15 (看街道)；站點多則 16 (看建築)
    zoom = 15 if len(df_stations) < 5 else 16

    # 2. 初始化地圖：直接以「您的位置」為中心
    m = folium.Map(
        location=[my_lat, my_lon], 
        zoom_start=zoom,
        control_scale=True # 顯示比例尺，讓使用者知道多遠
    )
    
    # 3. 標註「您的位置」 (藍色圖示)
    folium.Marker(
        location=[my_lat, my_lon],
        popup="<b>📍 您在這裡 / 搜尋目標</b>",
        icon=folium.Icon(color="blue", icon="info-sign"),
        z_index_offset=1000 # 確保您的位置標籤在最上層，不被站點擋住
    ).add_to(m)

    # 4. 標註 YouBike 站點
    for _, row in df_stations.iterrows():
        # 安全地處理站點名稱 (處理 TDX 的字典格式)
        station_name = row['StationName']
        if isinstance(station_name, dict) and 'Zh_tw' in station_name:
            name_str = station_name['Zh_tw']
        else:
            name_str = str(station_name)
            
        # 根據不同模式設定數量、彈出文字與圖示顏色
        if mode == "rent":
            # 優先使用預測數值，若無則用即時數值
            amount = row.get('Predicted_Bikes', row.get('AvailableRentBikes', 0))
            popup_text = f"<b>{name_str}</b><br>🚲 預測可借: {int(amount)} 輛"
            if amount < 3: color = 'red'
            elif amount < 10: color = 'orange'
            else: color = 'green'
        else:
            amount = row.get('AvailableReturnBikes', 0)
            popup_text = f"<b>{name_str}</b><br>🅿️ 目前可還空位: {int(amount)} 格"
            if amount < 3: color = 'red'
            elif amount < 10: color = 'orange'
            else: color = 'green'
            
        # 添加站點標記
        folium.Marker(
            location=[row['StationPositionLat'], row['StationPositionLon']],
            popup=popup_text,
            tooltip=name_str, # 滑鼠指過去就顯示名稱
            icon=folium.Icon(color=color, icon='bicycle', prefix='fa' if color != 'red' else 'info-sign')
        ).add_to(m)

    # 💡 邊界優化：如果站點距離太遠，才自動調整邊界
    # 如果您希望地圖「固定」在您的位置，可以註解掉 fit_bounds 這段
    if not df_stations.empty and len(df_stations) > 1:
        # 只在有站點時才調整，但為了保證「您的位置」在畫面中，把中心點也加入計算
        sw = [min(df_stations['StationPositionLat'].min(), my_lat), min(df_stations['StationPositionLon'].min(), my_lon)]
        ne = [max(df_stations['StationPositionLat'].max(), my_lat), max(df_stations['StationPositionLon'].max(), my_lon)]
        # 如果站點距離您的位置超過 2 公里，才縮放邊界，否則維持固定縮放
        m.fit_bounds([sw, ne], padding=(20, 20))
        
    return m