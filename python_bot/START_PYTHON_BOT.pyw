# Windows .pyw launcher: no console window when opened with Python Launcher / pythonw.exe.
from pathlib import Path
import os
import runpy
import sys

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))
try:
    runpy.run_path(str(HERE / 'python_bot.py'), run_name='__main__')
except Exception:
    import traceback
    with (HERE / 'startup_error.log').open('w', encoding='utf-8') as out:
        traceback.print_exc(file=out)
    try:
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showerror('Python Bot', 'Khởi động thất bại. Xem startup_error.log trong thư mục bot.')
        root.destroy()
    except Exception:
        pass
