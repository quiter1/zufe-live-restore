# 让窗口按真实分辨率绘制（高分屏不糊），必须在创建 Tk 之前调用。
def _enable_dpi_awareness():
    try:
        import ctypes as _ct
        try:
            _ct.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            _ct.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()
"""界面零件：浅色简约风（tkinter 自绘，不依赖 ttk）。"""

import ctypes
from ctypes import wintypes
import tkinter as tk

# ------------------------------------------------------------------ 配色
BG = '#F4F6FA'
CARD = '#FFFFFF'
CARD_HI = '#EEF2F8'
LINE = '#E3E9F2'
LINE_HI = '#CBD5E1'
TEXT = '#0F172A'
DIM = '#55657A'
FAINT = '#94A3B8'
ACCENT = '#2563EB'
ACCENT_HI = '#3B82F6'
ACCENT_DK = '#1D4ED8'
OK = '#0E9F6E'
WARN = '#D97706'
ERR = '#DC2626'
SOFT_OK = '#E7F7F0'
SOFT_OFF = '#F1F5F9'
FONT = 'Microsoft YaHei UI'
FONT_LATIN = 'Segoe UI'
FONT_MONO = 'Consolas'

_user32 = ctypes.windll.user32 if hasattr(ctypes, 'windll') else None


_BREAK_AFTER = '，。、；：！？）》」』）,.!?:;)]}…'
_BREAK_BEFORE = '（《「『([{'


def cjk_wrap(text, max_chars):
    """中文按字数折行（tk 的 wraplength 只认空格，中文整段不换行）。"""
    text = (text or "").strip()
    limit = max(4, int(max_chars))
    if len(text) <= limit:
        return text
    lines, buf = [], []
    for ch in text:
        if ch == "\n":
            lines.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
        if len(buf) >= limit:
            cut = len(buf)
            for k in range(len(buf) - 1, max(limit - 6, 0) - 1, -1):
                if buf[k] in _BREAK_AFTER or buf[k].isspace():
                    cut = k + 1
                    break
            lines.append("".join(buf[:cut]).strip())
            buf = buf[cut:]
    tail = "".join(buf).strip()
    if tail:
        lines.append(tail)
    return "\n".join(lines)


def font(size, bold=False, family='ui'):
    """family：ui=中文正文，latin=英文数字，mono=编号/时间。"""
    face = {'latin': FONT_LATIN, 'mono': FONT_MONO}.get(family, FONT)
    return (face, size, 'bold' if bold else 'normal')


# ------------------------------------------------------------------ 窗口
def apply_titlebar(win, dark=False):
    """标题栏跟主题走：dark=False 是浅色（Win10 1809+ 才有）。"""
    try:
        hwnd = _user32.GetParent(win.winfo_id()) or win.winfo_id()
        flag = 1 if dark else 0
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(ctypes.c_int(flag)), ctypes.sizeof(ctypes.c_int))
    except Exception:
        pass


def apply_dark_titlebar(win):
    """旧名字，等价于 apply_titlebar(win, dark=True)。"""
    apply_titlebar(win, dark=True)


def center(win, width, height, dy=-20):
    try:
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2 + dy)
        win.geometry(f'{width}x{height}+{x}+{y}')
    except Exception:
        win.geometry(f'{width}x{height}')


def bind_wheel(widget, handler):
    """把滚轮事件绑到控件和它所有子控件上。"""
    widget.bind('<MouseWheel>', handler)
    for child in widget.winfo_children():
        bind_wheel(child, handler)


# ------------------------------------------------------------------ 控件
class Card(tk.Frame):
    """带 1px 描边的卡片。"""

    def __init__(self, parent, bg=CARD, line=LINE, padx=0, pady=0, **kw):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=1,
                         highlightbackground=line, highlightcolor=line, **kw)
        self._padx, self._pady = padx, pady


class FlatButton(tk.Label):
    """扁平按钮：主色 / 幽灵 / 危险 / 纯文字。"""

    KINDS = {
        'primary': (ACCENT, '#FFFFFF', ACCENT_HI, ACCENT_DK),
        'ghost': (CARD, TEXT, CARD_HI, '#E6EDF7'),
        'danger': ('#FEF2F2', ERR, '#FEE2E2', '#FECACA'),
        'plain': (BG, DIM, CARD, CARD_HI),
        'dark': (TEXT, '#FFFFFF', '#1E293B', '#0B1220'),
    }

    def __init__(self, parent, text, command=None, kind='ghost', size=11, bold=False,
                 padx=16, pady=8, width=None, bg_parent=None):
        bg, fg, hover, press = self.KINDS.get(kind, self.KINDS['ghost'])
        if bg_parent is not None and kind == 'plain':
            bg = bg_parent
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font(size, bold),
                         padx=padx, pady=pady, cursor='hand2', bd=0)
        if width:
            self.configure(width=width)
        self._bg, self._fg, self._hover, self._press = bg, fg, hover, press
        self._command = command
        self._enabled = True
        self.bind('<Enter>', lambda e: self._paint(self._hover))
        self.bind('<Leave>', lambda e: self._paint(self._bg))
        self.bind('<ButtonPress-1>', lambda e: self._paint(self._press))
        self.bind('<ButtonRelease-1>', self._release)

    def _paint(self, color):
        if self._enabled:
            self.configure(bg=color)

    def _release(self, _event=None):
        if not self._enabled:
            return
        self._paint(self._hover)
        if self._command:
            self._command()

    def set_enabled(self, enabled, dim=None):
        self._enabled = bool(enabled)
        self.configure(bg=self._bg if enabled else '#F2F5F9',
                       fg=self._fg if enabled else FAINT,
                       cursor='hand2' if enabled else 'arrow')

    def set_text(self, text):
        self.configure(text=text)


class Toggle(tk.Canvas):
    """开关：45×25 的胶囊。"""

    def __init__(self, parent, value=True, command=None, bg=BG):
        super().__init__(parent, width=45, height=25, bg=bg, highlightthickness=0,
                         bd=0, cursor='hand2')
        self.value = bool(value)
        self.command = command
        self.bind('<Button-1>', self._click)
        self._draw()

    def _draw(self):
        self.delete('all')
        track = ACCENT if self.value else '#CFD9E8'
        self.create_oval(1, 2, 23, 24, fill=track, outline='')
        self.create_oval(22, 2, 44, 24, fill=track, outline='')
        self.create_rectangle(12, 2, 33, 24, fill=track, outline='')
        cx = 33 if self.value else 12
        self.create_oval(cx - 9, 4, cx + 9, 22, fill='#FFFFFF', outline='')

    def _click(self, _event=None):
        self.set(not self.value, notify=True)

    def set(self, value, notify=False):
        self.value = bool(value)
        self._draw()
        if notify and self.command:
            self.command(self.value)


class VScroll(tk.Frame):
    """垂直滚动区：canvas + 内嵌 frame + 自绘细滚动条。"""

    def __init__(self, parent, bg=BG, bar_bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.bar = tk.Canvas(self, width=9, bg=bar_bg, highlightthickness=0, bd=0)
        self.bar.pack(side='right', fill='y')
        self.thumb = self.bar.create_rectangle(3, 0, 6, 40, fill=LINE_HI, outline='')
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', self._refresh)
        self.canvas.bind('<Configure>', self._refresh)
        self.bar.bind('<Configure>', lambda e: self._sync_bar())
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self._drag = None
        self.bar.bind('<Button-1>', self._bar_click)
        self.bar.bind('<B1-Motion>', self._bar_drag)
        self.bar.bind('<ButtonRelease-1>', lambda e: setattr(self, '_drag', None))
        self.bind_wheel()

    def bind_wheel(self):
        def wheel(event):
            self.canvas.yview_scroll(int(-event.delta / 120), 'units')
            return 'break'
        bind_wheel(self.body, wheel)
        self.canvas.bind('<MouseWheel>', wheel)

    def _refresh(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        width = self.canvas.winfo_width()
        if width > 1:
            self.canvas.itemconfigure(self._win, width=width)
        self._sync_bar()

    def _on_scroll(self, first, last):
        try:
            self._span = (float(first), float(last))
        except Exception:
            self._span = (0.0, 1.0)
        self._sync_bar()

    def _sync_bar(self):
        first, last = getattr(self, '_span', (0.0, 1.0))
        height = max(1, self.bar.winfo_height())
        span = max(0.04, last - first)
        thumb_h = max(28, int(height * span))
        room = max(1e-6, 1.0 - span)
        top = int((height - thumb_h) * (first / room)) if span < 1.0 else 0
        self.bar.coords(self.thumb, 3, top, 6, top + thumb_h)

    def _bar_click(self, event):
        self._drag = event.y
        self._jump(event.y)

    def _bar_drag(self, event):
        if self._drag is None:
            return
        self._jump(event.y)

    def _jump(self, y):
        height = max(1, self.bar.winfo_height())
        self.canvas.yview_moveto(max(0.0, min(1.0, y / height)))

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def scroll_to_bottom(self):
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def at_bottom(self):
        try:
            return self.canvas.yview()[1] >= 0.995
        except Exception:
            return True


class TextBox(tk.Text):
    """只读的深色文本区（转写列表用）。"""

    def __init__(self, parent, size=11, **kw):
        kw.setdefault('width', 1)
        kw.setdefault('height', 1)
        super().__init__(parent, bg=CARD, fg=TEXT, font=font(size), bd=0,
                         highlightthickness=0, wrap='char', spacing1=3, spacing3=5,
                         padx=4, pady=2, cursor='arrow', **kw)
        self.tag_configure('time', foreground=FAINT, font=font(max(8, size - 1), family='mono'))
        self.tag_configure('text', foreground=TEXT, font=font(size))
        self.tag_configure('now', foreground=ACCENT)
        self.configure(state='disabled')
        self.bind('<MouseWheel>', self._wheel)

    def _wheel(self, event):
        self.yview_scroll(int(-event.delta / 120), 'units')
        return 'break'

    def append(self, clock, text, follow=True):
        self.configure(state='normal')
        self.insert('end', f'{clock}  ', 'time')
        self.insert('end', f'{text}\n', 'text')
        self.configure(state='disabled')
        if follow:
            self.see('end')

    def clear(self):
        self.configure(state='normal')
        self.delete('1.0', 'end')
        self.configure(state='disabled')


# ------------------------------------------------------------------ 窗口跟踪
class _TitleFinder:
    def __init__(self):
        self.hits = []
        self.hwnds = []
        self.proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(self._cb)

    def _cb(self, hwnd, _lparam):
        try:
            if not _user32.IsWindowVisible(hwnd):
                return True
            length = _user32.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if any(part in title for part in SKIP_TITLES):
                return True
            if all(part.lower() in title.lower() for part in self.needles):
                rect = wintypes.RECT()
                _user32.GetWindowRect(hwnd, ctypes.byref(rect))
                if rect.right - rect.left > 80 and rect.bottom - rect.top > 40:
                    self.hits.append((rect.left, rect.top, rect.right, rect.bottom))
                    self.hwnds.append(hwnd)
                    return False
        except Exception:
            pass
        return True


SKIP_TITLES = ('智播课堂', 'LiveSubBar')


def find_window_rect(*needles):
    """按标题关键字找一个可见窗口，返回 (l, t, r, b)；找不到返回 None。"""
    if _user32 is None or not needles:
        return None
    finder = _TitleFinder()
    finder.needles = [n for n in needles if n]
    try:
        _user32.EnumWindows(finder.proc, 0)
    except Exception:
        return None
    return finder.hits[0] if finder.hits else None


def find_window_hwnd(*needles):
    """按标题关键字找窗口句柄；找不到返回 None。"""
    if _user32 is None or not needles:
        return None
    finder = _TitleFinder()
    finder.needles = [n for n in needles if n]
    try:
        _user32.EnumWindows(finder.proc, 0)
    except Exception:
        return None
    return finder.hwnds[0] if finder.hwnds else None


def restore_window(hwnd):
    """把窗口从最大化/最小化恢复成普通状态（不然挪不动）。"""
    if _user32 is None or not hwnd:
        return False
    try:
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return True
    except Exception:
        return False


def move_window(hwnd, x, y, width, height):
    """把别的程序的窗口挪到指定位置和大小（排列视频窗口用）。"""
    if _user32 is None or not hwnd:
        return False
    try:
        return bool(_user32.MoveWindow(hwnd, int(x), int(y), int(width), int(height), True))
    except Exception:
        return False


def make_click_through(win):
    """让窗口不吃鼠标事件（字幕浮在视频上时用）。"""
    try:
        hwnd = _user32.GetParent(win.winfo_id()) or win.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
    except Exception:
        pass


def screen_size():
    try:
        return _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080

def bring_top(win):
    """把窗口强制提到所有置顶窗口之上（VLC 有时自己也置顶）。"""
    try:
        hwnd = int(win.wm_frame(), 16)
    except Exception:
        try:
            hwnd = win.winfo_id()
        except Exception:
            return
    try:
        u = ctypes.windll.user32
        SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE = 0x0002, 0x0001, 0x0010
        u.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:
        pass

def window_rect(hwnd):
    """返回窗口实际矩形 (left, top, width, height)。"""
    try:
        r = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(int(hwnd), ctypes.byref(r))
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        return None

def window_top_hwnd(win):
    try:
        return ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
    except Exception:
        return 0


def set_window_rect(win, x, y, width, height, topmost=True):
    """用 SetWindowPos 直接摆置顶窗口（Tk 的 geometry 对 overrideredirect+topmost 不总生效）。"""
    hwnd = window_top_hwnd(win)
    if not hwnd:
        return False
    try:
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        after = -1 if topmost else 0
        ctypes.windll.user32.SetWindowPos(hwnd, after, int(x), int(y), int(width), int(height),
                                          SWP_NOACTIVATE | SWP_SHOWWINDOW)
        return True
    except Exception:
        return False
