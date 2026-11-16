"""极简 WebSocket + CDP 客户端（只用标准库）。

用来跟 Edge 的 --remote-debugging-port 说话：
  * 在已经登录的页面里直接取 HTML，省掉「关浏览器 -> 再读 cookie」这一套
  * Runtime.evaluate 判断页面是否已经就绪
"""
import base64
import json
import os
import socket
import struct
import time
import urllib.request
from urllib.parse import urlparse


class WS:
    def __init__(self, ws_url, timeout=10):
        parts = urlparse(ws_url)
        host, port = parts.hostname, parts.port or 80
        path = parts.path + (('?' + parts.query) if parts.query else '')
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f'GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n'
               'Upgrade: websocket\r\nConnection: Upgrade\r\n'
               f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n')
        self.sock.sendall(req.encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError('WebSocket 握手失败（连接被关闭）')
            head += chunk
        status_line, rest = head.split(b'\r\n', 1)[0], head.split(b'\r\n\r\n', 1)[1]
        if b'101' not in status_line:
            raise RuntimeError('WebSocket 握手失败：' + status_line.decode('latin1', 'replace'))
        self.buf = rest
        self.next_id = 0

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError('WebSocket 连接已断开')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _send_frame(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack('!H', length)
        else:
            header.append(0x80 | 127)
            header += struct.pack('!Q', length)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def send(self, text):
        self._send_frame(0x1, text.encode('utf-8'))

    def recv(self, timeout=60):
        self.sock.settimeout(timeout)
        while True:
            b0, b1 = self._read(2)
            opcode = b0 & 0x0F
            masked = b1 & 0x80
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack('!H', self._read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self._read(8))[0]
            mask = self._read(4) if masked else None
            data = self._read(length)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 0x1:
                return data.decode('utf-8', 'replace')
            if opcode == 0x8:
                raise RuntimeError('WebSocket 被对端关闭')
            if opcode == 0x9:
                self._send_frame(0xA, data)
                continue

    def close(self):
        try:
            self._send_frame(0x8, b'')
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

    def call(self, method, params=None, timeout=25):
        self.next_id += 1
        mid = self.next_id
        self.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.recv(timeout=max(1, deadline - time.time())))
            if msg.get('id') == mid:
                if 'error' in msg:
                    raise RuntimeError(f"{method} 失败：{msg['error']}")
                return msg.get('result') or {}
        raise RuntimeError(f'{method} 超时')


def http_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def find_page(port, needle='', tries=40, delay=0.5):
    """等 devtools 端口起来，返回匹配的页面 target。"""
    for _ in range(tries):
        try:
            items = http_json(f'http://127.0.0.1:{port}/json/list')
            for item in items:
                if item.get('type') == 'page' and (not needle or needle in (item.get('url') or '')):
                    return item
        except Exception:
            pass
        time.sleep(delay)
    return None
