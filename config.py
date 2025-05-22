import json
import os
from typing import Dict, Any, Optional


class Config:
    """設定を管理するクラス"""
    DEFAULT_CONFIG_PATH = "solcast_config.json"
    
    def __init__(self, config_path=None):
        """コンフィグの初期化"""
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self.config_data = {}
        self._load_from_file()
    
    def _load_from_file(self):
        """設定ファイルから読み込み"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config_data = json.load(f)
            else:
                self.config_data = {}
        except Exception as e:
            print(f"設定の読み込みに失敗しました: {e}")
            self.config_data = {}
    
    def get(self, key, default=None):
        """設定値を取得する"""
        return self.config_data.get(key, default)
    
    def set(self, key, value):
        """設定値を設定する"""
        self.config_data[key] = value
        return self
    
    def save(self):
        """設定をファイルに保存する"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2)
            return True
        except Exception as e:
            print(f"設定の保存に失敗しました: {e}")
            return False
    
    @classmethod
    def load(cls, config_path=None):
        """設定をロードする（クラスメソッド）"""
        return cls(config_path)