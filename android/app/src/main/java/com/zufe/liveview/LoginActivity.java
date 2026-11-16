package com.zufe.liveview;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Message;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** 登录页：WebView 里登一次超星，页面里探到 args 就自动抓走画面地址并返回。 */
public class LoginActivity extends Activity {

    /**
     * 注入到页面里的小探针：先看 window.args，再扫页面 HTML，实在不行 fetch 一次原地址，
     * 找到 args 里的 main/ppt 就通过 LiveBridge 交回原生层。
     */
    private static final String PROBE = """
            (function () {
              if (window.__lvProbe) {
                try { window.__lvProbe.tick(); } catch (e) {}
                return 'already';
              }

              var reported = false;

              function send(o) {
                if (reported || !o) return;
                var sp = o.speech || null;
                var vids = o.videos || (sp && sp.videos) || null;
                if (!vids) return;
                var main = '', ppt = '';
                for (var i = 0; i < vids.length; i++) {
                  var v = vids[i] || {};
                  var t = String(v.type || '').toLowerCase();
                  var u = String(v.realHttp || v.http || '');
                  if (!u) continue;
                  if (t === 'main' && !main) main = u;
                  if (t === 'ppt' && !ppt) ppt = u;
                }
                if (!main) return;
                var course = '';
                if (sp && sp.settings) course = sp.settings.coursename || sp.settings.courseName || '';
                reported = true;
                try {
                  LiveBridge.onStreams(JSON.stringify({ main: main, ppt: ppt, course: String(course || '') }));
                } catch (e) {
                  reported = false;
                }
              }

              function status(txt) {
                if (reported) return;
                try { LiveBridge.onStatus(String(txt || '')); } catch (e) {}
              }

              function html() {
                try {
                  var h = document.documentElement;
                  return h ? (h.outerHTML || h.innerHTML || '') : '';
                } catch (e) { return ''; }
              }

              function matchBrace(text, start) {
                var depth = 0, inStr = false, esc = false;
                for (var k = start; k < text.length; k++) {
                  var c = text.charCodeAt(k);
                  if (inStr) {
                    if (esc) esc = false;
                    else if (c === 92) esc = true;
                    else if (c === 34) inStr = false;
                  } else {
                    if (c === 34) inStr = true;
                    else if (c === 123) depth++;
                    else if (c === 125) { depth--; if (depth === 0) return k + 1; }
                  }
                }
                return -1;
              }

              function scan(text) {
                if (!text) return null;
                var at = 0;
                while (at < text.length) {
                  var i = text.indexOf('args', at);
                  if (i < 0) return null;
                  at = i + 4;
                  var j = i + 4;
                  while (j < text.length) {
                    var c1 = text.charCodeAt(j);
                    if (c1 === 32 || c1 === 9 || c1 === 10 || c1 === 13) j++; else break;
                  }
                  if (text.charCodeAt(j) !== 61) continue;
                  j++;
                  while (j < text.length) {
                    var c2 = text.charCodeAt(j);
                    if (c2 === 32 || c2 === 9 || c2 === 10 || c2 === 13) j++; else break;
                  }
                  if (text.charCodeAt(j) !== 123) continue;
                  var end = matchBrace(text, j);
                  if (end < 0) continue;
                  try { return JSON.parse(text.substring(j, end)); } catch (e) {}
                }
                return null;
              }

              function tick() {
                if (reported) return;
                try { if (window.args) { send(window.args); if (reported) return; } } catch (e) {}
                try { var o = scan(html()); if (o) { send(o); if (reported) return; } } catch (e) {}
                try {
                  var t = html();
                  if (t && t.indexOf('fanyalogin') >= 0) status('请在下面登录（还没登录）');
                  else status(document.title || location.href);
                } catch (e) {}
                if (window.__lvFetching) return;
                window.__lvFetching = true;
                try {
                  fetch(location.href, { credentials: 'include', cache: 'no-store' })
                    .then(function (r) { return r.text(); })
                    .then(function (body) {
                      window.__lvFetching = false;
                      if (reported) return;
                      var o = scan(body);
                      if (o) send(o);
                    })
                    .catch(function () { window.__lvFetching = false; });
                } catch (e) {
                  window.__lvFetching = false;
                }
              }

              window.__lvProbe = { tick: tick };
              tick();
              setInterval(tick, 3000);
              return 'started';
            })()
            """;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private WebView web;
    private TextView status;
    private boolean loaded;
    private boolean retried;
    private TextView title;
    private String link = "";
    private String room = "";
    private boolean done;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        link = getIntent().getStringExtra("link");
        room = getIntent().getStringExtra("room");
        if (link == null) {
            link = "";
        }
        if (room == null) {
            room = "";
        }
        buildUi();
        if (link.isEmpty()) {
            status.setText("没有直播链接，先在首页把教室加进来");
        } else {
            web.loadUrl(link);
        }
    }

    private int dp(float v) {
        return Ui.dp(this, v);
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.BG);
        root.setFitsSystemWindows(true);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setBackgroundColor(Ui.SURFACE);
        header.setPadding(dp(16), dp(12), dp(16), dp(10));

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        title = Ui.text(this, "登录超星" + (room.isEmpty() ? "" : "（" + room + "）"), 17, Ui.TEXT, true);
        row.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button refresh = Ui.chip(this, "刷新", false);
        refresh.setOnClickListener(v -> web.reload());
        LinearLayout.LayoutParams rp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        rp.rightMargin = dp(8);
        row.addView(refresh, rp);

        Button cancel = Ui.chip(this, "取消", false);
        cancel.setOnClickListener(v -> {
            setResult(RESULT_CANCELED);
            finish();
        });
        row.addView(cancel);
        header.addView(row);

        status = Ui.text(this, "正在打开登录页…", 12, Ui.DIM, false);
        status.setPadding(0, dp(6), 0, 0);
        header.addView(status);
        root.addView(header, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        web = new WebView(this);
        web.setBackgroundColor(0xFF000000);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportMultipleWindows(true);
        s.setJavaScriptCanOpenWindowsAutomatically(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setUserAgentString("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                + "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);

        web.addJavascriptInterface(new Bridge(), "LiveBridge");
        loaded = false;
        retried = false;
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                status.setText("正在打开登录页…（校园网慢的话要十几秒）");
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                loaded = true;
                inject();
            }

            @Override
            public void onReceivedError(WebView view, android.webkit.WebResourceRequest request,
                                        android.webkit.WebResourceError error) {
                status.setText("页面没打开（网络问题），点右上「刷新」重试");
            }
        });
        ui.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (!loaded && !retried) {
                    retried = true;
                    status.setText("页面加载有点慢，正在自动重试…");
                    web.reload();
                    ui.postDelayed(this, 15000);
                } else if (!loaded) {
                    status.setText("还是没打开，点右上「刷新」再试，或检查网络");
                }
            }
        }, 15000);
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onCreateWindow(WebView view, boolean isDialog, boolean isUserGesture,
                                          Message resultMsg) {
                // 弹窗一律在当前页打开，别让登录跳到看不见的地方
                final WebView tmp = new WebView(LoginActivity.this);
                tmp.setWebViewClient(new WebViewClient() {
                    @Override
                    public boolean shouldOverrideUrlLoading(WebView v, String url) {
                        web.loadUrl(url);
                        return true;
                    }
                });
                WebView.WebViewTransport transport = (WebView.WebViewTransport) resultMsg.obj;
                transport.setWebView(tmp);
                resultMsg.sendToTarget();
                return true;
            }
        });

        root.addView(web, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(root);

        ui.postDelayed(new Runnable() {
            @Override
            public void run() {
                inject();
            }
        }, 2500);
    }

    private void inject() {
        if (web == null || done) {
            return;
        }
        try {
            web.evaluateJavascript(PROBE, null);
        } catch (Exception ignored) {
        }
    }

    public class Bridge {

        @JavascriptInterface
        public void onStreams(final String json) {
            ui.post(() -> {
                if (done) {
                    return;
                }
                Streams s = Streams.fromJson(json);
                if (!s.ok()) {
                    return;
                }
                done = true;
                Store.saveStream(LoginActivity.this, room, s);
                try {
                    CookieManager.getInstance().flush();
                } catch (Exception ignored) {
                }
                Intent data = new Intent();
                data.putExtra("room", room);
                data.putExtra("streams", json);
                setResult(RESULT_OK, data);
                finish();
            });
        }

        @JavascriptInterface
        public void onStatus(final String text) {
            ui.post(() -> {
                if (done) {
                    return;
                }
                if (text == null || text.trim().isEmpty()) {
                    status.setText("等待页面…");
                } else {
                    status.setText("当前页面：" + text);
                }
            });
        }
    }

    @Override
    protected void onDestroy() {
        try {
            if (web != null) {
                web.removeJavascriptInterface("LiveBridge");
                web.stopLoading();
                web.destroy();
            }
        } catch (Exception ignored) {
        }
        web = null;
        super.onDestroy();
    }
}
