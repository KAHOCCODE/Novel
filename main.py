"""Compact desktop downloader: queue above a large live journal."""
import os
import sys
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
from core.storage import read_json, atomic_json
from core.plugin_manager import PluginManager
from core.tasks import TaskManager, LABELS, ACTIVE

ROOT = Path(__file__).resolve().parent
from core.local_data import prepare_data
DATA = prepare_data(ROOT)
FONT = 'Segoe UI' if sys.platform == 'win32' else 'DejaVu Sans'
MONO = 'Consolas' if sys.platform == 'win32' else 'DejaVu Sans Mono'
BG, WHITE, INK, MUTED, BORDER, TEAL = '#F2F5F7', '#FFFFFF', '#163340', '#617986', '#DCE5EA', '#087F8C'
MODES = {'Tự động · tải đủ các phần': 'auto', 'HTTP · không chạy Chrome': 'http', 'Chromium chạy nền · không cửa sổ': 'background', 'Chromium hiện cửa sổ · xác minh': 'browser'}
ctk.set_appearance_mode('Light')


def open_path(path):
    path = str(Path(path).resolve())
    if sys.platform == 'win32': os.startfile(path)
    elif sys.platform == 'darwin': subprocess.Popen(['open', path])
    else: subprocess.Popen(['xdg-open', path])


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('Novel Downloader 5.1.1 · Hàng đợi & nhật ký')
        self.geometry(f'{min(1240, self.winfo_screenwidth()-40)}x{min(790, self.winfo_screenheight()-90)}')
        self.minsize(940, 620)
        self.configure(fg_color=BG)
        DATA.mkdir(parents=True, exist_ok=True)
        self.settings = read_json(DATA/'settings.json', {})
        self.boot_logs = []
        self.plugins = PluginManager(self.boot_logs.append)
        self.manager = TaskManager(DATA, self.plugins)
        self.selected_id = None
        self.last_log_lines = []
        self.log_task_id = None
        self.closing = False
        self.focus_log = False
        self.url = tk.StringVar()
        self.folder = tk.StringVar(value=self.settings.get('folder', str(ROOT/'Downloads')))
        self.source = tk.StringVar(value='Tự động')
        self.output = tk.StringVar(value='TXT · từng chương')
        self.interval = tk.StringVar(value=str(self.settings.get('interval', 3)))
        self.mode = tk.StringVar(value=self.settings.get('mode', next(iter(MODES))))
        if self.mode.get() not in MODES: self.mode.set(next(iter(MODES)))
        self.warp_auto = tk.BooleanVar(value=self.settings.get('warp_auto', False))
        self.warp_port = tk.StringVar(value=str(self.settings.get('warp_port', 40000)))
        self.mature = tk.BooleanVar(value=False)
        self.follow = tk.BooleanVar(value=True)
        self.autoscroll = tk.BooleanVar(value=True)
        self.display_url = tk.StringVar()
        self._build()
        self.url.trace_add('write', lambda *_: self.detect())
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        self.after(200, self.poll)

    def label(self, parent, text, size=13, color=INK, bold=False, **kw):
        return ctk.CTkLabel(parent, text=text, text_color=color, font=(FONT, size, 'bold' if bold else 'normal'), **kw)

    def button(self, parent, text, command, primary=False, width=100):
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=32, corner_radius=6,
                            fg_color=TEAL if primary else '#E7EEF2', hover_color='#086976' if primary else '#D6E3EA',
                            text_color=WHITE if primary else INK, font=(FONT, 12))

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        head = ctk.CTkFrame(self, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=16, pady=(10, 5))
        self.label(head, 'ND /', 22, TEAL, True).pack(side='left', padx=(0, 12))
        self.label(head, 'Hàng đợi & nhật ký', 19, bold=True).pack(side='left')
        self.button(head, 'Nguồn & plugin', self.sources, width=122).pack(side='right')
        self.button(head, 'Tùy chọn', self.options, width=85).pack(side='right', padx=6)
        self.count_label = self.label(head, '', 12, MUTED)
        self.count_label.pack(side='right', padx=12)
        card = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
        card.grid(row=1, column=0, sticky='ew', padx=16, pady=3)
        card.grid_columnconfigure(0, weight=1)
        line = ctk.CTkFrame(card, fg_color='transparent')
        line.grid(row=0, column=0, sticky='ew', padx=10, pady=(8, 2))
        line.grid_columnconfigure(0, weight=1)
        self.link_entry = ctk.CTkEntry(line, textvariable=self.url, height=34, border_color=BORDER)
        self.link_entry.grid(row=0, column=0, sticky='ew', padx=(0, 6))
        self.link_entry.bind('<Return>', lambda _: self.add())
        self.button(line, 'Dán link', self.paste, width=70).grid(row=0, column=1, padx=4)
        self.button(line, '+ Thêm truyện', self.add, True, width=116).grid(row=0, column=2)
        sub = ctk.CTkFrame(card, fg_color='transparent')
        sub.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 6))
        self.detect_label = self.label(sub, 'Dán link truyện/chương đầu để nhận diện.', 11, MUTED)
        self.detect_label.pack(side='left')
        self.mode_label = self.label(sub, self.mode.get(), 11, TEAL)
        self.mode_label.pack(side='right')
        self.banner = self.label(self, 'Sẵn sàng. Thêm truyện rồi chạy hàng đợi.', 12, TEAL, anchor='w')
        self.banner.grid(row=2, column=0, sticky='ew', padx=19, pady=(3, 6))
        self.pane = tk.PanedWindow(self, orient=tk.VERTICAL, bg=BG, sashwidth=7, bd=0)
        self.pane.grid(row=3, column=0, sticky='nsew', padx=16, pady=(0, 12))
        self.queue_frame = ctk.CTkFrame(self.pane, fg_color=WHITE, corner_radius=8)
        self.queue_frame.grid_columnconfigure(0, weight=1)
        self.queue_frame.grid_rowconfigure(1, weight=1)
        tools = ctk.CTkFrame(self.queue_frame, fg_color='transparent')
        tools.grid(row=0, column=0, sticky='ew', padx=8, pady=6)
        for text, command, primary, width in [('Chạy hàng đợi', self.run_queue, True, 118), ('Tạm dừng', self.pause, False, 90), ('Dừng', self.stop, False, 64), ('Tiếp tục tải', self.retry, False, 103), ('Mở thư mục', self.open_result, False, 100)]:
            button = self.button(tools, text, command, primary, width)
            button.pack(side='left', padx=(0, 6))
            if text == 'Tạm dừng': self.pause_btn = button
        self.button(tools, 'Bỏ tác vụ', self.remove, width=85).pack(side='right')
        self.clean_btn = self.button(tools, 'Dọn đã xong', self.clear_completed, width=108)
        self.clean_btn.pack(side='right', padx=6)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', background=WHITE, fieldbackground=WHITE, foreground=INK, rowheight=29, borderwidth=0, font=(FONT, 10))
        style.configure('Treeview.Heading', background='#EDF3F6', foreground=MUTED, font=(FONT, 10, 'bold'), relief='flat')
        style.map('Treeview', background=[('selected', '#DDF2F0')], foreground=[('selected', INK)])
        self.tree = ttk.Treeview(self.queue_frame, columns=('title', 'state', 'count', 'plugin'), show='headings', selectmode='browse', height=3)
        for key, text, width in [('title', 'TRUYỆN / NGUỒN', 370), ('state', 'TRẠNG THÁI', 160), ('count', 'ĐÃ LƯU', 75), ('plugin', 'PLUGIN', 190)]:
            self.tree.heading(key, text=text); self.tree.column(key, width=width, minwidth=65)
        self.tree.grid(row=1, column=0, sticky='nsew', padx=(8, 0), pady=(0, 8))
        scroll = ttk.Scrollbar(self.queue_frame, command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky='ns', padx=(0, 5), pady=(0, 8))
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.tree.bind('<Button-1>', lambda _: self.follow.set(False))
        self.tree.bind('<Key>', lambda _: self.follow.set(False))
        self.pane.add(self.queue_frame, minsize=110, height=135, stretch='never')
        detail = ctk.CTkFrame(self.pane, fg_color=WHITE, corner_radius=8)
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(3, weight=1)
        bar = ctk.CTkFrame(detail, fg_color='transparent')
        bar.grid(row=0, column=0, sticky='ew', padx=10, pady=(6, 2))
        self.detail_title = self.label(bar, 'NHẬT KÝ', 13, bold=True)
        self.detail_title.pack(side='left', padx=(0, 12))
        ctk.CTkCheckBox(bar, text='Theo tác vụ đang chạy', variable=self.follow, command=self.refresh, width=168, font=(FONT, 11), checkbox_width=17, checkbox_height=17).pack(side='left', padx=5)
        ctk.CTkCheckBox(bar, text='Tự cuộn', variable=self.autoscroll, width=82, font=(FONT, 11), checkbox_width=17, checkbox_height=17).pack(side='left', padx=5)
        self.expand_btn = self.button(bar, 'Phóng nhật ký', self.expand_log, width=110)
        self.expand_btn.pack(side='right')
        self.button(bar, 'Lưu log', self.export_log, width=75).pack(side='right', padx=6)
        row = ctk.CTkFrame(detail, fg_color='transparent')
        row.grid(row=1, column=0, sticky='ew', padx=10, pady=3)
        row.grid_columnconfigure(1, weight=1)
        self.label(row, 'Link hiện tại / lỗi:', 11, MUTED).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkEntry(row, textvariable=self.display_url, state='readonly', height=28, border_color=BORDER).grid(row=0, column=1, sticky='ew')
        self.button(row, 'Chép link', self.copy_url, width=79).grid(row=0, column=2, padx=(6, 0))
        self.verify_btn = self.button(row, 'Đã xác minh', self.verify, True, width=108)
        self.verify_btn.grid(row=0, column=3, padx=(6, 0)); self.verify_btn.grid_remove()
        self.detail_status = self.label(detail, 'Chọn tác vụ để xem nhật ký.', 11, MUTED, anchor='w')
        self.detail_status.grid(row=2, column=0, sticky='ew', padx=12, pady=2)
        log_frame = tk.Frame(detail, bg='#F7FAFC')
        log_frame.grid(row=3, column=0, sticky='nsew', padx=8, pady=(0, 8))
        log_frame.grid_columnconfigure(0, weight=1); log_frame.grid_rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap='word', font=(MONO, 11), bg='#F7FAFC', fg='#274654', relief='flat', padx=9, pady=8, height=10, state='disabled', selectbackground='#B8E4E3')
        self.log.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(log_frame, command=self.log.yview); sb.grid(row=0, column=1, sticky='ns')
        self.log.configure(yscrollcommand=sb.set)
        self.log.tag_configure('error', foreground='#B42D32')
        self.log.tag_configure('success', foreground='#087864')
        self.log.tag_configure('warn', foreground='#9D6500')
        self.log.tag_configure('link', foreground='#2765A2')
        self.pane.add(detail, minsize=220, stretch='always')

    def notify(self, message, error=False):
        self.banner.configure(text=message[:170], text_color='#B42D32' if error else TEAL)

    def detect(self):
        try:
            handler = self.plugins.find_handler(self.url.get().strip()) if self.source.get() == 'Tự động' else self.plugins.plugin_map.get(self.source.get())
            matched = handler and handler.can_handle(self.url.get().strip())
        except Exception:
            matched = False
        self.detect_label.configure(text=f'Nguồn: {handler.get_display_name()}' if matched else 'Dán link truyện/chương đầu để nhận diện.')
        self.mode_label.configure(text=self.mode.get())
        if not matched or handler.__class__.__name__ != 'FanFicFarePublicCrawler': self.output.set('TXT · từng chương')

    def paste(self):
        try: self.url.set(self.clipboard_get().strip())
        except tk.TclError: self.notify('Bộ nhớ tạm chưa có link.', True)

    def add(self):
        try:
            interval = float(self.interval.get())
            if not 1 <= interval <= 300: raise ValueError('Thời gian nghỉ phải từ 1 đến 300 giây.')
            task = self.manager.add(self.url.get().strip(), self.folder.get(), self.source.get(), self.output.get(), interval, self.mature.get(), connection_mode=MODES[self.mode.get()], network_mode='warp_auto' if self.warp_auto.get() else 'direct', warp_port=int(self.warp_port.get()))
            if not self.manager.active_id:
                self.selected_id = task['id']
            self.save_settings()
            self.url.set(''); self.refresh()
            self.notify('Đã thêm truyện. Chạy hàng đợi để bắt đầu.')
        except Exception as exc: self.notify(str(exc), True)

    def save_settings(self):
        self.settings.update(folder=self.folder.get(), interval=float(self.interval.get()), mode=self.mode.get(), warp_auto=self.warp_auto.get(), warp_port=int(self.warp_port.get()))
        atomic_json(DATA/'settings.json', self.settings)

    def options(self):
        variables = [self.mode, self.folder, self.source, self.output, self.interval, self.mature, self.warp_auto, self.warp_port]
        old_values = [v.get() for v in variables]
        win = ctk.CTkToplevel(self); win.title('Tùy chọn tải'); win.geometry('680x640'); win.transient(self); win.grab_set()
        def cancel():
            for var, value in zip(variables, old_values): var.set(value)
            self.detect(); win.destroy()
        win.protocol('WM_DELETE_WINDOW', cancel)
        body = ctk.CTkFrame(win, fg_color='transparent'); body.pack(fill='both', expand=True, padx=20, pady=14)
        body.grid_columnconfigure(0, weight=1)
        self.label(body, 'Cách tải', 14, bold=True).grid(row=0, column=0, sticky='w')
        ctk.CTkOptionMenu(body, variable=self.mode, values=list(MODES), width=590).grid(row=1, column=0, sticky='ew', pady=(3, 6))
        self.label(body, 'Tự động: tải trực tiếp; gặp phần JavaScript sẽ dùng Chromium chạy nền.\nHTTP chỉ dùng link trực tiếp. Chế độ hiện cửa sổ cho phép xác minh thủ công.', 11, MUTED, justify='left', wraplength=600).grid(row=2, column=0, sticky='w')
        self.label(body, 'Nơi lưu mặc định cho truyện thêm mới', 12, bold=True).grid(row=3, column=0, sticky='w', pady=(10, 2))
        folderrow = ctk.CTkFrame(body, fg_color='transparent'); folderrow.grid(row=4, column=0, sticky='ew'); folderrow.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(folderrow, textvariable=self.folder).grid(row=0, column=0, sticky='ew', padx=(0, 6))
        def choose():
            path = filedialog.askdirectory(parent=win)
            if path: self.folder.set(path)
        self.button(folderrow, 'Chọn…', choose, width=70).grid(row=0, column=1)
        self.label(body, 'Plugin', 12, bold=True).grid(row=5, column=0, sticky='w', pady=(8, 2))
        ctk.CTkOptionMenu(body, variable=self.source, values=['Tự động']+self.plugins.get_plugin_names(), width=590).grid(row=6, column=0, sticky='ew')
        row = ctk.CTkFrame(body, fg_color='transparent'); row.grid(row=7, column=0, sticky='ew', pady=12)
        self.label(row, 'Nghỉ giữa lượt tải (giây):', 12).pack(side='left')
        ctk.CTkEntry(row, textvariable=self.interval, width=70).pack(side='left', padx=8)
        ctk.CTkOptionMenu(row, variable=self.output, values=['TXT · từng chương', 'TXT · gộp', 'EPUB · gộp', 'HTML · gộp'], width=190).pack(side='right')
        self.label(body, 'Định dạng gộp và nội dung trưởng thành chỉ áp dụng cho FanFicFare.', 11, MUTED).grid(row=8, column=0, sticky='w')
        ctk.CTkCheckBox(body, text='Cho phép nội dung trưởng thành (FanFicFare)', variable=self.mature).grid(row=9, column=0, sticky='w', pady=8)
        proxyrow = ctk.CTkFrame(body, fg_color='transparent'); proxyrow.grid(row=10, column=0, sticky='ew', pady=7)
        ctk.CTkCheckBox(proxyrow, text='WARP riêng ứng dụng · tự kết nối lại', variable=self.warp_auto).pack(side='left')
        ctk.CTkEntry(proxyrow, textvariable=self.warp_port, width=70).pack(side='right')
        apply_task = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(body, text='Áp dụng cách tải và thời gian nghỉ cho tác vụ đang chọn', variable=apply_task).grid(row=11, column=0, sticky='w', pady=6)
        def save():
            try:
                from core.network import NetworkPolicy
                NetworkPolicy('warp_auto' if self.warp_auto.get() else 'direct', int(self.warp_port.get()))
                if not 1 <= float(self.interval.get()) <= 300: raise ValueError('Thời gian nghỉ phải từ 1 đến 300 giây.')
                t = self.manager.get(self.selected_id)
                if apply_task.get() and t:
                    if t['state'] in ACTIVE: raise ValueError('Dừng tác vụ trước khi đổi cách tải.')
                    t['network_mode'] = 'warp_auto' if self.warp_auto.get() else 'direct'; t['warp_port'] = int(self.warp_port.get())
                    t['connection_mode'] = MODES[self.mode.get()]; t['interval'] = float(self.interval.get()); self.manager.save()
                self.save_settings(); self.detect(); win.destroy()
            except Exception as exc: messagebox.showerror('Chưa lưu được', str(exc), parent=win)
        self.button(body, 'Lưu tùy chọn', save, True, 125).grid(row=12, column=0, sticky='e', pady=8)

    def sources(self):
        win = ctk.CTkToplevel(self); win.title('Nguồn & plugin'); win.geometry('790x570'); win.transient(self)
        bar = ctk.CTkFrame(win, fg_color='transparent'); bar.pack(fill='x', padx=15, pady=10)
        self.button(bar, 'Mở plugin', lambda: open_path(ROOT/'plugins'), True, 100).pack(side='left', padx=4)
        self.button(bar, 'Hướng dẫn', lambda: open_path(ROOT/'README.md'), width=100).pack(side='left', padx=4)
        query = tk.StringVar()
        ctk.CTkEntry(win, textvariable=query, placeholder_text='Lọc tên miền / plugin').pack(fill='x', padx=15)
        listing = ctk.CTkScrollableFrame(win, fg_color=WHITE); listing.pack(fill='both', expand=True, padx=15, pady=10)
        def render(*_):
            for w in listing.winfo_children(): w.destroy()
            for item in self.plugins.get_source_catalog():
                text = f'{item["name"]} · {item["domain"]}\n{item["provider"]}'
                if query.get().casefold() in text.casefold(): self.label(listing, text, 12, justify='left', anchor='w').pack(fill='x', padx=8, pady=6)
        def reload():
            if self.manager.active_id or self.manager.worker and self.manager.worker.is_alive():
                messagebox.showwarning('Tác vụ đang chạy', 'Dừng tác vụ trước khi nạp lại plugin.', parent=win); return
            self.boot_logs.clear(); self.plugins.load_plugins(); render()
            errors = [x for x in self.boot_logs if 'Không thể' in x]
            messagebox.showinfo('Nạp plugin', '\n'.join(errors) if errors else f'Đã nạp {self.plugins.plugin_count()} plugin.', parent=win)
        self.button(bar, 'Nạp lại plugin', reload, width=110).pack(side='left', padx=4)
        query.trace_add('write', render); render()

    def run_queue(self):
        self.follow.set(True); self.manager.auto_run = True; self.manager.start_next(); self.refresh()
        self.notify('Đang tải lần lượt. Nhật ký tự theo tác vụ đang chạy.')

    def pause(self):
        try: self.manager.pause(); self.refresh()
        except ValueError as exc: self.notify(str(exc), True)

    def stop(self):
        self.manager.stop(); self.refresh(); self.notify('Đang dừng; giữ các phần đã lưu và link hiện tại.')

    def retry(self):
        t = self.manager.get(self.selected_id)
        if not t or t['state'] in ACTIVE | {'queued', 'completed'}:
            self.notify('Chọn tác vụ bị lỗi hoặc đã dừng để tiếp tục.', True); return
        self.manager.retry(t['id']); self.run_queue()
        self.notify('Đang chạy lại tác vụ đã chọn. WikiCV tiếp tục từ mốc đã lưu; plugin cũ tùy khả năng khôi phục.')

    def remove(self):
        self.manager.remove(self.selected_id); self.refresh()

    def clear_completed(self):
        try:
            count = self.manager.clear_completed()
            if not self.manager.get(self.selected_id):
                self.selected_id = self.manager.active_id
            self.refresh()
            self.notify(f'Đã dọn {count} tác vụ hoàn tất khỏi danh sách. Tệp truyện, lịch sử và nhật ký được giữ lại.')
        except Exception as exc:
            self.notify(f'Chưa dọn được danh sách: {exc}', True)

    def verify(self):
        if self.manager.active_id: self.manager.verification_event.set()

    def open_result(self):
        t = self.manager.get(self.selected_id)
        if t:
            try: open_path(t.get('output_path') or t['folder'])
            except Exception as exc: self.notify(str(exc), True)

    def copy_url(self):
        if self.display_url.get():
            self.clipboard_clear(); self.clipboard_append(self.display_url.get()); self.notify('Đã sao chép link đang hiển thị.')

    def export_log(self):
        t = self.manager.get(self.selected_id)
        if not t: return
        path = filedialog.asksaveasfilename(defaultextension='.log', initialfile=f'nhat-ky-{t["id"][:8]}.log', filetypes=[('Nhật ký', '*.log'), ('Văn bản', '*.txt')])
        if path:
            try:
                src = DATA/f'{t["id"]}.log'
                text = src.read_text(encoding='utf-8') if src.exists() else '\n'.join(t['logs'])
                Path(path).write_text(text, encoding='utf-8-sig'); self.notify('Đã xuất toàn bộ nhật ký tác vụ.')
            except Exception as exc: self.notify(str(exc), True)

    def expand_log(self):
        self.focus_log = not self.focus_log
        if self.focus_log: self.pane.forget(self.queue_frame)
        else: self.pane.add(self.queue_frame, before=self.pane.panes()[0], minsize=110, height=135, stretch='never')
        self.expand_btn.configure(text='Hiện hàng đợi' if self.focus_log else 'Phóng nhật ký')

    def select(self, _=None):
        values = self.tree.selection()
        if values: self.selected_id = values[0]
        self.render_detail()

    def refresh(self):
        ids = set(self.tree.get_children())
        for t in self.manager.tasks:
            values = (t['title'], LABELS[t['state']], t.get('current', 0), t['plugin'])
            if t['id'] in ids: self.tree.item(t['id'], values=values); ids.remove(t['id'])
            else: self.tree.insert('', 'end', iid=t['id'], values=values)
        for tid in ids: self.tree.delete(tid)
        if self.follow.get() and self.manager.active_id: self.selected_id = self.manager.active_id
        if self.selected_id and self.tree.exists(self.selected_id):
            if self.tree.selection() != (self.selected_id,): self.tree.selection_set(self.selected_id); self.tree.see(self.selected_id)
        running = self.manager.get(self.manager.active_id)
        can_pause = running and running['state'] in {'running', 'paused'} and getattr(self.plugins.plugin_map.get(running['plugin']), 'supports_pause', True)
        self.pause_btn.configure(state='normal' if can_pause else 'disabled', text='Tiếp tục' if self.manager.pause_event.is_set() else 'Tạm dừng')
        self.count_label.configure(text=f'{sum(t["state"] == "queued" for t in self.manager.tasks)} chờ · {sum(t["state"] == "completed" for t in self.manager.tasks)} xong')
        self.clean_btn.configure(state='normal' if any(t['state'] == 'completed' for t in self.manager.tasks) else 'disabled')
        self.render_detail()

    def render_detail(self):
        t = self.manager.get(self.selected_id)
        active = self.manager.get(self.manager.active_id)
        if active and active['state'] == 'waiting_verification': self.verify_btn.grid()
        else: self.verify_btn.grid_remove()
        if t:
            self.detail_title.configure(text=LABELS[t['state']].upper())
            self.display_url.set((t.get('failure_url') if t['state'] == 'failed' else t.get('current_url')) or t['url'])
            status = f'{t.get("current", 0)} mục đã lưu · {t.get("status", "")} · {t.get("connection_mode", "http")}'
            if t['state'] == 'failed': status += ' · Đổi mạng nếu cần, rồi bấm Tiếp tục tải.'
            self.detail_status.configure(text=status[:145])
            lines = t['logs'] or ['Chưa có hoạt động. Bấm Chạy hàng đợi để bắt đầu.']
        else:
            self.detail_title.configure(text='NHẬT KÝ'); self.display_url.set('')
            self.detail_status.configure(text='Nhật ký hiện rõ link, chương/phần, thời gian chờ và lỗi.')
            lines = self.boot_logs
        tid = t['id'] if t else None
        if lines == self.last_log_lines and tid == self.log_task_id: return
        append = tid == self.log_task_id and len(lines) >= len(self.last_log_lines) and lines[:len(self.last_log_lines)] == self.last_log_lines
        view = self.log.yview()
        self.log.configure(state='normal')
        new_lines = lines[len(self.last_log_lines):] if append else lines
        if not append: self.log.delete('1.0', 'end')
        for line in new_lines:
            tag = 'error' if '[LỖI]' in line or '[LINK LỖI' in line else 'warn' if '[THỬ LẠI]' in line else 'success' if '[ĐÃ LƯU' in line or '[HOÀN TẤT]' in line else 'link' if 'http' in line else ''
            self.log.insert('end', line+'\n', tag)
        self.log.configure(state='disabled')
        if self.autoscroll.get(): self.log.see('end')
        elif not append and tid == self.log_task_id and view: self.log.yview_moveto(view[0])
        self.last_log_lines = list(lines); self.log_task_id = tid

    def poll(self):
        try:
            self.manager.drain(); self.refresh()
            if self.manager.notice:
                self.notify(*self.manager.notice); self.manager.notice = None
            if self.closing and not (self.manager.worker and self.manager.worker.is_alive()): self.destroy(); return
        except Exception as exc:
            self.manager.auto_run = False; self.manager.stop_event.set(); self.notify(str(exc), True)
        self.after(250, self.poll)

    def close(self):
        self.manager.auto_run = False
        if self.manager.worker and self.manager.worker.is_alive():
            self.closing = True; self.manager.stop(); self.notify('Đang dừng an toàn và lưu tiến độ…')
        else: self.destroy()


if __name__ == '__main__':
    from core.instance import acquire
    try:
        instance_lock = acquire(DATA)
    except RuntimeError as exc:
        notice = tk.Tk(); notice.withdraw(); messagebox.showerror('Ứng dụng đã mở', str(exc)); notice.destroy(); sys.exit(1)
    from core.desktop import create_app
    create_app(App, ROOT, DATA).mainloop()
