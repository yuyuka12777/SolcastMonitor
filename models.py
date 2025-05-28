from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class SolarForecast:
    """太陽光予測データを格納するクラス"""
    time: datetime
    ghi: float  # 全天日射量-水平面 (W/m^2)
    forecast_radiation: float  # 直達日射量 (W/m^2)
    # 以下はAPIから取得できない場合があるためOptional
    zenith: float  # 太陽天頂角 (度、0=真上、90=地平線)
    azimuth: float  # 太陽方位角 (度、0=北, 90=東, 180=南, 270=西)
    gti: float = 0.0  # 全天傾斜日射量-傾斜面 (W/m^2)
    gti_valid: bool = False  # GTIが有効かどうか
    air_temp: Optional[float] = None  # 気温（摂氏）
    cloud_opacity: float = 0.0  # 雲の不透明度 (0-1)
    wind_speed: float = 0.0  # 10m高さでの風速 (m/s)
    wind_direction: float = 0.0  # 10m高さでの風向 (度、0=北, 90=東, 180=南, 270=西)
    period: Optional[str] = None  # データ期間 (例: PT30M)


@dataclass
class ForecastRequest:
    """予測リクエストデータを格納するクラス"""
    latitude: float
    longitude: float
    hours: int
    api_key: str
    specific_date: Optional[datetime] = None  # 特定の日時（指定がある場合）
    timezone_offset: int = 9  # UTCからの時差（デフォルトは日本の+9時間）
    tilt: Optional[float] = None  # パネルの傾斜角（度）
    azimuth: Optional[float] = None  # パネルの方位角（度、0=北、90=東、180=南、270=西）
    array_type: str = "fixed"  # 太陽光パネルの種類："fixed"または"horizontal_single_axis"
    interval: int = 30  # データ間隔（分単位）
    is_solar_car: bool = False  # ソーラーカーモードフラグ
    solar_car_tilt: float = 10.0  # ソーラーカーのパネル傾斜角
    solar_car_direction: float = 180.0  # ソーラーカーの走行方向