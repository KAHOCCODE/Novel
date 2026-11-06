"""Queue-first desktop UI; advanced controls appear only when needed."""
import os,threading,queue,time
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import customtkinter as ctk
from core.tasks import ACTIVE,LABELS
from core.storage import read_json,atomic_json
from core.lifecycle import clean_task,remove_owned_tree,bytes_used


def create_app(Base,root,data):
 class Desktop(Base):
    def button(self, parent, text, command, primary=False, width=100):
        from main import FONT
        return ctk.CTkButton(parent,text=text,command=command,width=width,height=36,corner_radius=8,
            fg_color='#3567DD' if primary else '#EDF1F8',hover_color='#2855BD' if primary else '#E1E8F3',
            text_color='#FFFFFF' if primary else '#304359',font=(FONT,12))

    def bound_entry(self,parent,variable,**kwargs):
        # CTk placeholders do not work with textvariable; synchronize at the edges.
        entry=ctk.CTkEntry(parent,**kwargs)
        def edited(_=None):
            value=entry.get()
            if variable.get()!=value:variable.set(value)
        def changed(*_):
            if entry.winfo_exists() and entry.get()!=variable.get():
                entry.delete(0,'end')
                if variable.get():entry.insert(0,variable.get())
        entry.bind('<KeyRelease>',edited,add=True)
        entry.bind('<<Paste>>',lambda _:entry.after_idle(edited),add=True)
        entry.bind('<<Cut>>',lambda _:entry.after_idle(edited),add=True)
        variable.trace_add('write',changed);changed()
        return entry

    def _build(self):
        from main import FONT
        self.title('Novel Downloader 5.5')
        self.geometry(f'{min(1280,self.winfo_screenwidth()-40)}x{min(800,self.winfo_screenheight()-90)}')
        self.minsize(960,620);self.configure(fg_color='#F3F5F9')
        self.filter=tk.StringVar(value='Tất cả');self.search=tk.StringVar();self.technical=tk.BooleanVar(value=False)
        self.busy=False;self.actions=queue.Queue();self.logs_visible=True;self.last_render=None
        self.last_selection=None;self.toast_job=None
        self.grid_columnconfigure(0,weight=1);self.grid_rowconfigure(2,weight=1)
        head=ctk.CTkFrame(self,fg_color='transparent')
        head.grid(row=0,column=0,sticky='ew',padx=24,pady=(18,14))
        self.label(head,'N',23,color='#3567DD',bold=True,width=36).pack(side='left')
        self.label(head,'Novel Downloader',21,bold=True).pack(side='left',padx=(6,12))
        self.label(head,'5.5',11,color='#7A8799').pack(side='left')
        self.button(head,'Cài đặt  ▾',self.app_menu,width=100).pack(side='right')
        add=ctk.CTkFrame(self,fg_color='#FFFFFF',corner_radius=12,border_width=1,border_color='#E5EAF1')
        add.grid(row=1,column=0,sticky='ew',padx=24,pady=(0,16));add.grid_columnconfigure(0,weight=1)
        self.link_entry=self.bound_entry(add,self.url,height=44,border_width=0,
            placeholder_text='Dán link truyện hoặc chương bắt đầu…',fg_color='#FFFFFF',font=(FONT,13))
        self.link_entry.grid(row=0,column=0,sticky='ew',padx=(14,8),pady=10)
        self.link_entry.bind('<Return>',lambda _:self.add())
        self.add_btn=self.button(add,'Tải truyện',self.add,True,155);self.add_btn.grid(row=0,column=1,padx=(0,12))
        self.pane=tk.PanedWindow(self,orient=tk.HORIZONTAL,bg='#F3F5F9',sashwidth=12,bd=0,sashrelief='flat')
        self.pane.grid(row=2,column=0,sticky='nsew',padx=24)
        self.queue_frame=ctk.CTkFrame(self.pane,fg_color='#FFFFFF',corner_radius=12)
        card=self.queue_frame;card.grid_columnconfigure(0,weight=1);card.grid_rowconfigure(3,weight=1)
        title=ctk.CTkFrame(card,fg_color='transparent');title.grid(row=0,column=0,columnspan=2,sticky='ew',padx=16,pady=(14,10))
        self.label(title,'Danh sách tải',16,bold=True).pack(side='left')
        self.count_label=self.label(title,'',11,color='#7A8799');self.count_label.pack(side='left',padx=10)
        self.button(title,'•••',self.queue_menu,width=36).pack(side='right')
        tools=ctk.CTkFrame(card,fg_color='transparent');tools.grid(row=1,column=0,columnspan=2,sticky='ew',padx=16,pady=(0,12))
        self.run_btn=self.button(tools,'Tải hàng đợi',self.session_action,True,130);self.run_btn.pack(side='left')
        self.stop_btn=self.button(tools,'Dừng phiên',self.stop,width=96);self.stop_btn.pack(side='left',padx=8)
        self.stop_btn.pack_forget()
        self.search_entry=self.bound_entry(tools,self.search,placeholder_text='Tìm truyện',width=145,height=34,border_color='#E5EAF1')
        self.search_entry.pack(side='right')
        filters=ctk.CTkFrame(card,fg_color='transparent');filters.grid(row=2,column=0,columnspan=2,sticky='ew',padx=16,pady=(0,10))
        self.filter_menu=ctk.CTkOptionMenu(filters,variable=self.filter,values=['Tất cả','Đang tải','Chờ lượt','Cần xử lý','Hoàn tất'],
            command=lambda _:self.refresh(),width=135,height=28,fg_color='#F1F4F9',button_color='#F1F4F9',button_hover_color='#E1E8F3',text_color='#53647A',font=(FONT,11))
        self.filter_menu.pack(side='left')
        self.label(filters,'Chọn truyện để xem hoạt động',11,color='#7A8799').pack(side='right')
        self.search.trace_add('write',lambda *_:self.refresh())
        style=ttk.Style();style.theme_use('clam')
        style.configure('ND.Treeview',background='#FFFFFF',fieldbackground='#FFFFFF',foreground='#304359',rowheight=46,borderwidth=0,font=(FONT,10))
        style.configure('ND.Treeview.Heading',background='#F5F7FB',foreground='#7A8799',font=(FONT,9,'bold'),relief='flat',padding=(8,10))
        style.map('ND.Treeview',background=[('selected','#EAF0FF')],foreground=[('selected','#244FAA')])
        self.tree=ttk.Treeview(card,columns=('title','progress','state'),show='headings',selectmode='browse',style='ND.Treeview')
        for col,text,width,stretch in [('title','TRUYỆN',290,True),('progress','ĐÃ LƯU',74,False),('state','TRẠNG THÁI',112,False)]:
            self.tree.heading(col,text=text,anchor='w' if stretch else 'center');self.tree.column(col,width=width,minwidth=135 if stretch else width,stretch=stretch,anchor='w' if stretch else 'center')
        self.tree.grid(row=3,column=0,sticky='nsew',padx=(10,0),pady=(0,12))
        sb=ttk.Scrollbar(card,command=self.tree.yview);sb.grid(row=3,column=1,sticky='ns',padx=(0,8),pady=(0,12));self.tree.configure(yscrollcommand=sb.set)
        for tag,color in [('failed','#BD4553'),('waiting_verification','#A16A16'),('completed','#21826D'),('held','#8792A2')]:self.tree.tag_configure(tag,foreground=color)
        self.tree.bind('<<TreeviewSelect>>',self.select)
        self.tree.bind('<Button-1>',lambda _:self.follow.set(False))
        self.tree.bind('<Button-3>',self.row_menu)
        self.pane.add(card,minsize=440,width=620,stretch='always')
        self.detail_panel=ctk.CTkFrame(self.pane,fg_color='#FFFFFF',corner_radius=12)
        panel=self.detail_panel;panel.grid_columnconfigure(0,weight=1);panel.grid_rowconfigure(2,weight=1)
        top=ctk.CTkFrame(panel,fg_color='transparent');top.grid(row=0,column=0,sticky='ew',padx=16,pady=(14,10))
        self.view=tk.StringVar(value='Hoạt động')
        ctk.CTkSegmentedButton(top,values=['Hoạt động','Thông tin'],variable=self.view,command=self.change_view,
            font=(FONT,12),fg_color='#F1F4F9',selected_color='#DEE8FF',selected_hover_color='#D3E0FC',unselected_color='#F1F4F9',unselected_hover_color='#E1E8F3',text_color='#304359',text_color_disabled='#7A8799').pack(side='left')
        self.more_btn=self.button(top,'•••',self.more,width=36);self.more_btn.pack(side='right')
        self.context_card=ctk.CTkFrame(panel,fg_color='#F3F6FC',corner_radius=8)
        self.context_card.grid(row=1,column=0,sticky='ew',padx=16,pady=(0,12));self.context_card.grid_columnconfigure(0,weight=1)
        self.detail_status=self.label(self.context_card,'Chọn một truyện trong danh sách.',12,color='#53647A',anchor='w',justify='left',wraplength=390)
        self.detail_status.grid(row=0,column=0,sticky='ew',padx=12,pady=12)
        self.primary_btn=self.button(self.context_card,'Tải tiếp',self.primary_action,True,100)
        self.primary_btn.grid(row=1,column=0,sticky='w',padx=12,pady=(0,12));self.primary_btn.grid_remove()
        self.activity_frame=ctk.CTkFrame(panel,fg_color='transparent')
        self.activity_frame.grid(row=2,column=0,sticky='nsew',padx=16,pady=(0,12));self.activity_frame.grid_columnconfigure(0,weight=1);self.activity_frame.grid_rowconfigure(0,weight=1)
        self.log=tk.Text(self.activity_frame,wrap='word',font=(FONT,10),bg='#FFFFFF',fg='#44536A',relief='flat',bd=0,
            padx=2,pady=4,spacing1=6,spacing3=6,state='disabled',selectbackground='#D9E5FF',selectforeground='#244FAA')
        self.log.grid(row=0,column=0,sticky='nsew')
        sb=ttk.Scrollbar(self.activity_frame,command=self.log.yview);sb.grid(row=0,column=1,sticky='ns');self.log.configure(yscrollcommand=sb.set)
        for tag,color in [('time','#8F9BAD'),('error','#BD4553'),('success','#21826D'),('warn','#A16A16'),('normal','#44536A')]:self.log.tag_configure(tag,foreground=color)
        self.technical_switch=ctk.CTkSwitch(self.activity_frame,text='Log kỹ thuật',variable=self.technical,command=self.render_detail,font=(FONT,11),
            switch_width=30,switch_height=16,progress_color='#3567DD')
        self.technical_switch.grid(row=1,column=0,columnspan=2,sticky='w',pady=(10,0))
        self.info_frame=ctk.CTkScrollableFrame(panel,fg_color='transparent',corner_radius=0)
        self.info_frame.grid(row=2,column=0,sticky='nsew',padx=12,pady=(0,12));self.info_frame.grid_columnconfigure(0,weight=1)
        self.info_title=self.label(self.info_frame,'',15,bold=True,anchor='w',justify='left',wraplength=350)
        self.info_title.grid(row=0,column=0,sticky='ew',padx=4,pady=(4,16))
        self.label(self.info_frame,'LINK HIỆN TẠI',10,color='#7A8799',bold=True).grid(row=1,column=0,sticky='w',padx=4)
        ctk.CTkEntry(self.info_frame,textvariable=self.display_url,state='readonly',height=34,border_color='#E5EAF1').grid(row=2,column=0,sticky='ew',padx=4,pady=(4,6))
        self.button(self.info_frame,'Chép link',self.copy_url,width=100).grid(row=3,column=0,sticky='w',padx=4,pady=(0,18))
        self.label(self.info_frame,'NƠI LƯU',10,color='#7A8799',bold=True).grid(row=4,column=0,sticky='w',padx=4)
        self.info_folder=self.label(self.info_frame,'',12,color='#53647A',anchor='w',justify='left',wraplength=350)
        self.info_folder.grid(row=5,column=0,sticky='ew',padx=4,pady=(4,8))
        self.button(self.info_frame,'Mở thư mục',self.open_result,width=120).grid(row=6,column=0,sticky='w',padx=4,pady=(0,18))
        self.info_mode=self.label(self.info_frame,'',11,color='#7A8799',anchor='w',justify='left',wraplength=350)
        self.info_mode.grid(row=7,column=0,sticky='ew',padx=4)
        self.info_frame.grid_remove()
        self.pane.add(panel,minsize=400,width=560,stretch='always')
        self.banner=self.label(self,'Dán link rồi bấm Tải truyện để bắt đầu.',11,color='#7A8799',anchor='w')
        self.banner.grid(row=3,column=0,sticky='ew',padx=26,pady=(10,12))
        self.detail_panel.bind('<Configure>',self.resize_detail)

    def resize_detail(self,event=None):
        width=max(280,self.detail_panel.winfo_width()-70)
        self.detail_status.configure(wraplength=width)
        self.info_title.configure(wraplength=width);self.info_folder.configure(wraplength=width);self.info_mode.configure(wraplength=width)

    def detect(self):
        # Source detection stays automatic; no second source/mode display on the main screen.
        try:
            handler=self.plugins.find_handler(self.url.get().strip())
            if not handler or handler.__class__.__name__!='FanFicFarePublicCrawler':self.output.set('TXT · từng chương')
        except Exception:pass

    def app_menu(self):
        menu=tk.Menu(self,tearoff=0)
        for title,fn in [('Tùy chọn tải…',self.options),('Nguồn & plugin…',self.sources),('Dữ liệu & dung lượng…',self.storage)]:menu.add_command(label=title,command=fn)
        menu.tk_popup(self.winfo_pointerx(),self.winfo_pointery())

    def queue_menu(self):
        menu=tk.Menu(self,tearoff=0)
        menu.add_command(label='Dọn tác vụ hoàn tất',command=self.clear_completed,
            state='normal' if not self.manager.active_id and not self.busy and any(t['state']=='completed' for t in self.manager.tasks) else 'disabled')
        menu.add_command(label='Xem tác vụ đang tải',command=self.focus_active,state='normal' if self.manager.active_id else 'disabled')
        menu.tk_popup(self.winfo_pointerx(),self.winfo_pointery())

    def focus_active(self):
        self.follow.set(True);self.filter.set('Tất cả');self.search.set('');self.refresh()

    def notify(self,message,error=False):
        from core.ui_state import short_error
        message=short_error(message) if error else message
        self.banner.configure(text=message[:150],text_color='#BD4553' if error else '#7A8799')
        if self.toast_job:self.after_cancel(self.toast_job)
        self.toast_job=self.after(10000,lambda:self.banner.configure(text=''))

    def visible(self,t):
        f=self.filter.get();state=t['state']
        return (f=='Tất cả' or f=='Đang tải' and state in ACTIVE or f=='Chờ lượt' and state in {'queued','held'} or f=='Cần xử lý' and state in {'failed','stopped','needs_review'} or f=='Hoàn tất' and state=='completed') and self.search.get().casefold() in (t['title']+' '+t['url']).casefold()

    def state_text(self,t,positions):
        s=t['state']
        if s=='queued':return f'Chờ lượt {positions[t["id"]]}'
        if s=='held':return 'Để sau'
        if s=='waiting_verification':return 'Cần xác minh'
        if s=='needs_review':return 'Cần kiểm tra'
        return LABELS.get(s,s)

    def refresh(self):
        if not hasattr(self,'tree'):return
        positions={t['id']:i+1 for i,t in enumerate(t for t in self.manager.tasks if t['state']=='queued')}
        ids=set(self.tree.get_children());index=0
        for t in self.manager.tasks:
            if not self.visible(t):continue
            total=t.get('total');count=f'{t.get("current",0)}/{total}' if total else str(t.get('current',0))
            values=(t['title'],count,self.state_text(t,positions))
            if t['id'] in ids:
                if self.tree.item(t['id'],'values')!=tuple(str(v) for v in values):self.tree.item(t['id'],values=values,tags=(t['state'],))
                ids.remove(t['id'])
            else:self.tree.insert('','end',iid=t['id'],values=values,tags=(t['state'],))
            self.tree.move(t['id'],'',index);index+=1
        for tid in ids:self.tree.delete(tid)
        if self.follow.get() and self.manager.active_id:self.selected_id=self.manager.active_id
        if not self.selected_id and self.tree.get_children():self.selected_id=self.tree.get_children()[0]
        if self.selected_id and not self.tree.exists(self.selected_id):self.selected_id=self.tree.get_children()[0] if self.tree.get_children() else None
        if self.selected_id and self.tree.selection()!=(self.selected_id,):self.tree.selection_set(self.selected_id)
        active=self.manager.get(self.manager.active_id)
        worker_busy=bool(self.manager.worker and self.manager.worker.is_alive())
        if active:
            if active['state'] in {'running','paused'}:
                can_pause=getattr(self.plugins.plugin_map.get(active['plugin']),'supports_pause',True)
                self.run_btn.configure(text='Tiếp tục' if active['state']=='paused' else 'Tạm dừng',state='normal' if can_pause and not self.busy else 'disabled')
            else:self.run_btn.configure(text='Đang dừng…' if active['state']=='stopping' else 'Chờ xác minh',state='disabled')
            self.stop_btn.pack(side='left',padx=8,before=self.search_entry);self.stop_btn.configure(state='disabled' if active['state']=='stopping' else 'normal')
        else:
            self.run_btn.configure(text='Tải hàng đợi',state='normal' if positions and not self.busy and not worker_busy else 'disabled')
            self.stop_btn.pack_forget()
        self.add_btn.configure(text='Thêm vào hàng đợi' if active else 'Tải truyện',state='disabled' if self.busy else 'normal')
        self.count_label.configure(text=f'{len(self.manager.tasks)} truyện')
        self.more_btn.configure(state='normal' if self.manager.get(self.selected_id) and not self.busy else 'disabled')
        self.render_detail()

    def render_detail(self):
        from core.ui_state import activity_lines,short_error,selected_action
        t=self.manager.get(self.selected_id)
        if not t:
            message='Chọn một truyện trong danh sách.';color='#53647A';card='#F3F6FC'
            lines=[(None,'Chưa có hoạt động. Dán link ở trên để tải truyện.','normal')]
            self.display_url.set('');self.info_title.configure(text='Chưa chọn truyện');self.info_folder.configure(text='');self.info_mode.configure(text='')
        else:
            if t['state']=='failed':message=short_error(t.get('detail'));color='#A73C4B';card='#FFF1F3'
            elif t['state']=='needs_review':message=short_error(t.get('detail'));color='#936218';card='#FFF7E8'
            elif t.get('cleanup_error'):message='Nội dung đã tải xong; chưa dọn hết dữ liệu tạm.';color='#936218';card='#FFF7E8'
            elif t['state']=='completed':message='Đã lưu đầy đủ nội dung truyện.';color='#21826D';card='#ECF8F3'
            elif t['state']=='held':message='Truyện này chưa tham gia hàng đợi.';color='#53647A';card='#F3F6FC'
            elif t['state']=='queued':message='Sẽ tải lần lượt khi đến lượt.';color='#53647A';card='#F3F6FC'
            elif t['state']=='stopped':message='Có thể tải tiếp từ tiến độ đã lưu.';color='#53647A';card='#F3F6FC'
            else:
                chapter=t.get('chapter_title') or ''
                pn=t.get('current_part');total=t.get('parts_total')
                message=chapter+(f' · Phần {pn+1}/{total}' if pn is not None and total and total>1 else '')
                if t.get('wait_remaining'):message+=(f'\nChờ {t["wait_remaining"]} giây trước lượt tiếp theo.')
                if t['state']=='paused':message+='\nTiến độ được giữ trong khi tạm dừng.'
                if t['state']=='waiting_verification':message='Hoàn tất xác minh trong cửa sổ Chromium, rồi bấm Đã xác minh.'
                if not message:message=t.get('status') or 'Đang kết nối…'
                color='#53647A';card='#F3F6FC'
            self.display_url.set((t.get('failure_url') if t['state']=='failed' else t.get('current_url')) or t['url'])
            self.info_title.configure(text=t['title']);self.info_folder.configure(text=str(t.get('output_path') or t['folder']))
            names={'auto':'Tự động','http':'HTTP trực tiếp','background':'Chromium chạy nền','browser':'Chromium hiện cửa sổ'}
            self.info_mode.configure(text=(urlparse(t['url']).hostname or '')+'\nCách tải: '+names.get(t.get('connection_mode','http'),'HTTP trực tiếp'))
            lines=activity_lines(t.get('logs',[]),self.technical.get())
            if not lines:lines=[(None,'Chưa có hoạt động trong phiên này.','normal')]
        self.detail_status.configure(text=message,text_color=color);self.context_card.configure(fg_color=card)
        action=selected_action(t,self.manager.active_id)
        if action:
            self.primary_btn.configure(text=action[0],state='disabled' if self.busy or self.manager.worker and self.manager.worker.is_alive() and not self.manager.active_id else 'normal');self.primary_btn.grid()
        else:self.primary_btn.grid_remove()
        key=(t['id'] if t else None,self.technical.get(),tuple(lines))
        if key==self.last_render:return
        same=self.log_task_id==(t['id'] if t else None) and self.last_render and self.last_render[1]==self.technical.get()
        view=self.log.yview();at_bottom=not same or not view or view[1]>=0.98
        old=self.last_log_lines
        append=bool(same and len(lines)>=len(old) and lines[:len(old)]==old)
        self.log.configure(state='normal')
        if not append:self.log.delete('1.0','end')
        for stamp,text,tag in (lines[len(old):] if append else lines):
            if stamp:self.log.insert('end',stamp+'  ','time')
            self.log.insert('end',text+'\n',tag)
        self.log.configure(state='disabled')
        if at_bottom:self.log.see('end')
        elif not append and view:self.log.yview_moveto(view[0])
        self.last_render=key;self.last_log_lines=list(lines);self.log_task_id=t['id'] if t else None

    def change_view(self,_=None):
        if self.view.get()=='Hoạt động':self.info_frame.grid_remove();self.activity_frame.grid()
        else:self.activity_frame.grid_remove();self.info_frame.grid()

    def session_action(self):
        if self.manager.active_id:self.pause()
        else:self.run_queue()

    def primary_action(self):
        from core.ui_state import selected_action
        t=self.manager.get(self.selected_id);action=selected_action(t,self.manager.active_id)
        if not action or self.busy:return
        if action[1]=='verify':self.verify()
        elif action[1]=='retry':self.retry()
        elif action[1]=='enqueue':self.manager.hold(t['id']);self.run_queue()

    def add(self):
        if self.busy:return
        before={t['id'] for t in self.manager.tasks}
        super().add()
        created=next((t for t in self.manager.tasks if t['id'] not in before),None)
        if not created:return
        self.selected_id=created['id'];self.follow.set(False);self.filter.set('Tất cả');self.search.set('')
        self.manager.auto_run=True
        self.manager.start_next();self.refresh()
        self.notify('Đã thêm vào hàng đợi.' if self.manager.active_id!=created['id'] else 'Đang bắt đầu tải truyện.')

    def options(self):
        if self.busy:return
        from main import MODES,FONT
        win=ctk.CTkToplevel(self);win.title('Cài đặt tải truyện');win.geometry('620x520');win.minsize(600,500);win.transient(self);win.grab_set()
        # Edit local drafts; Cancel does not mutate live defaults or tasks.
        draft_folder=tk.StringVar(value=self.folder.get());draft_mode=tk.StringVar(value=self.mode.get());draft_interval=tk.StringVar(value=self.interval.get())
        draft_source=tk.StringVar(value=self.source.get());draft_output=tk.StringVar(value=self.output.get());draft_mature=tk.BooleanVar(value=self.mature.get())
        draft_warp=tk.BooleanVar(value=self.warp_auto.get());draft_port=tk.StringVar(value=self.warp_port.get())
        tabs=ctk.CTkTabview(win,fg_color='#FFFFFF');tabs.pack(fill='both',expand=True,padx=20,pady=(12,8))
        general=tabs.add('Tải truyện');advanced=tabs.add('Nâng cao')
        general.grid_columnconfigure(0,weight=1);advanced.grid_columnconfigure(0,weight=1)
        self.label(general,'Thư mục lưu truyện mới',13,bold=True).grid(row=0,column=0,sticky='w',pady=(12,6))
        row=ctk.CTkFrame(general,fg_color='transparent');row.grid(row=1,column=0,sticky='ew');row.grid_columnconfigure(0,weight=1)
        ctk.CTkEntry(row,textvariable=draft_folder,height=36).grid(row=0,column=0,sticky='ew')
        def browse():
            path=filedialog.askdirectory(parent=win)
            if path:draft_folder.set(path)
        self.button(row,'Chọn…',browse,width=75).grid(row=0,column=1,padx=(8,0))
        self.label(general,'Cách tải',13,bold=True).grid(row=2,column=0,sticky='w',pady=(20,6))
        ctk.CTkOptionMenu(general,variable=draft_mode,values=list(MODES),height=36).grid(row=3,column=0,sticky='ew')
        self.label(general,'Tự động dùng bộ tải JavaScript khi trang chia nhiều phần.',11,color='#7A8799',justify='left').grid(row=4,column=0,sticky='w',pady=(5,16))
        row=ctk.CTkFrame(general,fg_color='transparent');row.grid(row=5,column=0,sticky='ew')
        self.label(row,'Nghỉ giữa các lượt tải (giây)',12).pack(side='left')
        ctk.CTkEntry(row,textvariable=draft_interval,width=75,height=34).pack(side='right')
        self.label(general,'Cách tải và thời gian nghỉ cũng áp dụng cho tác vụ đang chọn nếu đã dừng.\nThư mục mới chỉ áp dụng cho truyện thêm sau.',11,color='#7A8799',justify='left',wraplength=530).grid(row=6,column=0,sticky='w',pady=18)
        self.label(advanced,'Nguồn tải',12,bold=True).grid(row=0,column=0,sticky='w',pady=(12,6))
        ctk.CTkOptionMenu(advanced,variable=draft_source,values=['Tự động']+self.plugins.get_plugin_names()).grid(row=1,column=0,sticky='ew')
        self.label(advanced,'Định dạng FanFicFare',12,bold=True).grid(row=2,column=0,sticky='w',pady=(16,6))
        ctk.CTkOptionMenu(advanced,variable=draft_output,values=['TXT · từng chương','TXT · gộp','EPUB · gộp','HTML · gộp']).grid(row=3,column=0,sticky='ew')
        ctk.CTkCheckBox(advanced,text='Nội dung trưởng thành (FanFicFare)',variable=draft_mature,font=(FONT,12)).grid(row=4,column=0,sticky='w',pady=14)
        ctk.CTkCheckBox(advanced,text='WARP riêng ứng dụng · tự kết nối lại',variable=draft_warp,font=(FONT,12)).grid(row=5,column=0,sticky='w',pady=(8,12))
        row=ctk.CTkFrame(advanced,fg_color='transparent');row.grid(row=6,column=0,sticky='ew')
        self.label(row,'Cổng proxy cục bộ',12).pack(side='left');ctk.CTkEntry(row,textvariable=draft_port,width=80).pack(side='right')
        footer=ctk.CTkFrame(win,fg_color='transparent');footer.pack(fill='x',padx=24,pady=(0,18))
        def save():
            try:
                from core.network import NetworkPolicy
                interval=float(draft_interval.get());port=int(draft_port.get())
                if not 1<=interval<=300:raise ValueError('Thời gian nghỉ phải từ 1 đến 300 giây.')
                if not draft_folder.get().strip():raise ValueError('Hãy chọn thư mục lưu.')
                NetworkPolicy('warp_auto' if draft_warp.get() else 'direct',port)
                t=self.manager.get(self.selected_id)
                if t and t['state'] not in ACTIVE|{'completed'}:
                    t.update(connection_mode=MODES[draft_mode.get()],interval=interval,network_mode='warp_auto' if draft_warp.get() else 'direct',warp_port=port)
                    self.manager.save()
                for live,draft in [(self.folder,draft_folder),(self.mode,draft_mode),(self.interval,draft_interval),(self.source,draft_source),(self.output,draft_output),(self.mature,draft_mature),(self.warp_auto,draft_warp),(self.warp_port,draft_port)]:live.set(draft.get())
                self.save_settings();self.refresh();win.destroy();self.notify('Đã lưu cài đặt.')
            except Exception as exc:messagebox.showerror('Chưa lưu được',str(exc),parent=win)
        self.button(footer,'Lưu cài đặt',save,True,125).pack(side='right')
        self.button(footer,'Hủy',win.destroy,width=75).pack(side='right',padx=8)

    def sources(self):
        if not self.busy:super().sources()

    def run_queue(self):
        if self.busy:return
        self.follow.set(True);self.manager.auto_run=True;self.manager.start_next();self.refresh()

    def retry(self):
        t=self.manager.get(self.selected_id)
        if not t or self.manager.active_id or self.busy:return
        if self.manager.worker and self.manager.worker.is_alive():return
        self.manager.retry(t['id']);self.run_queue()

    def stop(self):
        self.manager.stop();self.refresh()

    def pause(self):
        try:self.manager.pause();self.refresh()
        except ValueError as exc:self.notify(str(exc),True)

    def row_menu(self,event):
        tid=self.tree.identify_row(event.y)
        if tid:self.selected_id=tid;self.tree.selection_set(tid);self.render_detail();self.more()

    def more(self):
        t=self.manager.get(self.selected_id)
        if not t:return
        menu=tk.Menu(self,tearoff=0)
        inactive=not self.manager.active_id and not self.busy
        if t['state'] in {'queued','held'}:
            menu.add_command(label='Để sau' if t['state']=='queued' else 'Đưa vào hàng đợi',command=lambda:(self.manager.hold(t['id']),self.refresh()),state='normal' if not self.busy else 'disabled')
        menu.add_command(label='Đưa lên trước',command=lambda:self.reorder(-1),state='normal' if t['state'] not in ACTIVE and not self.busy else 'disabled')
        menu.add_command(label='Đưa xuống sau',command=lambda:self.reorder(1),state='normal' if t['state'] not in ACTIVE and not self.busy else 'disabled')
        menu.add_separator()
        menu.add_command(label='Chuyển nơi lưu…',command=self.relocate,state='normal' if inactive and t['state']!='completed' else 'disabled')
        menu.add_command(label='Xuất nhật ký đầy đủ…',command=self.export_log)
        menu.add_separator()
        menu.add_command(label='Bỏ tác vụ khỏi danh sách…',command=self.remove,state='normal' if t['state'] not in ACTIVE and not self.busy else 'disabled')
        menu.tk_popup(self.winfo_pointerx(),self.winfo_pointery())

    def reorder(self,delta):
        if self.busy:return
        self.manager.move(self.selected_id,delta);self.refresh()

    def remove(self):
        t=self.manager.get(self.selected_id)
        if not t or t['state'] in ACTIVE or self.busy:return
        self.manager.remove(t['id']);self.selected_id=None;self.refresh()
        self.notify('Đã bỏ tác vụ. Tệp truyện và mốc tải được giữ lại.')

    def clear_completed(self):
        if self.manager.active_id or self.busy:return
        self.manager.auto_run=False
        self.background(lambda:self.manager.clear_completed(),lambda n:self.notify(f'Đã dọn {n} tác vụ hoàn tất. Tệp truyện được giữ lại.'))


    def background(self,fn,done):
        if self.busy:return
        self.manager.auto_run=False
        self.busy=True;self.refresh();self.notify('Đang xử lý dữ liệu…')
        def work():
            try:self.actions.put((done,fn(),None))
            except Exception as e:self.actions.put((done,None,e))
        threading.Thread(target=work,daemon=True).start()

    def relocate(self):
        t=self.manager.get(self.selected_id)
        if not t or self.manager.active_id or self.busy:self.notify('Dừng phiên tải trước khi chuyển nơi lưu.',True);return
        if t['state']=='completed':self.notify('Truyện đã hoàn tất: dùng Mở nơi lưu để di chuyển TXT bằng File Explorer.');return
        self.manager.auto_run=False
        dest=filedialog.askdirectory(title='Nơi lưu mới cho truyện đang chọn',parent=self)
        if not dest:return
        if not messagebox.askyesno('Chuyển nơi lưu',f'Chuyển truyện và tiến độ sang:\n{dest}\n\nChỉ xóa bản ở nơi cũ sau khi kiểm tra bản sao và lưu tác vụ thành công. Nếu đích đã có truyện này, thao tác sẽ dừng để tránh ghi đè.',parent=self):return
        if any(x['id']!=t['id'] and x['url'].split('#')[0]==t['url'].split('#')[0] and Path(x['folder']).resolve()==Path(t['folder']).resolve() for x in self.manager.tasks):
            self.notify('Có tác vụ khác dùng cùng truyện và nơi lưu. Bỏ tác vụ trùng trước khi chuyển.',True);return
        def work():
            from core.relocate import relocate_task
            import copy,hashlib
            original=copy.deepcopy(t);updated=relocate_task(t,dest)
            oldpath=Path(original.get('output_path',''))
            t.clear();t.update(updated)
            try:self.manager.save()
            except Exception:t.clear();t.update(original);raise
            # Removing originals is separate from committing new references. On any mismatch keep originals.
            source=Path(original['folder']);key=hashlib.sha256(original['url'].split('#')[0].encode()).hexdigest()[:12]
            cp=source/'.noveldownloader'/f'wikicv-{key}.json'
            if cp.exists():
                state=read_json(cp,{});oldpath=Path(state.get('folder',''));newpath=Path(updated.get('output_path',''))
                if oldpath.resolve()!=newpath.resolve() and oldpath.is_dir() and oldpath.resolve().is_relative_to(source.resolve()) and oldpath.resolve()!=source.resolve():
                    for p in oldpath.rglob('*'):
                        if p.is_file() and p.read_bytes()!=(newpath/p.relative_to(oldpath)).read_bytes():raise ValueError('Đã đổi nơi lưu; giữ bản cũ vì kiểm tra cuối không khớp.')
                    remove_owned_tree(oldpath,source);cp.unlink()
            return dest
        self.background(work,lambda p:self.notify('Đã chuyển truyện và tiến độ sang '+p))

    def storage(self):
        win=ctk.CTkToplevel(self);win.title('Dữ liệu & dung lượng');win.geometry('790x560');win.transient(self)
        box=ctk.CTkTextbox(win,wrap='word');box.pack(fill='both',expand=True,padx=20,pady=20)
        from core.local_data import legacy_dir
        old=legacy_dir()
        def scan():
            paths=[('Nội dung tải mới',Path(self.folder.get())),('Cấu hình, hàng đợi, nhật ký đang tải',data),('Dữ liệu bản cũ (chưa xóa)',old),('Bản sao lưu cập nhật',root/'_updates'),('Trình duyệt cài riêng',root/'.browsers'),('Trình duyệt Playwright cũ dùng chung',Path(os.environ.get('LOCALAPPDATA',Path.home()/'.cache'))/'ms-playwright')]
            # No recursive scan of story library on the UI thread.
            text='DỮ LIỆU ĐƯỢC LƯU Ở ĐÂU?\n\n'+'\n\n'.join(f'{label}\n{p}' for label,p in paths)+'\n\nNhật ký tối đa khoảng 512 KB/tác vụ, màn hình chỉ hiện 100 dòng cuối. Truyện hoàn tất được dọn dữ liệu tạm; tác vụ nhỏ giữ đến khi bạn bấm Dọn hoàn tất.\n\nĐổi nơi lưu mặc định chỉ áp dụng cho truyện mới. Với truyện đang tải dở, chọn Thao tác → Chuyển nơi lưu truyện này.\n\nTrình duyệt và môi trường Python là phần mềm dùng lại, không phải rác truyện; không tự xóa trình duyệt dùng chung với ứng dụng khác.'
            box.configure(state='normal');box.delete('1.0','end');box.insert('end',text);box.configure(state='disabled')
        scan()
        buttons=ctk.CTkFrame(win,fg_color='transparent');buttons.pack(fill='x',padx=20,pady=(0,20))
        from main import open_path
        self.button(buttons,'Mở dữ liệu hiện tại',lambda:open_path(data),width=165).pack(side='left')
        def purge_legacy():
            if self.busy or self.manager.active_id or self.manager.worker and self.manager.worker.is_alive():messagebox.showinfo('Dừng phiên','Dừng tải trước khi dọn.',parent=win);return
            if old.resolve()==data.resolve():messagebox.showinfo('Đang dùng','Đây là nơi dữ liệu hiện tại; không thể dọn như bản cũ.',parent=win);return
            if not messagebox.askyesno('Dọn dữ liệu bản cũ',f'Xóa cấu hình, hàng đợi, lịch sử, nhật ký và hồ sơ Chromium cũ trong:\n{old}\n\nBản mới đã nhập hàng đợi vào {data}. Hãy đóng các bản ứng dụng cũ. Tệp không nhận diện và bản sao lưu cập nhật sẽ được giữ và báo lại.',parent=win):return
            def job():
                import re
                removed=0
                # Clean completed legacy checkpoints too, before deleting their records.
                records=read_json(old/'completed-history.json',[])+read_json(old/'tasks.json',[])
                for record in records:
                    if record.get('state')=='completed': clean_task(record,old)
                for p in old.iterdir() if old.exists() else []:
                    if p.name in {'settings.json','tasks.json','completed-history.json'} or re.fullmatch(r'[0-9a-f]{32}\.(log|last-error\.txt)',p.name):
                        if p.is_symlink():raise ValueError('Không xóa liên kết '+str(p))
                        p.unlink();removed+=1
                    elif p.name=='browser-profile':remove_owned_tree(p,old);removed+=1
                remains=[p.name for p in old.iterdir()] if old.exists() else []
                return f'Đã xóa {removed} mục dữ liệu cũ. '+('Còn: '+', '.join(remains) if remains else 'Không còn dữ liệu trong thư mục cũ.')
            self.background(job,lambda msg:(self.notify(msg),scan()))
        self.button(buttons,'Dọn dữ liệu bản cũ trên C:',purge_legacy,width=210).pack(side='right')
        tools=ctk.CTkFrame(win,fg_color='transparent');tools.pack(fill='x',padx=20,pady=(0,15))
        def measure():
            if self.busy or self.manager.active_id:
                self.notify("Dừng phiên trước khi quét dung lượng.");return
            def job():
                return '\n\nDUNG LƯỢNG ĐÃ ĐO\n'+'\n'.join(f'{p}: {bytes_used(p)/1048576:.1f} MB' for p in [data,old,root/'_updates',root/'.browsers'])
            def show(text):
                if win.winfo_exists():box.configure(state='normal');box.insert('end',text);box.configure(state='disabled');box.see('end')
            self.background(job,show)
        def clear_sessions():
            if self.busy or self.manager.active_id:return
            if not messagebox.askyesno('Dọn phiên tạm','Xóa bộ nhớ tạm và hồ sơ trình duyệt của các phiên đã dừng. Có thể phải xác minh lại khi dùng Chromium. Giữ mốc và phần truyện đang tải dở trong Downloads.',parent=win):return
            def job():
                remove_owned_tree(data/'sessions',data)
                remove_owned_tree(data/'runtime',data)
                (data/'runtime').mkdir(exist_ok=True)
                return 'Đã dọn phiên tạm; giữ tiến độ truyện tải dở.'
            self.background(job,lambda msg:self.notify(msg))
        self.button(tools,'Kiểm tra dung lượng',measure,width=160).pack(side='left')
        self.button(tools,'Dọn phiên tạm đã dừng',clear_sessions,width=190).pack(side='right')

    def poll(self):
        try:
            while not self.actions.empty():
                done,value,error=self.actions.get_nowait();self.busy=False
                if error:self.notify(str(error),True)
                else:done(value)
            if not self.busy:
                ended_id=self.manager.active_id
                self.manager.drain()
                if self.manager.notice and self.manager.notice[1] and ended_id:
                    self.selected_id=ended_id;self.follow.set(False)
                self.refresh()
            if self.manager.notice:self.manager.notice=None
            if self.closing and not self.busy and not (self.manager.worker and self.manager.worker.is_alive()):self.destroy();return
        except Exception as e:self.manager.auto_run=False;self.manager.stop_event.set();self.notify(str(e),True)
        self.after(500,self.poll)

    def close(self):
        if self.busy:self.notify('Đang chuyển/dọn dữ liệu, vui lòng chờ hoàn tất.');return
        super().close()
 return Desktop()
