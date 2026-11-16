"""智播课堂 Live · 桌面版界面（浅色简约风）。

- show_picker：选教室（搜索、卡片、添加/删除、账号设置）
- control_window：播放窗口（左边切画面，右边实时字幕 + 全部转写，底部字幕开关）
- 字幕条：浮在视频画面底部的无边框窗口，跟着播放器窗口走
"""

import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

import ui_kit as U
from subtitles import LiveTranscripts

PRODUCT = '智播课堂 Live'
TAGLINE = 'ZUFE LIVE VIEWER'


def _watch():
    import watch_live
    return watch_live


# ---------------------------------------------------------------- 小工具
def _field(parent, label, value='', show=None):
    """一行输入框：标题 + 深色 entry。"""
    tk.Label(parent, text=label, bg=U.BG, fg=U.DIM, font=U.font(10)).pack(anchor='w')
    var = tk.StringVar(value=value)
    entry = tk.Entry(parent, textvariable=var, bg=U.CARD, fg=U.TEXT, insertbackground=U.TEXT,
                     relief='flat', bd=0, font=U.font(11), highlightthickness=1,
                     highlightbackground=U.LINE, highlightcolor=U.ACCENT, show=show or '')
    entry.pack(fill='x', ipady=7, pady=(4, 12))
    return var, entry


def _modal(root, title, width, height):
    top = tk.Toplevel(root)
    top.title(title)
    top.configure(bg=U.BG)
    top.transient(root)
    top.resizable(False, False)
    U.center(top, width, height, dy=-40)
    U.apply_dark_titlebar(top)
    try:
        top.grab_set()
    except Exception:
        pass
    return top


# ---------------------------------------------------------------- 选教室
def show_picker(opts):
    W = _watch()
    rooms = W.load_rooms()
    state = {'room': None, 'filter': ''}
    selected = {'name': None}
    cards = {}

    root = tk.Tk()
    root.title(PRODUCT)
    root.configure(bg=U.BG)
    sw, sh = U.screen_size()
    win_w, win_h = min(1000, max(820, sw - 200)), min(780, max(600, sh - 120))
    U.center(root, win_w, win_h)
    root.minsize(min(820, win_w), min(600, win_h))
    U.apply_titlebar(root, dark=False)

    outer = tk.Frame(root, bg=U.BG)
    outer.pack(fill='both', expand=True, padx=22, pady=18)

    # ---- 头部
    head = tk.Frame(outer, bg=U.BG)
    head.pack(fill='x')
    titles = tk.Frame(head, bg=U.BG)
    titles.pack(side='left', fill='x', expand=True)
    brand = tk.Frame(titles, bg=U.BG)
    brand.pack(anchor='w')
    tk.Label(brand, text=PRODUCT, bg=U.BG, fg=U.TEXT,
             font=U.font(21, True)).pack(side='left')
    tk.Label(brand, text='  ' + TAGLINE, bg=U.BG, fg=U.ACCENT,
             font=U.font(9, True, 'latin')).pack(side='left', pady=(8, 0))
    sub_label = tk.Label(titles, text='', bg=U.BG, fg=U.DIM, font=U.font(10))
    sub_label.pack(anchor='w', pady=(3, 0))

    tools = tk.Frame(head, bg=U.BG)
    tools.pack(side='right')

    acc = W.load_account()
    btn_acc = U.FlatButton(tools, '账号设置', command=lambda: open_account(), kind='ghost')
    btn_acc.pack(side='right')
    btn_login = U.FlatButton(tools, '浏览器登录', command=lambda: do_login_now(), kind='ghost')
    btn_login.pack(side='right', padx=(0, 8))

    # ---- 搜索
    search_card = tk.Frame(outer, bg=U.CARD, highlightthickness=1,
                           highlightbackground=U.LINE, highlightcolor=U.LINE)
    search_card.pack(fill='x', pady=(16, 12))
    tk.Label(search_card, text='搜索', bg=U.CARD, fg=U.FAINT,
             font=U.font(10)).pack(side='left', padx=(14, 8), pady=9)
    search_var = tk.StringVar()
    entry = tk.Entry(search_card, textvariable=search_var, bg=U.CARD, fg=U.TEXT,
                     insertbackground=U.TEXT, relief='flat', bd=0, font=U.font(11),
                     highlightthickness=0)
    entry.pack(side='left', fill='x', expand=True, pady=9)
    clear_btn = tk.Label(search_card, text='清空', bg=U.CARD, fg=U.FAINT, font=U.font(9),
                         cursor='hand2', padx=12)
    clear_btn.pack(side='right')
    clear_btn.bind('<Button-1>', lambda e: (search_var.set(''), render()))

    # ---- 教室卡片区
    grid_box = U.VScroll(outer)
    grid_box.pack(fill='both', expand=True)
    for col in range(3):
        grid_box.body.columnconfigure(col, weight=1, uniform='room')

    def paint_card(name, is_sel):
        item = cards.get(name)
        if not item:
            return
        bg = U.CARD_HI if is_sel else U.CARD
        line = U.ACCENT if is_sel else U.LINE
        item['card'].configure(bg=bg, highlightbackground=line)
        item['inner'].configure(bg=bg)
        item['name'].configure(bg=bg, fg=U.TEXT)
        item['meta'].configure(bg=bg, fg=U.ACCENT if is_sel else U.FAINT)

    def select(name):
        selected['name'] = name
        for other in cards:
            paint_card(other, other == name)
        play_btn.set_enabled(bool(name))
        del_btn.set_enabled(bool(name))
        hint.configure(text=f'已选 {name} · 双击也能直接看' if name else '点一下卡片选中，再点「开始看」')

    def play_room(_event=None):
        name = selected['name']
        if not name:
            hint.configure(text='先点一间教室')
            return
        state['room'] = name
        root.destroy()

    def make_card(name, row, col):
        last = W.load_last_room()
        links = rooms.get(name) or []
        card = tk.Frame(grid_box.body, bg=U.CARD, highlightthickness=1,
                        highlightbackground=U.LINE, cursor='hand2')
        card.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
        inner = tk.Frame(card, bg=U.CARD)
        inner.pack(fill='both', expand=True, padx=15, pady=13)
        name_lbl = tk.Label(inner, text=name, bg=U.CARD, fg=U.TEXT,
                            font=U.font(16, True, 'mono'), anchor='w')
        name_lbl.pack(anchor='w')
        meta_text = f'{len(links)} 条链接' + (' · 上次看的' if name == last else '')
        meta = tk.Label(inner, text=meta_text, bg=U.CARD, fg=U.FAINT,
                        font=U.font(9, False, 'latin'), anchor='w')
        meta.pack(anchor='w', pady=(5, 0))

        def hover(on):
            if selected['name'] != name:
                bg = U.CARD_HI if on else U.CARD
                card.configure(bg=bg)
                inner.configure(bg=bg)
                name_lbl.configure(bg=bg)
                meta.configure(bg=bg)
        for widget in (card, inner, name_lbl, meta):
            widget.bind('<Enter>', lambda e: hover(True))
            widget.bind('<Leave>', lambda e: hover(False))
            widget.bind('<Button-1>', lambda e: select(name))
            widget.bind('<Double-1>', lambda e: (select(name), play_room()))
        cards[name] = {'card': card, 'inner': inner, 'name': name_lbl, 'meta': meta}

    def render():
        if search_var.get().strip() and search_var.get() != state['filter']:
            state['filter'] = search_var.get()
        query = state['filter'].strip().lower()
        fresh = W.load_rooms()
        rooms.clear()
        rooms.update(fresh)
        names = sorted(fresh, key=W.room_key)
        shown = [n for n in names if not query or query in n.lower()]
        grid_box.clear()
        cards.clear()
        for index, name in enumerate(shown):
            make_card(name, index // 3, index % 3)
        grid_box.bind_wheel()
        grid_box.canvas.update_idletasks()
        grid_box._refresh()
        grid_box.scroll_to_bottom()
        grid_box.canvas.yview_moveto(0)
        total = len(names)
        sub_label.configure(
            text=(f'共 {total} 间教室' if not query else f'找到 {len(shown)} 间（共 {total} 间）')
            + ' · 点一下选中，双击直接看')
        keep = selected['name'] if selected['name'] in shown else (shown[0] if shown else None)
        select(keep)

    search_var.trace_add('write', lambda *a: render())

    # ---- 底部
    foot = tk.Frame(outer, bg=U.BG)
    foot.pack(fill='x', pady=(14, 0))
    add_btn = U.FlatButton(foot, '添加教室', command=lambda: open_add(), kind='ghost')
    add_btn.pack(side='left')
    del_btn = U.FlatButton(foot, '删除选中', command=lambda: do_delete(), kind='ghost')
    del_btn.pack(side='left', padx=(8, 0))
    hint = tk.Label(foot, text='', bg=U.BG, fg=U.FAINT, font=U.font(9))
    hint.pack(side='left', padx=(14, 0))
    play_btn = U.FlatButton(foot, '开始看  ▶', command=play_room, kind='primary',
                            size=12, bold=True, padx=24, pady=9)
    play_btn.pack(side='right')

    # ---- 对话框
    def open_add():
        top = _modal(root, '添加教室', 520, 330)
        box = tk.Frame(top, bg=U.BG)
        box.pack(fill='both', expand=True, padx=20, pady=16)
        tk.Label(box, text='教室名和直播间链接', bg=U.BG, fg=U.TEXT,
                 font=U.font(13, True)).pack(anchor='w')
        tk.Label(box, text='链接就是浏览器地址栏里带 speechid=…&enc=… 的那串',
                 bg=U.BG, fg=U.FAINT, font=U.font(9)).pack(anchor='w', pady=(2, 14))
        name_var, name_entry = _field(box, '教室名（例如 9202 / B105）')
        link_var, link_entry = _field(box, '直播间链接')
        name_entry.focus_set()

        def save():
            name = name_var.get().strip().upper()
            link = W.normalize_link(link_var.get().strip())
            if not name:
                messagebox.showwarning('缺教室名', '先填教室名，例如 9202 / B105。', parent=top)
                return
            ok, why = W.check_link(link)
            if not ok:
                messagebox.showwarning('链接不对', why, parent=top)
                return
            current = W.load_rooms()
            links = current.get(name, [])
            if link in links:
                messagebox.showinfo('已经有了', f'{name} 已经有这条链接了。', parent=top)
                return
            links.append(link)
            current[name] = links
            W.save_rooms(current)
            selected['name'] = name
            state['filter'] = ''
            search_var.set('')
            render()
            top.destroy()
            hint.configure(text=f'{name} 已加入列表')

        bar = tk.Frame(box, bg=U.BG)
        bar.pack(fill='x', side='bottom')
        U.FlatButton(bar, '保存', command=save, kind='primary').pack(side='right')
        U.FlatButton(bar, '取消', command=top.destroy, kind='ghost').pack(side='right', padx=(0, 8))

    def open_account():
        top = _modal(root, '超星账号（可选）', 500, 400)
        box = tk.Frame(top, bg=U.BG)
        box.pack(fill='both', expand=True, padx=20, pady=16)
        tk.Label(box, text='填一次账号密码', bg=U.BG, fg=U.TEXT,
                 font=U.font(13, True)).pack(anchor='w')
        tk.Label(box, text='填了就能静默登录，不用每次开浏览器；不填也没关系。',
                 bg=U.BG, fg=U.FAINT, font=U.font(9)).pack(anchor='w', pady=(2, 14))
        cur = W.load_account()
        user_var, _ = _field(box, '超星账号（手机号 / 学号）', cur.get('user', ''))
        pass_var, _ = _field(box, '密码', cur.get('password', ''), show='*')

        def save():
            user, pwd = user_var.get().strip(), pass_var.get()
            if not user or not pwd:
                messagebox.showwarning('没填完', '账号和密码都要填。', parent=top)
                return
            W.save_account(user, pwd)
            btn_acc.set_text('账号设置')
            top.destroy()
            hint.configure(text=f'账号已保存（{user}）')

        def clear_login():
            try:
                W.close_our_edge(graceful=False)
            except Exception:
                pass
            for path in (W.PROFILE_DIR,):
                try:
                    if path.exists():
                        import shutil
                        shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass
            hint.configure(text='已清除浏览器里的登录状态')
            top.destroy()

        bar = tk.Frame(box, bg=U.BG)
        bar.pack(fill='x', side='bottom')
        U.FlatButton(bar, '保存', command=save, kind='primary').pack(side='right')
        U.FlatButton(bar, '取消', command=top.destroy, kind='ghost').pack(side='right', padx=(0, 8))
        U.FlatButton(bar, '清除浏览器登录状态', command=clear_login, kind='danger').pack(side='left')

    def do_login_now():
        name = selected['name']
        if not name:
            hint.configure(text='先点一间教室（用它打开登录页）')
            return
        link = (W.load_rooms().get(name) or [None])[0]
        if not link:
            hint.configure(text=f'{name} 还没有链接')
            return
        W.save_last_room(name)
        btn_login.set_enabled(False)
        btn_login.set_text('登录中…')
        hint.configure(text=f'正在打开浏览器，请用 {name} 的链接登录…')

        def worker():
            try:
                data = W.browser_login(link, name, log=lambda m: print(m, flush=True))
            except Exception as exc:
                message = f'{type(exc).__name__}: {exc}'
                root.after(0, lambda: done(False, message))
                return
            ok = bool(data and data.get('main'))
            if ok:
                W._cache_streams(name, data)
            root.after(0, lambda: done(ok))

        def done(ok, err=None):
            btn_login.set_enabled(True)
            btn_login.set_text('浏览器登录')
            if ok:
                hint.configure(text='登录成功，登录状态已保存')
                messagebox.showinfo('登录成功', '登录状态已保存，直接点「开始看」就行。', parent=root)
            else:
                hint.configure(text='登录没成功，可以再试一次')
                messagebox.showwarning('登录未完成', err or '没有检测到登录成功。', parent=root)

        threading.Thread(target=worker, daemon=True).start()

    def do_delete():
        name = selected['name']
        if not name:
            hint.configure(text='先点一间教室')
            return
        if not messagebox.askyesno('删除教室', f'确定从列表里删掉 {name} 吗？（不影响学校系统）',
                                   parent=root):
            return
        current = W.load_rooms()
        current.pop(name, None)
        W.save_rooms(current)
        selected['name'] = None
        render()
        hint.configure(text=f'已删除 {name}')

    root.bind('<Return>', play_room)
    root.bind('<Escape>', lambda e: root.destroy())
    render()
    entry.focus_set()
    root.mainloop()
    return state['room']


# ---------------------------------------------------------------- 字幕条
class SubtitleBar:
    """浮在视频画面底部的字幕条（无边框、置顶、不吃鼠标）。"""

    def __init__(self, root):
        self.top = tk.Toplevel(root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        try:
            self.top.title('LiveSubBar')
        except Exception:
            pass
        self.top.configure(bg='#05070A')
        try:
            self.top.attributes('-topmost', True)
            self.top.attributes('-alpha', 0.88)
        except Exception:
            pass
        self.canvas = tk.Canvas(self.top, bg='#05070A', highlightthickness=0, bd=0, height=64)
        self.canvas.pack(fill='both', expand=True)
        self.text = ''
        self.size = 16
        self._click_ready = False
        self._geo = None

    def set_text(self, text):
        text = (text or '').strip()
        if text == self.text:
            return
        self.text = text
        self._draw()

    def _draw(self):
        self.canvas.delete('all')
        width = max(200, self.top.winfo_width())
        height = max(40, self.top.winfo_height())
        if not self.text:
            return
        kwargs = dict(text=self.text, width=width - 34, justify='center', anchor='center',
                      font=(U.FONT, self.size, 'bold'))
        self.canvas.create_text(width / 2 + 1, height / 2 + 2, fill='#000000', **kwargs)
        self.canvas.create_text(width / 2, height / 2, fill='#FFFFFF', **kwargs)

    def show_at(self, x, y, width, height, size):
        width, height = int(width), int(height)
        # 关键顺序：先 deiconify 再 geometry。overrideredirect 的 Toplevel 在 withdrawn
        # 状态下设 geometry 会被忽略，deiconify 时才用默认位置（实测会跑到屏幕中间）。
        if not self.top.winfo_viewable():
            self.top.deiconify()
            self._geo = None
            if not self._click_ready:
                U.make_click_through(self.top)
                self._click_ready = True
        if (x, y, width, height) != self._geo:
            self._geo = (x, y, width, height)
            self.canvas.configure(height=height)
            self.top.geometry(f'{width}x{height}+{int(x)}+{int(y)}')
            self.top.update_idletasks()
        if self.size != size:
            self.size = size
            self._draw()
        try:
            self.top.attributes('-topmost', True)
        except Exception:
            pass
        self.top.lift()
        self._draw()

    def measure(self, text, size):
        try:
            f = tkfont.Font(family=U.FONT, size=size, weight='bold')
            return f.measure(text or ' ')
        except Exception:
            return len(text or ' ') * int(size * 1.1)

    def hide(self):
        if self.top.winfo_viewable():
            self.top.withdraw()


# ---------------------------------------------------------------- 播放窗口
def control_window(room, data, opts, player, kind):
    W = _watch()
    streams = {'main': data.get('main'), 'ppt': data.get('ppt')}
    course = (data.get('course') or '').strip()
    views = [(key, label) for key, label in W.VIEWS if streams.get(key)]
    if not views:
        print('[!] 这个直播间没有可播放的画面')
        return 1
    names = dict(views)
    want = str(opts.get('view') or '').lower()
    start_view = want if want in names else views[0][0]

    root = tk.Tk()
    root.title(f'{PRODUCT} · {room}')
    root.configure(bg=U.BG)
    sw, sh = U.screen_size()
    win_w = min(860, max(640, int(sw * 0.34)))
    win_h = max(560, sh - 60)
    root.geometry(f'{win_w}x{win_h}+{sw - win_w - 16}+6')
    root.minsize(min(600, win_w), min(520, win_h))
    U.apply_dark_titlebar(root)

    state = {'proc': None, 'view': None, 'sub_on': True, 'count': 0, 'arranged': False}
    q = queue.Queue()

    outer = tk.Frame(root, bg=U.BG)
    outer.pack(fill='both', expand=True, padx=18, pady=14)

    # ---- 头部
    head = tk.Frame(outer, bg=U.BG)
    head.pack(fill='x')
    left_head = tk.Frame(head, bg=U.BG)
    left_head.pack(side='left', fill='x', expand=True)
    tk.Label(left_head, text=room, bg=U.BG, fg=U.TEXT, font=U.font(22, True, 'mono')).pack(anchor='w')
    tk.Label(left_head, text=course or '直播间', bg=U.BG, fg=U.DIM,
             font=U.font(10)).pack(anchor='w', pady=(2, 0))
    pill = tk.Label(head, text='● 直播中', bg=U.SOFT_OK, fg=U.OK, font=U.font(10, True),
                    padx=12, pady=5)
    pill.pack(side='right')

    body = tk.Frame(outer, bg=U.BG)
    body.pack(fill='both', expand=True, pady=(14, 0))

    # ---- 左：画面控制
    left = U.Card(body)
    left.pack(side='left', fill='y')
    left.configure(width=252)
    left.pack_propagate(False)
    left_in = tk.Frame(left, bg=U.CARD)
    left_in.pack(fill='both', expand=True, padx=16, pady=16)
    tk.Label(left_in, text='画面', bg=U.CARD, fg=U.TEXT, font=U.font(12, True)).pack(anchor='w')
    tk.Label(left_in, text='视频在播放器窗口里，\n这里切换看哪一路。', bg=U.CARD, fg=U.FAINT,
             font=U.font(9), justify='left', anchor='w').pack(anchor='w', pady=(4, 14))

    view_btns = {}

    def seg_button(parent, text, action):
        lbl = tk.Label(parent, text=text, bg=U.CARD_HI, fg=U.TEXT, font=U.font(11, True),
                       padx=14, pady=10, cursor='hand2', anchor='w')
        lbl._on = False

        def paint(color):
            lbl.configure(bg=color)

        lbl.bind('<Enter>', lambda e: paint(U.ACCENT_HI if lbl._on else '#E8EEF7'))
        lbl.bind('<Leave>', lambda e: paint(U.ACCENT if lbl._on else U.CARD_HI))
        lbl.bind('<Button-1>', lambda e: action())
        lbl.set_on = lambda on: (setattr(lbl, '_on', on),
                                 lbl.configure(bg=U.ACCENT if on else U.CARD_HI,
                                               fg='#FFFFFF' if on else U.TEXT))
        return lbl

    def refresh_views():
        for key, btn in view_btns.items():
            btn.set_on(state['view'] == key)

    play_state = tk.Label(left_in, text='', bg=U.CARD, fg=U.DIM, font=U.font(9),
                          justify='left', anchor='w', wraplength=212)
    play_state.pack(anchor='w', pady=(16, 0))

    actions = tk.Frame(left_in, bg=U.CARD)
    actions.pack(fill='x', side='bottom')
    reload_btn = U.FlatButton(actions, '重新连接', command=lambda: (launch(state['view']), restart_subs()),
                              kind='ghost')
    reload_btn.pack(fill='x', pady=(0, 8))
    close_btn = U.FlatButton(actions, '关闭画面', command=lambda: stop_current(), kind='ghost')
    close_btn.pack(fill='x')
    aid = tk.Label(left_in, text=f'播放器：{"VLC" if kind == "vlc" else "ffplay"}',
                   bg=U.CARD, fg=U.FAINT, font=U.font(9), anchor='w', justify='left')
    aid.pack(anchor='w', pady=(10, 0))

    # ---- 右：字幕 + 转写
    right = tk.Frame(body, bg=U.BG)
    right.pack(side='left', fill='both', expand=True, padx=(14, 0))
    right.pack_propagate(False)

    now_card = U.Card(right)
    now_card.pack(fill='x')
    now_in = tk.Frame(now_card, bg=U.CARD)
    now_in.pack(fill='x', padx=16, pady=13)
    top_row = tk.Frame(now_in, bg=U.CARD)
    top_row.pack(fill='x')
    tk.Label(top_row, text='实时字幕', bg=U.CARD, fg=U.DIM, font=U.font(10)).pack(side='left')
    sub_state = tk.Label(top_row, text='等待识别…', bg=U.CARD, fg=U.FAINT, font=U.font(9))
    sub_state.pack(side='right')
    now_label = tk.Label(now_in, text='（还没识别到说话）', bg=U.CARD, fg=U.TEXT,
                         font=U.font(17, True), anchor='w', justify='left')
    now_label.pack(anchor='w', fill='x', pady=(8, 0))
    now_chars = {'n': max(9, int((win_w - 348) / 25))}

    def set_now(text):
        text = (text or '').strip()
        if not text:
            now_label.configure(text='（还没识别到说话）', fg=U.FAINT)
            return
        now_label.configure(text=U.cjk_wrap(text, now_chars['n']), fg=U.TEXT)

    all_card = U.Card(right)
    all_card.pack(fill='both', expand=True, pady=(12, 0))
    all_head = tk.Frame(all_card, bg=U.CARD)
    all_head.pack(fill='x', padx=16, pady=(12, 6))
    tk.Label(all_head, text='全部说过的话', bg=U.CARD, fg=U.TEXT,
             font=U.font(12, True)).pack(side='left')
    tk.Label(all_head, text='带时间 · 和网页端一样', bg=U.CARD, fg=U.FAINT,
             font=U.font(9, False, 'latin')).pack(side='left', padx=(8, 0))
    count_label = tk.Label(all_head, text='0 段', bg=U.CARD, fg=U.FAINT, font=U.font(9, False, 'mono'))
    count_label.pack(side='right')
    text_box = U.TextBox(all_card, size=11)
    text_box.pack(fill='both', expand=True, padx=12, pady=(0, 12))

    # ---- 底部：字幕开关
    foot = tk.Frame(outer, bg=U.BG)
    foot.pack(fill='x', pady=(12, 0))
    tk.Label(foot, text='字幕条', bg=U.BG, fg=U.TEXT, font=U.font(10, True)).pack(side='left')
    sub_hint = tk.Label(foot, text='浮在视频画面底部', bg=U.BG, fg=U.FAINT, font=U.font(9))
    status_foot = tk.Label(foot, text='', bg=U.BG, fg=U.DIM, font=U.font(9))
    status_foot.pack(side='right')

    bar = SubtitleBar(root)
    toggle = U.Toggle(foot, value=True, command=lambda v: on_toggle_sub(v), bg=U.BG)
    toggle.pack(side='left', padx=(10, 6))
    sub_hint.pack(side='left')

    def on_toggle_sub(value):
        state['sub_on'] = bool(value)
        sub_hint.configure(text='浮在视频画面底部' if value else '已关闭')
        if not value:
            bar.hide()

    # ---- 播放控制
    def stop_current():
        proc, state['proc'] = state['proc'], None
        W._stop_player(proc)
        play_state.configure(text='画面已关闭')
        pill.configure(text='○ 已停', bg=U.SOFT_OFF, fg=U.DIM)

    def launch(view):
        url = streams.get(view)
        if not url:
            play_state.configure(text=f'{names.get(view, view)}：这一路没有画面')
            return
        stop_current()
        title = f'{room} {names.get(view, "")}'.strip()
        try:
            state['proc'] = W._start_player(url, title, opts, player, kind)
        except Exception as exc:
            play_state.configure(text=f'启动播放器失败：{exc}')
            return
        state['view'] = view
        refresh_views()
        play_state.configure(text=f'正在播放：{names[view]}')
        pill.configure(text='● 直播中', bg=U.SOFT_OK, fg=U.OK)
        if not state['arranged']:
            root.after(1600, arrange_video)

    def arrange_video():
        """把播放器窗口摆到左边，控制窗摆到右边，像网页那样并排看。"""
        if state['arranged'] or not state['view']:
            return
        hwnd = U.find_window_hwnd(room, names.get(state['view'], '')) or U.find_window_hwnd(room)
        if not hwnd:
            root.after(900, arrange_video)
            return
        sw, sh = U.screen_size()
        panel_w = win_w
        video_w = max(600, sw - panel_w - 26)
        video_h = int(video_w * 9 / 16) + 62
        if video_h > sh - 30:
            video_h = sh - 30
            video_w = int((video_h - 62) * 16 / 9)
        U.restore_window(hwnd)
        U.move_window(hwnd, 0, 0, video_w, video_h)
        state['video_rect'] = (0, 0, video_w, video_h)
        state['arrange_left'] = 20
        try:
            root.update_idletasks()
            root.lift()
        except Exception:
            pass
        state['arranged'] = True

    for key, label in views:
        btn = seg_button(left_in, label, lambda k=key: launch(k))
        btn.pack(fill='x', pady=(0, 8))
        view_btns[key] = btn

    # ---- 字幕客户端
    client = {'obj': None}

    def restart_subs():
        old = client['obj']
        if old:
            old.stop()
        state['count'] = 0
        text_box.clear()
        count_label.configure(text='0 段')
        set_now('')
        obj = LiveTranscripts(streams.get('main') or '', data.get('enc') or '',
                              data.get('fid') or 0, data.get('speechid') or 0,
                              referer=data.get('link') or '', on_update=lambda: q.put('t'))
        client['obj'] = obj
        if not obj.start():
            sub_state.configure(text='没有开 AI 转写')
            status_foot.configure(text=obj.error or '字幕不可用')
            return
        sub_state.configure(text='连接中…')

    def drain():
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass
        obj = client['obj']
        if obj is not None:
            snap = obj.snapshot()
            new = snap['segments'][state['count']:]
            if new:
                follow = True
                for row in new:
                    text_box.append(row['clock'], row['text'], follow=follow)
                state['count'] = len(snap['segments'])
                count_label.configure(text=f"{state['count']} 段")
            live_text = snap['mid_text'] or (snap['segments'][-1]['text'] if snap['segments'] else '')
            if live_text:
                set_now(live_text)
                bar.set_text(live_text)
            if snap['status'] == 'error':
                sub_state.configure(text='连接异常')
                status_foot.configure(text=snap['error'][:60])
            elif snap['status'] == 'live':
                sub_state.configure(text='识别中')
            elif snap['status'] == 'waiting':
                sub_state.configure(text='等待说话…')
            status_foot.configure(
                text=f"{'已识别' if state['count'] else '等待'} {state['count']} 段"
                     + (f" · {names.get(state['view'], '')}" if state['view'] else ''))
        root.after(400, drain)

    def tick():
        proc = state['proc']
        if proc is not None and proc.poll() is not None:
            state['proc'] = None
            play_state.configure(text='画面窗口被关掉了，点「重新连接」再看')
            pill.configure(text='○ 已停', bg=U.SOFT_OFF, fg=U.DIM)
        hwnd2 = U.find_window_hwnd(room, names.get(state['view'], '')) or U.find_window_hwnd(room)
        if state.get('video_rect') and hwnd2:
            cur = U.window_rect(hwnd2)
            want = state['video_rect']
            if cur and (abs(cur[0] - want[0]) > 8 or abs(cur[1] - want[1]) > 8
                        or abs(cur[2] - want[2]) > 8 or abs(cur[3] - want[3]) > 8):
                U.move_window(hwnd2, want[0], want[1], want[2], want[3])
        if state['sub_on'] and state['view']:
            rect = U.window_rect(hwnd2) if hwnd2 else None
            if rect:
                rect = (rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3])
            if not rect:
                rect = U.find_window_rect(room, names.get(state['view'], ''))
                if not rect:
                    rect = U.find_window_rect(room)
            if rect:
                l, t, r, b = rect
                w, h = r - l, b - t
                if w > 240 and h > 150:
                    bar_h = max(42, min(78, int(w * 0.062)))
                    size = max(13, min(30, int(w / 40)))
                    maxw = int(w * 0.9)
                    text = (bar.text or ' ').strip() or ' '
                    tw = bar.measure(text, size) + int(size * 2.2)
                    bw = max(int(w * 0.22), min(maxw, tw))
                    bx = l + (w - bw) // 2
                    by = b - int(bar_h * 1.35) - bar_h
                    bar.show_at(bx, by, bw, bar_h, size)
            else:
                bar.hide()
        elif not state['sub_on']:
            bar.hide()
        root.after(450, tick)

    def on_close():
        try:
            obj = client['obj']
            if obj:
                obj.stop()
        except Exception:
            pass
        stop_current()
        try:
            bar.top.destroy()
        except Exception:
            pass
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', on_close)
    root.bind('<Escape>', lambda e: on_close())

    launch(start_view)
    restart_subs()
    root.after(400, drain)
    root.after(450, tick)
    root.mainloop()
    return 0
