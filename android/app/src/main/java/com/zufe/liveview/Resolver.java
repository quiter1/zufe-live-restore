package com.zufe.liveview;

import android.content.Context;
import android.webkit.CookieManager;

import org.json.JSONObject;

import java.io.IOException;
import java.net.URLDecoder;
import java.util.LinkedHashMap;
import java.util.Map;

/** 拿直播页 HTML：先试已登录的 cookie，再试填好的账号密码，都不行就让人去登录。 */
public final class Resolver {

    /** 需要人工登录一次。 */
    public static final class NeedLogin extends Exception {
        public NeedLogin(String message) {
            super(message);
        }
    }

    private Resolver() {
    }

    /** index 与 mobile_live 互相换一个，作为兜底地址。 */
    static String alt(String link) {
        String l = link == null ? "" : link.trim();
        if (l.toLowerCase(java.util.Locale.ROOT).contains("/vri-zelda/mobile_live")) {
            return l.replaceAll("(?i)/vri-zelda/mobile_live", "/vri-zelda/index");
        }
        if (l.toLowerCase(java.util.Locale.ROOT).contains("/vri-zelda/index")) {
            return l.replaceAll("(?i)/vri-zelda/index", "/vri-zelda/mobile_live");
        }
        return "";
    }

    public static Streams resolve(Context ctx, String room, String link) throws Exception {
        String cookie = webviewCookie(link);
        if (cookie != null) {
            for (String url : new String[]{link, alt(link)}) {
                if (url == null || url.isEmpty()) {
                    continue;
                }
                try {
                    String html = HttpHelper.get(url, cookie);
                    Streams s = PageParser.parse(html);
                    if (s != null) {
                        return s;
                    }
                } catch (Exception ignored) {
                    // cookie 过期、网络抖动，换下一个地址 / 往下走账号密码
                }
            }
        }

        if (Store.hasAccount(ctx)) {
            try {
                Streams s = loginAndFetch(link, Store.user(ctx), Store.password(ctx));
                if (s != null) {
                    return s;
                }
            } catch (Exception e) {
                throw new NeedLogin(e.getMessage() == null ? "用账号登录失败" : e.getMessage());
            }
        }
        throw new NeedLogin(Store.hasAccount(ctx)
                ? "用保存的账号登录没成功，试试在下面手动登录一次"
                : "还没有填账号密码，也没登录过，先手动登录一次");
    }

    public static String webviewCookie(String url) {
        try {
            String c = CookieManager.getInstance().getCookie(url);
            if (c == null || c.trim().isEmpty()) {
                return null;
            }
            return c;
        } catch (Exception e) {
            return null;
        }
    }

    /** 模拟电脑版那套登录：AES 加密的表单 POST 到 fanyalogin，再跟回直播页。 */
    static Streams loginAndFetch(String link, String user, String pass) throws Exception {
        HttpHelper.Client client = new HttpHelper.Client();
        HttpHelper.Page page = client.get(link);
        Streams direct = PageParser.parse(page.html);
        if (direct != null) {
            client.syncToCookieManager();
            return direct;
        }

        String refer = PageParser.findRefer(page.html, page.url);
        if (refer == null) {
            throw new IOException("登录页没找到 refer 参数，可能链接已失效");
        }
        Map<String, String> form = new LinkedHashMap<>();
        form.put("fid", "-1");
        form.put("uname", HttpHelper.aes(user));
        form.put("password", HttpHelper.aes(pass));
        form.put("refer", refer);
        form.put("t", "true");
        form.put("forbidotherlogin", "0");
        form.put("validate", "");
        form.put("doubleFactorLogin", "0");
        form.put("independentId", "");
        form.put("independentNameId", "");
        String resp = client.postForm(HttpHelper.LOGIN_URL, form, page.url);
        JSONObject j;
        try {
            j = new JSONObject(resp);
        } catch (Exception e) {
            throw new IOException("登录接口返回看不懂的内容，可能被网络拦了");
        }
        if (!j.optBoolean("status")) {
            String msg = j.optString("msg2", "");
            if (msg.isEmpty()) {
                msg = j.optString("mes", "");
            }
            if (msg.isEmpty()) {
                msg = "账号或密码不对";
            }
            throw new IOException(msg);
        }
        String next = j.optString("url", "");
        try {
            next = URLDecoder.decode(next, "UTF-8");
        } catch (Exception ignored) {
        }
        if (next.isEmpty()) {
            next = link;
        }
        page = client.get(next);
        Streams s = PageParser.parse(page.html);
        if (s == null && !next.equals(link)) {
            page = client.get(link);
            s = PageParser.parse(page.html);
        }
        if (s == null) {
            String other = alt(link);
            if (!other.isEmpty()) {
                page = client.get(other);
                s = PageParser.parse(page.html);
            }
        }
        if (s == null) {
            throw new IOException("登录成功了，但这个教室现在没有画面（可能还没开始直播）");
        }
        client.syncToCookieManager();
        return s;
    }
}
