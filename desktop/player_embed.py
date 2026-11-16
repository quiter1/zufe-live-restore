# -*- coding: utf-8 -*-
"""把 libVLC 直接嵌进我们自己的窗口（不再起 VLC 进程、没有 VLC 窗口）。

原理：python-vlc 的 media_player.set_hwnd() 把视频渲染目标指向任意窗口句柄，
      我们把 Tk 里的一块 Frame 的 HWND 交给它，画面就长在界面里了。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_vlc = None
_inst = None


def _candidate_dirs(player_path=None):
    """找放着 libvlc.dll 的目录。"""
    out = []
    if player_path:
        d = os.path.dirname(os.path.abspath(player_path))
        if os.path.isfile(os.path.join(d, 'libvlc.dll')):
            out.append(d)
    # 本目录 vlc\（程序自动下载的那份）
    for sub in ('vlc', os.path.join('vlc', 'vlc-3.0.24')):
        d = os.path.join(HERE, sub)
        if os.path.isfile(os.path.join(d, 'libvlc.dll')):
            out.append(d)
    # 注册表
    try:
        import winreg
        for root, key in ((winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\VideoLAN\VLC'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\VideoLAN\VLC'),
                          (winreg.HKEY_CURRENT_USER, r'SOFTWARE\VideoLAN\VLC')):
            try:
                with winreg.OpenKey(root, key) as k:
                    d = winreg.QueryValueEx(k, 'InstallDir')[0]
                if os.path.isfile(os.path.join(d, 'libvlc.dll')):
                    out.append(d)
            except OSError:
                continue
    except Exception:
        pass
    # 常见安装位置
    for d in (r'C:\Program Files\VideoLAN\VLC',
              r'C:\Program Files (x86)\VideoLAN\VLC',
              os.path.expandvars(r'%LOCALAPPDATA%\Programs\VideoLAN\VLC')):
        if os.path.isfile(os.path.join(d, 'libvlc.dll')):
            out.append(d)
    # 用户自己解压的 VLC（\Apps\VLC\vlc-x.y.z）
    try:
        base = os.path.expandvars(r'%USERPROFILE%\Apps\VLC')
        if os.path.isdir(base):
            for name in sorted(os.listdir(base), reverse=True):
                d = os.path.join(base, name)
                if os.path.isfile(os.path.join(d, 'libvlc.dll')):
                    out.append(d)
    except Exception:
        pass
    return out


def find_libvlc(player_path=None):
    dirs = _candidate_dirs(player_path)
    return dirs[0] if dirs else ''


def available(player_path=None):
    return bool(find_libvlc(player_path))


def _load(vlc_dir):
    """把 vlc 模块加载起来（第一次调用时设置 DLL 路径）。"""
    global _vlc, _inst
    if _vlc is not None:
        return _vlc
    os.environ['PYTHON_VLC_LIB_PATH'] = os.path.join(vlc_dir, 'libvlc.dll')
    os.environ['PYTHON_VLC_MODULE_PATH'] = os.path.join(vlc_dir, 'plugins')
    try:
        os.add_dll_directory(vlc_dir)
    except Exception:
        pass
    here = HERE
    if here not in sys.path:
        sys.path.insert(0, here)
    import vlc  # 同目录的 vlc.py（python-vlc，已修 py3.11+ 兼容）
    _vlc = vlc
    return vlc


class EmbeddedPlayer:
    """一个 libVLC 实例 + 一个播放器，画面绑在 Tk 控件上。"""

    def __init__(self, widget, player_path=None, volume=100, mute=False):
        self.ok = False
        self.err = ''
        self._player = None
        self._widget = widget
        self._volume = 0 if mute else max(0, min(100, int(volume)))
        vlc_dir = find_libvlc(player_path)
        if not vlc_dir:
            self.err = '没找到 libvlc.dll'
            return
        try:
            vlc = _load(vlc_dir)
            inst = vlc.Instance(['--no-video-title-show', '--quiet', '--no-osd'])
            if inst is None:
                self.err = 'libVLC 初始化失败'
                return
            self._inst = inst
            self._player = inst.media_player_new()
            self._player.audio_set_volume(self._volume)
            widget.update_idletasks()
            self._player.set_hwnd(widget.winfo_id())
            self.ok = True
        except Exception as exc:  # noqa: BLE001
            self.err = f'{type(exc).__name__}: {exc}'

    # --- 控制
    def play(self, url):
        if not self.ok:
            return False
        try:
            media = self._inst.media_new(url)
            for opt in ('network-caching=800', 'http-reconnect', 'live-caching=800'):
                try:
                    media.add_option(opt)
                except Exception:
                    pass
            self._player.set_media(media)
            self._player.play()
            return True
        except Exception as exc:  # noqa: BLE001
            self.err = f'{type(exc).__name__}: {exc}'
            return False

    def stop(self):
        if self.ok:
            try:
                self._player.stop()
            except Exception:
                pass

    def set_volume(self, value):
        self._volume = max(0, min(100, int(value)))
        if self.ok:
            try:
                self._player.audio_set_volume(self._volume)
            except Exception:
                pass

    def mute(self, flag=True):
        self.set_volume(0 if flag else self._volume or 100)

    def state(self):
        if not self.ok:
            return 'dead'
        try:
            return str(self._player.get_state()).split('.')[-1]
        except Exception:
            return 'unknown'

    def video_size(self):
        """返回当前视频的原始宽高 (w, h)，还没出画面时返回 (0, 0)。"""
        try:
            w, h = self.player.video_get_size(0)
            return int(w or 0), int(h or 0)
        except Exception:
            return 0, 0

    def playing(self):
        return self.state() == 'Playing'

    def failed(self):
        return self.state() in ('Error', 'Stopped')

    def close(self):
        if self.ok:
            try:
                self._player.stop()
                self._player.release()
            except Exception:
                pass
        self.ok = False
