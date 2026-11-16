package com.zufe.liveview;

import org.json.JSONArray;
import org.json.JSONObject;

import java.net.URLDecoder;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 从直播页 HTML 里挖出 args 对象，取出 main / ppt 两个 FLV 地址。 */
public final class PageParser {

    private static final Pattern ARGS = Pattern.compile("\\bargs\\s*=");
    private static final Pattern REFER = Pattern.compile(
            "id\\s*=\\s*[\"']refer[\"'][^>]*?value\\s*=\\s*[\"']([^\"']*)[\"']");
    private static final Pattern REFER_NAME = Pattern.compile(
            "name\\s*=\\s*[\"']refer[\"'][^>]*?value\\s*=\\s*[\"']([^\"']*)[\"']");

    private PageParser() {
    }

    public static Streams parse(String html) {
        if (html == null || html.isEmpty()) {
            return null;
        }
        Matcher m = ARGS.matcher(html);
        int from = 0;
        while (m.find(from)) {
            int i = m.end();
            from = m.end();
            while (i < html.length() && isSpace(html.charAt(i))) {
                i++;
            }
            if (i >= html.length() || html.charAt(i) != '{') {
                continue;
            }
            int end = matchBrace(html, i);
            if (end < 0) {
                continue;
            }
            Streams s = fromArgs(html.substring(i, end));
            if (s != null) {
                return s;
            }
            from = end;
        }
        return null;
    }

    private static boolean isSpace(char c) {
        return c == ' ' || c == '\t' || c == '\r' || c == '\n';
    }

    private static Streams fromArgs(String json) {
        try {
            JSONObject a = new JSONObject(json);
            JSONObject speech = a.optJSONObject("speech");
            JSONArray vids = a.optJSONArray("videos");
            if (vids == null && speech != null) {
                vids = speech.optJSONArray("videos");
            }
            if (vids == null) {
                return null;
            }
            Streams s = new Streams();
            for (int i = 0; i < vids.length(); i++) {
                JSONObject v = vids.optJSONObject(i);
                if (v == null) {
                    continue;
                }
                String type = v.optString("type", "").trim().toLowerCase(java.util.Locale.ROOT);
                String url = v.optString("realHttp", "").trim();
                if (url.isEmpty()) {
                    url = v.optString("http", "").trim();
                }
                if (url.isEmpty()) {
                    continue;
                }
                if ("main".equals(type) && s.main.isEmpty()) {
                    s.main = url;
                    s.enc = v.optString("urlEnc", "").trim();
                } else if ("ppt".equals(type) && s.ppt.isEmpty()) {
                    s.ppt = url;
                } else if ("other".equals(type) && s.other.isEmpty()) {
                    s.other = url;
                }
            }
            if (!s.ok()) {
                return null;
            }
            JSONObject st = speech == null ? null : speech.optJSONObject("settings");
            if (st != null) {
                String cn = st.optString("coursename", "");
                if (cn.isEmpty()) {
                    cn = st.optString("courseName", "");
                }
                s.course = cn == null ? "" : cn.trim();
            }
            s.fid = a.optString("fid", "").trim();
            if (s.fid.isEmpty() && st != null) {
                s.fid = st.optString("fid", "").trim();
            }
            if (speech != null) {
                s.speechid = speech.optString("speechId", "").trim();
                if (s.enc.isEmpty()) {
                    s.enc = speech.optString("enc", "").trim();
                }
            }
            return s;
        } catch (Exception e) {
            return null;
        }
    }

    /** 从 start 处的 '{' 找到配对的 '}'，跳过字符串里的括号。返回结束位置(不含)。 */
    static int matchBrace(String s, int start) {
        int depth = 0;
        boolean inStr = false;
        boolean esc = false;
        for (int i = start; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (inStr) {
                if (esc) {
                    esc = false;
                } else if (ch == '\\') {
                    esc = true;
                } else if (ch == '"') {
                    inStr = false;
                }
            } else {
                if (ch == '"') {
                    inStr = true;
                } else if (ch == '{') {
                    depth++;
                } else if (ch == '}') {
                    depth--;
                    if (depth == 0) {
                        return i + 1;
                    }
                }
            }
        }
        return -1;
    }

    /** 登录页里的 refer 参数：优先取表单 input，其次取地址栏。 */
    public static String findRefer(String html, String pageUrl) {
        if (html != null) {
            Matcher m = REFER.matcher(html);
            if (m.find() && !m.group(1).isEmpty()) {
                return m.group(1);
            }
            Matcher m2 = REFER_NAME.matcher(html);
            if (m2.find() && !m2.group(1).isEmpty()) {
                return m2.group(1);
            }
        }
        try {
            String q = java.net.URI.create(pageUrl).getRawQuery();
            if (q != null) {
                for (String kv : q.split("&")) {
                    int eq = kv.indexOf('=');
                    if (eq > 0 && "refer".equals(kv.substring(0, eq))) {
                        return URLDecoder.decode(kv.substring(eq + 1), "UTF-8");
                    }
                }
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    /** 这个页面看起来还没登录（超星会跳到登录页）。 */
    public static boolean looksLoggedOut(String html) {
        if (html == null || html.isEmpty()) {
            return true;
        }
        return html.contains("fanyalogin") || html.contains("id=\"refer\"")
                || html.contains("passport2.chaoxing.com/fanyalogin");
    }
}
