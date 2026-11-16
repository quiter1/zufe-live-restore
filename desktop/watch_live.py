"""浙财智慧教室 · 看直播画面（独立版）

特点：
  * 不带课表：直接选教室就看
  * 一个直播间有两路画面：教室摄像头（课堂画面）和教室电脑桌面（课件），
    播放后会弹出小控制窗，点按钮就能来回切换
  * 教室/直播间链接自己维护：界面上可【添加】和【删除】
  * 首次运行要填一次超星账号密码（登录后解析出直播流地址）
  * 缺 VLC 会自动下载便携版（官方源 + 清华镜像，SHA256 校验）

用法：
    看直播.bat                      # 打开选择窗口
    看直播.bat B105                 # 直接看指定教室
    看直播.bat --list               # 列出所有教室
    看直播.bat --dry-run B105       # 只解析流地址，不播放
    看直播.bat --no-install         # 禁用 VLC 自动下载

本目录里的文件：
    rooms.json      教室 -> 直播间链接（界面上的添加/删除都写这里）
    account.json    超星账号密码（只存在本机，分享时删掉）
    .stream_cache.json  上次解析到的流地址（自动生成）
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE = Path(__file__).resolve().parent
ROOMS_FILE = BASE / 'rooms.json'
ACCOUNT_FILE = BASE / 'account.json'
CACHE_FILE = BASE / '.stream_cache.json'

LIVE_HOST = 'psp-zelda.chaoxing.com'
LOGIN_URL = 'https://passport2.chaoxing.com/fanyalogin'
AES_KEY = b'u2oh6Vu^HWe4_AES'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 Edg/126.0')

VLC_VERSION = '3.0.24'
VLC_ZIP_NAME = f'vlc-{VLC_VERSION}-win64.zip'
VLC_EXPECT_SHA = 'fcf30850371ad10c9373cc4f0f4501e7dee49e3e9ae9f20c72fb2661a1ca6323'
VLC_URLS = [
    f'https://get.videolan.org/vlc/{VLC_VERSION}/win64/{VLC_ZIP_NAME}',
    f'https://mirrors.tuna.tsinghua.edu.cn/videolan-ftp/vlc/{VLC_VERSION}/win64/{VLC_ZIP_NAME}',
]


# ---------------------------------------------------------------- 小工具
def load_json(path, default=None):
    try:
        # utf-8-sig：万一文件被记事本存成带 BOM 的 UTF-8 也能读
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except Exception:
        return default if default is not None else {}


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')


def room_key(name):
    letters = ''.join(ch for ch in name if ch.isalpha())
    digits = ''.join(ch for ch in name if ch.isdigit())
    return (letters, int(digits) if digits else 0, name)


def load_rooms():
    data = load_json(ROOMS_FILE, {})
    out = {}
    for room, links in data.items():
        if isinstance(links, str):
            out[str(room).upper()] = [normalize_link(links)]
        elif isinstance(links, list):
            out[str(room).upper()] = [normalize_link(x) for x in links if str(x).strip()]
        else:
            out[str(room).upper()] = []
    return {k: v for k, v in out.items()}


def normalize_link(url):
    """统一成 PC 版地址：/vri-zelda/mobile_live → /vri-zelda/index（手机版那一套拿掉）。"""
    text = str(url or '').strip()
    return re.sub(r'/vri-zelda/mobile_live', '/vri-zelda/index', text, flags=re.I)


def save_rooms(rooms):
    fixed = {k: [normalize_link(x) for x in v] for k, v in rooms.items()}
    save_json(ROOMS_FILE, {k: v for k, v in sorted(fixed.items(), key=lambda kv: room_key(kv[0]))})


def load_account():
    return load_json(ACCOUNT_FILE, {})


def save_account(user, password):
    save_json(ACCOUNT_FILE, {'user': user, 'password': password})


def clear_account():
    """删掉保存的账号密码（下次就走浏览器登录）。"""
    try:
        ACCOUNT_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        save_json(ACCOUNT_FILE, {'user': '', 'password': ''})


LAST_ROOM_FILE = BASE / '.last_room.json'


def load_last_room():
    return str(load_json(LAST_ROOM_FILE, {}).get('room') or '').upper()


def save_last_room(room):
    try:
        save_json(LAST_ROOM_FILE, {'room': str(room or '').upper()})
    except Exception:
        pass


def check_link(url):
    """返回 (ok, 说明)。链接必须是直播间的 speechid+enc 地址。"""
    text = (url or '').strip()
    if not text:
        return False, '链接不能为空'
    if not re.match(r'^https?://', text, re.I):
        return False, '链接要以 http:// 或 https:// 开头'
    query = parse_qs(urlparse(text).query)
    if not query.get('speechid'):
        return False, '链接里没有 speechid 参数（应形如 …?speechid=1234&enc=abcd）'
    if not query.get('enc'):
        return False, '链接里没有 enc 参数'
    return True, 'ok'


# ---------------------------------------------------------------- 登录 + 解析流地址
def _aes_encrypt(value):
    from base64 import b64encode
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_KEY)
    return b64encode(cipher.encrypt(pad(str(value).encode(), 16))).decode()


def _page_args(text):
    match = re.search(r'\bargs\s*=\s*', text)
    if not match:
        return None
    return json.JSONDecoder().raw_decode(text[match.end():].lstrip())[0]


def _looks_like_login(resp):
    return ('passport2.chaoxing.com' in resp.url
            or 'fanyalogin' in resp.text
            or 'id="refer"' in resp.text)


def _find_refer(resp):
    match = re.search(r'id="refer"[^>]*value="([^"]*)"', resp.text)
    if match:
        return match.group(1)
    values = parse_qs(urlparse(resp.url).query).get('refer') or []
    return values[0] if values else None


class NeedAccount(Exception):
    pass


# ---------------------------------------------------------------- 浏览器登录
EDGE_CANDIDATES = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]
PROFILE_DIR = Path(os.environ.get('SKL_BROWSER_PROFILE') or (BASE / 'browser-profile'))


def find_edge():
    for path in EDGE_CANDIDATES:
        if Path(path).exists():
            return path
    return shutil.which('msedge') or shutil.which('chrome')


def _our_edge_pids():
    """只找「用我们这个 profile 启动」的 Edge 进程号。"""
    marker = str(PROFILE_DIR).replace("'", "''")
    script = (
        "$p = Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" "
        "| Where-Object { $_.CommandLine -like '*" + marker + "*' }; "
        "$p | ForEach-Object { $_.ProcessId }"
    )
    try:
        done = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                              capture_output=True, text=True, timeout=25)
        return [int(x) for x in (done.stdout or '').split() if x.strip().isdigit()]
    except Exception:
        return []


def _kill_profile_browsers(log=None):
    """只杀「用我们这个 profile 启动」的 Edge，绝不碰用户自己开的浏览器。"""
    for pid in _our_edge_pids():
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                       capture_output=True, timeout=15)


def close_our_edge(graceful=True, wait=15, log=None):
    """优雅关闭我们开的 Edge：发 WM_CLOSE 让它自己退出，cookie 才会写进磁盘。

    直接 TerminateProcess / taskkill /F 会丢掉内存里的 cookie —— 那样用户明明
    登录了，下次无头读取还是登录页。
    """
    pids = set(_our_edge_pids())
    if not pids:
        return
    if graceful:
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            handles = []
            enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            def callback(hwnd, _):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in pids:
                    handles.append(hwnd)
                return True

            user32.EnumWindows(enum_proc(callback), 0)
            for hwnd in handles:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
            if log:
                log(f'  正在关闭浏览器（优雅退出，让 cookie 落盘）… 窗口 {len(handles)} 个')
            deadline = time.time() + wait
            while time.time() < deadline:
                if not _our_edge_pids():
                    break
                time.sleep(0.5)
        except Exception as exc:
            if log:
                log(f'  （优雅关闭失败：{exc}）')
    if _our_edge_pids():
        if log:
            log('  还有进程没退出，强制结束')
        _kill_profile_browsers(log)


def _window_titles():
    """列出所有顶层窗口标题（用来判断登录页有没有变成直播页）。"""
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return []
    titles = []
    user32 = ctypes.windll.user32
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value:
                titles.append(buf.value)
        return True

    user32.EnumWindows(proc_type(callback), 0)
    return titles


def _edge_dump(url, timeout=90):
    """用同一个浏览器 profile 跑无头 Edge，把页面最终 DOM 打出来（含 args）。"""
    edge = find_edge()
    if not edge:
        raise RuntimeError('这台机器上没找到 Edge 浏览器')
    cmd = [edge, '--headless=new', '--disable-gpu', '--no-first-run',
           '--no-default-browser-check', f'--user-data-dir={PROFILE_DIR}',
           '--virtual-time-budget=6000', '--dump-dom', url]
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=timeout,
                              encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        raise RuntimeError('浏览器读取页面超时')
    return done.stdout or ''


def streams_from_html(html, room):
    """从页面 DOM 里抠出直播流；没登录/没配置返回 None。

    顺带带上字幕要用的三样东西：fid / speechid / enc（主画面的 urlEnc）。
    """
    args = _page_args(html or '')
    if not args:
        return None
    speech = args.get('speech') or {}
    settings = speech.get('settings') or {}
    videos = args.get('videos') or speech.get('videos') or []
    streams = {}
    enc = ''
    for item in videos:
        kind = str(item.get('type') or '')
        link = item.get('realHttp')
        if kind in ('main', 'ppt', 'other') and link:
            streams[kind] = link
            if kind == 'main' and not enc:
                enc = str(item.get('urlEnc') or '')
    if not streams.get('main'):
        return None
    course = str(settings.get('coursename') or settings.get('courseName') or '').strip()
    return {'room': room, 'main': streams.get('main'), 'ppt': streams.get('ppt'),
            'other': streams.get('other'), 'course': course,
            'fid': args.get('fid') or settings.get('fid') or 0,
            'speechid': speech.get('speechId') or settings.get('speechId') or 0,
            'enc': enc or str(speech.get('enc') or '')}


def _html_title(html):
    match = re.search(r'<title[^>]*>(.*?)</title>', html or '', re.S | re.I)
    return (match.group(1).strip()[:40] if match else '')


def _looks_logged_out(html):
    text = html or ''
    return ('fanyalogin' in text or 'id="refer"' in text
            or '统一身份认证' in text or 'cas/login' in text)


def _free_port(start=9333, end=9400):
    import socket
    for port in range(start, end):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError('找不到空闲端口给浏览器调试用')


_FETCH_JS = """(async () => {
  try {
    const r = await fetch(location.href, {credentials: 'include', cache: 'no-store'});
    const t = await r.text();
    return {href: location.href, title: document.title, len: t.length,
            hasArgs: /\\bargs\\s*=/.test(t), html: t};
  } catch (e) { return {error: String(e), href: location.href, title: document.title}; }
})()"""


def _pick_target(port):
    """挑页面 target：优先直播页（vri-zelda），否则任何 chaoxing 页面。"""
    from cdp_min import http_json
    try:
        items = http_json(f'http://127.0.0.1:{port}/json/list', timeout=4)
    except Exception:
        return None
    pages = [x for x in items if x.get('type') == 'page']
    for page in pages:
        if 'vri-zelda' in (page.get('url') or ''):
            return page
    for page in pages:
        if 'chaoxing' in (page.get('url') or ''):
            return page
    return pages[0] if pages else None


def _shutdown_browser(ws, log=print):
    """先让浏览器自己退（Browser.close），再兜底 WM_CLOSE / 强杀。"""
    if ws:
        try:
            ws.call('Browser.close', timeout=5)
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass
    close_our_edge(graceful=True, wait=12, log=log)


def browser_login(url, room, log=print, timeout=600):
    """打开 Edge 让用户自己登录，检测到直播页后直接在浏览器里把页面 HTML 取回来。

    不再靠「关浏览器再读 cookie」：走 CDP 在已登录页面里 fetch，登录一就绪就自动继续，
    不需要用户点任何按钮。
    """
    from cdp_min import WS, find_page
    edge = find_edge()
    if not edge:
        raise RuntimeError('这台机器上没找到 Edge 浏览器，无法用网页登录')
    close_our_edge(graceful=True, wait=6, log=None)
    time.sleep(1)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    log('还没登录，正在打开浏览器…请在窗口里登录（扫码或账号密码都行）')
    log('  登录成功后程序会自动继续，不用点任何按钮。')
    proc = subprocess.Popen([edge, f'--user-data-dir={PROFILE_DIR}',
                             f'--remote-debugging-port={port}', '--no-first-run',
                             '--no-default-browser-check', url])
    data = None
    ws = None
    current = None
    last_title = ''
    try:
        find_page(port, needle='', tries=60, delay=0.5)
        deadline = time.time() + timeout
        last_note = 0.0
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError('浏览器被关掉了，登录没完成')
            target = _pick_target(port)
            if not target:
                time.sleep(1)
                continue
            if current != target.get('id'):
                if ws:
                    try:
                        ws.close()
                    except Exception:
                        pass
                ws = WS(target['webSocketDebuggerUrl'])
                current = target.get('id')
            try:
                res = ws.call('Runtime.evaluate',
                              {'expression': _FETCH_JS, 'awaitPromise': True,
                               'returnByValue': True}, timeout=30)
                value = (res.get('result') or {}).get('value') or {}
                html = value.get('html') or ''
                last_title = value.get('title') or ''
                # 唯一成功标准：能真的解析出画面地址（不是标题、不是关键字）
                data = streams_from_html(html, room) if html else None
                if data:
                    log(f"  登录完成（{last_title or '直播页'}），已取到画面地址")
                    break
                if time.time() - last_note > 15:
                    last_note = time.time()
                    if value.get('hasArgs'):
                        log(f'  已进直播页但还没解析出画面（{len(html)} 字符），继续等…')
                    else:
                        log(f"  等待登录…（当前页面：{last_title or value.get('href') or '?'}）")
            except Exception:
                try:
                    ws.close()
                except Exception:
                    pass
                ws = None
                current = None
                time.sleep(1)
            time.sleep(2)
        if not data:
            raise RuntimeError(f'等待登录超时（最后停在「{last_title or "未知页面"}」）')
    finally:
        _shutdown_browser(ws, log=log)
    return data

class LoginFailed(RuntimeError):
    """账号密码被服务器拒绝（不是网络问题，不该无脑重试）。"""


def _resolve_by_password(link, room, log=print):
    """老办法：用账号密码走 passport 登录（有 account.json 时才会用）。"""
    import requests
    acc = load_account()
    user, password = str(acc.get('user', '')).strip(), str(acc.get('password', ''))
    if not user or not password:
        raise NeedAccount()
    session = requests.Session()
    session.headers.update({'User-Agent': UA, 'Accept-Language': 'zh-CN,zh;q=0.9'})
    page = session.get(link, timeout=25, allow_redirects=True)
    if _looks_like_login(page):
        log('  需要登录，正在用账号密码登录…')
        refer = _find_refer(page)
        if not refer:
            raise RuntimeError('登录页缺少 refer 参数')
        payload = {
            'fid': '-1', 'uname': _aes_encrypt(user), 'password': _aes_encrypt(password),
            'refer': refer, 't': 'true', 'forbidotherlogin': '0', 'validate': '',
            'doubleFactorLogin': '0', 'independentId': '', 'independentNameId': '',
        }
        login = session.post(LOGIN_URL, data=payload, timeout=25,
                             headers={'Referer': page.url})
        try:
            result = login.json()
        except Exception:
            raise RuntimeError('登录接口返回异常：' + login.text[:120])
        if not result.get('status'):
            raise LoginFailed(result.get('msg2') or result.get('mes') or '账号或密码不对')
        log('  登录成功')
        page = session.get(unquote(result.get('url') or link), timeout=25,
                           allow_redirects=True)
    page.raise_for_status()
    data = streams_from_html(page.text, room)
    if not data:
        raise RuntimeError('这个链接没有直播配置（可能链接过期，或需要重新登录）')
    return data


def resolve_stream(room, log=print, ask_login=None):
    """取直播流：先看浏览器有没有登录态，没有就弹浏览器让用户登录一次。

    顺序：① 已登录的浏览器 profile（无头读取，静默）→ ② 账号密码（如果你填过）
         → ③ 打开 Edge 让用户自己登录 → 关浏览器 → 再读。

    ask_login：可选回调 ask_login(reason) -> bool，用来问用户「要不要打开浏览器登录」；
    命令行模式下传 None，就直接走浏览器登录。
    """
    rooms = load_rooms()
    links = rooms.get(room) or []
    if not links:
        raise RuntimeError(f'教室 {room} 还没有直播间链接，先在界面上添加')
    link = links[0]
    log('  正在取画面地址…（这一步通常几秒，遇到要登录时最多可能要一分钟，请稍等）')

    # ① 浏览器里已经登录过：直接取，不用任何输入
    try:
        html = _edge_dump(link)
        data = streams_from_html(html, room)
        if data:
            log('  用浏览器里已保存的登录状态取到画面地址（无需登录）')
            _cache_streams(room, data)
            return data
        if _looks_logged_out(html):
            log('  浏览器里还没有登录态')
        else:
            log('  浏览器取到了页面，但没有直播配置（可能链接过期）')
    except Exception as exc:
        log(f'  （浏览器静默读取不可用：{exc}）')

    # ② 填过账号密码就用密码登录（比弹浏览器快）
    acc = load_account()
    if acc.get('user') and acc.get('password'):
        try:
            data = _resolve_by_password(link, room, log)
            log('  用账号密码登录成功')
            _cache_streams(room, data)
            return data
        except NeedAccount:
            pass
        except LoginFailed as exc:
            log(f'  账号密码不对：{exc}')
            if ask_login and not ask_login(str(exc)):
                raise RuntimeError(f'账号密码不对（{exc}）。可以在「账号设置」里改，或改成浏览器登录。')
        except Exception as exc:
            log(f'  账号密码登录失败：{exc}')
            if ask_login and not ask_login(str(exc)):
                raise RuntimeError(f'用账号密码登录失败：{exc}')

    # ③ 没账密 / 账密不对 / 账密登录失败：问一句要不要开浏览器自己登录
    if not (acc.get('user') and acc.get('password')):
        log('  还没有保存账号密码')
        if ask_login and not ask_login('还没有保存账号密码'):
            raise RuntimeError('没有可用的登录方式：去「账号设置」填账号密码，或用「浏览器登录」。')

    log('  正在打开浏览器，登录完成后会自动关掉（最多等 10 分钟）')
    data = browser_login(link, room, log)
    _cache_streams(room, data)
    return data


def _cache_streams(room, data):
    try:
        save_json(CACHE_FILE, {'room': room, 'main': data.get('main', ''),
                               'ppt': data.get('ppt', ''),
                               'other': data.get('other', ''),
                               'fid': data.get('fid') or 0,
                               'speechid': data.get('speechid') or 0,
                               'enc': data.get('enc') or '',
                               'course': data.get('course') or '',
                               'saved_at': time.time()})
    except Exception:
        pass


# ---------------------------------------------------------------- 播放器
def find_vlc():
    exe = shutil.which('vlc')
    if exe:
        return exe
    patterns = [
        str(BASE / 'vlc' / '**' / 'vlc.exe'),
        r'C:\Users\*\Apps\VLC\**\vlc.exe',
        r'C:\Program Files\VideoLAN\VLC\vlc.exe',
        r'C:\Program Files (x86)\VideoLAN\VLC\vlc.exe',
    ]
    for pattern in patterns:
        hits = [h for h in sorted(glob.glob(pattern, recursive=True))
                if 'vlc-cache' not in h.lower()]
        if hits:
            return hits[-1]
    return None


def ensure_vlc(log=print):
    """没装 VLC 就自动下载便携版到 本目录\\vlc，校验 SHA256 后解压。"""
    target = BASE / 'vlc'
    zip_path = target / VLC_ZIP_NAME
    urls = list(VLC_URLS)
    target.mkdir(parents=True, exist_ok=True)
    for url in urls:
        try:
            log(f'没找到 VLC，正在下载（{VLC_VERSION}，约 79 MB）…')
            log(f'  来源：{url}')
            with urllib.request.urlopen(url, timeout=30) as resp, open(zip_path, 'wb') as fh:
                total = int(resp.headers.get('Content-Length') or 0)
                got = last = 0
                while True:
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if total and got - last >= 8 * 1024 * 1024:
                        last = got
                        log(f'  已下载 {got / 1048576:.0f} / {total / 1048576:.0f} MB')
            digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            if digest.lower() != VLC_EXPECT_SHA:
                log('  [!] SHA256 不匹配，换下一个源')
                zip_path.unlink(missing_ok=True)
                continue
            log('  校验通过，正在解压…')
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(target)
            zip_path.unlink(missing_ok=True)
            hits = sorted(glob.glob(str(target / '**' / 'vlc.exe'), recursive=True))
            if hits:
                log(f'  VLC 已就绪：{hits[-1]}')
                return hits[-1]
            log('  [!] 解压后没找到 vlc.exe')
        except Exception as exc:
            log(f'  [!] 下载失败：{type(exc).__name__} {exc}')
            try:
                zip_path.unlink(missing_ok=True)
            except Exception:
                pass
    log('自动下载没成功。可手动下载 VLC 便携版解压到：' + str(target))
    return None


def find_ffplay():
    exe = shutil.which('ffplay')
    if exe:
        return exe
    patterns = [
        r'C:\Users\*\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\**\ffplay.exe',
        r'C:\Program Files\**\ffplay.exe',
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern, recursive=True))
        if hits:
            return hits[-1]
    return None


VIEWS = (('main', '课堂画面'), ('ppt', '电脑桌面'), ('other', '教室全景'))


def _start_player(url, title, opts, player, kind):
    """起一个播放器进程（返回 Popen，方便后续关掉/切换）。"""
    if kind == 'vlc':
        percent = (opts.get('vol') if opts.get('vol') is not None else 100) * opts.get('gain', 1.0)
        level = int(max(0, min(512, round(percent * 2.56))))
        cmd = [player, '--no-video-title-show', '--network-caching=600',
               '--no-video-on-top', '--no-qt-privacy-ask', f'--meta-title={title}']
        cmd.append('--no-audio' if opts.get('mute') else f'--volume={level}')
        cmd.append(url)
        return subprocess.Popen(cmd, creationflags=0x00000008, close_fds=True)
    cmd = [player, '-loglevel', 'error', '-fflags', 'nobuffer', '-flags', 'low_delay',
           '-framedrop', '-probesize', '32', '-analyzeduration', '0']
    if opts.get('mute'):
        cmd.append('-an')
    else:
        if opts.get('vol') is not None:
            cmd += ['-volume', str(min(100, opts['vol']))]
        if abs(opts.get('gain', 1.0) - 1.0) > 0.01:
            cmd += ['-af', f"volume={opts['gain']:g}"]
    cmd += ['-window_title', title, url]
    return subprocess.Popen(cmd)


def _stop_player(proc):
    if not proc or proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    except Exception:
        pass


def control_window(room, data, opts, player, kind):
    """播放窗口：左边切画面，右边实时字幕 + 全部转写（界面在 ui_windows.py）。"""
    import ui_windows
    return ui_windows.control_window(room, data, opts, player, kind)

def probe_stream(url, timeout=6):
    """粗略探一下这个直播地址现在有没有数据：有画面=服务端立刻开始吐字节。"""
    if not url:
        return False
    try:
        import requests
    except Exception:
        requests = None
    if requests is not None:
        try:
            r = requests.get(url, headers={'User-Agent': UA}, stream=True, timeout=timeout)
            try:
                if r.status_code not in (200, 206):
                    return False
                return bool(next(r.iter_content(256), b''))
            finally:
                r.close()
        except Exception:
            return False
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return bool(r.read(256))
    except Exception:
        return False


def play(room, opts=None):
    opts = opts or {}
    room = str(room or '').strip().upper()
    if not room:
        print('[!] 没有选择教室')
        return 1
    print(f'教室：{room}')
    print('  加载中，请稍等…（第一次取画面要连学校服务器，一般几秒到半分钟；需要登录时会弹浏览器）')
    streams, course, data = {}, '', {}
    ask = None
    try:
        import ui_windows as _uw
        ask = _uw.ask_browser_login
    except Exception:
        ask = None
    try:
        data = resolve_stream(room, log=print, ask_login=ask)
        streams = {'main': data.get('main'), 'ppt': data.get('ppt'),
                   'other': data.get('other')}
        course = data.get('course') or ''
    except NeedAccount:
        print('[!] 需要登录：请在弹出的浏览器里登录一次，或点【浏览器登录】')
        return 2
    except LoginFailed as exc:
        print(f'[!] 账号密码不对：{exc}')
        print('    到「账号设置」里改密码，或者两个都留空（清除账号）改用浏览器登录。')
        return 1
    except Exception as exc:
        if '账号密码' in str(exc) or '登录' in str(exc):
            print(f'[!] {exc}')
            return 1
        cached = load_json(CACHE_FILE, {})
        if str(cached.get('room', '')).upper() == room and (cached.get('main') or cached.get('url')):
            data = dict(cached)
            data['main'] = cached.get('main') or cached.get('url')
            data['room'] = room
            streams = {'main': data['main'], 'ppt': data.get('ppt'),
                       'other': data.get('other')}
            course = data.get('course') or ''
            if not probe_stream(streams.get('main')):
                print(f'[!] 解析失败（{exc}）')
                print('    上次缓存到的地址也放不出来了（直播地址会过期）。')
                print('    这间教室现在可能没在直播，或者需要重新登录一次。')
                return 1
            print(f'  [!] 解析失败（{exc}），改用上次缓存到的地址')
        else:
            print(f'[!] {exc}')
            print('    可以先点【浏览器登录】自己登一次，或者到「账号设置」里填账号密码。')
            return 1
    links = load_rooms().get(room) or []
    data['link'] = links[0] if links else ''
    data['room'] = room
    data['course'] = course
    for key, label in VIEWS:
        if streams.get(key):
            print(f'  {label}：{streams[key]}')
    if opts.get('dry'):
        return 0
    if not probe_stream(streams.get('main')):
        print('[!] 这间教室现在没有画面：可能没在上课/没开直播，或者直播刚结束。')
        print('    上课时间再试；如果确定在上课，点【浏览器登录】重新登一次再试。')
        return 1
    vlc = find_vlc()
    if not vlc and not opts.get('no_install'):
        vlc = ensure_vlc(log=print)
    player, kind = (vlc, 'vlc') if vlc else (find_ffplay(), 'ffplay')
    print(f'播放器：{player or "未找到 VLC / ffplay"}')
    if not player:
        print('没找到播放器。把上面的流地址丢进 VLC / PotPlayer 也能看：')
        return 0
    return control_window(room, data, opts, player, kind)


# ---------------------------------------------------------------- 界面
def show_picker(opts):
    """选教室（界面在 ui_windows.py）。"""
    import ui_windows
    return ui_windows.show_picker(opts)

# ---------------------------------------------------------------- 入口
def main():
    argv = sys.argv[1:]
    opts = {'dry': '--dry-run' in argv, 'mute': '--mute' in argv,
            'gain': 1.0, 'vol': None, 'no_install': '--no-install' in argv, 'view': None}
    if '--gain' in argv:
        try:
            opts['gain'] = float(argv[argv.index('--gain') + 1])
        except Exception:
            pass
    if '--vol' in argv:
        try:
            opts['vol'] = max(0, min(100, int(float(argv[argv.index('--vol') + 1]))))
        except Exception:
            pass
    if '--view' in argv:
        try:
            opts['view'] = str(argv[argv.index('--view') + 1]).strip().lower()
        except Exception:
            opts['view'] = None

    if '--list' in argv:
        rooms = load_rooms()
        if not rooms:
            print('还没有教室，打开界面添加即可')
        for room in sorted(rooms, key=room_key):
            print(f'{room:<9} {len(rooms[room])} 条链接')
        return 0

    skip = set()
    for flag in ('--gain', '--vol', '--view'):
        if flag in argv:
            skip.add(argv.index(flag) + 1)
    positional = [a for i, a in enumerate(argv) if not a.startswith('--') and i not in skip]
    if positional:
        return play(positional[0], opts)
    if opts['dry']:
        rooms = sorted(load_rooms(), key=room_key)
        if not rooms:
            print('[!] 还没有教室')
            return 1
        return play(rooms[0], opts)
    room = show_picker(opts)
    if not room:
        print('已取消')
        return 0
    return play(room, opts)


if __name__ == '__main__':
    sys.exit(main())
