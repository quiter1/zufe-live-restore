// ==UserScript==
// @name         智播课堂 · 强制显示直播真实画面
// @namespace    zufe.live.restore
// @version      0.2.0
// @description  不管页面写「直播已结束」，从页面配置里取两路直播流（课堂摄像头 + 电脑桌面），填回原来的两个画面窗口，并跟随窗口缩放
// @author       local
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

    // ---------------------------------------------------------------- 状态小徽标
    const badge = document.createElement('div');
    badge.style.cssText = [
        'position:fixed', 'right:12px', 'bottom:12px', 'z-index:2147483647',
        'background:#111c', 'color:#fff', 'font:12px/1.6 monospace', 'padding:6px 10px',
        'border-radius:6px', 'pointer-events:none', 'max-width:46vw', 'white-space:pre-wrap',
    ].join(';');
    const say = (t) => { badge.textContent = TAG + ' ' + t; if (DEBUG) console.log(TAG, t); };
    document.documentElement.appendChild(badge);

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
            if (s.main || s.ppt) return s;
        }
        const res = await fetch(location.href, { credentials: 'include', cache: 'no-store' });
        const args = parseArgsFromHtml(await res.text());
        if (!args) throw new Error('页面源码里没有 args');
        const s = streamsFromArgs(args);
        if (!s.main && !s.ppt) throw new Error('args 里没有视频源');
        return s;
    }

    // ---------------------------------------------------------------- 找两个窗口
    /** 按「面积」找两个候选：给调试和兜底用 */
    function candidates() {
        const list = [];
        document.querySelectorAll('div,section,video,canvas').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width < 200 || r.height < 120) return;
            if (r.width > innerWidth * 0.98 && r.height > innerHeight * 0.95) return;
            const cls = String(el.className || '');
            list.push({ el, w: Math.round(r.width), h: Math.round(r.height), cls: cls.slice(0, 70) });
        });
        list.sort((a, b) => b.w * b.h - a.w * a.h);
        return list;
    }

    /** 两个画面窗口：优先 class 命中，其次「最大两块互不包含的区域」 */
    function findPanes() {
        const byClass = [...document.querySelectorAll('div,section')].filter(el => {
            const r = el.getBoundingClientRect();
            if (r.width < 200 || r.height < 120) return false;
            return /player|video|live|stream|screen|ppt|preview|window|main/i.test(String(el.className || ''));
        }).sort((a, b) => {
            const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
            return rb.width * rb.height - ra.width * ra.height;
        });
        const picked = [];
        for (const el of byClass) {
            if (picked.some(p => p.contains(el) || el.contains(p))) continue;
            picked.push(el);
            if (picked.length === 2) break;
        }
        if (picked.length === 2) return picked;

        const videos = [...document.querySelectorAll('video')];
        if (videos.length >= 2) return videos.slice(0, 2).map(v => v.parentElement);

        // 最后兜底：面积最大的两块互不包含区域
        const cand = candidates();
        const out = [];
        for (const c of cand) {
            if (out.some(p => p.contains(c.el) || c.el.contains(p))) continue;
            out.push(c.el);
            if (out.length === 2) break;
        }
        return out;
    }

    function outline(elems, note) {
        elems.forEach((el, i) => {
            if (el.dataset.zufeOutline) return;
            el.dataset.zufeOutline = '1';
            el.style.outline = '3px solid ' + (i === 0 ? '#ff3b30' : '#0a84ff');
            const tag = document.createElement('div');
            const r = el.getBoundingClientRect();
            tag.textContent = `${i === 0 ? 'main' : 'ppt'} ${Math.round(r.width)}x${Math.round(r.height)} ${String(el.className || '').slice(0, 24)}`;
            tag.style.cssText = 'position:absolute;left:0;top:0;z-index:2147483647;background:#000c;color:#fff;font:11px monospace;padding:2px 4px;pointer-events:none';
            el.appendChild(tag);
        });
        if (note) say(note);
    }

    // ---------------------------------------------------------------- 播放器（跟随缩放）
    const players = new Map();   // pane -> {video, player, ro}

    function mount(container, url, label) {
        const old = players.get(container);
        if (old && old.url === url) return;
        if (old) { try { old.player && old.player.destroy(); } catch (e) {} old.video.remove(); players.delete(container); }

        container.style.position = container.style.position || 'relative';
        const video = document.createElement('video');
        video.dataset.zufeOwn = '1';
        video.muted = true;
        video.controls = true;
        video.autoplay = true;
        video.playsInline = true;
        video.title = label + '（点一下画面切换声音）';
        // 用绝对定位 + inset:0：容器怎么缩放，它就怎么跟着变
        video.style.cssText = 'position:absolute;left:0;top:0;right:0;bottom:0;width:100%;height:100%;z-index:2147483000;background:#000;object-fit:contain';
        video.addEventListener('click', () => { video.muted = !video.muted; });
        container.appendChild(video);

        // 把「直播已结束」那层压掉
        for (const child of container.children) {
            if (child !== video) child.style.visibility = 'hidden';
        }

        // 容器尺寸变化（窗口缩放 / 分栏拖动 / 播放器自适应）时重新贴合
        const sync = () => {
            const r = container.getBoundingClientRect();
            if (!r.width || !r.height) return;
            video.style.width = r.width + 'px';
            video.style.height = r.height + 'px';
        };
        const ro = new ResizeObserver(sync);
        ro.observe(container);
        window.addEventListener('resize', sync);
        sync();

        if (typeof mpegts === 'undefined') {
            say('mpegts.js 未加载，无法播 FLV（检查 @require）');
            return;
        }
        const player = mpegts.createPlayer(
            { type: 'flv', isLive: true, url },
            { enableStashBuffer: false, liveBufferLatencyChasing: true, autoCleanupSourceBuffer: true }
        );
        player.attachMediaElement(video);
        player.on(mpegts.Events.ERROR, (t, d) => { say(`${label} 播放出错：${t}/${d}`); warn(label, t, d); });
        player.load();
        const p = player.play();
        if (p && p.catch) p.catch(() => say(`${label} 自动播放被拦，点一下画面`));
        players.set(container, { video, player, ro, url });
        say(`${label} 已接管`);
    }

    // ---------------------------------------------------------------- 主流程
    async function run(attempt = 0) {
        // 调试模式：先把候选框描出来（不依赖登录/args）
        if (DEBUG) {
            const panes = findPanes();
            if (panes.length) outline(panes, '已描出候选窗口（红=main 蓝=ppt）');
            else say('调试：没找到候选窗口');
        }

        let streams;
        try {
            streams = await getStreams();
        } catch (e) {
            say(`取流失败：${e.message}（第 ${attempt + 1} 次）`);
            if (attempt < 20) setTimeout(() => run(attempt + 1), 2000);
            return;
        }

        const panes = findPanes();
        if (panes.length === 0) {
            if (attempt < 20) return setTimeout(() => run(attempt + 1), 1500);
            say('没找到画面窗口，加 ?zufe_debug=1 看候选');
            return;
        }
        const keys = ['main', 'ppt'];
        panes.slice(0, 2).forEach((pane, i) => {
            const key = keys[i] || 'main';
            const url = streams[key] || streams.main || streams.ppt;
            if (url) mount(pane, url, key === 'main' ? '课堂画面' : '电脑桌面');
        });
        say('两路都已接管；窗口缩放会跟随');
    }

    setTimeout(() => run(), 1200);
    let lastUrl = location.href;
    setInterval(() => {
        if (location.href !== lastUrl) { lastUrl = location.href; players.clear(); setTimeout(() => run(), 1200); }
    }, 1500);
})();
