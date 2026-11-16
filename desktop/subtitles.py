"""实时字幕：轮询智播课堂的 /vri-zelda/api/live-ts 接口。

网页端就是这么拿字幕的：播放器 loadedmetadata 之后，每 1 秒 GET 一次，
带上 live_url（当前这路流的地址）、enc（这路流的 urlEnc）、fid、speechid，
以及上一轮返回的 offset_id / start_time。返回里有：

    {"start_time": 毫秒时间戳, "offset_id": 123, "transcripts": [
        {"id": 123, "start": 1.55, "end": 2.71, "text": "对。"}],
     "last_mid_text": {"text": "嗯"}}

- transcripts：已经识别完的句子（start/end 是相对 start_time 的秒数）
- last_mid_text：正在说的这半句，网页就把它显示在视频底部

不需要登录态，只要带浏览器 UA 和 Referer 就行（实测）。
"""

import threading
import time

import requests

API = 'https://psp-zelda.chaoxing.com/vri-zelda/api/live-ts'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 Edg/126.0')


def _fmt_clock(ms):
    try:
        return time.strftime('%H:%M:%S', time.localtime(ms / 1000.0))
    except Exception:
        return '--:--:--'


class LiveTranscripts:
    """后台线程轮询字幕；主线程定期取 snapshot() 就行。"""

    def __init__(self, live_url, enc, fid, speechid, referer='', interval=1.5, on_update=None):
        self.live_url = (live_url or '').strip()
        self.enc = (enc or '').strip()
        self.fid = int(fid or 0)
        self.speechid = int(speechid or 0)
        self.referer = referer or 'https://psp-zelda.chaoxing.com/'
        self.interval = max(0.8, float(interval))
        self.on_update = on_update
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.segments = []          # [{'id','start','end','text','clock'}]
        self.seen = set()
        self.mid_text = ''
        self.status = 'idle'        # idle / waiting / live / error
        self.error = ''
        self.base_ms = 0
        self.offset = 0
        self.cursor_start = 0
        self.fails = 0

    # ------------------------------------------------------------ 生命周期
    def start(self):
        if not self.live_url or not self.enc:
            self.status = 'error'
            self.error = '缺少字幕参数（这间教室没取到 enc）'
            return False
        self.status = 'waiting'
        self._thread = threading.Thread(target=self._loop, name='live-ts', daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()

    def alive(self):
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    # ------------------------------------------------------------ 对外快照
    def snapshot(self):
        with self._lock:
            return {
                'segments': list(self.segments),
                'mid_text': self.mid_text,
                'status': self.status,
                'error': self.error,
                'count': len(self.segments),
            }

    # ------------------------------------------------------------ 内部
    def _loop(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': UA,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.referer,
            'X-Requested-With': 'XMLHttpRequest',
        })
        while not self._stop.is_set():
            try:
                data = self._poll(session)
                if data is not None:
                    self._absorb(data)
            except Exception as exc:
                self.fails += 1
                with self._lock:
                    self.status = 'error'
                    self.error = f'{type(exc).__name__}: {exc}'[:120]
                self._stop.wait(min(6.0, 1.5 * self.fails))
                continue
            self._stop.wait(self.interval)
        with self._lock:
            if self.status != 'error':
                self.status = 'stopped'

    def _poll(self, session):
        params = {
            'live_url': self.live_url,
            'enc': self.enc,
            'offset_id': self.offset,
            'start_time': self.cursor_start,
            'fid': self.fid,
            'speechid': self.speechid,
        }
        resp = session.get(API, params=params, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f'HTTP {resp.status_code}')
        ctype = resp.headers.get('content-type') or ''
        if 'json' not in ctype.lower():
            raise RuntimeError('接口没返回 JSON（多半是页面地址过期了）')
        return resp.json()

    def _absorb(self, data):
        if not isinstance(data, dict):
            return
        segs = data.get('transcripts') or []
        mid = ((data.get('last_mid_text') or {}).get('text') or '').strip()
        offset = data.get('offset_id')
        start_ms = data.get('start_time')
        new_rows = []
        with self._lock:
            self.fails = 0
            if start_ms:
                self.base_ms = int(start_ms)
            if offset is not None:
                self.offset = int(offset)
            if start_ms:
                self.cursor_start = int(start_ms)
            for item in segs:
                try:
                    sid = int(item.get('id'))
                except Exception:
                    continue
                text = str(item.get('text') or '').strip()
                if sid in self.seen:
                    continue
                self.seen.add(sid)
                if not text:
                    continue
                begin = float(item.get('start') or 0)
                row = {
                    'id': sid,
                    'start': begin,
                    'end': float(item.get('end') or begin),
                    'text': text,
                    'clock': _fmt_clock((self.base_ms or 0) + begin * 1000.0),
                }
                self.segments.append(row)
                new_rows.append(row)
            if mid:
                self.mid_text = mid
            elif new_rows:
                self.mid_text = ''
            self.status = 'live' if (self.segments or self.mid_text) else self.status
        if new_rows or mid:
            cb = self.on_update
            if cb:
                try:
                    cb()
                except Exception:
                    pass
        if self.status == 'waiting' and (new_rows or mid):
            with self._lock:
                self.status = 'live'


def probe(live_url, enc, fid, speechid, referer='', seconds=12):
    """命令行自测：打印这几秒里拿到的字幕。"""
    def _dump():
        snap = client.snapshot()
        print(f"[{snap['status']}] 段数={snap['count']} 当前={snap['mid_text']!r} {snap['error']}")
        for row in snap['segments'][-5:]:
            print(f"  {row['clock']}  {row['text']}")
    client = LiveTranscripts(live_url, enc, fid, speechid, referer=referer, on_update=_dump)
    client.start()
    time.sleep(seconds)
    client.stop()


if __name__ == '__main__':
    import json
    import re
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    base = Path(__file__).resolve().parent
    rooms = json.loads((base / 'rooms.json').read_text(encoding='utf-8-sig'))
    room = sys.argv[1] if len(sys.argv) > 1 else sorted(rooms)[0]
    link = (rooms.get(room) or [''])[0]
    html = requests.get(link, headers={'User-Agent': UA}, timeout=25).text
    match = re.search(r'\bargs\s*=\s*(\{.*)', html, re.S)
    if not match:
        print('页面里没有 args（没登录？）')
        raise SystemExit(1)
    args, _ = json.JSONDecoder().raw_decode(match.group(1))
    speech = args.get('speech') or {}
    videos = speech.get('videos') or args.get('videos') or []
    main = next((v for v in videos if v.get('type') == 'main'), {})
    probe(main.get('realHttp') or '', main.get('urlEnc') or '', args.get('fid') or 0,
          speech.get('speechId') or 0, referer=link, seconds=20)
