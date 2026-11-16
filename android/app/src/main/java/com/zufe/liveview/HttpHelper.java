package com.zufe.liveview;

import android.util.Base64;
import android.webkit.CookieManager;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** 取直播页用的极简 HTTP：自己管 cookie，手动跟重定向，附带超星登录用的那套加密。 */
public final class HttpHelper {

    public static final String UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            + "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0";
    public static final String LOGIN_URL = "https://passport2.chaoxing.com/fanyalogin";
    private static final String AES_KEY = "u2oh6Vu^HWe4_AES";

    private HttpHelper() {
    }

    public static final class Page {
        public String url = "";
        public String html = "";
    }

    public static String get(String url, String cookieHeader) throws IOException {
        Client client = new Client();
        if (cookieHeader != null && !cookieHeader.trim().isEmpty()) {
            for (String part : cookieHeader.split(";")) {
                int eq = part.indexOf('=');
                if (eq > 0) {
                    client.jar.put(part.substring(0, eq).trim(), part.substring(eq + 1).trim());
                }
            }
        }
        return client.get(url).html;
    }

    /** 一次带 cookie 的会话。 */
    public static final class Client {
        final Map<String, String> jar = new LinkedHashMap<>();

        public Page get(String url) throws IOException {
            return request("GET", url, null, null);
        }

        public String postForm(String url, Map<String, String> form, String referer) throws IOException {
            StringBuilder sb = new StringBuilder();
            for (Map.Entry<String, String> e : form.entrySet()) {
                if (sb.length() > 0) {
                    sb.append('&');
                }
                sb.append(URLEncoder.encode(e.getKey(), "UTF-8"))
                        .append('=')
                        .append(URLEncoder.encode(e.getValue() == null ? "" : e.getValue(), "UTF-8"));
            }
            return request("POST", url, sb.toString(), referer).html;
        }

        Page request(String method, String url, String body, String referer) throws IOException {
            String current = url;
            String m = method;
            String b = body;
            for (int hop = 0; hop < 8; hop++) {
                HttpURLConnection conn = (HttpURLConnection) new URL(current).openConnection();
                conn.setInstanceFollowRedirects(false);
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(25000);
                conn.setRequestMethod(m);
                conn.setRequestProperty("User-Agent", UA);
                conn.setRequestProperty("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.6");
                conn.setRequestProperty("Accept",
                        "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8");
                String ck = cookieHeader();
                if (ck != null) {
                    conn.setRequestProperty("Cookie", ck);
                }
                if (referer != null) {
                    conn.setRequestProperty("Referer", referer);
                }
                if (b != null) {
                    byte[] payload = b.getBytes("UTF-8");
                    conn.setDoOutput(true);
                    conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8");
                    conn.setFixedLengthStreamingMode(payload.length);
                    OutputStream out = conn.getOutputStream();
                    out.write(payload);
                    out.close();
                }
                int code = conn.getResponseCode();
                absorbCookies(conn);
                if (code >= 300 && code < 400) {
                    String loc = conn.getHeaderField("Location");
                    conn.disconnect();
                    if (loc == null || loc.isEmpty()) {
                        throw new IOException("跳转到了空地址");
                    }
                    current = new URL(new URL(current), loc).toString();
                    referer = current;
                    m = "GET";
                    b = null;
                    continue;
                }
                InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
                Page p = new Page();
                p.url = current;
                p.html = readAll(in);
                conn.disconnect();
                return p;
            }
            throw new IOException("重定向太多次了");
        }

        private void absorbCookies(HttpURLConnection conn) {
            for (Map.Entry<String, List<String>> e : conn.getHeaderFields().entrySet()) {
                if (e.getKey() == null || !"set-cookie".equals(e.getKey().toLowerCase(Locale.ROOT))) {
                    continue;
                }
                for (String h : e.getValue()) {
                    if (h == null) {
                        continue;
                    }
                    String pair = h.split(";", 2)[0];
                    int eq = pair.indexOf('=');
                    if (eq <= 0) {
                        continue;
                    }
                    jar.put(pair.substring(0, eq).trim(), pair.substring(eq + 1).trim());
                }
            }
        }

        private String cookieHeader() {
            if (jar.isEmpty()) {
                return null;
            }
            StringBuilder sb = new StringBuilder();
            for (Map.Entry<String, String> e : jar.entrySet()) {
                if (sb.length() > 0) {
                    sb.append("; ");
                }
                sb.append(e.getKey()).append('=').append(e.getValue());
            }
            return sb.toString();
        }

        /** 登录拿到的 cookie 交给 WebView，下次打开登录页就是已登录状态。 */
        public void syncToCookieManager() {
            CookieManager cm = CookieManager.getInstance();
            List<String> hosts = new ArrayList<>();
            hosts.add("https://psp-zelda.chaoxing.com/");
            hosts.add("https://passport2.chaoxing.com/");
            hosts.add("https://chaoxing.com/");
            for (String host : hosts) {
                for (Map.Entry<String, String> e : jar.entrySet()) {
                    cm.setCookie(host, e.getKey() + "=" + e.getValue() + "; path=/");
                }
            }
            cm.flush();
        }
    }

    public static String readAll(InputStream in) throws IOException {
        if (in == null) {
            return "";
        }
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = in.read(buf)) > 0) {
            bo.write(buf, 0, n);
        }
        in.close();
        return bo.toString("UTF-8");
    }

    /** 超星登录表单里的 uname / password 是 AES-CBC + base64，key 当 iv。 */
    public static String aes(String plain) throws IOException {
        try {
            byte[] key = AES_KEY.getBytes("UTF-8");
            Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new IvParameterSpec(key));
            byte[] enc = cipher.doFinal(plain.getBytes("UTF-8"));
            return Base64.encodeToString(enc, Base64.NO_WRAP);
        } catch (Exception e) {
            throw new IOException("登录参数加密失败: " + e.getMessage());
        }
    }
}
