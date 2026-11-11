// ==UserScript==
// @name         智播课堂 · 强制显示直播真实画面
// @namespace    zufe.live.restore
// @version      0.4.0
// @description  页面写「直播已结束」也能放真实直播流；画面里带一条悬浮控制条，按钮在「现场画面 / 电脑桌面」之间切换，也可以把另一路单独开成浮窗
// @author       quiter1
// @match        https://psp-zelda.chaoxing.com/vri-zelda/*
// @require      https://cdn.jsdelivr.net/npm/mpegts.js@1.7.3/dist/mpegts.js
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const TAG = '[直播恢复]';
    const DEBUG = /[?&]zufe_debug=1/.test(location.href) || localStorage.getItem('zufe_debug') === '1';
    const log = (...a) => console.log(TAG, ...a);
    const warn = (...a) => console.warn(TAG, ...a);

    const Z = window.__zufe = { streams: {}, view: null, main: null, pip: null, last: '' };
    const VIEW_NAME = { main: '现场画面', ppt: '电脑桌面' };

    function say(text) {
        Z.last = text;
        if (DEBUG) console.log(TAG, text);
        const el = document.getElementById('zufe-status');
        if (el) el.textContent = text;
    }

    // ---------------------------------------------------------------- 解析 args
    function streamsFromArgs(args) {
        const sp = (args && args.speech) || {};
        const vids = (args && args.videos) || sp.videos || [];
        const out = {};
        for (const v of vids) {
            const t = String(v.type || '');
            if ((t === 'main' || t === 'ppt') && v.realHttp) out[t] = v.realHttp;
        }
        return out;
    }

    function parseArgsFromHtml(html) {
        const m = /\bargs\s*=\s*/.exec(html || '');
        if (!m) return null;
        const text = html.slice(m.index + m[0].length).trimStart();
        let depth = 0, quote = null, end = -1;
        for (let i = 0; i < text.length; i++) {
            const ch = text[i];
            if (quote) {
                if (ch === '\\') { i++; continue; }
                if (ch === quote) quote = null;
                continue;
            }
            if (ch === '"' || ch === "'") { quote = ch; continue; }
            if (ch === '{') depth++;
            else if (ch === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
        }
        if (end < 0) return null;
        try { return Function('return (' + text.slice(0, end) + ')')(); }
        catch (e) { warn('args 解析失败', e); return null; }
    }

    async function getStreams() {
        if (window.args && typeof window.args === 'object') {
            const s = streamsFromArgs(window.args);
            if (s.main || s.ppt) { Z.streams = s; return s; }
        }
        const res = await fetch(location.href, { credentials: 'include', cache: 'no-store' });
        const args = parseArgsFromHtml(await res.text());
        if (!args) throw new Error('页面源码里没有 args');
        const s = streamsFromArgs(args);
        if (!s.main && !s.ppt) throw new Error('args 里没有视频源');
        Z.streams = s;
        return s;
    }

    // ---------------------------------------------------------------- 找主画面容器
    function visible(el) {
        if (!el || !el.isConnected) return false;
        const r = el.getBoundingClientRect();
        if (r.width < 120 || r.height < 80) return false;
        const cs = getComputedStyle(el);
        return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity || 1) > 0.05;
    }

    function findMainPane() {
        const cands = [];
        // 页面自带 video/canvas 的父节点最可靠
        document.querySelectorAll('video,canvas').forEach(m => {
            const p = m.closest('div') || m.parentElement;
            if (p && p !== document.body) cands.push(p);
        });
        document.querySelectorAll('div,section').forEach(el => {
            if (!/player|video|live|stream|screen|ppt|preview/i.test(String(el.className || ''))) return;
            const r = el.getBoundingClientRect();
            if (r.width >= 320 && r.height >= 180) cands.push(el);
        });
        const uniq = [];
        for (const el of cands) {
            if (uniq.some(x => x === el || x.contains(el) || el.contains(x))) continue;
            if (!visible(el)) continue;
            uniq.push(el);
        }
        uniq.sort((a, b) => {
            const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
            return rb.width * rb.height - ra.width * ra.height;
        });
        return uniq[0] || null;
    }

    // ---------------------------------------------------------------- 播放器
    function destroyCard(card) {
        if (!card) return;
        try { card.player && card.player.pause(); } catch (e) {}
        try { card.player && card.player.unload(); } catch (e) {}
        try { card.player && card.player.detachMediaElement(); } catch (e) {}
        try { card.player && card.player.destroy(); } catch (e) {}
        try { card.ro && card.ro.disconnect(); } catch (e) {}
        try { card.video && card.video.remove(); } catch (e) {}
        try { card.box && card.box.remove(); } catch (e) {}
    }

    function createPlayer(video, url, label) {
        if (typeof mpegts === 'undefined') {
            say('mpegts.js 没加载（检查 @require / 网络）');
            return null;
        }
        const player = mpegts.createPlayer(
            { type: 'flv', isLive: true, url },
            { enableStashBuffer: false, liveBufferLatencyChasing: true, autoCleanupSourceBuffer: true }
        );
        player.attachMediaElement(video);
        player.on(mpegts.Events.ERROR, (t, d) => { say(`${label} 播放出错：${t}/${d}`); warn(label, t, d); });
        player.load();
        video.addEventListener('playing', () => {
            say(`${label} 播放中 ${video.videoWidth}x${video.videoHeight}`);
        }, { once: true });
        const p = player.play();
        if (p && p.catch) p.catch(() => say(`${label} 自动播放被拦，点一下画面`));
        return player;
    }

    /** 主画面：把 video 贴进页面那块大容器 */
    function showInPane(pane, url, label) {
        destroyCard(Z.main);
        pane.style.position = pane.style.position || 'relative';
        const video = document.createElement('video');
        video.muted = true;
        video.controls = true;
        video.autoplay = true;
        video.playsInline = true;
        video.title = label + '（点一下切换声音）';
        video.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;z-index:2147483000;background:#000;object-fit:contain';
        video.addEventListener('click', () => { video.muted = !video.muted; });
        pane.appendChild(video);
        for (const child of pane.children) if (child !== video) child.style.visibility = 'hidden';

        const sync = () => {
            const r = pane.getBoundingClientRect();
            if (!r.width || !r.height) return;
            video.style.width = r.width + 'px';
            video.style.height = r.height + 'px';
        };
        const ro = new ResizeObserver(sync);
        ro.observe(pane);
        window.addEventListener('resize', sync);
        sync();

        const player = createPlayer(video, url, label);
        Z.main = { video, player, ro, url, pane, kind: 'main' };
        Z.view = url === Z.streams.main ? 'main' : 'ppt';
        updateBar();
    }

    /** 浮窗：另一路单独开在小窗里（可拖动 / 可缩放） */
    function togglePip() {
        if (Z.pip) { destroyCard(Z.pip); Z.pip = null; updateBar(); return; }
        const other = Z.view === 'main' ? 'ppt' : 'main';
        const url = Z.streams[other];
        if (!url) return;
        const box = document.createElement('div');
        box.id = 'zufe-pip';
        box.style.cssText = [
            'position:fixed', 'left:16px', 'bottom:64px', 'width:380px', 'height:230px',
            'min-width:200px', 'min-height:120px', 'resize:both', 'overflow:hidden',
            'background:#000', 'border:1px solid #555', 'border-radius:8px',
            'box-shadow:0 8px 28px #000a', 'z-index:2147483002',
        ].join(';');
        const bar = document.createElement('div');
        bar.textContent = VIEW_NAME[other] + '　(拖动 / 右下角缩放)';
        bar.style.cssText = [
            'position:absolute', 'left:0', 'top:0', 'right:0', 'height:22px', 'line-height:22px',
            'background:#000a', 'color:#fff', 'font:12px "Microsoft YaHei"', 'padding:0 8px',
            'cursor:move', 'z-index:2', 'user-select:none',
        ].join(';');
        const video = document.createElement('video');
        video.muted = true; video.controls = true; video.autoplay = true; video.playsInline = true;
        video.style.cssText = 'position:absolute;left:0;top:22px;width:100%;height:calc(100% - 22px);object-fit:contain;background:#000';
        box.appendChild(bar); box.appendChild(video); document.body.appendChild(box);

        let drag = null;
        bar.addEventListener('pointerdown', (e) => {
            drag = { dx: e.clientX - box.offsetLeft, dy: e.clientY - box.offsetTop };
            bar.setPointerCapture(e.pointerId);
        });
        bar.addEventListener('pointermove', (e) => {
            if (!drag) return;
            box.style.left = Math.max(0, e.clientX - drag.dx) + 'px';
            box.style.top = Math.max(0, e.clientY - drag.dy) + 'px';
            box.style.bottom = 'auto';
        });
        bar.addEventListener('pointerup', () => { drag = null; });

        Z.pip = { box, video, player: createPlayer(video, url, VIEW_NAME[other]), kind: other };
        updateBar();
    }

    // ---------------------------------------------------------------- 控制条
    function buildBar() {
        if (document.getElementById('zufe-bar')) return;
        const bar = document.createElement('div');
        bar.id = 'zufe-bar';
        bar.style.cssText = [
            'position:fixed', 'left:50%', 'transform:translateX(-50%)', 'bottom:14px',
            'z-index:2147483646', 'display:flex', 'gap:8px', 'align-items:center',
            'background:#0b1220e6', 'color:#fff', 'padding:8px 12px', 'border-radius:10px',
            'font:13px "Microsoft YaHei",sans-serif', 'box-shadow:0 8px 24px #0007',
            'border:1px solid #ffffff22',
        ].join(';');

        const mkBtn = (text, id) => {
            const b = document.createElement('button');
            b.id = id;
            b.textContent = text;
            b.style.cssText = [
                'cursor:pointer', 'border:0', 'border-radius:7px', 'padding:6px 12px',
                'font:13px "Microsoft YaHei",sans-serif', 'background:#ffffff1a', 'color:#fff',
            ].join(';');
            return b;
        };

        const bMain = mkBtn('现场画面', 'zufe-btn-main');
        const bPpt = mkBtn('电脑桌面', 'zufe-btn-ppt');
        const bPip = mkBtn('浮窗', 'zufe-btn-pip');
        const bClose = mkBtn('✕', 'zufe-btn-close');
        const status = document.createElement('span');
        status.id = 'zufe-status';
        status.textContent = '准备中…';
        status.style.cssText = 'opacity:.75;margin-left:6px;max-width:34vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';

        bMain.onclick = () => switchTo('main');
        bPpt.onclick = () => switchTo('ppt');
        bPip.onclick = togglePip;
        bClose.onclick = () => {
            destroyCard(Z.main); destroyCard(Z.pip); Z.main = Z.pip = null;
            bar.remove();
        };

        bar.append(bMain, bPpt, bPip, bClose, status);
        document.body.appendChild(bar);
    }

    function updateBar() {
        const set = (id, active) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.style.background = active ? '#2f6fed' : '#ffffff1a';
            el.style.fontWeight = active ? '700' : '400';
        };
        set('zufe-btn-main', Z.view === 'main');
        set('zufe-btn-ppt', Z.view === 'ppt');
        const pip = document.getElementById('zufe-btn-pip');
        if (pip) pip.style.background = Z.pip ? '#2f6fed' : '#ffffff1a';
    }

    function switchTo(view) {
        const url = Z.streams[view];
        const pane = Z.main ? Z.main.pane : findMainPane();
        if (!url || !pane) { say('这一路没有画面'); return; }
        showInPane(pane, url, VIEW_NAME[view]);
        say('已切换到：' + VIEW_NAME[view]);
    }

    // ---------------------------------------------------------------- 主流程
    let started = false;

    async function run(attempt = 0) {
        buildBar();
        let streams;
        try {
            streams = await getStreams();
        } catch (e) {
            say(`取流失败：${e.message}`);
            if (attempt < 20) setTimeout(() => run(attempt + 1), 2000);
            return;
        }
        const pane = findMainPane();
        if (!pane) {
            say('还没找到画面容器，稍等…');
            if (attempt < 20) return setTimeout(() => run(attempt + 1), 1500);
            say('没找到画面容器，可加 ?zufe_debug=1 看看');
            return;
        }
        started = true;
        showInPane(pane, streams.main || streams.ppt, '现场画面');
        say('就绪：可点上面按钮切换画面');
    }

    setTimeout(run, 1200);
    let lastUrl = location.href;
    setInterval(() => {
        if (location.href !== lastUrl) {
            lastUrl = location.href;
            destroyCard(Z.main); destroyCard(Z.pip);
            Z.main = Z.pip = null; started = false;
            setTimeout(run, 1200);
        }
    }, 1500);
})();
