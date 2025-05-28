"""
MIT License

Copyright (c) 2023 [著作権者の名前]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, font  # fontモジュールを明示的にインポート
from ui import SolcastApp


def main():
    """アプリケーションのエントリーポイント"""
    try:
        # 通常のTkウィンドウを作成
        root = tk.Tk()
        root.title("Solcast太陽光予測モニター")
        
        # 標準のスタイル設定
        style = ttk.Style()
        if "clam" in style.theme_names():  # clamテーマが利用可能か確認
            style.theme_use("clam")
        
        # ヘルプ情報の定義
        panel_help = {
            "fixed": "固定された太陽光パネル。傾斜角と方位角の両方を設定する必要があります。",
            "horizontal_single_axis": "水平一軸追尾型パネル。傾斜角は自動計算され、方位角は追尾軸の方向を示します。",
            "solar_car": "ソーラーカー用パネル。移動する車両上のパネルに最適化された計算を行います。"
        }
        
        app = SolcastApp(root, panel_help=panel_help)
        root.mainloop()
    except Exception as e:
        # 未処理の例外をキャッチしてダイアログ表示
        import traceback
        
        error_message = f"予期せぬエラーが発生しました:\n{str(e)}\n\n{traceback.format_exc()}"
        messagebox.showerror("エラー", error_message)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())