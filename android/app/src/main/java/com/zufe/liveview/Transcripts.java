package com.zufe.liveview;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * 超星直播 AI 转写客户端：轮询 /vri-zelda/api/live-ts。
 * 只要 UA + Referer，不需要登录 cookie。
 */
public class Transcripts {

    public static class Seg {
        public int id;
        public double start;
        public double end;
        public String text = "";
        public String clock = "";
    }

    public interface Listener {
        void onUpdate(Transcripts t);
    }

    private final String liveUrl;
    private final String enc;
    private final String fid;
    private final String speechid;
    private final String referer;

    private final List<Seg> segs = new ArrayList<>();
    private final Set<Integer> seen = new HashSet<>();
    private long baseMs;
    private long offsetId;
    private long startTime;
    private String mid = "";
    private String status = "idle";
    private String error = "";
    private boolean running;
    private Thread thread;
    private Listener listener;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final SimpleDateFormat clockFmt = new SimpleDateFormat("HH:mm:ss", Locale.CHINA);

    public Transcripts(String liveUrl, String enc, String fid, String speechid, String referer) {
        this.liveUrl = nz(liveUrl);
        this.enc = nz(enc);
        this.fid = nz(fid);
        this.speechid = nz(speechid);
        this.referer = nz(referer);
    }

    private static String nz(String s) {
        return s == null ? "" : s;
    }

    public boolean usable() {
        return !liveUrl.isEmpty() && !enc.isEmpty() && !speechid.isEmpty();
    }

    public void setListener(Listener l) {
        listener = l;
    }

    public String status() {
        return status;
    }

    public String error() {
        return error;
    }

    public String mid() {
        return mid;
    }

    public synchronized List<Seg> segments() {
        return new ArrayList<>(segs);
    }

    public synchronized int count() {
        return segs.size();
    }

    public void start() {
        if (running || !usable()) {
            if (!usable()) {
                status = "off";
            }
            return;
        }
        running = true;
        status = "waiting";
        thread = new Thread(this::loop, "live-ts");
        thread.setDaemon(true);
        thread.start();
    }

    public void stop() {
        running = false;
        Thread t = thread;
        thread = null;
        if (t != null) {
            t.interrupt();
        }
        status = "stopped";
    }

    private void loop() {
        int fails = 0;
        while (running) {
            try {
                if (poll()) {
                    fails = 0;
                    status = "live";
                }
                sleep(fails == 0 ? 1500 : Math.min(6000, 1500 * fails));
            } catch (InterruptedException ie) {
                return;
            } catch (Exception e) {
                fails++;
                error = e.getClass().getSimpleName() + (e.getMessage() == null ? "" : "：" + e.getMessage());
                status = "error";
                notifyUi();
                try {
                    sleep(Math.min(6000, 1500 * fails));
                } catch (InterruptedException ie) {
                    return;
                }
            }
        }
    }

    private void sleep(long ms) throws InterruptedException {
        Thread.sleep(ms);
    }

    private boolean poll() throws Exception {
        String q = "live_url=" + URLEncoder.encode(liveUrl, "UTF-8")
                + "&enc=" + URLEncoder.encode(enc, "UTF-8")
                + "&offset_id=" + offsetId
                + "&start_time=" + startTime
                + "&fid=" + URLEncoder.encode(fid, "UTF-8")
                + "&speechid=" + URLEncoder.encode(speechid, "UTF-8");
        HttpURLConnection c = (HttpURLConnection) new URL(
                "https://psp-zelda.chaoxing.com/vri-zelda/api/live-ts?" + q).openConnection();
        c.setRequestMethod("GET");
        c.setConnectTimeout(12000);
        c.setReadTimeout(15000);
        c.setRequestProperty("User-Agent", HttpHelper.UA);
        c.setRequestProperty("Accept", "application/json, text/plain, */*");
        c.setRequestProperty("X-Requested-With", "XMLHttpRequest");
        if (!referer.isEmpty()) {
            c.setRequestProperty("Referer", referer);
        }
        int code = c.getResponseCode();
        String body;
        InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
        body = readAll(in);
        c.disconnect();
        if (code != 200) {
            throw new Exception("HTTP " + code);
        }
        JSONObject o = new JSONObject(body);
        boolean got = absorb(o);
        notifyUi();
        return got;
    }

    private boolean absorb(JSONObject o) {
        boolean changed = false;
        long st = o.optLong("start_time", startTime);
        long off = o.optLong("offset_id", offsetId);
        synchronized (this) {
            if (off > 0) {
                offsetId = off;
            }
            if (st > 0) {
                startTime = st;
                if (baseMs == 0) {
                    baseMs = st;
                }
            }
            JSONArray arr = o.optJSONArray("transcripts");
            if (arr != null) {
                for (int i = 0; i < arr.length(); i++) {
                    JSONObject row = arr.optJSONObject(i);
                    if (row == null) {
                        continue;
                    }
                    int id = row.optInt("id", 0);
                    String text = nz(row.optString("text")).trim();
                    if (text.isEmpty() || (id != 0 && seen.contains(id))) {
                        continue;
                    }
                    if (id != 0) {
                        seen.add(id);
                    }
                    Seg s = new Seg();
                    s.id = id;
                    s.start = row.optDouble("start", 0);
                    s.end = row.optDouble("end", 0);
                    s.text = text;
                    long ms = baseMs + (long) (s.start * 1000);
                    s.clock = clockFmt.format(new Date(ms > 0 ? ms : System.currentTimeMillis()));
                    segs.add(s);
                    changed = true;
                }
            }
            JSONObject midObj = o.optJSONObject("last_mid_text");
            String m = midObj == null ? "" : nz(midObj.optString("text")).trim();
            if (!m.equals(mid)) {
                mid = m;
                changed = true;
            }
        }
        return changed;
    }

    private void notifyUi() {
        final Listener l = listener;
        if (l == null) {
            return;
        }
        main.post(() -> l.onUpdate(this));
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) {
            return "";
        }
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] b = new byte[8192];
        int n;
        while ((n = in.read(b)) > 0) {
            buf.write(b, 0, n);
        }
        in.close();
        return new String(buf.toByteArray(), "UTF-8");
    }
}
