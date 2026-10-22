"""Python Bot v0.9.6 - desktop website monitor (standard library only)."""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox
from urllib.parse import urlparse
from update_manager import check_release, download_release
def extract_jan(message):
    """Read standalone JAN/EAN digits only."""
    return set(re.findall(r'(?<![0-9])(?:[0-9]{8}|[0-9]{13}|[0-9]{14})(?![0-9])', str(message)))

def matches_tasks(message, tasks):
    codes = extract_jan(message)
    return [t for t in tasks if t.get('enabled', True) and str(t.get('jan', '')).strip() in codes and t.get('jan')]



# Release automation: versioned source is published by GitHub Actions.
# Compatibility build: keep v0.6.0 self-contained for the v0.5 updater.
APP_NAME = 'Python Bot'
VERSION = '0.9.6'
BASE = Path(os.getenv('APPDATA', str(Path.home()))) / 'PythonBot'
DATA_FILE = BASE / 'config.json'
BG = '#101116'
SIDEBAR = '#181a20'
PANEL = '#202229'
FG = '#f0f1f4'
MUTED = '#a1a5b1'
ACCENT = '#ff842b'
GREEN = '#45d58a'

DEFAULT = {'interval': 90, 'tasks': [], 'profiles': [], 'proxies': [], 'update_url': '', 'discord_channel_id': '', 'discord_auto_start': True, 'discord_auto_monitor': True, 'discord_trigger_on_message': False}


def load_data():
    try:
        data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Invalid settings')
        return {**DEFAULT, **data}
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT))


def save_data(data):
    BASE.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(DATA_FILE)


def fetch_status(url, keyword):
    parsed = urlparse(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname:
        return 'URL không hợp lệ'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; PythonBotMonitor/0.1)'})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            # Limit download; some pages are enormous.
            content = response.read(750_000).decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
            if response.status != 200:
                return f'HTTP {response.status}'
            if keyword:
                return 'Tìm thấy từ khóa' if keyword.casefold() in content.casefold() else 'Chưa thấy từ khóa'
            return 'Trang truy cập được'
    except urllib.error.HTTPError as e:
        return f'HTTP {e.code}'
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return f'Lỗi kết nối: {str(e)[:85]}'


class PythonBot(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'{APP_NAME} v{VERSION}')
        self.geometry('1190x760')
        self.minsize(900, 620)
        self.configure(bg=BG)
        self.data = load_data()
        # Sensitive card fields live only in Tk memory, never in config.json.
        self.session_card_pan = tk.StringVar(master=self)
        self.session_card_exp = tk.StringVar(master=self)
        self.session_card_cvv = tk.StringVar(master=self)
        self.events = queue.Queue()
        self.running = False
        self.worker = None
        self.latest_release = None
        self.update_busy = False
        self.discord_listener = None
        self.discord_state = 'Chưa kết nối'
        self.active_page = 'Giám sát'
        self.nav_buttons = {}
        self._build()
        self.show_page('Giám sát')
        self.after(250, self.poll_events)
        self.after(900, self.maybe_start_discord)
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def label(self, parent, text, size=11, color=FG, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, cmd, primary=False):
        return tk.Button(parent, text=text, command=cmd, bg=ACCENT if primary else '#30333d',
                         fg='white', font=('Segoe UI', 10, 'bold'), relief='flat',
                         activebackground='#bb5c1a', activeforeground='white', cursor='hand2',
                         padx=14, pady=9, bd=0)

    def entry(self, parent, width=40):
        e = tk.Entry(parent, width=width, bg='#12141b', fg=FG, insertbackground='white',
                     relief='flat', font=('Segoe UI', 11), highlightthickness=1,
                     highlightbackground='#414550', highlightcolor=ACCENT)
        return e

    def _build(self):
        self.sidebar = tk.Frame(self, bg=SIDEBAR, width=215)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text='◉  Python Bot', fg=FG, bg=SIDEBAR,
                 font=('Segoe UI', 18, 'bold'), pady=23).pack(fill='x')
        tk.Label(self.sidebar, text='ĐIỀU KHIỂN', fg=MUTED, bg=SIDEBAR,
                 font=('Segoe UI', 9)).pack(anchor='w', padx=20, pady=(16, 8))
        for name in ('Tổng quan', 'Giám sát', 'Tác vụ', 'Hồ sơ', 'Proxy', 'Discord', 'JAN/EAN', 'Yamada Guest', 'Thẻ', 'Gmail OTP', 'Cài đặt'):
            b = tk.Button(self.sidebar, text='   '+name, anchor='w', bg=SIDEBAR, fg=FG,
                          activebackground=PANEL, activeforeground=ACCENT, relief='flat',
                          font=('Segoe UI', 11), padx=14, pady=13,
                          command=lambda n=name: self.show_page(n))
            b.pack(fill='x', padx=7, pady=1)
            self.nav_buttons[name] = b
        tk.Label(self.sidebar, text=f'● Python Bot v{VERSION}', fg=GREEN, bg=SIDEBAR,
                 font=('Segoe UI', 9)).pack(side='bottom', anchor='w', padx=20, pady=18)
        self.main = tk.Frame(self, bg=BG)
        self.main.pack(side='left', fill='both', expand=True)

    def clear(self):
        for child in self.main.winfo_children():
            child.destroy()

    def heading(self, title, detail=''):
        top = tk.Frame(self.main, bg=BG)
        top.pack(fill='x', padx=24, pady=(20, 8))
        self.label(top, title, 20, bold=True).pack(anchor='w')
        if detail:
            self.label(top, detail, 10, MUTED).pack(anchor='w', pady=(5, 0))

    def panel(self):
        p = tk.Frame(self.main, bg=PANEL, padx=17, pady=15,
                     highlightthickness=1, highlightbackground='#31343d')
        p.pack(fill='x', padx=24, pady=9)
        return p

    def show_page(self, name):
        self.active_page = name
        self.clear()
        for title, btn in self.nav_buttons.items():
            btn.configure(bg=PANEL if title == name else SIDEBAR,
                          fg=ACCENT if title == name else FG)
        getattr(self, 'page_' + {'Tổng quan':'overview','Giám sát':'monitor',
                'Tác vụ':'tasks','Hồ sơ':'profiles','Proxy':'proxy','Discord':'discord','JAN/EAN':'jan','Yamada Guest':'yamada_guest','Thẻ':'cards','Gmail OTP':'gmail_otp','Cài đặt':'settings'}[name])()

    def page_overview(self):
        self.heading('Tổng quan', 'Trung tâm điều khiển Python Bot')
        p = self.panel()
        self.label(p, f'Số tác vụ: {len(self.data["tasks"])}', 15, bold=True).pack(anchor='w', pady=8)
        self.label(p, f'Tác vụ đang bật: {sum(t.get("enabled", True) for t in self.data["tasks"])}', 14).pack(anchor='w', pady=8)
        self.label(p, f'Trạng thái giám sát: {"Đang chạy" if self.running else "Đang dừng"}', 14,
                   GREEN if self.running else MUTED).pack(anchor='w', pady=8)
        self.label(p, 'Bản đầu tiên chỉ kiểm tra trang/từ khóa, không tự đặt hàng hay thanh toán.',
                   10, MUTED).pack(anchor='w', pady=14)
        self.button(p, 'Mở giám sát', lambda: self.show_page('Giám sát'), True).pack(anchor='w')

    def page_monitor(self):
        self.heading('Giám sát', 'Theo dõi các liên kết sản phẩm bằng HTTP; kiểm tra theo chu kỳ, không vượt CAPTCHA.')
        controls = self.panel()
        self.status_label = self.label(controls, '● Đang chạy' if self.running else '● Đang dừng',
                                       12, GREEN if self.running else MUTED, bold=True)
        self.status_label.pack(side='left')
        self.button(controls, 'Dừng', self.stop).pack(side='right', padx=5)
        self.button(controls, 'Bắt đầu', self.start, True).pack(side='right', padx=5)
        form = self.panel()
        self.label(form, 'Tên sản phẩm / trang', 10, MUTED).grid(row=0, column=0, sticky='w', pady=4)
        self.label(form, 'Link (URL)', 10, MUTED).grid(row=0, column=1, sticky='w', pady=4, padx=10)
        self.label(form, 'Từ khóa cần tìm (tùy chọn)', 10, MUTED).grid(row=0, column=2, sticky='w', pady=4)
        self.name_entry = self.entry(form, 19)
        self.url_entry = self.entry(form, 43)
        self.keyword_entry = self.entry(form, 21)
        self.name_entry.grid(row=1, column=0, padx=(0,10), pady=8, sticky='ew')
        self.url_entry.grid(row=1, column=1, padx=(0,10), pady=8, sticky='ew')
        self.keyword_entry.grid(row=1, column=2, pady=8, sticky='ew')
        self.button(form, '+ Thêm tác vụ', self.add_task, True).grid(row=2, column=0, sticky='w', pady=8)
        self.button(form, 'Kiểm tra một lượt', self.run_once).grid(row=2, column=1, sticky='w', pady=8)
        self.label(form, 'JAN/EAN (tùy chọn; cần có để khớp thông báo Discord):', 10, MUTED).grid(row=3, column=0, columnspan=2, sticky='w', pady=(9,3))
        self.jan_entry = self.entry(form, 24)
        self.jan_entry.grid(row=4, column=0, sticky='w', pady=4)
        form.columnconfigure(1, weight=1)
        p = self.panel()
        self.label(p, 'TÁC VỤ GIÁM SÁT', 11, bold=True).pack(anchor='w', pady=(0,10))
        self.tree = ttk.Treeview(p, columns=('name','url','keyword','status','updated'), show='headings', height=10)
        for c, title, width in [('name','Tên',140), ('url','Địa chỉ web',240),
                                ('keyword','Từ khóa',140), ('status','Trạng thái',165),
                                ('updated','Lần kiểm tra',115)]:
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, stretch=c == 'url')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('Treeview', background='#171a21', foreground=FG, fieldbackground='#171a21',
                        rowheight=29, borderwidth=0, font=('Segoe UI', 10))
        style.configure('Treeview.Heading', background='#333741', foreground=FG,
                        relief='flat', font=('Segoe UI', 10, 'bold'))
        style.map('Treeview', background=[('selected','#63452f')])
        self.tree.pack(fill='both', expand=True)
        row = tk.Frame(p, bg=PANEL)
        row.pack(fill='x', pady=(10,0))
        self.button(row, 'Mở link', self.open_selected).pack(side='left', padx=(0,8))
        self.button(row, 'Bật / Tắt', self.toggle_selected).pack(side='left', padx=(0,8))
        self.button(row, 'Xóa tác vụ', self.remove_selected).pack(side='left')
        self.render_tasks()
        self.logline = self.label(self.main, 'Nhật ký: Chưa có hoạt động', 10, MUTED, anchor='w')
        self.logline.pack(fill='x', padx=25, pady=9)

    def render_tasks(self):
        if not hasattr(self, 'tree') or not self.tree.winfo_exists():
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, t in enumerate(self.data['tasks']):
            status = t.get('status','Chưa kiểm tra') if t.get('enabled',True) else 'Tạm dừng'
            self.tree.insert('', 'end', iid=str(idx), values=(t['name'] + ' [' + t.get('jan','chưa có JAN') + ']',t['url'],t['keyword'],status,t.get('updated','—')))

    def add_task(self):
        name, url, keyword = self.name_entry.get().strip(), self.url_entry.get().strip(), self.keyword_entry.get().strip()
        jan = self.jan_entry.get().strip()
        if jan and not re.fullmatch(r'(?:[0-9]{8}|[0-9]{13}|[0-9]{14})', jan):
            messagebox.showerror('JAN/EAN', 'JAN/EAN không bắt buộc. Nếu nhập, dùng 8, 13 hoặc 14 chữ số.')
            return
        parsed = urlparse(url)
        if not name or parsed.scheme not in ('https','http') or not parsed.hostname:
            messagebox.showerror('Thiếu thông tin', 'Nhập tên và URL http/https hợp lệ.')
            return
        self.data['tasks'].append({'name':name,'url':url,'keyword':keyword,'enabled':True,
                                   'status':'Chưa kiểm tra','updated':'—','jan':jan})
        save_data(self.data)
        self.render_tasks()
        for x in (self.name_entry,self.url_entry,self.keyword_entry,self.jan_entry): x.delete(0,'end')

    def selected_index(self):
        if not self.tree.selection():
            messagebox.showinfo('Chọn tác vụ', 'Chọn một dòng trong danh sách trước.')
            return None
        return int(self.tree.selection()[0])

    def open_selected(self):
        idx = self.selected_index()
        if idx is not None: webbrowser.open(self.data['tasks'][idx]['url'])

    def toggle_selected(self):
        idx = self.selected_index()
        if idx is not None:
            t = self.data['tasks'][idx]
            t['enabled'] = not t.get('enabled',True)
            save_data(self.data)
            self.render_tasks()

    def remove_selected(self):
        idx = self.selected_index()
        if idx is not None and messagebox.askyesno('Xóa tác vụ', 'Bạn có chắc muốn xóa tác vụ này?'):
            del self.data['tasks'][idx]
            save_data(self.data)
            self.render_tasks()

    def run_once(self):
        if self.worker and self.worker.is_alive():
            return
        self.worker = threading.Thread(target=self.check_all, daemon=True)
        self.worker.start()

    def check_all(self):
        snapshot = [(t['url'],t['keyword']) for t in self.data['tasks'] if t.get('enabled', True)]
        for url, keyword in snapshot:
            result = fetch_status(url, keyword)
            self.events.put(('result', url, keyword, result, datetime.now().strftime('%H:%M:%S')))
            time.sleep(0.5)
        self.events.put(('log','Đã hoàn thành lượt kiểm tra.'))

    def start(self):
        if self.running: return
        self.running = True
        self.show_page('Giám sát')
        self.schedule_cycle()

    def schedule_cycle(self):
        if not self.running: return
        self.run_once()
        self.after(max(30,int(self.data['interval']))*1000, self.schedule_cycle)

    def stop(self):
        self.running = False
        if self.active_page == 'Giám sát': self.show_page('Giám sát')

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'result':
                    _,url,keyword,status,updated = event
                    for t in self.data['tasks']:
                        if t['url'] == url and t['keyword'] == keyword:
                            t.update(status=status,updated=updated)
                    save_data(self.data)
                    if self.active_page == 'Giám sát': self.render_tasks()
                    if 'Tìm thấy' in status: self.bell()
                elif event[0] == 'update_check':
                    self.update_busy = False
                    self.latest_release = event[1]
                    if self.active_page == 'Cài đặt':
                        self.update_button.configure(state='normal')
                        self.update_msg.configure(text=('Lỗi: ' + event[2]) if event[2] else
                            (f'Có phiên bản mới: v{event[1]["version"]}' if event[1] else 'Bạn đang dùng phiên bản mới nhất.'))
                    if event[1] and not event[2]:
                        self.install_update()
                elif event[0] == 'update_download':
                    self.update_busy = False
                    if event[2]:
                        if self.active_page == 'Cài đặt':
                            self.update_msg.configure(text='Tải thất bại: ' + event[2])
                    elif event[1]:
                        self.apply_downloaded_update(event[1])
                elif event[0] == 'gmail_status':
                    if self.active_page == 'Gmail OTP' and hasattr(self, 'gmail_status'):
                        self.gmail_status.config(text=event[1])
                elif event[0] == 'yamada_status':
                    if self.active_page == 'Yamada Guest' and hasattr(self, 'yamada_status'):
                        self.yamada_status.configure(text=event[1])
                        self.yamada_log_event(event[1])
                elif event[0] == 'discord_signal':
                    content = event[2] if len(event) > 2 else ''
                    self.handle_notification(content, 'Discord Bot')
                elif event[0] == 'discord_url':
                    pass
                elif event[0] == 'discord_state':
                    self.discord_state = event[1]
                    if self.active_page == 'Discord':
                        self.discord_status.configure(text='Trạng thái: ' + self.discord_state)
                elif event[0] == 'log' and self.active_page == 'Giám sát':
                    self.logline.config(text='Nhật ký: '+event[1])
        except queue.Empty:
            pass
        self.after(250, self.poll_events)

    def page_tasks(self):
        self.heading('Tác vụ', 'Quản lý các tác vụ giám sát đã tạo')
        p = self.panel()
        if not self.data['tasks']:
            self.label(p, 'Chưa có tác vụ. Vào Giám sát để thêm liên kết.', 12, MUTED).pack(anchor='w')
        for t in self.data['tasks']:
            self.label(p, f'• {t["name"]}  |  {t.get("status", "Chưa kiểm tra")}', 11).pack(anchor='w', pady=8)
        self.button(p, 'Đi đến giám sát', lambda:self.show_page('Giám sát'), True).pack(anchor='w', pady=10)

    # Shipping profile records are stored separately from payments and credentials.
    def profile_records(self):
        """Convert old profile-name strings to editable dictionaries."""
        records = []
        for item in self.data.get('profiles', []):
            if isinstance(item, str):
                records.append({'label': item})
            elif isinstance(item, dict):
                records.append(item)
        return records

    def page_profiles(self):
        self.heading('Hồ sơ giao hàng Nhật Bản', 'Tạo, sửa và lưu thông tin giao hàng. Không lưu số thẻ, CVV, OTP hoặc mật khẩu.')
        profiles = self.profile_records()
        self.profile_fields = {}
        editor = self.panel()
        self.label(editor, 'Chọn hồ sơ để sửa (hoặc tạo mới)', 11, bold=True).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 7))
        names = ['+ Hồ sơ mới'] + [str(p.get('label', 'Chưa đặt tên')) for p in profiles]
        self.profile_choice = ttk.Combobox(editor, values=names, state='readonly', width=44)
        self.profile_choice.current(0)
        self.profile_choice.grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 12))
        self.profile_choice.bind('<<ComboboxSelected>>', self.load_profile_form)
        fields = [
            ('label', 'Tên hồ sơ *'),
            ('last_name', 'Họ (姓) *'),
            ('first_name', 'Tên (名) *'),
            ('last_kana', 'Họ Katakana (セイ)'),
            ('first_kana', 'Tên Katakana (メイ)'),
            ('postal', 'Mã bưu điện (郵便番号) *'),
            ('prefecture', 'Tỉnh / thành (都道府県) *'),
            ('city', 'Quận, thành phố (市区町村) *'),
            ('address1', 'Địa chỉ / số nhà (丁目・番地) *'),
            ('address2', 'Tòa nhà / số phòng'),
            ('phone', 'Số điện thoại *'),
            ('email', 'Email (tùy chọn)'),
        ]
        for i, (key, title) in enumerate(fields):
            c = i % 2
            r = 2 + (i // 2) * 2
            self.label(editor, title, 10, MUTED).grid(row=r, column=c, sticky='w', padx=(0, 20), pady=(4,2))
            entry = self.entry(editor, 36)
            entry.grid(row=r+1, column=c, sticky='w', padx=(0, 20), pady=(0,6))
            self.profile_fields[key] = entry
        controls = tk.Frame(editor, bg=PANEL)
        controls.grid(row=15, column=0, columnspan=2, sticky='w', pady=(12,4))
        self.button(controls, 'Lưu hồ sơ', self.save_profile, True).pack(side='left', padx=(0,8))
        self.button(controls, 'Hồ sơ mới', self.new_profile).pack(side='left', padx=(0,8))
        self.button(controls, 'Xóa hồ sơ', self.delete_profile).pack(side='left')
        self.label(editor, 'Lưu trong %APPDATA%\\PythonBot\\config.json dưới dạng văn bản thường. Chỉ nhập thông tin của bạn; không chia sẻ file cấu hình.', 9, MUTED, wraplength=760, justify='left').grid(row=16,column=0,columnspan=2,sticky='w',pady=(10,0))
        if profiles:
            self.profile_choice.current(1)
            self.load_profile_form()

    def load_profile_form(self, event=None):
        idx = self.profile_choice.current() - 1
        profiles = self.profile_records()
        profile = profiles[idx] if 0 <= idx < len(profiles) else {}
        for key, widget in self.profile_fields.items():
            widget.delete(0, 'end')
            widget.insert(0, str(profile.get(key, '')))

    def new_profile(self):
        self.profile_choice.current(0)
        self.load_profile_form()

    def save_profile(self):
        import re as _re
        form = {key: widget.get().strip() for key, widget in self.profile_fields.items()}
        required = ('label','last_name','first_name','postal','prefecture','city','address1','phone')
        missing = [key for key in required if not form[key]]
        if missing:
            messagebox.showerror('Hồ sơ', 'Vui lòng nhập đủ các trường có dấu *.')
            return
        postal = form['postal'].replace('-', '')
        if not _re.fullmatch(r'[0-9]{7}', postal):
            messagebox.showerror('Hồ sơ', 'Mã bưu điện Nhật phải gồm 7 chữ số.')
            return
        form['postal'] = postal[:3] + '-' + postal[3:]
        phone = form['phone'].replace('-', '').replace(' ', '')
        if not _re.fullmatch(r'0[0-9]{9,10}', phone):
            messagebox.showerror('Hồ sơ', 'Số điện thoại Nhật cần 10 hoặc 11 chữ số, bắt đầu bằng 0.')
            return
        if form['email'] and not _re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', form['email']):
            messagebox.showerror('Hồ sơ', 'Email không hợp lệ.')
            return
        profiles = self.profile_records()
        idx = self.profile_choice.current() - 1
        if any(i != idx and p.get('label') == form['label'] for i,p in enumerate(profiles)):
            messagebox.showerror('Hồ sơ', 'Tên hồ sơ đã tồn tại.')
            return
        if 0 <= idx < len(profiles):
            profiles[idx] = form
        else:
            profiles.append(form)
        self.data['profiles'] = profiles
        save_data(self.data)
        self.show_page('Hồ sơ')
        self.profile_choice.current(profiles.index(form)+1)
        self.load_profile_form()
        messagebox.showinfo('Hồ sơ', 'Đã lưu hồ sơ giao hàng.')

    def delete_profile(self):
        idx = self.profile_choice.current() - 1
        profiles = self.profile_records()
        if not 0 <= idx < len(profiles):
            return
        if not messagebox.askyesno('Xóa hồ sơ', 'Xóa hồ sơ này?'):
            return
        profiles.pop(idx)
        self.data['profiles'] = profiles
        save_data(self.data)
        self.show_page('Hồ sơ')

    def page_cards(self):
        self.heading('Thẻ - nhập thử', 'Kiểm tra thông tin thẻ trong phiên chạy. Không lưu số thẻ, CVV hay tự thanh toán.')
        p = self.panel()
        self.label(p, 'Tên thẻ / ngân hàng (ví dụ EPOS)', 10, MUTED).pack(anchor='w')
        self.card_label = self.entry(p, 34)
        self.card_label.pack(anchor='w', pady=4)
        self.label(p, '4 số cuối để lưu nhãn thẻ (tùy chọn)', 10, MUTED).pack(anchor='w')
        self.card_last4 = self.entry(p, 12)
        self.card_last4.pack(anchor='w', pady=4)
        self.button(p, 'Lưu tên và 4 số cuối', self.save_card_label).pack(anchor='w', pady=8)
        for card in self.data.get('card_labels', []):
            self.label(p, str(card.get('label','')) + '  •••• ' + str(card.get('last4','')), 11).pack(anchor='w', pady=3)

        test = self.panel()
        self.label(test, 'KIỂM TRA NHẬP THẺ - KHÔNG GỬI ĐẾN WEBSITE', 12, bold=True).pack(anchor='w', pady=(0,8))
        self.label(test, 'Số thẻ (chỉ giữ trong ô nhập đến khi bạn xóa/đóng ứng dụng)', 10, MUTED).pack(anchor='w')
        self.test_pan = self.entry(test, 36)
        self.test_pan.config(show='●', textvariable=self.session_card_pan)
        self.test_pan.pack(anchor='w', pady=4)
        self.label(test, 'Hết hạn MM/YY', 10, MUTED).pack(anchor='w')
        self.test_exp = self.entry(test, 10)
        self.test_exp.config(textvariable=self.session_card_exp)
        self.test_exp.pack(anchor='w', pady=4)
        self.label(test, 'CVV/CVC (không lưu)', 10, MUTED).pack(anchor='w')
        self.test_cvv = self.entry(test, 10)
        self.test_cvv.config(show='●', textvariable=self.session_card_cvv)
        self.test_cvv.pack(anchor='w', pady=4)
        row = tk.Frame(test, bg=PANEL)
        row.pack(anchor='w', pady=9)
        self.button(row, 'Kiểm tra định dạng', self.validate_test_card, True).pack(side='left', padx=(0,9))
        self.button(row, 'Xóa thông tin nhạy cảm', self.clear_test_card).pack(side='left')
        self.card_test_result = self.label(test, 'Chưa kiểm tra', 10, MUTED)
        self.card_test_result.pack(anchor='w', pady=5)
        self.label(test, 'Chỉ kiểm tra định dạng, không xác nhận thẻ tồn tại/hợp lệ để thanh toán. Sử dụng Chrome Autofill cho checkout và nhập CVV, OTP bằng tay.', 10, MUTED, wraplength=780, justify='left').pack(anchor='w', pady=6)
        self.button(test, 'Mở cài đặt thẻ Chrome', self.open_chrome_payments, True).pack(anchor='w', pady=5)
        self.label(test, 'Sau khi thêm thẻ vào Chrome, mở Yamada bằng nút Mở trang Guest (Chrome thông thường). Tại ô thẻ trên checkout, chọn gợi ý Autofill và xác thực theo yêu cầu của ngân hàng.', 10, MUTED, wraplength=780, justify='left').pack(anchor='w', pady=5)

    def open_chrome_payments(self):
        import shutil
        import os
        from pathlib import Path
        candidates = [shutil.which('chrome'), shutil.which('chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES',''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)',''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA',''), 'Google', 'Chrome', 'Application', 'chrome.exe')]
        for executable in candidates:
            if executable and Path(executable).is_file():
                try:
                    subprocess.Popen([executable, 'chrome://settings/payments'])
                    return
                except OSError:
                    continue
        messagebox.showinfo('Chrome Autofill', 'Mở Chrome thông thường và dán: chrome://settings/payments')


    def clear_test_card(self):
        self.session_card_pan.set('')
        self.session_card_exp.set('')
        self.session_card_cvv.set('')
        if hasattr(self, 'card_test_result') and self.card_test_result.winfo_exists():
            self.card_test_result.config(text='Đã xóa thông tin nhạy cảm trong phiên.')

    def validate_test_card(self):
        from datetime import datetime as _dt
        pan = re.sub(r'[ -]', '', self.test_pan.get())
        expiry = self.test_exp.get().strip()
        cvv = self.test_cvv.get().strip()
        errors = []
        if not re.fullmatch(r'[0-9]{12,19}', pan):
            errors.append('Số thẻ cần 12–19 chữ số.')
        else:
            total = 0
            for index, digit in enumerate(reversed(pan)):
                num = int(digit)
                if index % 2:
                    num *= 2
                    if num > 9: num -= 9
                total += num
            if total % 10:
                errors.append('Số thẻ không đạt kiểm tra Luhn.')
        m = re.fullmatch(r'(0[1-9]|1[0-2])/([0-9]{2})', expiry)
        if not m:
            errors.append('Hết hạn theo MM/YY.')
        elif (2000+int(m.group(2)), int(m.group(1))) < (_dt.now().year, _dt.now().month):
            errors.append('Thẻ đã hết hạn.')
        if not re.fullmatch(r'[0-9]{3,4}', cvv):
            errors.append('CVV cần 3 hoặc 4 chữ số.')
        self.card_test_result.config(text='; '.join(errors) if errors else 'Định dạng hợp lệ (chưa xác minh thanh toán).')
        self.card_test_result.config(text='; '.join(errors) if errors else 'Định dạng hợp lệ. Dữ liệu chỉ tồn tại trong phiên; dùng nút Xóa khi xong.')

    def save_card_label(self):
        label, last4 = self.card_label.get().strip(), self.card_last4.get().strip()
        if not label or not re.fullmatch(r'[0-9]{4}', last4):
            messagebox.showerror('Thẻ', 'Nhập tên thẻ và đúng 4 số cuối.')
            return
        cards = self.data.setdefault('card_labels', [])
        if any(x.get('label') == label for x in cards):
            messagebox.showerror('Thẻ', 'Tên thẻ đã tồn tại.')
            return
        cards.append({'label': label, 'last4': last4})
        save_data(self.data)
        self.show_page('Thẻ')

    def page_gmail_otp(self):
        self.heading('Gmail OTP', 'Đọc thư xác minh qua Google OAuth (chỉ đọc), hiển thị mã để nhập thủ công.')
        p = self.panel()
        self.label(p, 'Google OAuth: kết nối Gmail chỉ đọc. Không dùng mật khẩu Gmail hoặc App Password.', 11, MUTED, wraplength=780).pack(anchor='w', pady=6)
        self.label(p, 'Đặt tệp OAuth Desktop client tại %APPDATA%\\PythonBot\\gmail_client_secret.json. Chỉ lưu tệp đó trên máy.', 10, MUTED, wraplength=780, justify='left').pack(anchor='w', pady=6)
        self.label(p, 'Cài: py -m pip install google-auth-oauthlib google-api-python-client', 10, MUTED).pack(anchor='w', pady=6)
        row = tk.Frame(p, bg=PANEL)
        row.pack(anchor='w', pady=10)
        self.button(row, 'Kết nối Gmail (OAuth)', self.gmail_login, True).pack(side='left', padx=(0,8))
        self.button(row, 'Đọc thư OTP mới nhất', self.gmail_check).pack(side='left')
        self.gmail_status = self.label(p, 'Chưa kết nối Gmail.', 11, MUTED, wraplength=780, justify='left')
        self.gmail_status.pack(anchor='w', pady=6)
        self.label(p, 'Chỉ xem các thư gần đây có từ khóa OTP / verification / 認証. Mã không được lưu vào file hoặc tự gửi lên website.', 10, MUTED, wraplength=780, justify='left').pack(anchor='w', pady=8)

    def gmail_login(self):
        credential_file = BASE / 'gmail_client_secret.json'
        if not credential_file.is_file():
            messagebox.showerror('Gmail OAuth', 'Thiếu gmail_client_secret.json. Cần tạo OAuth Desktop Client và bật Gmail API trên Google Cloud.')
            return
        if hasattr(self, 'gmail_status'): self.gmail_status.config(text='Đang mở trình duyệt để đăng nhập Google...')
        def work():
            try:
                from google_auth_oauthlib.flow import InstalledAppFlow
                from googleapiclient.discovery import build
                flow = InstalledAppFlow.from_client_secrets_file(str(credential_file), ['https://www.googleapis.com/auth/gmail.readonly'])
                credentials = flow.run_local_server(port=0, open_browser=True)
                self.gmail_service = build('gmail', 'v1', credentials=credentials, cache_discovery=False)
                self.events.put(('gmail_status', 'Gmail đã kết nối (chỉ đọc). Có thể kiểm tra OTP.'))
            except Exception as exc:
                self.events.put(('gmail_status', 'Không kết nối Gmail: ' + str(exc)[:230]))
        threading.Thread(target=work, daemon=True).start()

    def gmail_check(self):
        service = getattr(self, 'gmail_service', None)
        if service is None:
            messagebox.showinfo('Gmail', 'Hãy kết nối Gmail trước.')
            return
        if hasattr(self, 'gmail_status'): self.gmail_status.config(text='Đang tìm email xác minh trong 1 ngày gần đây...')
        def work():
            try:
                query = 'newer_than:1d (OTP OR "verification code" OR "security code" OR "認証コード" OR "ワンタイム")'
                results = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
                items = results.get('messages', [])
                if not items:
                    self.events.put(('gmail_status', 'Không tìm thấy email xác minh gần đây.'))
                    return
                import base64
                for item in items:
                    msg = service.users().messages().get(userId='me', id=item['id'], format='full').execute()
                    parts = [msg.get('payload', {})]
                    lines = [msg.get('snippet', '')]
                    while parts:
                        part = parts.pop()
                        parts.extend(part.get('parts', []))
                        if part.get('mimeType') == 'text/plain':
                            data = part.get('body', {}).get('data')
                            if data:
                                lines.append(base64.urlsafe_b64decode(data + '=' * (-len(data)%4)).decode('utf-8', 'replace')[:20000])
                    content = '\n'.join(lines)
                    match = re.search(r'(?i)(?:OTP|verification code|security code|認証コード|ワンタイム|確認コード)[^0-9]{0,60}([0-9]{4,8})(?![0-9])',content)
                    if match:
                        self.events.put(('gmail_status', 'Mã xác minh trong email gần đây: ' + match.group(1) + ' — nhập thủ công, không chia sẻ.'))
                        return
                self.events.put(('gmail_status', 'Có thư xác minh nhưng chưa xác định được mã. Hãy kiểm tra trong Gmail.'))
            except Exception as exc:
                self.events.put(('gmail_status', 'Lỗi đọc Gmail: ' + str(exc)[:230]))
        threading.Thread(target=work, daemon=True).start()

    def page_proxy(self):
        self.heading('Proxy', 'Danh mục proxy (bản 0.1 chỉ quản lý nhãn; chưa kết nối qua proxy)')
        p = self.panel()
        self.label(p, 'Để tránh lưu thông tin xác thực không mã hóa, bản này không nhận username/password proxy.',
                   11, MUTED).pack(anchor='w', pady=10)
        self.label(p, 'Hỗ trợ kết nối proxy sẽ được thêm ở bản phát triển tiếp theo.', 11).pack(anchor='w', pady=10)

    def handle_notification(self, content, source='Thông báo'):
        codes = extract_jan(content)
        matching = matches_tasks(content, self.data['tasks'])
        if not matching:
            if hasattr(self, 'jan_result') and self.jan_result.winfo_exists():
                self.jan_result.config(text='Không có tác vụ trùng. Mã: ' + (', '.join(sorted(codes)) or 'không có'))
            return
        if hasattr(self, 'jan_result') and self.jan_result.winfo_exists():
            self.jan_result.config(text='Khớp ' + str(len(matching)) + ' tác vụ: ' + ', '.join(t['name'] for t in matching)[:180])
        for task in matching:
            if not task.get('enabled', True):
                continue
            task['status'] = 'Đang kiểm tra theo JAN/EAN'
            url, keyword = task['url'], task.get('keyword', '')
            def work(u=url, k=keyword):
                result = fetch_status(u, k)
                self.events.put(('result', u, k, result, datetime.now().strftime('%H:%M:%S')))
            threading.Thread(target=work, daemon=True).start()
        if self.active_page == 'Giám sát':
            self.render_tasks()

    def page_jan(self):
        self.heading('Lọc JAN/EAN', 'Chỉ chạy tác vụ có mã 8, 13 hoặc 14 chữ số trùng thông báo. Không tự checkout.')
        p = self.panel()
        self.label(p, 'Dán nội dung thông báo Discord để thử bộ lọc:', 11, bold=True).pack(anchor='w', pady=(0,8))
        self.jan_text = tk.Text(p, height=7, bg='#12141b', fg=FG, insertbackground=FG, relief='flat')
        self.jan_text.pack(fill='x', pady=6)
        self.button(p, 'Kiểm tra và chạy tác vụ trùng JAN', self.test_jan, True).pack(anchor='w', pady=8)
        self.jan_result = self.label(p, 'Chưa kiểm tra', 11, MUTED)
        self.jan_result.pack(anchor='w', pady=8)
        self.label(p, 'Chỉ dùng dữ liệu được cấp quyền: dán thủ công hoặc Discord Bot trong server đã cấp quyền.', 10, MUTED, wraplength=700, justify='left').pack(anchor='w', pady=8)

    def test_jan(self):
        self.handle_notification(self.jan_text.get('1.0', 'end'), 'Dán thử')

    def page_yamada_guest(self):
        self.heading('Yamada Guest - thử riêng', 'Chạy ẩn khi kiểm tra và thử thêm giỏ; thanh toán và 3D Secure cần mở Chrome để xác nhận.')
        p = self.panel()
        self.label(p, 'Link sản phẩm Yamada Webcom:', 11, bold=True).pack(anchor='w', pady=(0,7))
        self.yamada_url = self.entry(p, 85)
        self.yamada_url.insert(0, self.data.get('yamada_guest_url', ''))
        self.yamada_url.pack(anchor='w', pady=6)
        self.label(p, 'Hồ sơ giao hàng (chọn để quản lý, chưa tự điền website):', 10, MUTED).pack(anchor='w', pady=(12,4))
        self.yamada_profile = ttk.Combobox(p, state='readonly', width=40,
            values=['Chưa chọn'] + [str(v.get('label','')) for v in self.profile_records()])
        self.yamada_profile.current(0)
        self.yamada_profile.pack(anchor='w', pady=4)
        sec = self.panel()
        self.label(sec, 'THẺ TRONG PHIÊN (KHÔNG LƯU VÀO FILE)', 12, bold=True).pack(anchor='w', pady=(0,7))
        self.label(sec, 'Số thẻ', 10, MUTED).pack(anchor='w')
        pan_entry = self.entry(sec, 40)
        pan_entry.config(show='●', textvariable=self.session_card_pan)
        pan_entry.pack(anchor='w', pady=3)
        self.label(sec, 'Hết hạn (MM/YY)', 10, MUTED).pack(anchor='w')
        expiry_entry = self.entry(sec, 12)
        expiry_entry.config(textvariable=self.session_card_exp)
        expiry_entry.pack(anchor='w', pady=3)
        self.label(sec, 'CVV/CVC', 10, MUTED).pack(anchor='w')
        cvv_entry = self.entry(sec, 12)
        cvv_entry.config(show='●', textvariable=self.session_card_cvv)
        cvv_entry.pack(anchor='w', pady=3)
        self.button(sec, 'Xóa dữ liệu thẻ trong phiên', self.clear_test_card).pack(anchor='w', pady=7)
        self.label(sec, 'Các ô này chỉ dùng để chuẩn bị và kiểm tra nhập liệu. Phiên bản này chưa tự chuyển số thẻ hoặc CVV vào checkout Yamada, chưa tự đặt hàng.', 10, MUTED, wraplength=730, justify='left').pack(anchor='w', pady=5)
        self.label(p, 'Chế độ thử an toàn: mở trang và thử thêm giỏ; luôn dừng trước xác nhận đơn hàng.', 10, MUTED, wraplength=740).pack(anchor='w', pady=7)
        row = tk.Frame(p, bg=PANEL)
        row.pack(anchor='w', pady=10)
        self.button(row, 'Mở trang Guest (Chrome)', self.yamada_open_guest, True).pack(side='left', padx=(0,8))
        self.button(row, 'Thử AutoCart ẩn', self.yamada_autocart_test).pack(side='left')
        self.yamada_status = self.label(p, 'Chưa chạy thử.', 11, MUTED, wraplength=750, justify='left')
        self.yamada_status.pack(anchor='w', pady=10)
        self.label(p, 'AutoCart ẩn cần Playwright và Chrome. Trình duyệt ẩn không thể hiện riêng cửa sổ 3DS mà giữ nguyên phiên giao dịch; mở Chrome thường để tiếp tục thanh toán và xác thực.', 10, MUTED, wraplength=750, justify='left').pack(anchor='w', pady=5)
        history = self.panel()
        self.label(history, 'NHẬT KÝ YAMADA GUEST', 12, bold=True).pack(anchor='w', pady=(0,7))
        self.yamada_log = tk.Text(history, height=10, bg='#0b0d12', fg='#cbd4e1', insertbackground='white',
                                  font=('Consolas', 10), state='disabled', wrap='word', relief='flat')
        self.yamada_log.pack(fill='both', expand=True)
        self.yamada_log_event('Sẵn sàng. Chưa thực hiện giao dịch.')
        self.label(history, 'Không hiển thị, lưu hoặc ghi nhật ký số thẻ, CVV và OTP.', 10, MUTED).pack(anchor='w', pady=5)

    def yamada_log_event(self, detail):
        if hasattr(self, 'yamada_log') and self.yamada_log.winfo_exists():
            self.yamada_log.config(state='normal')
            self.yamada_log.insert('end', '[' + datetime.now().strftime('%H:%M:%S') + '] ' + detail + '\n')
            self.yamada_log.see('end')
            self.yamada_log.config(state='disabled')


    def yamada_validate_url(self):
        url = self.yamada_url.get().strip()
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or host not in ('www.yamada-denkiweb.com','yamada-denkiweb.com'):
            messagebox.showerror('Yamada Guest', 'Chỉ chấp nhận URL HTTPS của www.yamada-denkiweb.com')
            return None
        self.data['yamada_guest_url'] = url
        save_data(self.data)
        return url

    def yamada_open_guest(self):
        url = self.yamada_validate_url()
        if not url:
            return
        webbrowser.open(url)
        self.yamada_log_event('Đã mở trang sản phẩm bằng trình duyệt mặc định.')
        self.yamada_status.configure(text='Đã mở trang trong trình duyệt mặc định. Nếu Chrome là mặc định và đã lưu thẻ, Chrome có thể đề xuất Autofill ở bước thanh toán. Bạn tự xác nhận CVV/3DS.')

    def yamada_autocart_test(self):
        url = self.yamada_validate_url()
        if not url:
            return
        self.yamada_status.configure(text='Đang kiểm tra Yamada ẩn...')
        self.yamada_log_event('Bắt đầu thử kết nối Yamada bằng Chrome ẩn.')
        def emit(msg):
            self.events.put(('yamada_status', msg))
        def work():
            try:
                from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError
                with sync_playwright() as p:
                    # Retry only when the HTTP/2 transport fails. A fresh browser is required.
                    for attempt in range(2):
                        launch_args = ['--disable-http2'] if attempt else []
                        browser = None
                        try:
                            browser = p.chromium.launch(channel='chrome', headless=True,
                                                        args=launch_args, timeout=20000)
                            context = browser.new_context(locale='ja-JP')
                            page = context.new_page()
                            try:
                                response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
                            except PWError as exc:
                                detail = str(exc)
                                if 'ERR_HTTP2_PROTOCOL_ERROR' in detail and attempt == 0:
                                    emit('Kết nối HTTP/2 thất bại. Thử lại một lần bằng HTTP/1.1...')
                                    continue
                                if 'ERR_HTTP2_PROTOCOL_ERROR' in detail:
                                    emit('Lỗi giao thức mạng vẫn còn. Hãy thử mở Yamada trong Chrome thường, kiểm tra VPN/proxy và mạng.')
                                else:
                                    emit('Không mở được trang Yamada: ' + detail[:180])
                                return
                            if response and response.status >= 400:
                                emit('Yamada trả về HTTP ' + str(response.status) + '. Dừng kiểm tra.')
                                return
                            host = (urlparse(page.url).hostname or '').lower()
                            if host not in ('www.yamada-denkiweb.com', 'yamada-denkiweb.com'):
                                emit('Trang chuyển sang miền khác. Dừng để kiểm tra thủ công.')
                                return
                            emit('Đã tải trang. Đang tìm nút thêm giỏ...')
                            selectors = (
                                page.get_by_role('button', name=re.compile('カートに入れる|カートへ入れる|カートに追加')),
                                page.get_by_role('link', name=re.compile('カートに入れる|カートへ入れる|カートに追加')),
                                page.locator('input[type=submit][value*="カート"]')
                            )
                            clicked = False
                            for candidate in selectors:
                                try:
                                    if candidate.count() and candidate.first.is_visible() and candidate.first.is_enabled():
                                        candidate.first.click(timeout=3500)
                                        clicked = True
                                        break
                                except PWError:
                                    continue
                            emit('Đã thử thêm vào giỏ; chưa đặt hàng hoặc thanh toán.' if clicked
                                 else 'Không tìm thấy nút thêm giỏ khả dụng. Hãy kiểm tra trang bằng Chrome thường.')
                            return
                        except PWTimeout:
                            emit('Yamada phản hồi quá chậm. Dừng tác vụ; có thể thử lại hoặc đổi mạng.')
                            return
                        except Exception as exc:
                            emit('Lỗi Chrome ẩn: ' + str(exc)[:200])
                            return
                        finally:
                            if browser:
                                try:
                                    browser.close()
                                except Exception:
                                    pass
            except ImportError:
                emit('Thiếu Playwright: py -m pip install playwright')
            except Exception as exc:
                emit('Lỗi kiểm tra: ' + str(exc)[:200])
        threading.Thread(target=work, daemon=True).start()

    def page_discord(self):
        self.heading('Discord', 'Tự thêm và giám sát liên kết nhận từ kênh Discord được cấp quyền')
        p = self.panel()
        self.label(p, 'Trạng thái: ' + self.discord_state, 12, GREEN, bold=True).pack(anchor='w', pady=6)
        self.discord_status = p.winfo_children()[-1]
        self.label(p, 'Channel ID (chỉ theo dõi kênh này):', 10, MUTED).pack(anchor='w', pady=(12, 4))
        self.channel_entry = self.entry(p, 45)
        self.channel_entry.insert(0, self.data.get('discord_channel_id', ''))
        self.channel_entry.pack(anchor='w', pady=4)
        self.discord_start_var = tk.BooleanVar(value=self.data.get('discord_auto_start', True))
        self.discord_monitor_var = tk.BooleanVar(value=self.data.get('discord_auto_monitor', True))
        self.discord_trigger_var = tk.BooleanVar(value=self.data.get('discord_trigger_on_message', True))
        for var, txt in ((self.discord_start_var, 'Kết nối Discord khi mở Python Bot'),
                         (self.discord_monitor_var, 'Tự bắt đầu giám sát khi có link mới'),
                         (self.discord_trigger_var, 'Chỉ chạy khi tin nhắn chứa JAN/EAN trùng tác vụ')):
            tk.Checkbutton(p, text=txt, variable=var, bg=PANEL, fg=FG,
                           activebackground=PANEL, activeforeground=FG,
                           selectcolor='#333741').pack(anchor='w', pady=6)
        row = tk.Frame(p, bg=PANEL)
        row.pack(anchor='w', pady=12)
        self.button(row, 'Lưu cài đặt', self.save_discord_settings, True).pack(side='left', padx=(0, 8))
        self.button(row, 'Kết nối Discord', self.connect_discord).pack(side='left')
        self.label(p, 'Đặt token Bot trong biến môi trường PYTHON_BOT_DISCORD_TOKEN (không dùng token người dùng).',
                   10, MUTED, wraplength=740, justify='left').pack(anchor='w', pady=8)
        self.label(p, 'Discord Developer Portal: bật Message Content Intent, thêm Bot vào server và cấp View Channel, Read Message History.',
                   10, MUTED, wraplength=740, justify='left').pack(anchor='w', pady=8)
        self.label(p, 'Trong server đã cấp quyền: nhận JAN/EAN từ tin nhắn / embed; chỉ kiểm tra tác vụ trùng mã. Không tự mua hàng.',
                   10, MUTED, wraplength=740, justify='left').pack(anchor='w', pady=8)

    def save_discord_settings(self):
        channel = self.channel_entry.get().strip()
        if channel and not (channel.isascii() and channel.isdecimal() and 15 <= len(channel) <= 22):
            messagebox.showerror('Channel ID', 'Channel ID phải gồm 15-22 chữ số.')
            return False
        self.data['discord_channel_id'] = channel
        self.data['discord_auto_start'] = self.discord_start_var.get()
        self.data['discord_auto_monitor'] = self.discord_monitor_var.get()
        self.data['discord_trigger_on_message'] = self.discord_trigger_var.get()
        save_data(self.data)
        self.discord_state = 'Đã lưu thiết lập. Kết nối lại để đổi kênh.'
        self.discord_status.configure(text='Trạng thái: ' + self.discord_state)
        return True

    def maybe_start_discord(self):
        if self.data.get('discord_auto_start') and self.data.get('discord_channel_id'):
            self.connect_discord()

    def connect_discord(self):
        if self.active_page == 'Discord' and not self.save_discord_settings():
            return
        if self.discord_listener and self.discord_listener.is_alive():
            self.events.put(('discord_state', 'Đã kết nối hoặc đang kết nối. Khởi động lại ứng dụng để đổi kênh.'))
            return
        channel = self.data.get('discord_channel_id', '')
        if not channel:
            self.events.put(('discord_state', 'Chưa có Channel ID.'))
            return
        try:
            from discord_listener import listen
        except ImportError:
            self.events.put(('discord_state', 'Thiếu discord.py. Cài: py -m pip install discord.py'))
            return
        self.discord_listener = threading.Thread(target=listen, args=(self.events, channel), daemon=True)
        self.discord_listener.start()

    def page_settings(self):
        self.heading('Cài đặt', f'Python Bot v{VERSION}')
        p = self.panel()
        self.label(p, 'Thời gian giữa các lượt kiểm tra (giây, tối thiểu 30):', 11).pack(anchor='w', pady=6)
        self.interval_entry = self.entry(p, 10)
        self.interval_entry.insert(0,str(self.data['interval']))
        self.interval_entry.pack(anchor='w', pady=5)
        self.button(p, 'Lưu cài đặt', self.save_settings, True).pack(anchor='w', pady=8)
        self.label(p, 'Tập tin cấu hình: '+str(DATA_FILE), 10, MUTED,
                   wraplength=700, justify='left').pack(anchor='w', pady=8)
        self.label(p, 'Lưu ý: Không lưu thẻ ngân hàng, OTP hoặc mật khẩu vào ứng dụng.', 10, MUTED).pack(anchor='w')
        upd = self.panel()
        self.label(upd, 'CẬP NHẬT PHẦN MỀM', 12, bold=True).pack(anchor='w', pady=(0,8))
        self.label(upd, 'Nguồn: GitHub Releases / namnguyen1956868-blip / Python-Bot-Updates', 10, MUTED).pack(anchor='w', pady=6)
        self.update_button = self.button(upd, 'UPDATE — Kiểm tra và cài đặt', self.check_updates, True)
        self.update_button.pack(anchor='w', pady=8)
        self.update_msg = self.label(self.main, 'Bấm UPDATE để kiểm tra phiên bản mới.', 10, MUTED)
        self.update_msg.pack(anchor='w', padx=25, pady=8)

    def check_updates(self):
        if self.update_busy:
            return
        self.update_busy = True
        self.update_button.configure(state='disabled')
        self.update_msg.configure(text='Đang kiểm tra GitHub Releases...')
        def work():
            try:
                found = check_release(VERSION)
                self.events.put(('update_check', found, None))
            except Exception as exc:
                self.events.put(('update_check', None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def install_update(self):
        manifest = self.latest_release
        if not manifest or self.update_busy:
            return
        if not messagebox.askyesno('Cập nhật', f'Tải và cài Python Bot v{manifest["version"]}?\nỨng dụng sẽ tự khởi động lại.'):
            return
        self.update_busy = True
        self.update_button.configure(state='disabled')
        self.update_msg.configure(text='Đang tải bản cập nhật và xác minh SHA-256...')
        def work():
            try:
                archive = download_release(manifest)
                self.events.put(('update_download', str(archive), None))
            except Exception as exc:
                self.events.put(('update_download', None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def apply_downloaded_update(self, path):
        folder = Path(__file__).resolve().parent
        script = folder / 'apply_update.py'
        if not script.is_file():
            messagebox.showerror('Thiếu file', 'Không tìm thấy apply_update.py')
            return
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            subprocess.Popen([sys.executable, str(script), path, str(folder), str(os.getpid())],
                             cwd=str(folder), creationflags=flags)
            self.on_close()
        except OSError as exc:
            messagebox.showerror('Cập nhật thất bại', str(exc))

    def save_settings(self):
        try:
            value = int(self.interval_entry.get())
            if value < 30: raise ValueError()
        except ValueError:
            messagebox.showerror('Không hợp lệ','Nhập số nguyên từ 30 giây trở lên.')
            return
        self.data['interval'] = value
        save_data(self.data)
        messagebox.showinfo('Đã lưu','Đã cập nhật cài đặt. Dừng/bắt đầu lại giám sát để áp dụng chu kỳ mới.')

    def on_close(self):
        self.clear_test_card()
        self.running = False
        self.destroy()


if __name__ == '__main__':
    PythonBot().mainloop()
