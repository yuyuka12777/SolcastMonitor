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
        if request.specific_date:
            # UTCに変換
            utc_date = request.specific_date - timedelta(hours=request.timezone_offset)
            params["start_date"] = utc_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
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
            return SolcastAPI._process_forecast_data(
                data,
                request.latitude,
                request.longitude,
                request.timezone_offset,
                request.specific_date
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
    def _process_forecast_data(
        data: Dict[str, Any],
        latitude: float,
        longitude: float,
        timezone_offset: int = 9,
        specific_date: Optional[datetime] = None
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
            
            # 特定の時刻が指定されている場合、その時刻のデータのみ抽出
            if specific_date:
                # 日付と時間が一致するか確認（分まで一致）
                if (local_time_dt.year != specific_date.year or 
                    local_time_dt.month != specific_date.month or 
                    local_time_dt.day != specific_date.day or 
                    local_time_dt.hour != specific_date.hour):
                    continue
        
            # APIレスポンスから直接zenithとazimuthを取得しようとする
            # 利用できない場合は計算値を使用
            zenith = item.get("zenith")
            azimuth = item.get("azimuth")
            
            if zenith is None or azimuth is None:
                # 太陽位置の計算
                sun_position = SolcastAPI._calculate_sun_position(local_time_dt, latitude, longitude)
                zenith = sun_position["zenith"]
                azimuth = sun_position["azimuth"]
            
            # GTIのデータチェック
            gti = item.get("gti", 0.0)
            gti_valid = "gti" in item and item["gti"] is not None
            
            # 気温データの取得
            air_temp = item.get("air_temp")
            
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
                air_temp=air_temp  # 気温
            )
            forecasts.append(forecast)
    
        return sorted(forecasts, key=lambda x: x.time)