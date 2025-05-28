import requests
from datetime import datetime, timedelta
import json
from typing import List, Dict, Any, Optional
from models import SolarForecast, ForecastRequest
from dateutil.parser import parse
import math


class SolcastAPI:
    """Solcast APIとの通信を処理するクラス"""
    BASE_URL = "https://api.solcast.com.au"
    
    @staticmethod
    def get_forecast(request: ForecastRequest) -> List[SolarForecast]:
        """
        指定された座標の予測データを取得する
        """
        # 最新のエンドポイントを使用
        forecast_url = f"{SolcastAPI.BASE_URL}/data/forecast/radiation_and_weather"
        
        # APIドキュメントに従ったパラメータ
        params = {
            "latitude": request.latitude,
            "longitude": request.longitude,
            "hours": request.hours,
            "format": "json",
            "api_key": request.api_key
        }
        
        # 間隔パラメータを追加
        if request.interval != 30:  # デフォルト値と異なる場合のみ
            params["period"] = f"PT{request.interval}M"
    
        # パネルパラメータを追加
        if request.array_type:
            params["array_type"] = request.array_type
        
            if request.array_type == "fixed" and request.tilt is not None:
                params["tilt"] = request.tilt
                
            if request.azimuth is not None:
                params["azimuth"] = request.azimuth
    
        # 特定の日時が指定されている場合
        # 注意: start_dateパラメータを使わないようにする
        # 代わりに後でフィルタリングする
        
        try:
            print(f"予測データ取得中: {forecast_url}")
            response = requests.get(forecast_url, params=params)
            print(f"レスポンスステータス: {response.status_code}")
            
            if response.status_code == 429:
                print("レート制限に達しました。しばらく待ってから再試行してください。")
                return []
                
            if response.status_code != 200:
                print(f"APIエラー: {response.status_code} - {response.text}")
                return []
                
            response.raise_for_status()
            data = response.json()
            
            # APIからのレスポンス構造をデバッグ出力
            if "forecasts" in data and data["forecasts"]:
                first_item = data["forecasts"][0]
                print(f"最初の予測データの利用可能なフィールド: {list(first_item.keys())}")
            
            # データの整形と太陽位置の計算
            # ソーラーカーモードの場合の処理を追加
            is_solar_car = getattr(request, 'is_solar_car', False)
            solar_car_tilt = getattr(request, 'solar_car_tilt', 10.0)
            solar_car_direction = getattr(request, 'solar_car_direction', 180.0)
            
            return SolcastAPI._process_forecast_data(
                data,
                request.latitude,
                request.longitude,
                request.timezone_offset,
                request.specific_date,
                is_solar_car,
                solar_car_tilt,
                solar_car_direction
            )
            
        except requests.RequestException as e:
            print(f"API通信エラー: {str(e)}")
            return []
    
    @staticmethod
    def _calculate_sun_position(date_time: datetime, latitude: float, longitude: float) -> Dict[str, float]:
        """
        特定の日時と位置における太陽位置（天頂角と方位角）を計算する
        簡易計算式を使用
        """
        # 日付から通算日を計算
        day_of_year = date_time.timetuple().tm_yday
        
        # 時間を小数で表現（時 + 分/60 + 秒/3600）
        hour = date_time.hour + date_time.minute/60 + date_time.second/3600
        
        # 太陽赤緯の計算
        delta = 23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365))
        
        # 地方時と太陽時の補正（簡易版）
        time_correction = 4 * longitude  # 経度1度あたり4分の時差
        solar_time = hour + time_correction / 60
        
        # 時角の計算（15度/時間）
        hour_angle = 15 * (solar_time - 12)
        
        # 天頂角の計算
        lat_rad = math.radians(latitude)
        delta_rad = math.radians(delta)
        hour_angle_rad = math.radians(hour_angle)
        
        cos_zenith = (math.sin(lat_rad) * math.sin(delta_rad) + 
                    math.cos(lat_rad) * math.cos(delta_rad) * math.cos(hour_angle_rad))
        zenith = math.degrees(math.acos(max(min(cos_zenith, 1.0), -1.0)))
        
        # 方位角の計算
        sin_azimuth = -math.cos(delta_rad) * math.sin(hour_angle_rad) / math.sin(math.radians(zenith))
        cos_azimuth = (math.sin(delta_rad) - math.sin(lat_rad) * math.cos(math.radians(zenith))) / (
                    math.cos(lat_rad) * math.sin(math.radians(zenith)))
        
        # 方位角の調整
        if sin_azimuth >= 0 and cos_azimuth >= 0:
            azimuth = math.degrees(math.asin(max(min(sin_azimuth, 1.0), -1.0)))
        elif sin_azimuth >= 0 and cos_azimuth < 0:
            azimuth = 180 - math.degrees(math.asin(max(min(sin_azimuth, 1.0), -1.0)))
        elif sin_azimuth < 0 and cos_azimuth < 0:
            azimuth = 180 - math.degrees(math.asin(max(min(sin_azimuth, 1.0), -1.0)))
        else:
            azimuth = 360 + math.degrees(math.asin(max(min(sin_azimuth, 1.0), -1.0)))
        
        return {"zenith": zenith, "azimuth": azimuth}
    
    @staticmethod
    def _calculate_gti_for_solar_car(ghi, dni, zenith, azimuth, tilt, car_direction):
        """ソーラーカー用のGTI(全天傾斜日射量)を計算する"""
        # ラジアンに変換
        zenith_rad = math.radians(zenith)
        azimuth_rad = math.radians(azimuth)
        tilt_rad = math.radians(tilt)
        car_direction_rad = math.radians(car_direction)
        
        # 太陽光の入射角を計算（パネル法線と太陽光の角度）
        cos_incidence = (math.cos(tilt_rad) * math.cos(zenith_rad) + 
                         math.sin(tilt_rad) * math.sin(zenith_rad) * 
                         math.cos(azimuth_rad - car_direction_rad))
        
        # 直達成分（入射角が90度以上なら0）
        beam = dni * max(0, cos_incidence)
        
        # 散乱成分（簡易等方性モデル）
        diffuse = (ghi - dni * math.cos(zenith_rad)) * (1 + math.cos(tilt_rad)) / 2
        if diffuse < 0:
            diffuse = 0
        
        # 地面反射成分（アルベド=0.2と仮定）
        albedo = 0.2
        reflected = ghi * albedo * (1 - math.cos(tilt_rad)) / 2
        
        # ソーラーカー特有の補正（走行中の揺れによる損失など）
        car_correction = 0.95
        
        # 合計GTI
        gti = (beam + diffuse + reflected) * car_correction
        
        return gti

    @staticmethod
    def _process_forecast_data(
        data: Dict[str, Any],
        latitude: float,
        longitude: float,
        timezone_offset: int = 9,
        specific_date: Optional[datetime] = None,
        is_solar_car: bool = False,
        solar_car_tilt: float = 10.0,
        solar_car_direction: float = 180.0
    ) -> List[SolarForecast]:
        """
        APIから取得したデータを処理して予測データリストを作成する
        """
        forecasts = []
        
        # APIのレスポンス構造に合わせて処理
        forecast_items = data.get("forecasts", [])
        
        if not forecast_items:
            print("予測データがありません")
            return []
        
        # 最初のアイテムの詳細をデバッグ出力
        if forecast_items:
            first_item = forecast_items[0]
            print(f"最初の予測データの詳細:")
            for key, value in first_item.items():
                print(f"  {key}: {value}")
        
        all_forecasts = []
        
        for item in forecast_items:
            # 時間の解析
            time_str = item.get("period_end")
            if not time_str:
                continue
            
            # UTCの時刻をパース
            time_dt = parse(time_str)
            
            # 指定されたタイムゾーンに変換
            tz_offset = timedelta(hours=timezone_offset)
            local_time_dt = time_dt + tz_offset
            
            # 太陽位置の計算
            sun_position = SolcastAPI._calculate_sun_position(local_time_dt, latitude, longitude)
            zenith = sun_position["zenith"]
            azimuth = sun_position["azimuth"]
            
            # GTIのデータチェック
            gti = item.get("gti", 0.0)
            gti_valid = "gti" in item and item["gti"] is not None
            
            # ソーラーカーモードの場合は独自のGTI計算を行う
            if is_solar_car:
                ghi = item.get("ghi", 0)
                dni = item.get("dni", 0)
                # 太陽位置が計算されていることを確認
                if zenith is not None and azimuth is not None:
                    gti = SolcastAPI._calculate_gti_for_solar_car(
                        ghi, dni, zenith, azimuth, solar_car_tilt, solar_car_direction
                    )
                    gti_valid = True
            
            # 予測データの作成 - APIドキュメントのフィールド名を使用
            forecast = SolarForecast(
                time=local_time_dt,
                cloud_opacity=item.get("cloud_opacity", 0),  # クラウドの不透明度
                wind_speed=item.get("wind_speed_10m", 0),    # 10m高さの風速
                wind_direction=item.get("wind_direction_10m", 0),  # 10m高さの風向
                zenith=zenith,  # 太陽天頂角
                azimuth=azimuth,  # 太陽方位角
                ghi=item.get("ghi", 0),  # 全天日射量
                gti=gti,  # 傾斜面日射量 
                forecast_radiation=item.get("dni", 0),  # 直達日射量
                gti_valid=gti_valid,  # GTIが有効かどうか
                air_temp=item.get("air_temp")  # 気温
            )
            all_forecasts.append(forecast)
        
        # 特定の日時が指定されている場合は、その日時に最も近いデータを返す
        if specific_date:
            # 特定日時をタイムゾーン考慮して処理
            target_date = specific_date
            print(f"指定された日時: {target_date}")
            
            # 日付が一致するデータだけをフィルタリング
            date_filtered = [f for f in all_forecasts if (
                f.time.year == target_date.year and 
                f.time.month == target_date.month and 
                f.time.day == target_date.day
            )]
            
            if date_filtered:
                # 時間が近いものを優先的に選択
                date_filtered.sort(key=lambda x: abs((x.time.hour * 60 + x.time.minute) - 
                                                    (target_date.hour * 60 + target_date.minute)))
                forecasts = date_filtered
            else:
                # 日付一致のデータがない場合は最も時間的に近いデータを返す
                all_forecasts.sort(key=lambda x: abs((x.time - target_date).total_seconds()))
                forecasts = all_forecasts[:24]  # 最大24件を返す
        else:
            forecasts = all_forecasts
    
        return sorted(forecasts, key=lambda x: x.time)