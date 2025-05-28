import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
from datetime import datetime, timedelta
from typing import List, Callable, Optional

from models import SolarForecast, ForecastRequest
from config import Config
from solcast_api import SolcastAPI


class ResultWindow:
    """予測結果を表示する別ウィンドウクラス"""
    
    def __init__(self, parent, title="予測結果詳細"):
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("700x500")
        self.window.minsize(600, 400)
        
        # ウィンドウが閉じられたときのフラグ
        self.is_closed = False
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 結果表示用テキストエリア
        self.result_text = scrolledtext.ScrolledText(self.window, wrap=tk.WORD)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ボタンフレーム
        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 閉じるボタン
        ttk.Button(button_frame, text="閉じる", command=self._on_close).pack(side=tk.RIGHT)
    
    def display_forecasts(self, forecasts, timezone_offset, display_count, has_gti_params=False, use_specific_time=False, specific_time_str=""):
        """予測データを表示"""
        self.result_text.delete(1.0, tk.END)
        
        tz_sign = "+" if timezone_offset >= 0 else ""
        
        if not forecasts:
            self.result_text.insert(tk.END, "予測データが見つかりませんでした\n")
            return
        
        # 表示するデータを制限
        display_forecasts = forecasts[:display_count]
        
        self.result_text.insert(tk.END, f"予測データ詳細 - 表示: {len(display_forecasts)}件 / 取得: {len(forecasts)}件 (UTC{tz_sign}{timezone_offset})\n\n")
        
        # 時刻指定されていた場合の注記
        if use_specific_time and specific_time_str:
            self.result_text.insert(tk.END, f"※ 指定日時: {specific_time_str} の近くのデータを表示しています\n")
        
        # 利用可能なデータに関する注記を表示
        self.result_text.insert(tk.END, "※ 利用可能なデータ: 日時、全天日射量(GHI)、直達日射量(DNI)、気温\n")
        self.result_text.insert(tk.END, "※ 太陽位置(天頂角・方位角)は計算値です\n")
        
        if not has_gti_params:
            self.result_text.insert(tk.END, "※ GTIを表示するには傾斜角と方位角を設定してください\n")
        
        self.result_text.insert(tk.END, "\n")
        
        for forecast in display_forecasts:
            self.result_text.insert(tk.END, f"日時: {forecast.time.strftime('%Y-%m-%d %H:%M')}\n")
            
            # データ期間がある場合は表示
            if hasattr(forecast, 'period') and forecast.period:
                self.result_text.insert(tk.END, f"データ期間: {forecast.period}\n")
            
            # 気温データがあれば表示
            if hasattr(forecast, "air_temp") and forecast.air_temp is not None:
                self.result_text.insert(tk.END, f"気温: {forecast.air_temp}℃\n")
            
            # APIから取得できる値のみ表示
            self.result_text.insert(tk.END, f"全天日射量(GHI): {forecast.ghi:.2f} W/m²\n")
            self.result_text.insert(tk.END, f"予測照射量/直達日射量(DNI): {forecast.forecast_radiation:.2f} W/m²\n")
            
            # GTIの表示
            if hasattr(forecast, "gti_valid") and forecast.gti_valid:
                self.result_text.insert(tk.END, f"全天傾斜日射量(GTI): {forecast.gti:.2f} W/m²\n")
            elif has_gti_params:
                self.result_text.insert(tk.END, "全天傾斜日射量(GTI): データなし\n")
            else:
                self.result_text.insert(tk.END, "全天傾斜日射量(GTI): 設定が必要\n")
            
            # 太陽位置情報（計算値）
            self.result_text.insert(tk.END, f"太陽天頂角: {forecast.zenith:.2f}°\n")
            self.result_text.insert(tk.END, f"太陽方位角: {forecast.azimuth:.2f}°\n")
            
            self.result_text.insert(tk.END, "-" * 50 + "\n")
        
        # ウィンドウを前面に表示
        self.window.lift()
    
    def _on_close(self):
        """ウィンドウが閉じられたときの処理"""
        self.is_closed = True
        self.window.destroy()


class SolcastApp:
    """アプリケーションのメインUIクラス"""
    # デフォルトの最小待機時間（秒）
    DEFAULT_REQUEST_INTERVAL = 30
    
    def __init__(self, root, panel_help=None):
        self.root = root
        self.root.title("Solcast太陽光予測モニター")
        self.root.geometry("800x600")
        self.root.minsize(800, 600)
        
        # ヘルプ情報
        self.panel_help = panel_help or {
            "fixed": "固定パネル",
            "horizontal_single_axis": "水平一軸追尾型"
        }
        
        # Configインスタンスを作成
        self.config = Config.load()
        self.forecasts: List[SolarForecast] = []
        
        # 最小待機時間を設定
        self.MIN_REQUEST_INTERVAL = int(self.config.get("api_cooltime", 30))
        
        # 最後のリクエスト時刻を記録
        self.last_request_time = datetime.min
        
        # 別ウィンドウ表示のオプション
        self.use_separate_window_var = tk.BooleanVar(value=False)
        self.result_window = None
        
        self._create_widgets()
        self._load_saved_settings()
    
    def _create_widgets(self):
        """UIウィジェットを作成する"""
        # メインフレーム
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # API設定フレーム - API Keyとクールタイムの両方を含む
        api_settings_frame = ttk.LabelFrame(main_frame, text="API設定")
        api_settings_frame.pack(fill=tk.X, pady=5)
        
        # API Key設定
        api_frame = ttk.Frame(api_settings_frame)
        api_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(api_frame, text="Solcast API Key:").pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar()
        ttk.Entry(api_frame, textvariable=self.api_key_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(api_frame, text="保存", command=self._save_api_key).pack(side=tk.LEFT)
        
        # クールタイム設定
        cooltime_frame = ttk.Frame(api_settings_frame)
        cooltime_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(cooltime_frame, text="APIクールタイム(秒):").pack(side=tk.LEFT)
        self.cooltime_var = tk.StringVar(value=str(self.MIN_REQUEST_INTERVAL))
        cooltime_spinner = ttk.Spinbox(
            cooltime_frame,
            from_=0,
            to=600,  # 最大10分
            increment=5,
            textvariable=self.cooltime_var,
            width=5
        )
        cooltime_spinner.pack(side=tk.LEFT, padx=5)
        ttk.Button(cooltime_frame, text="適用", command=self._apply_cooltime).pack(side=tk.LEFT)
        ttk.Label(cooltime_frame, text="※値を小さくしすぎるとAPI制限にかかる可能性があります").pack(side=tk.LEFT, padx=(10, 0))
        
        # 入力フレーム
        input_frame = ttk.LabelFrame(main_frame, text="予測条件設定")
        input_frame.pack(fill=tk.X, pady=5)
        
        # 位置情報設定
        location_frame = ttk.Frame(input_frame)
        location_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(location_frame, text="緯度:").pack(side=tk.LEFT)
        self.latitude_var = tk.StringVar()
        ttk.Entry(location_frame, textvariable=self.latitude_var, width=10).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(location_frame, text="経度:").pack(side=tk.LEFT, padx=(10, 0))
        self.longitude_var = tk.StringVar()
        ttk.Entry(location_frame, textvariable=self.longitude_var, width=10).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(location_frame, text="予測時間(時間):").pack(side=tk.LEFT, padx=(10, 0))
        self.hours_var = tk.StringVar()
        ttk.Entry(location_frame, textvariable=self.hours_var, width=5).pack(side=tk.LEFT, padx=5)
        
        # データ間隔設定を追加
        interval_frame = ttk.Frame(input_frame)
        interval_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(interval_frame, text="データ間隔(分):").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="30")  # デフォルト30分
        interval_combo = ttk.Combobox(interval_frame, 
                                textvariable=self.interval_var,
                                values=["5", "10", "15", "30"],
                                width=5,
                                state="readonly")
        interval_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(interval_frame, text="※データ間隔を小さくすると、取得できる最大時間が短くなります").pack(side=tk.LEFT, padx=(10, 0))
        
        # タイムゾーン設定
        tz_frame = ttk.Frame(input_frame)
        tz_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(tz_frame, text="タイムゾーン (UTC+/-)").pack(side=tk.LEFT)
        self.timezone_var = tk.StringVar(value="9")  # デフォルトUTC+9（日本時間）
        ttk.Spinbox(tz_frame, from_=-12, to=14, textvariable=self.timezone_var, width=3).pack(side=tk.LEFT, padx=5)
        ttk.Label(tz_frame, text="※表示のみローカル時間に変換されます").pack(side=tk.LEFT, padx=5)
        
        # 表示件数設定
        count_frame = ttk.Frame(input_frame)
        count_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(count_frame, text="表示件数:").pack(side=tk.LEFT)
        self.display_count_var = tk.StringVar(value="3")  # デフォルト3件
        ttk.Spinbox(
            count_frame,
            from_=1,
            to=100,
            increment=1,
            textvariable=self.display_count_var,
            width=3
        ).pack(side=tk.LEFT, padx=5)
        ttk.Label(count_frame, text="※多くの件数を表示する場合は予測時間も増やしてください").pack(side=tk.LEFT, padx=5)
        
        # 特定時刻設定
        time_frame = ttk.Frame(input_frame)
        time_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 特定時刻の有効/無効
        self.use_specific_time_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            time_frame, 
            text="特定時刻を指定", 
            variable=self.use_specific_time_var,
            command=self._toggle_time_inputs
        ).pack(side=tk.LEFT)
        
        # 日付入力
        ttk.Label(time_frame, text="日付:").pack(side=tk.LEFT, padx=(10, 0))
        self.year_var = tk.StringVar(value=datetime.now().strftime("%Y"))
        ttk.Entry(time_frame, textvariable=self.year_var, width=5).pack(side=tk.LEFT)
        ttk.Label(time_frame, text="/").pack(side=tk.LEFT)
        self.month_var = tk.StringVar(value=datetime.now().strftime("%m"))
        ttk.Entry(time_frame, textvariable=self.month_var, width=3).pack(side=tk.LEFT)
        ttk.Label(time_frame, text="/").pack(side=tk.LEFT)
        self.day_var = tk.StringVar(value=datetime.now().strftime("%d"))
        ttk.Entry(time_frame, textvariable=self.day_var, width=3).pack(side=tk.LEFT)
        
        # 時刻入力
        ttk.Label(time_frame, text="時刻:").pack(side=tk.LEFT, padx=(10, 0))
        self.hour_var = tk.StringVar(value=datetime.now().strftime("%H"))
        ttk.Entry(time_frame, textvariable=self.hour_var, width=3).pack(side=tk.LEFT)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        self.minute_var = tk.StringVar(value="00")
        ttk.Entry(time_frame, textvariable=self.minute_var, width=3).pack(side=tk.LEFT)
        
        # 初期状態で時刻指定関連のウィジェットを無効化
        self._toggle_time_inputs()
        
        # 実行ボタン
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.fetch_button = ttk.Button(button_frame, text="予測データ取得", command=self._fetch_forecast)
        self.fetch_button.pack(side=tk.LEFT)
        
        # 別ウィンドウ表示オプション
        ttk.Checkbutton(
            button_frame,
            text="結果を別ウィンドウに表示",
            variable=self.use_separate_window_var
        ).pack(side=tk.LEFT, padx=10)
        
        self.status_var = tk.StringVar(value="準備完了")
        ttk.Label(button_frame, textvariable=self.status_var).pack(side=tk.LEFT, padx=10)
        
        # 太陽光パネル設定フレーム
        panel_frame = ttk.LabelFrame(main_frame, text="太陽光パネル設定")
        panel_frame.pack(fill=tk.X, pady=5)
        
        panel_type_frame = ttk.Frame(panel_frame)
        panel_type_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(panel_type_frame, text="パネル種類:").pack(side=tk.LEFT)
        self.array_type_var = tk.StringVar(value="fixed")
        array_type_combo = ttk.Combobox(panel_type_frame, 
                                        textvariable=self.array_type_var,
                                        values=["fixed", "horizontal_single_axis", "solar_car"],
                                        width=20,
                                        state="readonly")
        array_type_combo.pack(side=tk.LEFT, padx=5)
        array_type_combo.bind("<<ComboboxSelected>>", self._toggle_panel_params)
        
        # パネル種類の説明ラベル
        self.panel_desc_var = tk.StringVar(value=self.panel_help.get("fixed", "固定パネル"))
        self.panel_desc_label = ttk.Label(panel_type_frame, textvariable=self.panel_desc_var, wraplength=350)
        self.panel_desc_label.pack(side=tk.LEFT, padx=5)

        # ソーラーカー専用設定フレーム
        self.solar_car_frame = ttk.Frame(panel_frame)
        
        ttk.Label(self.solar_car_frame, text="初期傾斜角(度):").pack(side=tk.LEFT)
        self.solar_car_tilt_var = tk.StringVar(value="10")
        ttk.Entry(self.solar_car_frame, textvariable=self.solar_car_tilt_var, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(self.solar_car_frame, text="走行方位角(度):").pack(side=tk.LEFT, padx=(10, 0))
        self.solar_car_direction_var = tk.StringVar(value="180")
        ttk.Entry(self.solar_car_frame, textvariable=self.solar_car_direction_var, width=5).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(self.solar_car_frame, text="※ソーラーカーの走行方向: 0=北, 90=東, 180=南, 270=西").pack(side=tk.LEFT, padx=(5, 0))
        
        # 参照用に親フレームを保存
        self.panel_frame = panel_frame
        
        # 通常の傾斜角と方位角
        panel_params_frame = ttk.Frame(panel_frame)
        panel_params_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(panel_params_frame, text="傾斜角(度):").pack(side=tk.LEFT)
        self.tilt_var = tk.StringVar()
        self.tilt_entry = ttk.Entry(panel_params_frame, textvariable=self.tilt_var, width=5)
        self.tilt_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(panel_params_frame, text="方位角(度):").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(panel_params_frame, text="0=北、90=東、180=南、270=西").pack(side=tk.LEFT, padx=(0, 10))
        self.panel_azimuth_var = tk.StringVar()
        self.azimuth_entry = ttk.Entry(panel_params_frame, textvariable=self.panel_azimuth_var, width=5)
        self.azimuth_entry.pack(side=tk.LEFT, padx=5)
        
        # 表示フレーム
        display_frame = ttk.LabelFrame(main_frame, text="予測結果")
        display_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # テキスト表示のみ
        self.result_text = scrolledtext.ScrolledText(display_frame, wrap=tk.WORD)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def _toggle_time_inputs(self):
        """時刻入力フィールドの有効/無効を切り替える"""
        state = "normal" if self.use_specific_time_var.get() else "disabled"
        for var_name in ["year_var", "month_var", "day_var", "hour_var", "minute_var"]:
            for widget in self.root.winfo_children():
                if hasattr(self, var_name):
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Frame):
                            for grandchild in child.winfo_children():
                                if isinstance(grandchild, ttk.Entry) and grandchild.cget("textvariable") == getattr(self, var_name).name:
                                    grandchild.configure(state=state)
    
    def _load_saved_settings(self):
        """保存された設定を読み込む"""
        self.api_key_var.set(self.config.get("api_key", ""))
        self.latitude_var.set(str(self.config.get("default_latitude", 35.6895)))
        self.longitude_var.set(str(self.config.get("default_longitude", 139.6917)))
        self.hours_var.set(str(self.config.get("default_hours", 24)))
        self.timezone_var.set(str(self.config.get("timezone_offset", 9)))
        self.display_count_var.set(str(self.config.get("display_count", 3)))  # 表示件数も設定から読み込む
        self.use_separate_window_var.set(self.config.get("use_separate_window", False))
    
    def _save_api_key(self):
        """API Keyを保存する"""
        api_key = self.api_key_var.get().strip()
        if api_key:
            # Config.save_api_key(api_key) の代わりに：
            self.config.set("api_key", api_key)
            self.config.save()
            messagebox.showinfo("情報", "API Keyを保存しました")
        else:
            messagebox.showerror("エラー", "API Keyを入力してください")
    
    def _apply_cooltime(self):
        """クールタイム設定を適用"""
        try:
            cooltime = int(self.cooltime_var.get())
            if cooltime < 0:
                raise ValueError("クールタイムは0以上の値を入力してください")
            
            # 最小クールタイムを設定
            self.MIN_REQUEST_INTERVAL = max(cooltime, 5)
            
            # 設定を保存
            self.config.set("api_cooltime", self.MIN_REQUEST_INTERVAL)
            self.config.save()
            
            messagebox.showinfo("情報", f"APIクールタイムを{self.MIN_REQUEST_INTERVAL}秒に設定しました")
        
        except ValueError:
            messagebox.showerror("エラー", "正しいクールタイムを入力してください")
    
    def _fetch_forecast(self):
        """予測データを取得する（レート制限考慮）"""
        # 入力チェック
        try:
            latitude = float(self.latitude_var.get())
            longitude = float(self.longitude_var.get())
            hours = int(self.hours_var.get())
            api_key = self.api_key_var.get().strip()
            timezone_offset = int(self.timezone_var.get())
            
            # タイムゾーンの妥当性チェック
            if not (-12 <= timezone_offset <= 14):
                messagebox.showerror("エラー", "タイムゾーンは-12から+14の間で入力してください")
                return
            
            if not api_key:
                messagebox.showerror("エラー", "API Keyを入力してください")
                return
                
            if not (-90 <= latitude <= 90):
                messagebox.showerror("エラー", "緯度は-90から90の間で入力してください")
                return
                
            if not (-180 <= longitude <= 180):
                messagebox.showerror("エラー", "経度は-180から180の間で入力してください")
                return
                
            if hours <= 0 or hours > 168:
                messagebox.showerror("エラー", "予測時間は1から168の間で入力してください")
                return
            
            # 特定時刻の処理
            specific_date = None
            if self.use_specific_time_var.get():
                try:
                    year = int(self.year_var.get())
                    month = int(self.month_var.get())
                    day = int(self.day_var.get())
                    hour = int(self.hour_var.get())
                    minute = int(self.minute_var.get())
                    
                    specific_date = datetime(year, month, day, hour, minute)
                    
                    # 時刻指定に関する情報メッセージ
                    messagebox.showinfo("情報", "指定された日時に最も近い予測データを表示します。")
                    
                except ValueError:
                    messagebox.showerror("エラー", "日付と時刻の形式が正しくありません")
                    return
        
        except ValueError:
            messagebox.showerror("エラー", "正しい数値を入力してください")
            return
        
        # パネルパラメータ取得
        array_type = self.array_type_var.get()
        
        tilt = None
        if array_type == "fixed" and self.tilt_var.get():
            try:
                tilt = float(self.tilt_var.get())
                if not (0 <= tilt <= 90):
                    messagebox.showerror("エラー", "傾斜角は0から90の間で入力してください")
                    return
            except ValueError:
                messagebox.showerror("エラー", "傾斜角は数値で入力してください")
                return
        
        panel_azimuth = None
        if self.panel_azimuth_var.get():
            try:
                panel_azimuth = float(self.panel_azimuth_var.get())
                if not (0 <= panel_azimuth <= 360):
                    messagebox.showerror("エラー", "方位角は0から360の間で入力してください")
                    return
            except ValueError:
                messagebox.showerror("エラー", "方位角は数値で入力してください")
                return
        
        # レート制限のチェック
        now = datetime.now()
        time_since_last_request = (now - self.last_request_time).total_seconds()
        
        if time_since_last_request < self.MIN_REQUEST_INTERVAL:
            # 前回のリクエストから十分な時間が経過していない場合
            wait_seconds = int(self.MIN_REQUEST_INTERVAL - time_since_last_request) + 1
            message = f"APIのレート制限を防ぐため、あと{wait_seconds}秒お待ちください。"
            messagebox.showinfo("情報", message)
            return
        
        # 取得中の状態にする
        self.fetch_button.config(state=tk.DISABLED)
        self.status_var.set("データ取得中...")
        self.root.update_idletasks()
        
        # 最終リクエスト時刻を更新
        self.last_request_time = now
        
        # 間隔の処理を追加
        interval = int(self.interval_var.get())
        
        # 間隔に応じて最大時間数を調整
        max_hours = 1  # デフォルト1時間まで
        if hours > max_hours:
            hours = max_hours
            self.hours_var.set(str(max_hours))
            messagebox.showinfo("情報", f"選択された間隔では最大{max_hours}時間までのデータを取得します")
        
        # バックグラウンドでAPIリクエスト実行
        thread = threading.Thread(
            target=self._background_fetch, 
            args=(latitude, longitude, hours, api_key, specific_date, timezone_offset, 
                  array_type, tilt, panel_azimuth, interval)
        )
        thread.daemon = True
        thread.start()
    
    def _background_fetch(self, latitude: float, longitude: float, hours: int, 
                   api_key: str, specific_date: Optional[datetime] = None,
                   timezone_offset: int = 9, array_type: str = "fixed",
                   tilt: Optional[float] = None, panel_azimuth: Optional[float] = None,
                   interval: int = 30):
        """バックグラウンドでのデータ取得処理"""
        # ソーラーカーモードのフラグ
        is_solar_car = array_type == "solar_car"
        solar_car_tilt = 10.0
        solar_car_direction = 180.0
        
        # ソーラーカーモードの場合のパラメータ調整
        if is_solar_car:
            try:
                # ソーラーカーモード用の値を取得
                solar_car_tilt = float(self.solar_car_tilt_var.get()) if self.solar_car_tilt_var.get() else 10.0
                solar_car_direction = float(self.solar_car_direction_var.get()) if self.solar_car_direction_var.get() else 180.0
                
                # API用にパラメータを設定 - 標準APIリクエストには固定パネルとして送信
                array_type = "fixed"
                tilt = solar_car_tilt
                panel_azimuth = solar_car_direction
            except ValueError:
                # 数値変換エラーの場合はデフォルト値を使用
                array_type = "fixed"
                tilt = 10.0
                panel_azimuth = 180.0
        
        request = ForecastRequest(
            latitude=latitude,
            longitude=longitude,
            hours=hours,
            api_key=api_key,
            specific_date=specific_date,
            timezone_offset=timezone_offset,
            tilt=tilt,
            azimuth=panel_azimuth,
            array_type=array_type,
            interval=interval,
            is_solar_car=is_solar_car,
            solar_car_tilt=solar_car_tilt,
            solar_car_direction=solar_car_direction
        )
        
        try:
            forecasts = SolcastAPI.get_forecast(request)
            
            # UI更新はメインスレッドで行う
            self.root.after(0, lambda: self._update_forecast_display(
                forecasts, timezone_offset, tilt is not None or array_type == "horizontal_single_axis"))
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
            print(f"エラー詳細: {error_msg}")
            self.root.after(0, lambda: self._handle_fetch_error(error_msg))
    
    def _update_forecast_display(self, forecasts: List[SolarForecast], timezone_offset: int, has_gti_params: bool = False):
        """予測結果の表示を更新する"""
        # 取得した全予測データを保存
        self.forecasts = forecasts
        
        # 表示件数の取得と適用
        try:
            display_count = int(self.display_count_var.get())
            if display_count <= 0:
                display_count = 1
            elif display_count > len(forecasts):
                display_count = len(forecasts)
        except ValueError:
            display_count = 3  # デフォルト値
        
        # 時刻指定されているかどうか
        is_specific_time = self.use_specific_time_var.get()
        specific_time_str = ""
        if is_specific_time:
            try:
                specific_time_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()} {self.hour_var.get()}:{self.minute_var.get()}"
            except:
                pass
        
        # 別ウィンドウ表示が選択されている場合
        if self.use_separate_window_var.get():
            # 既存のウィンドウがあるか確認
            if self.result_window is None or getattr(self.result_window, 'is_closed', True):
                self.result_window = ResultWindow(self.root, f"予測結果詳細 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            
            # 結果を別ウィンドウに表示
            self.result_window.display_forecasts(
                forecasts, 
                timezone_offset, 
                display_count, 
                has_gti_params,
                is_specific_time,
                specific_time_str
            )
            
            # メインウィンドウには結果概要のみ表示
            self.result_text.delete(1.0, tk.END)
            tz_sign = "+" if timezone_offset >= 0 else ""
            
            if not forecasts:
                self.result_text.insert(tk.END, "予測データが見つかりませんでした\n\n")
                self.result_text.insert(tk.END, "考えられる原因:\n")
                self.result_text.insert(tk.END, "・指定された位置情報が正しくない\n")
                self.result_text.insert(tk.END, "・APIキーが無効または上限に達している\n")
                self.result_text.insert(tk.END, "・API呼び出しが失敗した\n")
                self.result_text.insert(tk.END, "\nパラメータを調整して再試行してください\n")
                self.fetch_button.config(state=tk.NORMAL)
                self.status_var.set("データなし")
                return
            else:
                self.result_text.insert(tk.END, f"予測データ - 取得: {len(forecasts)}件 (UTC{tz_sign}{timezone_offset})\n\n")
                self.result_text.insert(tk.END, "※ 詳細は別ウィンドウに表示されています\n")
                self.result_text.insert(tk.END, "※ 詳細ウィンドウが見つからない場合は、チェックボックスを外して再取得してください\n\n")
                
                # パネル設定の説明を追加
                panel_type = self.array_type_var.get()
                if panel_type == "fixed":
                    self.result_text.insert(tk.END, f"※ 固定パネル設定: 傾斜角={self.tilt_var.get() or 'なし'}, 方位角={self.panel_azimuth_var.get() or 'なし'}\n")
                elif panel_type == "horizontal_single_axis":
                    self.result_text.insert(tk.END, f"※ 水平一軸追尾型パネル設定: 軸方位角={self.panel_azimuth_var.get() or 'なし'}\n")
        else:
            # 従来通りメインウィンドウに表示
            self.result_text.delete(1.0, tk.END)
            
            tz_sign = "+" if timezone_offset >= 0 else ""
            
            if not forecasts:
                self.result_text.insert(tk.END, "予測データが見つかりませんでした\n\n")
                self.result_text.insert(tk.END, "考えられる原因:\n")
                self.result_text.insert(tk.END, "・指定された位置情報が正しくない\n")
                self.result_text.insert(tk.END, "・APIキーが無効または上限に達している\n")
                self.result_text.insert(tk.END, "・API呼び出しが失敗した\n")
                self.result_text.insert(tk.END, "\nパラメータを調整して再試行してください\n")
                self.fetch_button.config(state=tk.NORMAL)
                self.status_var.set("データなし")
                return
            
            # 表示するデータを制限
            display_forecasts = forecasts[:display_count]
            
            self.result_text.insert(tk.END, f"予測データ - 表示: {len(display_forecasts)}件 / 取得: {len(forecasts)}件 (UTC{tz_sign}{timezone_offset})\n\n")
            
            # 時刻指定されていた場合の注記
            if is_specific_time and specific_time_str:
                self.result_text.insert(tk.END, f"※ 指定日時: {specific_time_str} の近くのデータを表示しています\n")
            
            # 利用可能なデータに関する注記を表示
            self.result_text.insert(tk.END, "※ 利用可能なデータ: 日時、全天日射量(GHI)、直達日射量(DNI)、気温\n")
            self.result_text.insert(tk.END, "※ 太陽位置(天頂角・方位角)は計算値です\n")
            
            # パネル設定の説明を追加
            panel_type = self.array_type_var.get()
            panel_info = ""
            
            if panel_type == "fixed":
                panel_info = f"固定パネル設定: 傾斜角={self.tilt_var.get() or 'なし'}, 方位角={self.panel_azimuth_var.get() or 'なし'}"
            elif panel_type == "horizontal_single_axis":
                panel_info = f"水平一軸追尾型パネル設定: 軸方位角={self.panel_azimuth_var.get() or 'なし'}"
            elif panel_type == "solar_car":
                panel_info = f"ソーラーカー設定: 初期傾斜角={self.solar_car_tilt_var.get()}°, 走行方位角={self.solar_car_direction_var.get()}°"
            
            if panel_info:
                self.result_text.insert(tk.END, f"※ {panel_info}\n")
            
            if panel_type == "solar_car":
                self.result_text.insert(tk.END, "※ ソーラーカーモードでは走行中の姿勢変化を近似した計算を行います\n")
                self.result_text.insert(tk.END, "※ 実際の値は走行条件によって変動する可能性があります\n")
            
            if not has_gti_params:
                self.result_text.insert(tk.END, "※ GTIを表示するには傾斜角と方位角を設定してください\n")
            
            self.result_text.insert(tk.END, "\n")
            
            for forecast in display_forecasts:
                self.result_text.insert(tk.END, f"日時: {forecast.time.strftime('%Y-%m-%d %H:%M')}\n")
                
                # データ期間がある場合は表示
                if hasattr(forecast, 'period') and forecast.period:
                    self.result_text.insert(tk.END, f"データ期間: {forecast.period}\n")
                
                # 気温データがあれば表示
                if hasattr(forecast, "air_temp") and forecast.air_temp is not None:
                    self.result_text.insert(tk.END, f"気温: {forecast.air_temp}℃\n")
                
                # APIから取得できる値のみ表示
                self.result_text.insert(tk.END, f"全天日射量(GHI): {forecast.ghi:.2f} W/m²\n")
                self.result_text.insert(tk.END, f"予測照射量/直達日射量(DNI): {forecast.forecast_radiation:.2f} W/m²\n")
                
                # GTIの表示
                if hasattr(forecast, "gti_valid") and forecast.gti_valid:
                    self.result_text.insert(tk.END, f"全天傾斜日射量(GTI): {forecast.gti:.2f} W/m²\n")
                elif has_gti_params:
                    self.result_text.insert(tk.END, "全天傾斜日射量(GTI): データなし\n")
                else:
                    self.result_text.insert(tk.END, "全天傾斜日射量(GTI): 設定が必要\n")
                
                # 太陽位置情報（計算値）
                self.result_text.insert(tk.END, f"太陽天頂角: {forecast.zenith:.2f}°\n")
                self.result_text.insert(tk.END, f"太陽方位角: {forecast.azimuth:.2f}°\n")
                
                self.result_text.insert(tk.END, "-" * 50 + "\n")
        
        # UIを元の状態に戻す
        self.fetch_button.config(state=tk.NORMAL)
        self.status_var.set(f"最終更新: {datetime.now().strftime('%H:%M:%S')}")
    
    def _handle_fetch_error(self, error_msg: str):
        """データ取得エラーの処理"""
        messagebox.showerror("エラー", f"データ取得中にエラーが発生しました:\n{error_msg}")
        self.fetch_button.config(state=tk.NORMAL)
        self.status_var.set("エラー発生")
    
    def _toggle_panel_params(self, event=None):
        """パネル種類に応じて入力フィールドを有効/無効化"""
        panel_type = self.array_type_var.get()
        
        # ソーラーカーフレームの表示/非表示
        if panel_type == "solar_car":
            # 単にパックし直す - 特定の位置指定はしない
            self.solar_car_frame.pack(fill=tk.X, padx=5, pady=5)
        else:
            self.solar_car_frame.pack_forget()
        
        if panel_type == "fixed":
            self.tilt_entry.config(state="normal")
            self.azimuth_entry.config(state="normal")
        elif panel_type == "solar_car":
            self.tilt_entry.config(state="disabled")
            self.azimuth_entry.config(state="disabled")
        else:  # horizontal_single_axis
            self.tilt_entry.config(state="disabled")
            self.azimuth_entry.config(state="normal")  # 方位角は軸の方向として使用
            
        # パネル種類の説明を更新
        if panel_type in self.panel_help:
            self.panel_desc_var.set(self.panel_help[panel_type])