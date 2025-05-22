import sys
import tkinter as tk
from tkinter import ttk, messagebox
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
            
        app = SolcastApp(root)
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