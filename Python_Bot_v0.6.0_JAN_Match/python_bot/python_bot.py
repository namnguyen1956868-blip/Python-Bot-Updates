"""Python Bot v0.6.0 - desktop website monitor (standard library only)."""
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
from jan_match import extract_jan, matches_tasks

APP_NAME = 'Python Bot'
VERSION = '0.6.0'
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
        for name in ('Tổng quan', 'Giám sát', 'Tác vụ', 'Hồ sơ', 'Proxy', 'Discord', 'JAN/EAN', 'Cài đặt'):
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
                'Tác vụ':'tasks','Hồ sơ':'profiles','Proxy':'proxy','Discord':'discord','JAN/EAN':'jan','Cài đặt':'settings'}[name])()

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
        self.label(form, 'JAN/EAN của sản phẩm (8, 13 hoặc 14 số):', 10, MUTED).grid(row=3, column=0, columnspan=2, sticky='w', pady=(9,3))
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
        if not re.fullmatch(r'(?:[0-9]{8}|[0-9]{13}|[0-9]{14})', jan or ''):
            messagebox.showerror('JAN/EAN', 'Cần nhập đúng mã JAN/EAN gồm 8, 13 hoặc 14 chữ số.')
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
                elif event[0] == 'discord_signal':
                    # Authorized bot signal: exact JAN matching; never run all tasks.
                    text = event[2] if len(event) > 2 else ''
                    self.handle_notification(text, 'Discord Bot')
                elif event[0] == 'discord_url':
                    # Do not create unmatched tasks from notification URLs.
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

    def page_profiles(self):
        self.heading('Hồ sơ', 'Lưu tên hồ sơ để tổ chức công việc. Không lưu mật khẩu hoặc thông tin thẻ.')
        p = self.panel()
        self.profile_entry = self.entry(p, 38)
        self.profile_entry.pack(side='left', padx=(0,10))
        self.button(p, '+ Tạo hồ sơ', self.add_profile, True).pack(side='left')
        listing = self.panel()
        for name in self.data['profiles']:
            self.label(listing, '◉  '+name, 12).pack(anchor='w', pady=7)
        if not self.data['profiles']: self.label(listing, 'Chưa có hồ sơ.', 11, MUTED).pack(anchor='w')

    def add_profile(self):
        value = self.profile_entry.get().strip()
        if value and value not in self.data['profiles']:
            self.data['profiles'].append(value)
            save_data(self.data)
            self.show_page('Hồ sơ')

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
            self.events.put(('log', f'{source}: không có JAN/EAN trùng tác vụ; bỏ qua. Mã: {", ".join(sorted(codes)) or "không có"}'))
            if hasattr(self, 'jan_result') and self.jan_result.winfo_exists():
                self.jan_result.config(text='Không có tác vụ trùng. Mã nhận được: ' + (', '.join(sorted(codes)) or 'không có'))
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
        self.events.put(('log', f'{source}: đã kích hoạt {len(matching)} tác vụ trùng JAN/EAN'))
        if self.active_page == 'Giám sát': self.render_tasks()

    def page_jan(self):
        self.heading('Lọc JAN/EAN', 'Chỉ chạy tác vụ có mã 8, 13 hoặc 14 chữ số trùng thông báo. Không tự checkout.')
        p = self.panel()
        self.label(p, 'Dán nội dung thông báo Discord để thử bộ lọc:', 11, bold=True).pack(anchor='w', pady=(0,8))
        self.jan_text = tk.Text(p, height=7, bg='#12141b', fg=FG, insertbackground=FG, relief='flat')
        self.jan_text.pack(fill='x', pady=6)
        self.button(p, 'Kiểm tra và chạy tác vụ trùng JAN', self.test_jan, True).pack(anchor='w', pady=8)
        self.jan_result = self.label(p, 'Chưa kiểm tra', 11, MUTED)
        self.jan_result.pack(anchor='w', pady=8)
        self.label(p, 'Chỉ dùng dữ liệu được cấp quyền: dán thủ công hoặc Discord Bot trong server đã cấp quyền. Không thể tự đọc nội dung JHG khi chỉ là thành viên.', 10, MUTED, wraplength=700, justify='left').pack(anchor='w', pady=8)

    def test_jan(self):
        self.handle_notification(self.jan_text.get('1.0', 'end'), 'Dán thử')

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
        self.running = False
        self.destroy()


if __name__ == '__main__':
    PythonBot().mainloop()
