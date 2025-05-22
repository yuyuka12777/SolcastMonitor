import json
import os
from typing import Dict, Any, Optional


class Config:
    """設定値を管理するクラス"""
    DEFAULT_CONFIG = {
        "api_key": "",
        "default_latitude": 35.6895,
        "default_longitude": 139.6917,
        "default_hours": 24
    }
    
    CONFIG_FILE = "solcast_config.json"
    
    @classmethod
    def load(cls) -> Dict[str, Any]:
        """設定ファイルを読み込む"""
        if os.path.exists(cls.CONFIG_FILE):
            try:
                with open(cls.CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"設定ファイル読み込みエラー: {str(e)}")
        return cls.DEFAULT_CONFIG.copy()
    
    @classmethod
    def save(cls, config: Dict[str, Any]) -> None:
        """設定ファイルを保存する"""
        try:
            with open(cls.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"設定ファイル保存エラー: {str(e)}")
    
    @classmethod
    def get_api_key(cls) -> str:
        """API keyを取得"""
        return cls.load().get("api_key", "")
    
    @classmethod
    def save_api_key(cls, api_key: str) -> None:
        """API keyを保存"""
        config = cls.load()
        config["api_key"] = api_key
        cls.save(config)
    
    def set(self, key, value):
        """設定値を保存する"""
        self.config_data[key] = value
        
    def save(self):
        """設定をファイルに保存する"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config_data, f, indent=2)
            return True
        except Exception as e:
            print(f"設定の保存に失敗しました: {e}")
            return False